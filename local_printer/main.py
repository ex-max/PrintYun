# -*- coding: utf-8 -*-
"""本地打印拦截器 — 主入口（虚拟打印机方案 v4）。

核心策略：
  * PayPrint 虚拟打印机 + Redmon 拦截用户打印，PS 文件保存到 C:\\PrintJobs
  * FileWatcher 监控 C:\\PrintJobs 目录，发现新 .ps 文件后推入处理队列
  * WalkInProcessor 串行处理：PS→PDF→读页数→创建订单→弹窗付款→SumatraPDF 打印
  * 真实打印机（TOSHIBA）永远不暂停，Web 已付款订单可以畅通打印
  * WebOrderConsumer 从 Redis print_queue 消费 Web 订单，直接打印到真实打印机

进程结构：
  FileWatcher      : 轮询 C:\\PrintJobs，发现新 PS 文件
  WalkInProcessor  : 串行消费 → PS→PDF → 弹窗付款 → 打印到真实打印机
  WebOrderConsumer : 订阅 Redis print_queue → SumatraPDF 到真实打印机
  TrayIcon (可选)   : 系统托盘退出菜单
"""

import os
import sys
import time
import queue
import threading
import logging
from logging.handlers import TimedRotatingFileHandler

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from local_printer import config
from local_printer.job_processor import (
    create_order_via_api, get_pay_url, update_order_status,
)
from local_printer.printer_utils import (
    convert_ps_to_pdf, read_pdf_pages, print_pdf, cleanup,
)
from local_printer.payment_window import show_payment_window
from local_printer.web_consumer import WebOrderConsumer

