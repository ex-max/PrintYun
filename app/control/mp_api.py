# -*- coding: utf-8 -*-
"""小程序 API 蓝图。

为微信小程序提供专用接口，使用 /api/mp 前缀。
不影响现有 Web 云打印的任何逻辑。

接口鉴权：通过 JWT Token 校验用户身份。
"""

import os
import logging
import datetime
import hashlib
import json
from functools import wraps

import requests
from flask import Blueprint, request, jsonify, g, current_app
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app.models import db, User, Order, PrintPlace
from app.utils import next_trade_number, save_order_atomic, read_pdf_pages

logger = logging.getLogger(__name__)

mp_api = Blueprint('mp_api', __name__)

# ============ 配置 ============

# 小程序 AppID 和 AppSecret（从环境变量读取）
MP_APPID = os.environ.get('MP_APPID', '')
MP_SECRET = os.environ.get('MP_SECRET', '')

# JWT 密钥（从环境变量读取，与 Web 端共用或独立）
JWT_SECRET = os.environ.get('JWT_SECRET', os.environ.get('SECRET_KEY', 'your-secret-key'))
JWT_EXPIRE_HOURS = int(os.environ.get('JWT_EXPIRE_HOURS', '168'))  # 默认 7 天

# 文件上传配置
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


# ============ 工具函数 ============

def _unit_price(print_color, print_way):
    """计算单价（元/页）：按颜色 × 单/双面定价。"""
    is_duplex = print_way != 'one-sided'
    if print_color == 'CMYGray':
        return 0.5 if is_duplex else 0.3
    else:
        return 1.7 if is_duplex else 1.0


def _allowed_file(filename):
    """检查文件扩展名是否允许。"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def _generate_token(user_id, openid=''):
    """生成 JWT Token。"""
    import time
    import base64
    import hmac
    
    timestamp = int(time.time())
    expire = timestamp + JWT_EXPIRE_HOURS * 3600
    
    # 简单的 token 结构：user_id:timestamp:expire:signature
    payload = f"{user_id}:{timestamp}:{expire}"
    signature = hmac.new(
        JWT_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token


def _verify_token(token):
    """验证 JWT Token，返回 user_id 或 None。"""
    import time
    import base64
    import hmac
    
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(':')
        if len(parts) != 4:
            return None
        
        user_id, timestamp, expire, signature = parts
        expire = int(expire)
        
        # 检查是否过期
        if expire < int(time.time()):
            return None
        
        # 验证签名
        payload = f"{user_id}:{timestamp}:{expire}"
        expected_sig = hmac.new(
            JWT_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        if signature != expected_sig:
            return None
        
        return int(user_id)
    except Exception as e:
        logger.warning('Token 验证失败: %s', e)
        return None


def _require_auth(f):
    """装饰器：要求用户已登录。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'code': 401, 'msg': '请先登录'}), 401
        
        token = auth_header[7:]
        user_id = _verify_token(token)
        if not user_id:
            return jsonify({'code': 401, 'msg': '登录已过期，请重新登录'}), 401
        
        # 检查用户是否存在且有效
        user = User.query.get(user_id)
        if not user or not user.Is_Active:
            return jsonify({'code': 401, 'msg': '用户不存在或已被禁用'}), 401
        
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def _json_response(data=None, code=0, msg='success'):
    """统一 JSON 响应格式。"""
    return jsonify({
        'code': code,
        'msg': msg,
        'data': data or {}
    })


# ============ 认证模块 ============

