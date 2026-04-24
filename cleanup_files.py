# -*- coding: utf-8 -*-
"""上传文件定期清理脚本。

删除 30 天前已完成(3) / 已取消(-2) / 打印失败(-1) 订单的上传文件。
使用方式：
  手动：  python cleanup_files.py
  定时：  Windows 任务计划 / Linux cron 每天执行一次
"""

import os
import sys
import datetime
import logging

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=False)
except ImportError:
    pass

from app import app, db
from app.models import Order

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('cleanup_files')

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'app', 'static', 'Upload_Files')
BEFORE_SWITCH_DIR = os.path.join(UPLOAD_DIR, 'BeforeSwitchFile')
KEEP_DAYS = int(os.environ.get('CLEANUP_KEEP_DAYS', '30'))


def cleanup():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=KEEP_DAYS)
    log.info('开始清理 %d 天前的已完成/已取消/失败订单文件 (截止 %s)', KEEP_DAYS, cutoff)

    with app.app_context():
        old_orders = (
            Order.query
            .filter(Order.Print_Status.in_([3, -1, -2]))
            .filter(Order.Born_Date < cutoff)
            .all()
        )

        deleted = 0
        for order in old_orders:
            if not order.File_Dir:
                continue
            # 删除转换后文件
            fpath = os.path.join(UPLOAD_DIR, order.File_Dir)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    deleted += 1
                    log.info('已删除: %s', order.File_Dir)
                except Exception as e:
                    log.warning('删除失败 %s: %s', fpath, e)

            # 删除转换前源文件（BeforeSwitchFile 目录）
            for bdir in [BEFORE_SWITCH_DIR]:
                bpath = os.path.join(bdir, order.File_Dir)
                if os.path.exists(bpath):
                    try:
                        os.remove(bpath)
                    except Exception:
                        pass
                # 也尝试原始扩展名的文件
                base = os.path.splitext(order.File_Dir)[0]
                for ext in ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt']:
                    src = os.path.join(bdir, base + ext)
                    if os.path.exists(src):
                        try:
                            os.remove(src)
                        except Exception:
                            pass

        log.info('清理完成：共处理 %d 个订单，删除 %d 个文件', len(old_orders), deleted)


if __name__ == '__main__':
    cleanup()
