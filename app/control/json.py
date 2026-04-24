from flask import Blueprint, request, redirect, url_for, jsonify
import datetime, json, requests, qrcode, time, os, logging
from app.utils import query_status, sign
from flask_login import login_required, current_user
from app.models import User, Order, OrderLog, db
from PIL import Image

jsons = Blueprint(
    'jsons',
    __name__
)

logger = logging.getLogger(__name__)

_XORPAY_SECRET = os.environ.get('XORPAY_SECRET', '')

# 支付的 信息
@jsons.route('/js_pay', methods=['POST'])
@login_required
def js_pay():
    if request.method == 'POST':
        data = request.form
        trideid = data['tradeid']
        query = Order.query.filter(Order.Trade_Number == trideid).first()

        pay_data = {
            'name': str(query.File_Name),
            'pay_type': data['pay_type'],
            'price': str(query.Print_Money),
            'order_id': str(data['order_id']),
            'expire': 3600,
            'order_uid': str(data['order_uid']),
            'notify_url': 'http://xxx.com/jsons/native',   #请求回调，自己修改
        }

        if not _XORPAY_SECRET:
            return jsonify({'mas': 'XORPAY_SECRET 未配置'}), 503

        # 将 参数 转为散列值
        pay_data['sign'] = sign(
            pay_data['name'],
            pay_data['pay_type'],
            pay_data['price'],
            pay_data['order_id'],
            pay_data['notify_url'],
            _XORPAY_SECRET,
        )
        # 访问网站并传递参数
        logger.info('请求数据: %s', pay_data)
        resp = requests.post('https://xorpay.com/api/pay/xxxx', data=pay_data)  #微信支付使用xorpay
        if resp.status_code == 200:
            json_resp = json.loads(resp.text)
            logger.info('得到的数据：%s', json_resp)
            logger.debug('二维码链接：%s', json_resp['info']['qr'])
            img = qrcode.make(json_resp['info']['qr'])
            Image.Image.save(img, 'app/static/pay_qrcode/' + data['pay_type']+data['tradeid'] + '.jpg')
            return jsonify({'url': data['pay_type']+data['tradeid'], 'aoid': json_resp['aoid']})
        else:
            return redirect(url_for('printer.select'))
    else:
        return jsonify({'mas': 'error-pay'})


@jsons.route('/native', methods=['GET', 'POST'])
def native_url():
    if request.method == "POST":
        requ = dict(request.form)
        aoid = requ['aoid']
        queryStatus = query_status(aoid)
        if queryStatus['status'] in ['payed', 'success']:
            order = Order.query.filter(Order.Trade_Number == requ['order_id'][6:]).with_for_update().first()
            if not order or order.Print_Status != 0:
                return 'success'  # 幂等：已处理过直接返回
            # 支付成功 → 状态 1（已支付待打印），由 printer_daemon 领取后改为 2
            old_status = order.Print_Status
            order.Print_Status = 1
            db.session.add(order)
            db.session.add(OrderLog(
                Order_Id=order.Id,
                Operator_Id=None,
                Action='paid',
                From_Status=old_status,
                To_Status=1,
                Note='XORPay 回调确认支付成功',
            ))
            db.session.commit()
            # 通知 daemon 立即打印
            try:
                from worker import conn as redis_conn
                redis_conn.lpush('print_queue', str(order.Id))
            except Exception:
                pass
            return 'success'
        else:
            pass


@jsons.route('/delete', methods=['GET', 'POST'])
@login_required
def delete_data():
    if request.method != "POST":
        return jsonify({'status': 'method-not-allowed'}), 405

    quer = request.form
    g_id = quer['trade_id'][6:]
    one = Order.query.filter(Order.Trade_Number == g_id).first()
    if not one:
        return jsonify({'status': 'not-found'}), 404
    # 仅允许管理员 或 订单所属用户 删除
    if current_user.Role != 'admin' and one.User_Id != current_user.Id:
        return jsonify({'status': 'forbidden'}), 403

    new_filename = quer.get('new_filename', '')
    filename = quer.get('filename', '')
    # 归一化路径，防止传入 ../ 逃逸
    upload_dir = os.path.abspath(os.path.join('app', 'static', 'Upload_Files'))
    before_dir = os.path.join(upload_dir, 'BeforeSwitchFile')

    def _safe_remove(base, name):
        if not name:
            return
        target = os.path.abspath(os.path.join(base, name))
        if not target.startswith(base + os.sep):
            return
        try:
            os.remove(target)
        except OSError:
            pass

    _safe_remove(upload_dir, new_filename)
    _safe_remove(before_dir, filename)

    db.session.delete(one)
    db.session.commit()
    return jsonify({'status': 'success'})


