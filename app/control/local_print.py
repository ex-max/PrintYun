# -*- coding: utf-8 -*-
"""本地打印拦截器 — 后端 API。

为桌面端守护程序提供订单创建、支付链接获取、状态查询接口。
不影响现有 Web 云打印的任何逻辑。

接口鉴权：通过 .env 中的 LOCAL_PRINT_KEY 做简单密钥校验，
桌面程序每次请求带 X-Local-Key 头。
"""

import os
import logging
from flask import Blueprint, request, jsonify
from app.models import db, Order
from app.utils import next_trade_number, save_order_atomic

logger = logging.getLogger(__name__)

local_print = Blueprint('local_print', __name__)

_LOCAL_KEY = os.environ.get('LOCAL_PRINT_KEY', '')

_local_user_id = None


def _get_local_user_id():
    """获取本地打印专用用户 ID（首次调用时查询/创建，然后缓存）。"""
    global _local_user_id
    if _local_user_id is not None:
        return _local_user_id

    from app.models import User
    # 先找是否已有 local_printer 系统用户
    u = User.query.filter_by(Tel_Number='local_printer').first()
    if u:
        _local_user_id = u.Id
        return _local_user_id

    # 没有则取第一个 admin 用户
    admin = User.query.filter_by(Role='admin').first()
    if admin:
        _local_user_id = admin.Id
        return _local_user_id

    # 兜底：取任意用户
    any_user = User.query.first()
    if any_user:
        _local_user_id = any_user.Id
        return _local_user_id

    return None


def _check_key():
    """校验机器密钥，防止外部随意调用。"""
    if not _LOCAL_KEY:
        return True  # 未配置密钥时放行（开发阶段）
    return request.headers.get('X-Local-Key', '') == _LOCAL_KEY


def _unit_price(color, duplex):
    """价格计算（与 printer.py 保持一致）。"""
    is_duplex = duplex != 'one-sided'
    if color == 'CMYGray':
        return 0.5 if is_duplex else 0.3
    else:
        return 1.7 if is_duplex else 1.0


# ---------- API 接口 ----------

@local_print.route('/create_order', methods=['POST'])
def create_order():
    """桌面程序创建本地打印订单。

    请求体 JSON：
        pages       int    页数
        color       str    "CMYGray" | "RGB"
        duplex      str    "one-sided" | "two-sided-long-edge" | "two-sided-short-edge"
        copies      int    份数（默认 1）
        paper       str    纸张（默认 "A4"）
        filename    str    原始文件名（展示用）
    """
    if not _check_key():
        return jsonify({'error': '鉴权失败'}), 403

    data = request.get_json(force=True, silent=True) or {}
    pages = int(data.get('pages', 0))
    color = data.get('color', 'CMYGray')
    duplex = data.get('duplex', 'one-sided')
    copies = int(data.get('copies', 1)) or 1
    paper = data.get('paper', 'A4')
    filename = data.get('filename', '本地打印')

    if pages <= 0:
        return jsonify({'error': '页数必须大于 0'}), 400

    unit_p = _unit_price(color, duplex)
    cost = round(unit_p * pages * copies, 2)

    user_id = _get_local_user_id()
    if user_id is None:
        return jsonify({'error': '系统中没有用户，请先通过 Web 注册一个账号'}), 500

    order = Order()
    order.User_Id = user_id
    order.File_Dir = ''
    order.File_Name = filename
    order.Print_Place = 'local'  # 标识本地打印订单
    order.Print_pages = pages
    order.Print_Copies = copies
    order.Print_Direction = '3'  # 竖版
    order.Print_Colour = color
    order.Print_size = paper
    order.Print_way = duplex
    order.Print_Money = cost
    order.Trade_Number = next_trade_number()
    order.Time_Way = '1'  # 直接打印

    try:
        trade_number = save_order_atomic(order)
    except Exception as e:
        logger.error('创建本地打印订单失败: %s', e)
        return jsonify({'error': '创建订单失败'}), 500

    logger.info('本地打印订单已创建: %s, %d页, ¥%.2f', trade_number, pages, cost)
    return jsonify({
        'trade_number': trade_number,
        'cost': cost,
        'pages': pages,
        'copies': copies,
        'unit_price': unit_p,
    })


