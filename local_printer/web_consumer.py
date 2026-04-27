# -*- coding: utf-8 -*-
"""WebOrderConsumer —— 订阅 Redis `print_queue`，消费 Web 端已付款订单。

直接调用 SumatraPDF 将 PDF 发送到真实打印机。
真实打印机永远不暂停，无需任何 pause/resume 协调。
"""

import os
import time
import threading
import logging
import subprocess
import requests

from local_printer import config

logger = logging.getLogger(__name__)


class WebOrderConsumer(threading.Thread):
    """Redis 消费者线程：把 Web 端已付款订单送到物理打印机。"""

    def __init__(self, redis_conn, printer_name):
        super().__init__(daemon=True, name='WebOrderConsumer')
        self.redis = redis_conn
        self.printer_name = printer_name
        self._running = True

    # ---- API 调用 ----

    def _api_headers(self):
        return {'X-Local-Key': config.MACHINE_KEY,
                'Content-Type': 'application/json'}

    def _api_url(self, path):
        return f'{config.SERVER_URL}/local/{path}'

    def _claim(self, order_id):
        """向后端原子领取订单，返回 dict 或 None。"""
        try:
            resp = requests.post(
                self._api_url('claim_web_order'),
                json={'id': int(order_id)},
                headers=self._api_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning('领取订单 #%s 失败 (%d): %s',
                           order_id, resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error('领取订单 #%s 异常: %s', order_id, e)
        return None

    def _update_status(self, trade_number, status):
        try:
            requests.post(
                self._api_url('update_status'),
                json={'trade_number': trade_number, 'status': status},
                headers=self._api_headers(),
                timeout=5,
            )
        except Exception as e:
            logger.warning('更新订单状态失败: %s', e)

    # ---- SumatraPDF 打印 ----

    def _build_sumatra_cmd(self, pdf_path, color, duplex, copies, paper,
                           direction):
        parts = []
        if color == 'CMYGray':
            parts.append('monochrome')
        elif color in ('RGB', 'color'):
            parts.append('color')
        if duplex == 'one-sided':
            parts.append('simplex')
        elif duplex == 'two-sided-long-edge':
            parts.append('duplexlong')
        elif duplex == 'two-sided-short-edge':
            parts.append('duplexshort')
        if copies > 1:
            parts.append(f'{copies}x')
        if str(direction) == '4':
            parts.append('landscape')
        elif str(direction) == '3':
            parts.append('portrait')
        if paper:
            parts.append(f'paper={paper}')
        settings = ','.join(parts)

        cmd = [config.SUMATRA_PATH]
        if self.printer_name:
            cmd += ['-print-to', self.printer_name]
        else:
            cmd += ['-print-to-default']
        if settings:
            cmd += ['-print-settings', settings]
        cmd += ['-silent', '-exit-when-done', pdf_path]
        return cmd, settings

    def _print_order(self, order):
        """调用 SumatraPDF 打印，返回是否成功。"""
        pdf_path = order.get('pdf_path', '')
        if not pdf_path or not os.path.exists(pdf_path):
            logger.error('Web 订单 %s 的 PDF 不存在: %s',
                         order.get('trade_number'), pdf_path)
            return False

        cmd, settings = self._build_sumatra_cmd(
            pdf_path,
            order.get('color', 'CMYGray'),
            order.get('duplex', 'one-sided'),
            int(order.get('copies', 1)),
            order.get('paper', 'A4'),
            order.get('direction', ''),
        )

        logger.info('SumatraPDF 打印 Web 订单 %s  参数=%s',
                    order.get('trade_number'), settings or '(无)')

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.error('SumatraPDF 超时: %s', order.get('trade_number'))
            return False
        except Exception as e:
            logger.exception('SumatraPDF 异常: %s', e)
            return False

        if proc.returncode == 0:
            logger.info('SumatraPDF 打印成功: %s', order.get('trade_number'))
            return True

        stderr = (proc.stderr or b'').decode('utf-8', errors='replace')[:300]
        logger.error('SumatraPDF 退出码 %d  stderr=%s',
                     proc.returncode, stderr)
        return False

    # ---- 主循环 ----

    def run(self):
        logger.info('WebOrderConsumer 线程启动，监听 Redis print_queue')
        while self._running:
            try:
                # blpop 阻塞等待，5 秒超时让 _running 有机会检查退出
                result = self.redis.blpop('print_queue', timeout=5)
            except Exception as e:
                logger.warning('Redis blpop 异常: %s', e)
                time.sleep(2)
                continue

            if not result:
                continue  # 超时无消息

            _queue_name, raw_value = result
            try:
                order_id = int(raw_value)
            except (TypeError, ValueError):
                logger.warning('print_queue 收到非法消息: %r', raw_value)
                continue

            logger.info('收到 Web 订单信号: id=%d', order_id)

            # 1. 向后端原子领取订单（Print_Status 1 -> 2）
            order = self._claim(order_id)
            if not order:
                logger.info('订单 #%d 领取失败，跳过', order_id)
                continue

            trade_number = order.get('trade_number', '')
            logger.info('领取 Web 订单成功: #%d %s (%d 页 / ¥%.2f)',
                        order_id, trade_number,
                        order.get('pages', 0), order.get('money', 0))

            # 2. 直接打印到真实打印机（无需 pause/resume）
            ok = self._print_order(order)

            # 3. 更新最终状态：3=完成，-1=失败
            self._update_status(trade_number, 3 if ok else -1)
            logger.info('Web 订单 %s 处理结果: %s',
                        trade_number, '已完成' if ok else '失败')

        logger.info('WebOrderConsumer 线程已退出')

    def stop(self):
        self._running = False