# ---- 日志 ----
log_dir = os.path.join(_PROJECT_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        TimedRotatingFileHandler(
            os.path.join(log_dir, 'local_printer.log'),
            when='midnight', backupCount=30, encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger('local_printer')


# =============================================================================
# FileWatcher —— 轮询 C:\PrintJobs 目录，发现新 PS 文件
# =============================================================================

class FileWatcher(threading.Thread):
    """监控目录中的新 .ps 文件，等待文件写入完成后推入队列。

    Redmon 把打印数据通过 save_job.py 保存到 watch_dir，本线程定期扫描，
    发现文件大小稳定（settle_time 秒内不变）后认为写入完成，推入处理队列。
    """

    def __init__(self, watch_dir, walkin_queue, poll_interval=1.0,
                 settle_time=2.0):
        super().__init__(daemon=True, name='FileWatcher')
        self.watch_dir = watch_dir
        self.walkin_queue = walkin_queue
        self.poll_interval = poll_interval
        self.settle_time = settle_time
        self._known_files = set()   # 已处理过的文件名
        self._pending = {}          # 文件名 → (上次大小, 大小稳定起始时间)
        self._running = True

    def run(self):
        logger.info('FileWatcher 启动，监控目录: %s', self.watch_dir)
        self._scan_existing()
        while self._running:
            try:
                self._scan_once()
            except Exception as e:
                logger.exception('FileWatcher 扫描异常: %s', e)
            time.sleep(self.poll_interval)
        logger.info('FileWatcher 已退出')

    def _scan_existing(self):
        """启动时扫描已有文件，标记为已知（不处理历史文件）。"""
        try:
            for f in os.listdir(self.watch_dir):
                if f.lower().endswith('.ps'):
                    self._known_files.add(f)
            if self._known_files:
                logger.info('跳过 %d 个已有 PS 文件', len(self._known_files))
        except Exception as e:
            logger.warning('扫描已有文件失败: %s', e)

    def _scan_once(self):
        """扫描一次目录，发现新的、写入完成的 PS 文件。"""
        try:
            files = [f for f in os.listdir(self.watch_dir)
                     if f.lower().endswith('.ps')]
        except Exception:
            return

        current_files = set(files)

        # 清理已消失的 pending 记录
        for fname in list(self._pending.keys()):
            if fname not in current_files:
                del self._pending[fname]

        for fname in files:
            if fname in self._known_files:
                continue

            filepath = os.path.join(self.watch_dir, fname)
            try:
                current_size = os.path.getsize(filepath)
            except OSError:
                continue

            if current_size == 0:
                continue  # 还在创建中

            if fname not in self._pending:
                # 首次发现
                self._pending[fname] = (current_size, time.time())
                logger.debug('发现新文件: %s (%d bytes)', fname, current_size)
                continue

            prev_size, stable_since = self._pending[fname]

            if current_size != prev_size:
                # 大小还在变化，更新记录
                self._pending[fname] = (current_size, time.time())
                continue

            # 大小稳定，检查是否过了 settle_time
            if time.time() - stable_since < self.settle_time:
                continue

            # 文件已稳定，推入处理队列
            self._known_files.add(fname)
            del self._pending[fname]
            logger.info('===== 检测到新打印文件: %s (%d bytes) =====',
                        fname, current_size)
            self.walkin_queue.put(filepath)

    def stop(self):
        self._running = False


# =============================================================================
# WalkInProcessor —— 串行处理走入式打印任务
# =============================================================================

class WalkInProcessor(threading.Thread):
    """走入式打印任务处理：PS→PDF→读页数→创建订单→弹窗付款→打印到真实打印机。

    一次只处理一个任务（tkinter 弹窗不支持并发），其余排队等待。
    """

    def __init__(self, real_printer_name, walkin_queue):
        super().__init__(daemon=True, name='WalkInProcessor')
        self.real_printer_name = real_printer_name
        self.walkin_queue = walkin_queue
        self._running = True

    def run(self):
        logger.info('WalkInProcessor 启动，打印目标: %s',
                     self.real_printer_name)
        while self._running:
            try:
                ps_path = self.walkin_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._handle(ps_path)
            except Exception as e:
                logger.exception('处理走入式任务异常: %s', e)
        logger.info('WalkInProcessor 已退出')

    def _handle(self, ps_path):
        """处理一个 PS 文件的完整流程。"""
        filename = os.path.basename(ps_path)
        logger.info('开始处理: %s', filename)

        # 1. PS → PDF
        pdf_path = convert_ps_to_pdf(ps_path)
        if not pdf_path:
            logger.error('PS 转 PDF 失败，跳过: %s', filename)
            cleanup(ps_path)
            return

        # 2. 读取页数
        pages = read_pdf_pages(pdf_path)
        if pages <= 0:
            logger.error('无法读取页数，跳过: %s', filename)
            cleanup(ps_path, pdf_path)
            return

        # 3. 显示名（save_job.py 生成的文件名无法还原原始文档名）
        display_name = '本地打印文档'
        logger.info('文件: %s → %d 页', filename, pages)

        # 4. 创建订单
        color = config.DEFAULT_COLOR
        duplex = config.DEFAULT_DUPLEX
        copies = config.DEFAULT_COPIES
        paper = config.DEFAULT_PAPER

        order_info = create_order_via_api(
            pages, color, duplex, copies, paper, display_name)
        if not order_info:
            logger.error('创建订单失败，跳过')
            cleanup(ps_path, pdf_path)
            return

        trade_number = order_info['trade_number']
        logger.info('订单已创建: %s, %d 页, ¥%.2f',
                     trade_number, pages, order_info['cost'])

        # 5. 获取支付链接
        pay_info = get_pay_url(trade_number)
        if not pay_info:
            logger.error('获取支付链接失败')
            update_order_status(trade_number, -2)
            cleanup(ps_path, pdf_path)
            return

        # 6. 弹窗付款
        order_info['filename'] = display_name
        result = show_payment_window(order_info, pay_info)
        logger.info('支付窗口结果: %s', result)

        if result == 'paid':
            # 7. 付款成功 → 打印到真实打印机
            logger.info('付款成功，发送到打印机: %s', self.real_printer_name)
            success = print_pdf(pdf_path, color, duplex, copies, paper)
            if success:
                update_order_status(trade_number, 3)  # 已完成
                logger.info('打印完成: %s', trade_number)
            else:
                update_order_status(trade_number, -1)  # 打印失败
                logger.error('打印失败: %s', trade_number)
        else:
            # 取消或超时
            update_order_status(trade_number, -2)
            logger.info('用户取消/超时: %s', trade_number)

        # 8. 清理临时文件
        cleanup(ps_path, pdf_path)
        logger.info('===== 任务结束: %s =====', trade_number)

    def stop(self):
        self._running = False


# =============================================================================
# 系统托盘
# =============================================================================

def _create_tray_icon(shutdown_callback, printer_name, watch_dir):
    try:
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new('RGB', (64, 64), '#1E9FFF')
        draw = ImageDraw.Draw(img)
        draw.rectangle([12, 20, 52, 50], fill='white', outline='#333', width=2)
        draw.rectangle([18, 8, 46, 24], fill='#eee', outline='#333', width=2)
        draw.ellipse([40, 28, 48, 36], fill='#52C41A')

        def on_quit(icon, item):
            logger.info('用户从托盘退出')
            shutdown_callback()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem(
                f'真实打印机: {printer_name}', None, enabled=False),
            pystray.MenuItem(
                f'监控目录: {watch_dir}', None, enabled=False),
            pystray.MenuItem('拦截器运行中', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', on_quit),
        )
        return pystray.Icon('local_printer', img, '云打印-本地拦截器', menu)
    except ImportError:
        return None


# =============================================================================
# main
# =============================================================================

def _connect_redis():
    """连接 Redis（用于 WebOrderConsumer）。失败返回 None。"""
    try:
        # 加载 .env 以拿到 REDISTOGO_URL
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_PROJECT_DIR, '.env'), override=False)
        except ImportError:
            pass
        import redis
        url = os.environ.get('REDISTOGO_URL', 'redis://localhost:6379')
        conn = redis.Redis.from_url(url)
        conn.ping()
        logger.info('Redis 连接成功: %s', url)
        return conn
    except Exception as e:
        logger.warning('Redis 连接失败，WebOrderConsumer 不会启动: %s', e)
        return None


