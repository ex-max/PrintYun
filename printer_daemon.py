# -*- coding: utf-8 -*-
"""自动打印守护进程。

职责：
  * 定期（默认 3 秒）轮询 `Order` 表
  * 领取 `Print_Status == 1`（已支付未打印）的订单，原子把状态改为 2（处理中）
  * 按订单参数调 SumatraPDF 发送到指定打印机
  * 成功 → 3（已打印完成）；失败 → -1（打印失败）

独立进程，与 Flask/worker 解耦；多实例运行时通过原子 UPDATE 防止重复打印。

依赖配置（.env）：
  PRINTER_NAME           打印机名，如 "HP LaserJet M1005"
  SUMATRA_PATH           SumatraPDF.exe 完整路径
  PRINTER_POLL_SECONDS   轮询间隔（默认 3）
"""

import os
import sys
import time
import signal
import subprocess
import logging

# 先加载 .env，再 import app（app/__init__.py 在导入时会读环境变量）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=False)
except ImportError:
    pass

from app import app, db
from app.models import Order

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('printer_daemon')

# ---- 配置 ----
PRINTER_NAME = os.environ.get('PRINTER_NAME', '').strip()
SUMATRA_PATH = os.environ.get(
    'SUMATRA_PATH',
    r'C:\Program Files\SumatraPDF\SumatraPDF.exe',
)
POLL_INTERVAL = int(os.environ.get('PRINTER_POLL_SECONDS', '3'))
PRINT_TIMEOUT = int(os.environ.get('PRINTER_TIMEOUT_SECONDS', '120'))
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'app', 'static', 'Upload_Files')

# ---- 状态值（与 models.py / to_json 约定保持一致）----
STATUS_PAID = 1      # 已支付，待打印
STATUS_PRINTING = 2  # 正在打印
STATUS_DONE = 3      # 打印完成
STATUS_FAILED = -1   # 打印失败

_running = True


def _shutdown(signum, _frame):
    global _running
    log.info('收到信号 %s，准备优雅退出...', signum)
    _running = False


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def map_print_settings(order):
    """把订单字段映射成 SumatraPDF -print-settings 字符串。"""
    parts = []

    # 颜色
    if order.Print_Colour == 'CMYGray':
        parts.append('monochrome')
    elif order.Print_Colour == 'RGB':
        parts.append('color')

    # 单/双面
    way = (order.Print_way or '').lower()
    if way == 'one-sided':
        parts.append('simplex')
    elif way == 'two-sided-long-edge':
        parts.append('duplexlong')
    elif way == 'two-sided-short-edge':
        parts.append('duplexshort')

    # 份数
    copies = int(order.Print_Copies or 1)
    if copies > 1:
        parts.append(f'{copies}x')

    # 方向：forms.py 里 3=竖版，4=横版
    if str(order.Print_Direction) == '4':
        parts.append('landscape')
    elif str(order.Print_Direction) == '3':
        parts.append('portrait')

    # 纸张尺寸
    if order.Print_size:
        parts.append(f'paper={order.Print_size}')

    return ','.join(parts)


def send_to_printer(order):
    """实际调用 SumatraPDF 打印一单。返回 True/False。"""
    if not order.File_Dir:
        log.error('订单 %s 没有 File_Dir', order.Trade_Number)
        return False

    file_path = os.path.join(UPLOAD_DIR, order.File_Dir)
    if not os.path.exists(file_path):
        log.error('订单 %s 文件不存在：%s', order.Trade_Number, file_path)
        return False

    settings = map_print_settings(order)
    cmd = [SUMATRA_PATH]
    if PRINTER_NAME:
        cmd += ['-print-to', PRINTER_NAME]
    else:
        cmd += ['-print-to-default']
    if settings:
        cmd += ['-print-settings', settings]
    cmd += ['-silent', '-exit-when-done', file_path]

    log.info('打印订单 %s  文件=%s  参数=%s',
             order.Trade_Number, order.File_Dir, settings or '(无)')

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=PRINT_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.error('订单 %s 打印超时（%ss）', order.Trade_Number, PRINT_TIMEOUT)
        return False
    except Exception as e:
        log.exception('订单 %s 调用打印器异常：%s', order.Trade_Number, e)
        return False

    if proc.returncode == 0:
        return True

    stderr = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else ''
    log.error('订单 %s SumatraPDF 退出码 %s  stderr=%s',
              order.Trade_Number, proc.returncode, stderr[:500])
    return False


def claim_one_order():
    """原子地把一笔 Print_Status=1 的订单改成 2，返回领到的订单对象。"""
    order = (
        Order.query
        .filter(Order.Print_Status == STATUS_PAID)
        .order_by(Order.Id)
        .first()
    )
    if order is None:
        return None

    stmt = db.text(
        "UPDATE `Order` SET Print_Status = :new "
        "WHERE Id = :oid AND Print_Status = :old"
    )
    result = db.session.execute(stmt, {
        'new': STATUS_PRINTING,
        'oid': order.Id,
        'old': STATUS_PAID,
    })
    db.session.commit()

    if result.rowcount == 1:
        db.session.refresh(order)
        return order
    # 被别人抢走了
    return None


def main_loop():
    log.info('=' * 60)
    log.info('printer_daemon 启动')
    log.info('轮询间隔：%s 秒', POLL_INTERVAL)
    log.info('打印机  ：%s', PRINTER_NAME or '(系统默认)')
    log.info('SumatraPDF：%s', SUMATRA_PATH)
    log.info('上传目录：%s', UPLOAD_DIR)
    log.info('=' * 60)

    if not os.path.exists(SUMATRA_PATH):
        log.error('找不到 SumatraPDF.exe，请在 .env 里设置 SUMATRA_PATH')
        sys.exit(1)

    # Redis 连接用于接收打印信号
    try:
        import redis as _redis
        _redis_url = os.getenv('REDISTOGO_URL', 'redis://:123456@localhost:6379')
        _rconn = _redis.Redis.from_url(_redis_url)
        _rconn.ping()
        log.info('Redis 信号通知已启用（blpop print_queue）')
    except Exception as e:
        _rconn = None
        log.warning('Redis 不可用，回退到纯 DB 轮询：%s', e)

    while _running:
        try:
            # 优先通过 Redis blpop 等待信号（支付成功时 lpush 的）
            if _rconn:
                try:
                    msg = _rconn.blpop('print_queue', timeout=POLL_INTERVAL)
                except Exception:
                    msg = None
                    time.sleep(POLL_INTERVAL)
            else:
                time.sleep(POLL_INTERVAL)

            with app.app_context():
                order = claim_one_order()
                if order is None:
                    continue

                ok = send_to_printer(order)

                # 重新获取订单（已经是新 session 下的对象）
                order = Order.query.get(order.Id)
                order.Print_Status = STATUS_DONE if ok else STATUS_FAILED
                db.session.commit()

                log.info('订单 %s 处理结果：%s',
                         order.Trade_Number, '成功' if ok else '失败')
        except Exception as e:
            log.exception('主循环异常：%s', e)
            time.sleep(POLL_INTERVAL)

    log.info('printer_daemon 已退出')


if __name__ == '__main__':
    main_loop()