@mp_api.route('/auth/login', methods=['POST'])
def auth_login():
    """微信小程序一键登录（静默登录 + 授权获取用户信息）。
    
    流程：
    1. 前端先调用 wx.login() 获取 code
    2. 前端通过 button/wx.getUserProfile 获取用户信息
    3. 后端用 code 换取 openid，保存/更新用户昵称和头像
    
    请求体：
        code: wx.login() 返回的 code（必需）
        userInfo: 微信用户信息（可选，结构：{nickName, avatarUrl}）
    
    返回：
        token: JWT Token
        user: 用户信息
    """
    data = request.get_json(force=True, silent=True) or {}
    code = data.get('code', '').strip()
    user_info = data.get('userInfo', {})
    
    if not code:
        return _json_response(code=400, msg='缺少登录凭证')
    
    # 调用微信 code2Session 接口
    try:
        url = 'https://api.weixin.qq.com/sns/jscode2session'
        params = {
            'appid': MP_APPID,
            'secret': MP_SECRET,
            'js_code': code,
            'grant_type': 'authorization_code'
        }
        
        resp = requests.get(url, params=params, timeout=10)
        result = resp.json()
        
        if 'errcode' in result and result['errcode'] != 0:
            logger.error('微信登录失败: %s', result)
            return _json_response(code=400, msg=f"微信登录失败: {result.get('errmsg', '未知错误')}")
        
        openid = result.get('openid', '')
        
        if not openid:
            return _json_response(code=400, msg='获取 OpenID 失败')
        
        # 查找或创建用户
        user = User.query.filter_by(Tel_Number=f'wx_{openid}').first()
        is_new_user = False
        
        if not user:
            # 创建新用户
            user = User()
            user.Tel_Number = f'wx_{openid}'
            user.Role = 'user'
            user.Is_Active = True
            user.Register_Date = datetime.date.today()
            user.Born_Date_Day = datetime.date.today()
            is_new_user = True
            logger.info('小程序新用户注册: %s', openid)
        
        # 更新用户信息（昵称和头像）
        if user_info:
            nickname = user_info.get('nickName', '').strip()
            avatar_url = user_info.get('avatarUrl', '').strip()
            if nickname:
                user.Nickname = nickname
            if avatar_url:
                user.Avatar_Url = avatar_url
        
        db.session.add(user)
        db.session.commit()
        
        # 生成 Token
        token = _generate_token(user.Id, openid)
        
        return _json_response({
            'token': token,
            'user': {
                'id': user.Id,
                'nickname': user.Nickname or '',
                'phone': user.Tel_Number if not user.Tel_Number.startswith('wx_') else '',
                'avatarUrl': user.Avatar_Url or ''
            },
            'isNewUser': is_new_user
        })
        
    except requests.RequestException as e:
        logger.error('调用微信接口失败: %s', e)
        return _json_response(code=500, msg='网络错误，请重试')
    except Exception as e:
        logger.error('登录异常: %s', e, exc_info=True)
        return _json_response(code=500, msg='登录失败，请重试')


@mp_api.route('/auth/refresh', methods=['POST'])
@_require_auth
def auth_refresh():
    """刷新 Token。"""
    token = _generate_token(g.current_user.Id)
    return _json_response({'token': token})


@mp_api.route('/auth/logout', methods=['POST'])
@_require_auth
def auth_logout():
    """退出登录（客户端删除 Token 即可）。"""
    return _json_response()


@mp_api.route('/auth/bindPhone', methods=['POST'])
@_require_auth
def auth_bind_phone():
    """绑定手机号。
    
    请求体：
        encryptedData: 微信加密数据
        iv: 加密算法初始向量
    
    或：
        phone: 手机号
        code: 验证码
    """
    data = request.get_json(force=True, silent=True) or {}
    
    # 方式一：微信手机号授权
    encrypted_data = data.get('encryptedData', '')
    iv = data.get('iv', '')
    
    if encrypted_data and iv:
        # TODO: 解密微信手机号数据
        # 需要使用 session_key 解密，这里简化处理
        # 实际生产需要维护 session_key
        return _json_response(code=501, msg='功能开发中')
    
    # 方式二：手机号 + 验证码
    phone = data.get('phone', '').strip()
    sms_code = data.get('code', '').strip()
    
    if not phone or not sms_code:
        return _json_response(code=400, msg='请提供手机号和验证码')
    
    # TODO: 验证短信验证码
    # 这里简化处理，实际需要对接短信服务
    
    # 检查手机号是否已被其他用户绑定
    existing = User.query.filter_by(Tel_Number=phone).first()
    if existing and existing.Id != g.current_user.Id:
        return _json_response(code=400, msg='该手机号已被其他账号绑定')
    
    # 绑定手机号
    g.current_user.Tel_Number = phone
    db.session.commit()
    
    return _json_response({'phone': phone})