def main():
    real_printer = config.PRINTER_NAME
    if not real_printer:
        try:
            import win32print
            real_printer = win32print.GetDefaultPrinter()
        except Exception:
            logger.error('未配置 PRINTER_NAME 且无法获取默认打印机')
            input('按 Enter 退出...')
            return

    watch_dir = config.WATCH_DIR

    logger.info('=' * 60)
    logger.info('本地打印拦截器启动 (虚拟打印机方案 v4)')
    logger.info('监控目录  : %s', watch_dir)
    logger.info('真实打印机: %s', real_printer)
    logger.info('服务器    : %s', config.SERVER_URL)
    logger.info('★ 真实打印机不会被暂停，Web 订单可畅通打印')
    logger.info('=' * 60)

    # 确保监控目录存在
    os.makedirs(watch_dir, exist_ok=True)

    walkin_queue = queue.Queue()

    watcher = FileWatcher(watch_dir, walkin_queue,
                          poll_interval=config.POLL_INTERVAL,
                          settle_time=2.0)
    processor = WalkInProcessor(real_printer, walkin_queue)
    web_consumer = None

    redis_conn = _connect_redis()
    if redis_conn is not None:
        web_consumer = WebOrderConsumer(redis_conn, real_printer)

    def _shutdown():
        logger.info('关闭中...')
        watcher.stop()
        processor.stop()
        if web_consumer:
            web_consumer.stop()

    tray_icon = _create_tray_icon(_shutdown, real_printer, watch_dir)
    if tray_icon:
        tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
        tray_thread.start()

    # 启动线程
    watcher.start()
    processor.start()
    if web_consumer:
        web_consumer.start()

    try:
        # 主线程阻塞等待 watcher 退出
        while watcher.is_alive():
            watcher.join(timeout=1)
    except KeyboardInterrupt:
        logger.info('收到 Ctrl+C')
        _shutdown()

    logger.info('====== 本地打印拦截器已退出 ======')


if __name__ == '__main__':
    main()
