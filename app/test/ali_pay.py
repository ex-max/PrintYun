from flask import Flask, Blueprint, render_template, request, flash, session, redirect, url_for
import json, os, time, random
from app.models import User, Order, db

cloud_pay = Blueprint('cloud_pay', __name__)

from alipay import AliPay

basepath = os.path.abspath(os.path.dirname(__file__))  # 当前文件所在目录
parentdir = os.path.dirname(basepath)  # 父级目录

private = os.path.join(parentdir, "certs", "app_private_key.pem")  # 私钥路径
public = os.path.join(parentdir, "certs", "app_public_key.pem")  # 公钥路径
alipay_public_test = os.path.join(parentdir, 'certs', 'zhifubaogongyao.txt')

# 沙箱 APPID 与本地 certs/ 下的密钥对对应；可用环境变量覆盖
_ALIPAY_APPID = os.environ.get('ALIPAY_APPID') or '9021000158658446'
_ALIPAY_DEBUG = os.environ.get('ALIPAY_DEBUG', 'true').lower() != 'false'
_ALIPAY_GATEWAY = os.environ.get(
    'ALIPAY_GATEWAY',
    'https://openapi-sandbox.dl.alipaydev.com/gateway.do' if _ALIPAY_DEBUG
    else 'https://openapi.alipay.com/gateway.do'
)
# 公网回跳根地址（cpolar/ngrok 场景）；留空则用请求自身 host
_PUBLIC_BASE = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')

_alipays = None


def _read_key(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        print(f'[ali_pay] 读取密钥失败 {path}: {e}')
        return None


def get_alipay():
    """懒加载 AliPay 客户端，密钥缺失时不阻断整个 app 启动。"""
    global _alipays
    if _alipays is not None:
        return _alipays
    app_private_key_string = _read_key(private)
    alipay_public_test_string = _read_key(alipay_public_test)
    if not app_private_key_string or not alipay_public_test_string:
        return None
    try:
        _alipays = AliPay(
            appid=_ALIPAY_APPID,
            app_notify_url=None,
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_test_string,
            debug=_ALIPAY_DEBUG,
        )
    except Exception as e:
        print(f'[ali_pay] 初始化 AliPay 失败: {e}')
        _alipays = None
    return _alipays


def _make_alipay_trade_no(db_trade_number: str) -> str:
    """生成每次支付唯一的 out_trade_no，避免复用同一订单号命中支付宝 CONTEXT_INCONSISTENT。
    格式：<DB Trade_Number>#<毫秒时间戳><随机 3 位>；回调时用 _to_db_trade_number 还原。
    """
    suffix = f"{int(time.time() * 1000)}{random.randint(100, 999)}"
    return f"{db_trade_number}#{suffix}"


def _to_db_trade_number(alipay_out_trade_no: str) -> str:
    """回调里拿到的 out_trade_no 可能是我们拼的 '#suffix' 形式，也可能是旧的原样。"""
    if not alipay_out_trade_no:
        return ''
    return alipay_out_trade_no.split('#', 1)[0]


def _callback_base():
    # 默认用 request.host_url（ProxyFix 已识别 X-Forwarded-Proto/Host，
    # cpolar/ngrok 公网 https 域名会被正确解析）——这样 cpolar 换域名
    # 也不需要改 .env。PUBLIC_BASE_URL 仅作为"无请求上下文"或想强制覆盖
    # 时的兜底。
    try:
        host = request.host_url.rstrip('/')
        if host:
            return host
    except RuntimeError:
        pass
    return _PUBLIC_BASE


@cloud_pay.route('/alipay1', methods=['GET', 'POST'])
def ali_mobilepay():
    alipays = get_alipay()
    if alipays is None:
        return '支付服务未配置', 503
    tradeid = request.form.get("tradeid")
    dati = Order.query.filter(Order.Trade_Number == tradeid).first()
    if not dati:
        return '订单不存在', 404
    cost = float(dati.Print_Money or 0)

    base = _callback_base()
    order_string = alipays.api_alipay_trade_wap_pay(
        out_trade_no=_make_alipay_trade_no(tradeid),
        total_amount=cost,
        subject='云打印订单',
        return_url=base + "/cloud_pay/alipayresult1",
        notify_url=base + '/cloud_pay/native',
    )
    return redirect(_ALIPAY_GATEWAY + "?" + order_string)


@cloud_pay.route('/alipay2', methods=['GET', 'POST'])
def ali_computerpay():
    alipays = get_alipay()
    if alipays is None:
        return '支付服务未配置', 503
    tradeid = request.form.get("tradeid")
    dati = Order.query.filter(Order.Trade_Number == tradeid).first()
    if not dati:
        return '订单不存在', 404
    cost = float(dati.Print_Money or 0)

    base = _callback_base()
    order_string = alipays.api_alipay_trade_page_pay(
        out_trade_no=_make_alipay_trade_no(tradeid),
        total_amount=cost,
        subject='云打印订单',
        return_url=base + "/cloud_pay/alipayresult1",
        notify_url=base + '/cloud_pay/native',
    )
    return redirect(_ALIPAY_GATEWAY + "?" + order_string)


# 支付宝同步回调接口（用户浏览器付款完成后跳回）
@cloud_pay.route('/alipayresult1', methods=['GET', 'POST'])
def alipayresult1():
    alipays = get_alipay()
    if alipays is None:
        return '支付服务未配置', 503

    data = request.args.to_dict() if request.method == 'GET' else request.form.to_dict()
    signature = data.pop("sign", None)

    verified = False
    if signature:
        try:
            verified = alipays.verify(data, signature)
        except Exception as e:
            print(f'[alipayresult1] 验签异常: {e}')

    alipay_trade_no = data.get("out_trade_no", "")
    db_trade_no = _to_db_trade_number(alipay_trade_no)
    if verified and db_trade_no:
        order = Order.query.filter(Order.Trade_Number == db_trade_no).first()
        if order and order.Print_Status == 0:
            # 支付成功后直接进入打印队列（2），店员端只管“完成/失败”
            old_status = order.Print_Status
            order.Print_Status = 2
            db.session.add(OrderLog(
                Order_Id=order.Id,
                Operator_Id=None,
                Action='paid',
                From_Status=old_status,
                To_Status=2,
                Note='支付宝同步回跳确认支付成功',
            ))
            db.session.commit()

    return render_template('use_templates/pay_success.html',
                           ok=verified, trade_id=db_trade_no)


# 支付宝异步通知接口
@cloud_pay.route('/native', methods=['POST'])
def alipayresult2():
    alipays = get_alipay()
    if alipays is None:
        return '支付服务未配置', 503
    data = request.form.to_dict()
    signature = data.pop("sign", None)
    if not signature:
        return "fail"

    try:
        success = alipays.verify(data, signature)
    except Exception as e:
        print(f'[alipayresult2] 验签异常: {e}')
        return "fail"

    if success and data.get("trade_status") in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        db_trade_no = _to_db_trade_number(data.get("out_trade_no", ""))
        result_order = Order.query.filter(Order.Trade_Number == db_trade_no).first()
        if result_order and result_order.Print_Status == 0:
            # 支付完成后直接进入打印队列（2）
            old_status = result_order.Print_Status
            result_order.Print_Status = 2
            db.session.add(result_order)
            db.session.add(OrderLog(
                Order_Id=result_order.Id,
                Operator_Id=None,
                Action='paid',
                From_Status=old_status,
                To_Status=2,
                Note='支付宝异步通知确认支付成功',
            ))
            db.session.commit()
        return "success"
    return "fail"