# ============ 用户模块 ============

@mp_api.route('/user/info')
@_require_auth
def user_info():
    """获取用户信息和消费统计。"""
    user = g.current_user
    
    # 统计订单
    total_orders = Order.query.filter_by(User_Id=user.Id).count()
    completed_orders = Order.query.filter_by(User_Id=user.Id, Print_Status=3).all()
    total_amount = sum(o.Print_Money or 0 for o in completed_orders)
    
    # 本月统计
    today = datetime.date.today()
    month_start = today.replace(day=1)
    month_orders = Order.query.filter(
        Order.User_Id == user.Id,
        Order.Born_Date_Day >= month_start,
        Order.Print_Status == 3
    ).all()
    month_amount = sum(o.Print_Money or 0 for o in month_orders)
    
    return _json_response({
        'user': {
            'id': user.Id,
            'nickname': user.Nickname or '',
            'phone': user.Tel_Number if not user.Tel_Number.startswith('wx_') else '',
            'avatarUrl': user.Avatar_Url or ''
        },
        'totalOrders': total_orders,
        'totalAmount': round(total_amount, 2),
        'monthOrders': len(month_orders),
        'monthAmount': round(month_amount, 2)
    })


# ============ 文件上传模块 ============

@mp_api.route('/upload', methods=['POST'])
@_require_auth
def upload_file():
    """上传文件。
    
    表单字段：
        file: 文件
        type: 文件类型（可选，用于身份证打印等特殊场景）
    
    返回：
        fileId: 文件 ID
        filePath: 文件路径
        pageCount: PDF 页数（PDF 文件）
    """
    if 'file' not in request.files:
        return _json_response(code=400, msg='请选择文件')
    
    file = request.files['file']
    if not file.filename:
        return _json_response(code=400, msg='文件名为空')
    
    # 检查文件类型
    if not _allowed_file(file.filename):
        return _json_response(code=400, msg='不支持的文件格式')
    
    # 生成文件名
    ext = os.path.splitext(file.filename)[1].lower()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{g.current_user.Id}_{timestamp}{secure_filename(file.filename)}"
    
    # 保存路径
    upload_dir = os.path.join(current_app.static_folder, 'Upload_Files')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, new_filename)
    
    # 保存文件
    file.save(file_path)
    
    # 检查文件大小
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        return _json_response(code=400, msg='文件大小不能超过 50MB')
    
    # PDF 文件读取页数
    page_count = 0
    need_convert = ext not in {'.pdf', '.jpg', '.jpeg', '.png'}
    
    if ext == '.pdf':
        try:
            page_count = read_pdf_pages(file_path)
        except Exception as e:
            logger.warning('读取 PDF 页数失败: %s', e)
    
    return _json_response({
        'fileId': new_filename,
        'filePath': new_filename,
        'fileName': file.filename,
        'fileSize': file_size,
        'pageCount': page_count,
        'needConvert': need_convert
    })


@mp_api.route('/upload/convertStatus')
def convert_status():
    """查询文件转换状态。"""
    file_id = request.args.get('fileId', '').strip()
    if not file_id:
        return _json_response(code=400, msg='缺少文件 ID')
    
    # 检查转换后的 PDF 是否存在
    upload_dir = os.path.join(current_app.static_folder, 'Upload_Files')
    pdf_path = os.path.join(upload_dir, file_id.rsplit('.', 1)[0] + '.pdf')
    
    if os.path.exists(pdf_path):
        page_count = read_pdf_pages(pdf_path) if file_id.endswith('.pdf') else 1
        return _json_response({
            'status': 'success',
            'pageCount': page_count,
            'progress': 100
        })
    
    # 检查原文件是否存在（转换中或失败）
    original_path = os.path.join(upload_dir, file_id)
    if not os.path.exists(original_path):
        return _json_response({'status': 'failed', 'pageCount': 0, 'progress': 0})
    
    # 转换中（实际项目中应该查询任务队列）
    return _json_response({
        'status': 'pending',
        'pageCount': 0,
        'progress': 50
    })