@jsons.route('/query_status', methods=['POST'])
def query_statu():
    if request.method == 'POST':
        quer = request.form
        aoid = quer['aoid']
        resp = requests.get('https://xorpay.com/api/query/' + aoid)
        msg = json.loads(resp.text)
        if msg['status'] == 'success':
            return jsonify({'quey_status': 'success'})
        else:
            return jsonify({'quey_status': 'no'})
    else:
        pass


@jsons.route('/date_times', methods=['GET', 'POST'])
@login_required
def querys():
    form = request.form
    tel_number = form['tel_num']
    date_time = form['date_time']
    page = int(form['page'])
    per_page = int(form['limit'])
    if current_user.Role == 'admin':
        if tel_number == '' and date_time == '':
            Order_date_tel = []
            dati = Order.query
            num = dati.count()
            pagination = dati.paginate(page=page,per_page=per_page)
            item = pagination.items
            for i in item:
                Order_date_tel.append(i.to_json())
            return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}

        elif tel_number != '' and date_time == '':
            Order_date_tel = []
            user = User.query.filter(User.Tel_Number == tel_number).first()
            if user:
                try:
                    dati = Order.query.filter(Order.User_Id == user.Id)
                    pagination = dati.paginate(page=int(page), per_page=int(per_page))
                    num = dati.count()
                    item = pagination.items
                    for i in item:
                        Order_date_tel.append(i.to_json())
                    return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}
                except AttributeError as e:
                    return {'code': 404, 'msg': '请检验请求接口的数据', 'error': e}

                except TypeError as e:
                    return {'code': 404, 'msg': '无此信息', 'error': e}

        elif tel_number == '' and date_time != '':
                try:
                    Order_date_tel = []
                    date_time_date = datetime.datetime.strptime(date_time, '%Y-%m-%d').date()
                    dati = Order.query.filter(Order.Born_Date_Day == date_time_date)
                    num = dati.count()
                    pagination = dati.paginate(page=int(page), per_page=int(per_page))
                    item = pagination.items
                    for i in item:
                        Order_date_tel.append(i.to_json())
                    return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}
                except AttributeError as e:
                    return {'code': 404, 'msg': '请检验请求接口的数据', 'error': e}

                except TypeError as e:
                    return {'code': 404, 'msg': '无此信息', 'error': e}

        # 如果数据库中没有该数据将会报错
        else:
            try:
                Order_date_tel = []
                date_time_date = datetime.datetime.strptime(date_time, '%Y-%m-%d').date()
                user = User.query.filter(User.Tel_Number == tel_number).first()
                if user:
                    dati = Order.query.filter(Order.User_Id == user.Id , Order.Born_Date_Day == date_time_date)
                    num = dati.count()
                    pagination = dati.paginate(page=int(page), per_page=int(per_page))
                    item = pagination.items
                    for i in item:
                        Order_date_tel.append(i.to_json())
                    return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}
                else:
                    return {'code': 404, 'msg': '无此信息'}
            except AttributeError as e:
                return {'code': 404, 'msg': '请检验请求接口的数据', 'error': e}

            except TypeError as e:
                return {'code': 404, 'msg': '无此信息', 'error': e}
    else:
        if date_time == '':
            Order_date_tel = []
            dati = Order.query.filter(Order.User_Id == current_user.Id)
            num = dati.count()
            pagination = dati.paginate(page=page, per_page=per_page)
            item = pagination.items
            for i in  item:
                Order_date_tel.append(i.to_json())
            return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}
        else:
            try:
                Order_date_tel = []
                date_time_date = datetime.datetime.strptime(date_time, '%Y-%m-%d').date()
                dati = Order.query.filter(Order.User_Id == current_user.Id , Order.Born_Date_Day == date_time_date)
                num = dati.count()
                pagination = dati.paginate(page=int(page), per_page=int(per_page))
                item = pagination.items
                for i in item:
                    Order_date_tel.append(i.to_json())
                return {'code': 0, 'msg': '', 'count': num , 'data': Order_date_tel}
            except AttributeError as e:
                return {'code': 404, 'msg': '请检验请求接口的数据', 'error': e}

            except TypeError as e:
                return {'code': 404, 'msg': '无此信息', 'error': e}