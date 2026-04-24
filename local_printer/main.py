# -*- coding: utf-8 -*-
"""本地打印拦截器 — 主入口（Spooler 监控方案 v2）。

核心策略：启动时暂停打印机 → 所有任务自动排队不打印 → 付款后临时恢复。

流程：
  1. 启动时将打印机设为暂停状态
  2. 新任务进入队列（自动排队，不会打印）
  3. 弹出付款窗口 → 用户扫码付款
  4. 付款成功 → 临时恢复打印机 → 等任务打完 → 再次暂停打印机
  5. 取消/超时 → 删除该任务
"""

import os
import sys
import time
import threading
import logging
from logging.handlers import TimedRotatingFileHandler

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

import win32print

from local_printer import config
from local_printer.job_processor import (
    create_order_via_api, get_pay_url, update_order_status,
)
from local_printer.payment_window import show_payment_window

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


class SpoolerWatcher:
    """监控打印机 Spooler 队列，拦截新任务。

    策略：打印机本身保持暂停状态 → 任务进来不会打印 → 付款后临时恢复。
    """

    def __init__(self, printer_name):
        self.printer_name = printer_name
        self._known_jobs = set()
        self._running = True
        self._processing = False

    # ---- 打印机级操作 ----

    def _open_printer_admin(self):
        """以管理员权限打开打印机句柄。"""
        # OpenPrinter 的第二个参数 pDefault 可以指定访问级别
        # PRINTER_ALL_ACCESS = 0x000F000C
        return win32print.OpenPrinter(
            self.printer_name,
            {'DesiredAccess': win32print.PRINTER_ALL_ACCESS},
        )

    def _pause_printer(self):
        """暂停打印机（所有新任务自动排队不打印）。"""
        try:
            handle = self._open_printer_admin()
            try:
                win32print.SetPrinter(handle, 0, None, win32print.PRINTER_CONTROL_PAUSE)
                logger.info('打印机已暂停: %s', self.printer_name)
            finally:
                win32print.ClosePrinter(handle)
        except Exception as e:
            logger.error('暂停打印机失败: %s', e)

    def _resume_printer(self):
        """恢复打印机。"""
        try:
            handle = self._open_printer_admin()
            try:
                win32print.SetPrinter(handle, 0, None, win32print.PRINTER_CONTROL_RESUME)
                logger.info('打印机已恢复')
            finally:
                win32print.ClosePrinter(handle)
        except Exception as e:
            logger.error('恢复打印机失败: %s', e)

    # ---- 任务级操作 ----

    def _get_jobs(self):
        """获取队列中的所有任务（level 2 获取更多信息）。"""
        try:
            handle = win32print.OpenPrinter(self.printer_name)
            try:
                # Level 2 包含更完整的页数信息
                jobs = win32print.EnumJobs(handle, 0, 100, 2)
                return jobs
            except Exception:
                # Level 2 失败时降级到 level 1
                try:
                    jobs = win32print.EnumJobs(handle, 0, 100, 1)
                    return jobs
                except Exception:
                    return []
            finally:
                win32print.ClosePrinter(handle)
        except Exception as e:
            logger.error('获取打印队列失败: %s', e)
            return []

    def _delete_job(self, job_id):
        """删除指定任务。"""
        try:
            handle = self._open_printer_admin()
            try:
                win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                logger.info('已删除任务 #%d', job_id)
                return True
            finally:
                win32print.ClosePrinter(handle)
        except Exception as e:
            logger.error('删除任务 #%d 失败: %s', job_id, e)
            return False

    def _wait_job_complete(self, job_id, timeout=120):
        """等待指定任务打印完成（从队列消失）。"""
        start = time.time()
        while time.time() - start < timeout:
            jobs = self._get_jobs()
            job_ids = [j.get('JobId', j.get('pJobId', 0)) for j in jobs]
            if job_id not in job_ids:
                logger.info('任务 #%d 已打印完成', job_id)
                return True
            time.sleep(1)
        logger.warning('等待任务 #%d 完成超时', job_id)
        return False

    def _get_page_count(self, job_info):
        """从任务信息获取页数（尝试多个字段）。"""
        # Level 2 字段
        pages = job_info.get('TotalPages', 0)
        if pages <= 0:
            pages = job_info.get('pTotalPages', 0)
        if pages <= 0:
            # 尝试从 Size 估算（每页约 50-100KB）
            size = job_info.get('Size', 0)
            if size > 0:
                pages = max(1, size // 80000)  # 粗估
        if pages <= 0:
            pages = 1
        return pages

    def _get_doc_name(self, job_info):
        """获取文档名。"""
        name = (job_info.get('pDocument', '')
                or job_info.get('Document', '')
                or '未知文档')
        return name

    def _get_job_id(self, job_info):
        return job_info.get('JobId', job_info.get('pJobId', 0))

    # ---- 核心处理 ----

    def _handle_new_job(self, job_info):
        """处理一个新的打印任务。打印机此时处于暂停状态，任务不会打印。"""
        job_id = self._get_job_id(job_info)
        doc_name = self._get_doc_name(job_info)

        # 等待 1.5 秒让 Spooler 完成处理（获得准确页数）
        time.sleep(1.5)

        # 重新读取任务信息（页数可能更新了）
        jobs = self._get_jobs()
        updated_info = None
        for j in jobs:
            if self._get_job_id(j) == job_id:
                updated_info = j
                break
        if updated_info:
            job_info = updated_info

        pages = self._get_page_count(job_info)
        logger.info('===== 新打印任务 #%d: %s (%d页) =====', job_id, doc_name, pages)

        # 1. 创建订单
        color = config.DEFAULT_COLOR
        duplex = config.DEFAULT_DUPLEX
        copies = config.DEFAULT_COPIES
        paper = config.DEFAULT_PAPER

        order_info = create_order_via_api(pages, color, duplex, copies, paper, doc_name)
        if not order_info:
            logger.error('创建订单失败，删除任务')
            self._delete_job(job_id)
            return

        trade_number = order_info['trade_number']
        logger.info('订单: %s, ¥%.2f', trade_number, order_info['cost'])

        # 2. 获取支付链接
        pay_info = get_pay_url(trade_number)
        if not pay_info:
            logger.error('获取支付链接失败，删除任务')
            update_order_status(trade_number, -2)
            self._delete_job(job_id)
            return

        # 3. 弹窗付款
        order_info['filename'] = doc_name
        result = show_payment_window(order_info, pay_info)
        logger.info('弹窗结果: %s', result)

        if result == 'paid':
            # 4a. 付款成功 → 临时恢复打印机 → 等任务打完 → 再暂停
            logger.info('付款成功！临时恢复打印机...')
            self._resume_printer()
            self._wait_job_complete(job_id, timeout=120)
            self._pause_printer()
            update_order_status(trade_number, 3)
            logger.info('打印完成: %s', trade_number)
        else:
            # 4b. 取消/超时 → 删除任务
            logger.info('用户取消/超时，删除任务 #%d', job_id)
            self._delete_job(job_id)
            update_order_status(trade_number, -2)

        logger.info('===== 任务 #%d 处理完毕 =====', job_id)

    def poll(self):
        """扫描一次队列，处理新任务。"""
        jobs = self._get_jobs()
        for job in jobs:
            job_id = self._get_job_id(job)
            if job_id in self._known_jobs:
                continue

            self._known_jobs.add(job_id)

            if self._processing:
                logger.warning('正在处理其他任务，#%d 排队等待', job_id)
                continue

            self._processing = True
            try:
                self._handle_new_job(job)
            except Exception as e:
                logger.exception('处理任务 #%d 异常: %s', job_id, e)
            finally:
                self._processing = False

    def run_loop(self):
        """主循环。"""
        # ★ 启动时暂停打印机
        self._pause_printer()
        logger.info('开始监控打印机: %s （已暂停，等待付款后打印）', self.printer_name)

        while self._running:
            try:
                self.poll()
            except Exception as e:
                logger.exception('监控循环异常: %s', e)
            time.sleep(0.5)

        # 退出时恢复打印机
        self._resume_printer()

    def stop(self):
        self._running = False


# ---- 系统托盘 ----

def _create_tray_icon(watcher):
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
            watcher.stop()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem(f'打印机: {watcher.printer_name} (拦截中)', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出（恢复打印机）', on_quit),
        )
        return pystray.Icon('local_printer', img, '云打印-本地拦截器', menu)
    except ImportError:
        return None


def main():
    printer_name = config.PRINTER_NAME
    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()

    logger.info('====== 本地打印拦截器启动 (Spooler 监控 v2) ======')
    logger.info('打印机: %s', printer_name)
    logger.info('服务器: %s', config.SERVER_URL)

    # 验证打印机
    try:
        handle = win32print.OpenPrinter(printer_name)
        win32print.ClosePrinter(handle)
    except Exception as e:
        logger.error('无法连接打印机 "%s": %s', printer_name, e)
        input('按 Enter 退出...')
        return

    watcher = SpoolerWatcher(printer_name)

    tray_icon = _create_tray_icon(watcher)
    if tray_icon:
        tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
        tray_thread.start()

    try:
        watcher.run_loop()
    except KeyboardInterrupt:
        watcher.stop()
        if tray_icon:
            tray_icon.stop()

    logger.info('====== 本地打印拦截器已退出 ======')


if __name__ == '__main__':
    main()