# ============ 订单模块 ============

@mp_api.route('/orders')
@_require_auth
def order_list():
    """获取订单列表。
    
    参数：
        status: 订单状态筛选（可选）
        page: 页码（默认 1）
        pageSize: 每页数量（默认 20）
    """
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    
    query = Order.query.filter_by(User_Id=g.current_user.Id)
    
    # 状态筛选
    if status:
        try:
            status_int = int(status)
            query = query.filter_by(Print_Status=status_int)
        except ValueError:
            pass
    
    # 排序分页
    query = query.order_by(Order.Id.desc())
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)
    
    orders = []
    for o in pagination.items:
        orders.append({
            'tradeNumber': o.Trade_Number,
            'fileName': o.File_Name or '',
            'printPlace': o.Print_Place,
            'printPlaceName': o.Print_Place,  # TODO: 关联 PrintPlace 表获取名称
            'color': o.Print_Colour,
            'colorText': '黑白' if o.Print_Colour == 'CMYGray' else '彩色',
            'printWay': o.Print_way,
            'printWayText': {'one-sided': '单面', 'two-sided-long-edge': '双面长边', 'two-sided-short-edge': '双面短边'}.get(o.Print_way, o.Print_way),
            'copies': o.Print_Copies or 1,
            'pages': o.Print_pages or 0,
            'amount': float(o.Print_Money or 0),
            'status': o.Print_Status,
            'createdAt': o.Born_Date.strftime('%Y-%m-%d %H:%M') if o.Born_Date else ''
        })
    
    return _json_response({
        'list': orders,
        'total': pagination.total,
        'page': page,
        'pageSize': page_size,
        'hasMore': pagination.has_next
    })


@mp_api.route('/orders/<trade_number>')
@_require_auth
def order_detail(trade_number):
    """获取订单详情。"""
    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return _json_response(code=404, msg='订单不存在')
    
    # 权限检查
    if order.User_Id != g.current_user.Id and g.current_user.Role != 'admin':
        return _json_response(code=403, msg='无权查看此订单')
    
    return _json_response({
        'tradeNumber': order.Trade_Number,
        'fileName': order.File_Name or '',
        'filePreviewUrl': f'/static/Upload_Files/{order.File_Dir}' if order.File_Dir else '',
        'printPlace': order.Print_Place,
        'printPlaceName': order.Print_Place,
        'color': order.Print_Colour,
        'colorText': '黑白' if order.Print_Colour == 'CMYGray' else '彩色',
        'printWay': order.Print_way,
        'printWayText': {'one-sided': '单面', 'two-sided-long-edge': '双面长边', 'two-sided-short-edge': '双面短边'}.get(order.Print_way, order.Print_way),
        'direction': order.Print_Direction,
        'directionText': '竖版' if order.Print_Direction == '3' else '横版',
        'paperSize': order.Print_size,
        'copies': order.Print_Copies or 1,
        'pages': order.Print_pages or 0,
        'amount': float(order.Print_Money or 0),
        'status': order.Print_Status,
        'statusText': {-2: '已取消', -1: '打印失败', 0: '待支付', 1: '已支付', 2: '打印中', 3: '已完成'}.get(order.Print_Status, '未知'),
        'createdAt': order.Born_Date.strftime('%Y-%m-%d %H:%M:%S') if order.Born_Date else '',
        'paidAt': '',  # TODO: 从 OrderLog 获取
        'completedAt': ''
    })