@local_print.route('/pay_url')
def pay_url():
    """获取支付宝付款链接，供桌面弹窗生成二维码。"""
    if not _check_key():
        return jsonify({'error': '鉴权失败'}), 403

    trade_number = request.args.get('trade_number', '').strip()
    if not trade_number:
        return jsonify({'error': '缺少 trade_number'}), 400

    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    cost = float(order.Print_Money or 0)
    if cost <= 0:
        return jsonify({'error': '订单金额异常'}), 400

    # 调用支付宝生成支付链接
    try:
        from app.test.ali_pay import get_alipay, _make_alipay_trade_no, _callback_base, _ALIPAY_GATEWAY
        alipay = get_alipay()
        if alipay is None:
            return jsonify({'error': '支付宝未配置'}), 503

        base = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:5000').rstrip('/')
        alipay_trade_no = _make_alipay_trade_no(trade_number)

        # 生成电脑端支付链接（扫码付）
        order_string = alipay.api_alipay_trade_precreate(
            out_trade_no=alipay_trade_no,
            total_amount=cost,
            subject=f'打印费-{order.File_Name}',
            notify_url=base + '/cloud_pay/native_alipay',
        )
        # precreate 返回的是一个字典，里面有 qr_code
        qr_code = order_string.get('qr_code', '') if isinstance(order_string, dict) else ''

        if not qr_code:
            # 降级：用手机网页支付链接生成二维码
            order_string2 = alipay.api_alipay_trade_wap_pay(
                out_trade_no=alipay_trade_no,
                total_amount=cost,
                subject=f'打印费-{order.File_Name}',
                return_url=base + '/cloud_pay/alipayresult1',
                notify_url=base + '/cloud_pay/native_alipay',
            )
            pay_link = _ALIPAY_GATEWAY + '?' + order_string2
            return jsonify({
                'qr_data': pay_link,
                'pay_url': pay_link,
            })

        return jsonify({
            'qr_data': qr_code,
            'pay_url': qr_code,
        })
    except Exception as e:
        logger.error('生成支付链接失败: %s', e)
        return jsonify({'error': f'生成支付链接失败: {e}'}), 500


@local_print.route('/check_status')
def check_status():
    """桌面程序轮询订单付款状态。

    如果数据库中还是未支付，会主动查询支付宝确认（不依赖回调）。
    """
    if not _check_key():
        return jsonify({'error': '鉴权失败'}), 403

    trade_number = request.args.get('trade_number', '').strip()
    if not trade_number:
        return jsonify({'error': '缺少 trade_number'}), 400

    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    status = int(order.Print_Status or 0)

    # ★ 如果数据库显示未支付，主动查询支付宝
    if status == 0:
        try:
            from app.test.ali_pay import get_alipay, _make_alipay_trade_no
            alipay = get_alipay()
            if alipay:
                alipay_trade_no = _make_alipay_trade_no(trade_number)
                result = alipay.api_alipay_trade_query(out_trade_no=alipay_trade_no)
                trade_status = ''
                if isinstance(result, dict):
                    trade_status = result.get('trade_status', '')
                elif isinstance(result, str):
                    trade_status = result

                if trade_status in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
                    # 支付宝确认已付款 → 更新数据库
                    order.Print_Status = 1
                    db.session.commit()
                    status = 1
                    logger.info('主动查询确认已付款: %s', trade_number)
        except Exception as e:
            logger.warning('主动查询支付宝失败: %s', e)

    STATUS_TEXT = {
        -2: '已取消', -1: '打印失败', 0: '未支付',
        1: '已支付', 2: '正在打印', 3: '已完成',
    }
    return jsonify({
        'status': status,
        'status_text': STATUS_TEXT.get(status, f'状态 {status}'),
        'paid': status >= 1,
    })


@local_print.route('/update_status', methods=['POST'])
def update_status():
    """桌面程序更新订单状态（打印完成/取消）。"""
    if not _check_key():
        return jsonify({'error': '鉴权失败'}), 403

    data = request.get_json(force=True, silent=True) or {}
    trade_number = data.get('trade_number', '').strip()
    new_status = data.get('status')

    if not trade_number or new_status is None:
        return jsonify({'error': '参数不完整'}), 400

    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    order.Print_Status = int(new_status)
    db.session.commit()
    logger.info('本地打印订单 %s 状态更新为 %s', trade_number, new_status)
    return jsonify({'ok': True})
