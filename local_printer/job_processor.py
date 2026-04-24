# -*- coding: utf-8 -*-
"""本地打印拦截器 — 打印任务处理器。

串联完整流程：PS → PDF → 读页数 → 创建订单 → 弹窗付款 → 打印。
"""

import os
import logging
import requests

from local_printer import config
from local_printer.printer_utils import convert_ps_to_pdf, read_pdf_pages, print_pdf, cleanup

logger = logging.getLogger(__name__)


def _api_headers():
    return {'X-Local-Key': config.MACHINE_KEY, 'Content-Type': 'application/json'}


def _api_url(path):
    return f'{config.SERVER_URL}/local/{path}'


def create_order_via_api(pages, color, duplex, copies, paper, filename):
    """调后端 API 创建本地打印订单。返回 dict 或 None。"""
    try:
        resp = requests.post(
            _api_url('create_order'),
            json={
                'pages': pages,
                'color': color,
                'duplex': duplex,
                'copies': copies,
                'paper': paper,
                'filename': filename,
            },
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error('创建订单失败 (%d): %s', resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error('创建订单请求异常: %s', e)
    return None


def get_pay_url(trade_number):
    """获取支付链接。返回 dict 或 None。"""
    try:
        resp = requests.get(
            _api_url('pay_url'),
            params={'trade_number': trade_number},
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error('获取支付链接失败 (%d): %s', resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error('获取支付链接请求异常: %s', e)
    return None


def check_payment_status(trade_number):
    """查询订单状态。返回 dict 或 None。"""
    try:
        resp = requests.get(
            _api_url('check_status'),
            params={'trade_number': trade_number},
            headers=_api_headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def update_order_status(trade_number, status):
    """更新订单状态。"""
    try:
        requests.post(
            _api_url('update_status'),
            json={'trade_number': trade_number, 'status': status},
            headers=_api_headers(),
            timeout=5,
        )
    except Exception as e:
        logger.warning('更新订单状态失败: %s', e)


def process_print_job(ps_file_path, show_payment_window_func):
    """处理一个打印任务的完整流程。

    Args:
        ps_file_path: PostScript 文件路径
        show_payment_window_func: 弹窗函数，签名 (order_info, pay_info) -> 'paid' | 'cancelled' | 'timeout'
    """
    logger.info('========== 新打印任务: %s ==========', os.path.basename(ps_file_path))

    # 1. PS → PDF
    pdf_path = convert_ps_to_pdf(ps_file_path)
    if not pdf_path:
        logger.error('PS 转 PDF 失败，任务中止')
        cleanup(ps_file_path)
        return

    # 2. 读取页数
    pages = read_pdf_pages(pdf_path)
    if pages <= 0:
        logger.error('无法读取页数，任务中止')
        cleanup(ps_file_path, pdf_path)
        return

    # 3. 创建订单
    # 尝试从 PS 文件名猜原始文件名（Redmon 可能会传递文档标题）
    raw_name = os.path.splitext(os.path.basename(ps_file_path))[0]
    # 清理 UUID 前缀
    if len(raw_name) == 32 or (len(raw_name) > 32 and raw_name[:8].isalnum()):
        display_name = '本地打印文档'
    else:
        display_name = raw_name

    color = config.DEFAULT_COLOR
    duplex = config.DEFAULT_DUPLEX
    copies = config.DEFAULT_COPIES
    paper = config.DEFAULT_PAPER

    order_info = create_order_via_api(pages, color, duplex, copies, paper, display_name)
    if not order_info:
        logger.error('创建订单失败，任务中止')
        cleanup(ps_file_path, pdf_path)
        return

    trade_number = order_info['trade_number']
    logger.info('订单已创建: %s, %d 页, ¥%.2f', trade_number, pages, order_info['cost'])

    # 4. 获取支付链接
    pay_info = get_pay_url(trade_number)
    if not pay_info:
        logger.error('获取支付链接失败，任务中止')
        update_order_status(trade_number, -2)
        cleanup(ps_file_path, pdf_path)
        return

    # 5. 弹窗付款
    result = show_payment_window_func(order_info, pay_info)
    logger.info('弹窗结果: %s', result)

    if result == 'paid':
        # 6. 付款成功 → 打印
        logger.info('付款成功，开始打印...')
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

    # 7. 清理临时文件
    cleanup(ps_file_path, pdf_path)
    logger.info('========== 任务结束: %s ==========', trade_number)