@mp_api.route('/orders', methods=['POST'])
@_require_auth
def create_order():
    """创建订单。
    
    请求体：
        fileId: 文件 ID
        fileName: 文件名
        printPlace: 打印点 Key
        copies: 份数
        paperSize: 纸张大小
        direction: 打印方向
        printWay: 打印方式
        color: 颜色
        pages: 页数
    """
    data = request.get_json(force=True, silent=True) or {}
    
    # 参数校验
    file_id = data.get('fileId', '').strip()
    file_name = data.get('fileName', '').strip()
    print_place = data.get('printPlace', '').strip()
    copies = int(data.get('copies', 1) or 1)
    paper_size = data.get('paperSize', 'A4').strip()
    direction = data.get('direction', '3').strip()
    print_way = data.get('printWay', 'one-sided').strip()
    color = data.get('color', 'CMYGray').strip()
    pages = int(data.get('pages', 0) or 0)
    
    if not file_id:
        return _json_response(code=400, msg='请先上传文件')
    if pages <= 0:
        return _json_response(code=400, msg='页数无效')
    
    # 计算价格
    unit_price = _unit_price(color, print_way)
    total_amount = round(unit_price * pages * copies, 2)
    
    # 创建订单
    order = Order()
    order.User_Id = g.current_user.Id
    order.File_Dir = file_id
    order.File_Name = file_name
    order.Print_Place = print_place
    order.Print_Copies = copies
    order.Print_pages = pages
    order.Print_Direction = direction
    order.Print_Colour = color
    order.Print_size = paper_size
    order.Print_way = print_way
    order.Print_Money = total_amount
    order.Time_Way = 1  # 直接打印
    order.Trade_Number = next_trade_number()
    
    try:
        trade_number = save_order_atomic(order)
        logger.info('小程序订单创建成功: %s, 金额: %.2f', trade_number, total_amount)
        
        return _json_response({
            'tradeNumber': trade_number,
            'amount': str(total_amount)
        })
    except Exception as e:
        logger.error('创建订单失败: %s', e, exc_info=True)
        return _json_response(code=500, msg='订单创建失败，请重试')


@mp_api.route('/orders/batch', methods=['POST'])
@_require_auth
def create_batch_orders():
    """批量创建订单。
    
    请求体：
        orders: 订单列表 [{fileId, fileName, printPlace, copies, paperSize, direction, printWay, color, pages}]
    """
    data = request.get_json(force=True, silent=True) or {}
    orders_data = data.get('orders', [])
    
    if not orders_data or not isinstance(orders_data, list):
        return _json_response(code=400, msg='请提供订单列表')
    
    if len(orders_data) > 20:
        return _json_response(code=400, msg='单次最多提交20个文件')
    
    created_orders = []
    total_amount = 0.0
    
    try:
        for item in orders_data:
            # 参数校验
            file_id = item.get('fileId', '').strip()
            file_name = item.get('fileName', '').strip()
            print_place = item.get('printPlace', '').strip()
            copies = int(item.get('copies', 1) or 1)
            paper_size = item.get('paperSize', 'A4').strip()
            direction = item.get('direction', '3').strip()
            print_way = item.get('printWay', 'one-sided').strip()
            color = item.get('color', 'CMYGray').strip()
            pages = int(item.get('pages', 0) or 0)
            
            if not file_id or pages <= 0:
                continue
            
            # 计算价格
            unit_price = _unit_price(color, print_way)
            order_amount = round(unit_price * pages * copies, 2)
            total_amount += order_amount
            
            # 创建订单
            order = Order()
            order.User_Id = g.current_user.Id
            order.File_Dir = file_id
            order.File_Name = file_name
            order.Print_Place = print_place
            order.Print_Copies = copies
            order.Print_pages = pages
            order.Print_Direction = direction
            order.Print_Colour = color
            order.Print_size = paper_size
            order.Print_way = print_way
            order.Print_Money = order_amount
            order.Time_Way = 1
            order.Trade_Number = next_trade_number()
            
            db.session.add(order)
            db.session.flush()  # 获取 ID
            
            created_orders.append(order.Trade_Number)
        
        db.session.commit()
        
        logger.info('批量订单创建成功: %d 个订单, 总金额: %.2f', len(created_orders), total_amount)
        
        return _json_response({
            'tradeNumbers': created_orders,
            'totalAmount': str(round(total_amount, 2)),
            'count': len(created_orders)
        })
    except Exception as e:
        db.session.rollback()
        logger.error('批量创建订单失败: %s', e, exc_info=True)
        return _json_response(code=500, msg='订单创建失败，请重试')


@mp_api.route('/orders/<trade_number>/cancel', methods=['POST'])
@_require_auth
def cancel_order(trade_number):
    """取消订单。"""
    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return _json_response(code=404, msg='订单不存在')
    
    # 权限检查
    if order.User_Id != g.current_user.Id and g.current_user.Role != 'admin':
        return _json_response(code=403, msg='无权操作此订单')
    
    # 状态检查
    if order.Print_Status != 0:
        return _json_response(code=400, msg='只能取消待支付的订单')
    
    order.Print_Status = -2  # 已取消
    db.session.commit()
    
    logger.info('订单已取消: %s', trade_number)
    return _json_response()


@mp_api.route('/orders/<trade_number>/reprint', methods=['POST'])
@_require_auth
def reprint_order(trade_number):
    """再次打印（基于旧订单创建新订单）。"""
    old_order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not old_order:
        return _json_response(code=404, msg='订单不存在')
    
    # 权限检查
    if old_order.User_Id != g.current_user.Id and g.current_user.Role != 'admin':
        return _json_response(code=403, msg='无权操作此订单')
    
    # 创建新订单
    new_order = Order()
    new_order.User_Id = g.current_user.Id
    new_order.File_Dir = old_order.File_Dir
    new_order.File_Name = old_order.File_Name
    new_order.Print_Place = old_order.Print_Place
    new_order.Print_Copies = old_order.Print_Copies
    new_order.Print_pages = old_order.Print_pages
    new_order.Print_Direction = old_order.Print_Direction
    new_order.Print_Colour = old_order.Print_Colour
    new_order.Print_size = old_order.Print_size
    new_order.Print_way = old_order.Print_way
    new_order.Print_Money = old_order.Print_Money
    new_order.Time_Way = 1
    new_order.Trade_Number = next_trade_number()
    
    try:
        trade_number = save_order_atomic(new_order)
        logger.info('再次打印订单创建成功: %s', trade_number)
        
        return _json_response({
            'tradeNumber': trade_number,
            'amount': str(new_order.Print_Money)
        })
    except Exception as e:
        logger.error('再次打印创建订单失败: %s', e, exc_info=True)
        return _json_response(code=500, msg='操作失败，请重试')


@mp_api.route('/orders/<trade_number>/status')
@_require_auth
def order_status(trade_number):
    """查询订单状态（用于支付轮询）。"""
    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return _json_response(code=404, msg='订单不存在')
    
    return _json_response({
        'status': order.Print_Status,
        'paid': order.Print_Status >= 1
    })


@mp_api.route('/orders/idcard', methods=['POST'])
@_require_auth
def create_idcard_order():
    """创建身份证打印订单。
    
    请求体：
        frontFileId: 正面文件 ID
        backFileId: 反面文件 ID
        copies: 份数
    """
    data = request.get_json(force=True, silent=True) or {}
    
    front_file_id = data.get('frontFileId', '').strip()
    back_file_id = data.get('backFileId', '').strip()
    copies = int(data.get('copies', 1) or 1)
    
    if not front_file_id or not back_file_id:
        return _json_response(code=400, msg='请上传身份证正反面')
    
    # 身份证打印固定价格：1元/份
    total_amount = copies * 1.0
    
    # 创建订单
    order = Order()
    order.User_Id = g.current_user.Id
    order.File_Dir = f"{front_file_id}|{back_file_id}"  # 用 | 分隔两个文件
    order.File_Name = '身份证打印'
    order.Print_Place = 'default'
    order.Print_Copies = copies
    order.Print_pages = 1  # 身份证固定 1 页
    order.Print_Direction = '3'
    order.Print_Colour = 'CMYGray'
    order.Print_size = 'A4'
    order.Print_way = 'one-sided'
    order.Print_Money = total_amount
    order.Time_Way = 1
    order.Trade_Number = next_trade_number()
    
    try:
        trade_number = save_order_atomic(order)
        logger.info('身份证打印订单创建成功: %s', trade_number)
        
        return _json_response({
            'tradeNumber': trade_number,
            'amount': str(total_amount)
        })
    except Exception as e:
        logger.error('创建身份证打印订单失败: %s', e, exc_info=True)
        return _json_response(code=500, msg='订单创建失败，请重试')


# ============ 支付模块 ============

@mp_api.route('/pay/wechat', methods=['POST'])
@_require_auth
def wechat_pay():
    """获取微信支付参数。
    
    请求体：
        tradeNumber: 订单号
    """
    data = request.get_json(force=True, silent=True) or {}
    trade_number = data.get('tradeNumber', '').strip()
    
    if not trade_number:
        return _json_response(code=400, msg='缺少订单号')
    
    order = Order.query.filter_by(Trade_Number=trade_number).first()
    if not order:
        return _json_response(code=404, msg='订单不存在')
    
    # 权限检查
    if order.User_Id != g.current_user.Id:
        return _json_response(code=403, msg='无权操作此订单')
    
    # 状态检查
    if order.Print_Status != 0:
        return _json_response(code=400, msg='订单状态异常')
    
    amount = float(order.Print_Money or 0)
    if amount <= 0:
        return _json_response(code=400, msg='订单金额异常')
    
    # TODO: 调用微信支付统一下单接口
    # 这里返回模拟数据，实际需要对接微信支付
    import time
    timestamp = str(int(time.time()))
    nonce_str = hashlib.md5(f"{trade_number}{timestamp}".encode()).hexdigest()
    
    return _json_response({
        'timeStamp': timestamp,
        'nonceStr': nonce_str,
        'package': f'prepay_id=wx{trade_number}',
        'signType': 'MD5',
        'paySign': hashlib.md5(f"{MP_APPID}{timestamp}{nonce_str}".encode()).hexdigest().upper()
    })


# ============ 打印点模块 ============

@mp_api.route('/printPlaces')
def print_places():
    """获取打印点列表。"""
    places = PrintPlace.query.filter_by(Is_Active=True).order_by(PrintPlace.Sort).all()
    
    result = []
    for p in places:
        result.append({
            'key': p.Key,
            'name': p.Name,
            'address': p.Address or '',
            'phone': '',  # PrintPlace 表暂无电话字段，可后续扩展
            'businessHours': '',
            'latitude': None,
            'longitude': None,
            'status': 'open'  # 简化处理，实际应根据营业时间判断
        })
    
    return _json_response({'list': result})


# ============ 打印参数模块 ============

@mp_api.route('/printOptions')
def print_options():
    """获取打印参数选项（用于前端下拉框）。"""
    return _json_response({
        'paperSizes': ['A4'],
        'colors': [
            {'value': 'CMYGray', 'label': '黑白'},
            {'value': 'RGB', 'label': '彩色'}
        ],
        'printWays': [
            {'value': 'one-sided', 'label': '单面'},
            {'value': 'two-sided-long-edge', 'label': '双面长边'},
            {'value': 'two-sided-short-edge', 'label': '双面短边'}
        ],
        'directions': [
            {'value': '3', 'label': '竖版'},
            {'value': '4', 'label': '横版'}
        ],
        'prices': {
            'CMYGray': {'one-sided': 0.30, 'two-sided': 0.50},
            'RGB': {'one-sided': 1.00, 'two-sided': 1.70}
        }
    })
