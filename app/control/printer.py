from flask import Blueprint, request, render_template, flash, session, jsonify, url_for
import os, datetime, time
from werkzeug.utils import secure_filename
from app.utils import read_pdf_pages, next_trade_number, save_order_atomic
from flask_login import login_required, current_user
from app.models import User, Order, db
from app.forms import Print
from worker import que, switch_topdf, conn
# from app.utils import switch_topdf

printer = Blueprint('printer', __name__)


def _unit_price(print_color, print_way):
    """计算单价（元/页）：按 颜色 × 单/双面 四档定价"""
    is_duplex = print_way != 'one-sided'
    if print_color == 'CMYGray':
        return 0.5 if is_duplex else 0.3
    else:
        return 1.7 if is_duplex else 1.0


def _is_mobile():
    agent = request.environ.get('HTTP_USER_AGENT', '')
    return 1 if ('AppleWebKit' in agent and 'Mobile' in agent) else ''


@printer.route('/print')
@login_required
def print1():
    return 'sss'


@printer.route('/select', methods=['GET', 'POST'])
@login_required
def select():
    pageCount = 0
    cost = 0

    datetimes = datetime.datetime.now()
    now = str(datetimes.year) + "-" + str(datetimes.month) + "-" + str(datetimes.day) + "_" + str(
        datetimes.hour) + "-" + str(datetimes.minute) + "-" + str(datetimes.second)
    form = Print()
    # 权限分流：admin 看所有订单历史；普通用户只能看自己的
    if current_user.Role == 'admin':
        datas = Order.query.order_by(Order.Id.desc()).limit(11).all()
        user_datas = []
    else:
        datas = []
        user_datas = (
            Order.query
            .filter(Order.User_Id == current_user.Id)
            .order_by(Order.Id.desc())
            .limit(8)
            .all()
        )
    if form.validate_on_submit():
        # ---- 文件类型白名单校验 ----
        _allowed_ext = {'.pdf', '.jpg', '.jpeg', '.png',
                        '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
        _fname = form.print_file.data.filename if form.print_file.data else ''
        _ext = os.path.splitext(_fname)[1].lower() if _fname else ''
        if _ext not in _allowed_ext:
            flash(f'不支持的文件格式（{_ext}），请上传 PDF/图片/Office 文档')
            return render_template('use_templates/layui_orderForGoods.html', now=now, form=form,
                                   datas=datas, user_datas=user_datas, error='1')

        if form.print_demand.data == '0':
            print_file = form.print_file.data
            print_place = form.print_place.data
            print_copies = form.print_copies.data
            print_type = form.print_type.data
            print_color = form.print_color.data
            print_size = form.print_size.data
            print_way = form.print_way.data
            print_time = form.print_time.data
            time_way = form.print_demand.data

            filename = print_file.filename
            index_point = filename.rindex('.')
            new_filename = str(current_user.Tel_Number) + '_' + now + filename[index_point:]
            basepath = os.path.abspath(os.path.dirname(__file__))  # 当前文件所在目录
            parentdir = os.path.dirname(basepath)  # 父级目录
            upload_path = os.path.join(parentdir, 'static/Upload_Files/BeforeSwitchFile/', new_filename)
            print_file.save(upload_path)

            user = User.query.filter(User.Tel_Number == current_user.Tel_Number).first()

            order_forsql = Order()
            order_forsql.Time_Way = time_way
            order_forsql.User_Id = user.Id
            order_forsql.File_Dir = new_filename
            order_forsql.File_Name = filename
            order_forsql.Print_Place = print_place
            order_forsql.Print_Copies = print_copies
            order_forsql.Print_Direction = print_type
            order_forsql.Print_Colour = print_color
            order_forsql.Print_size = print_size
            order_forsql.Print_way = print_way
            order_forsql.Print_Date = print_time
            order_forsql.Trade_Number = next_trade_number()

            macs = save_order_atomic(order_forsql)

            data = {
                "print_place": print_place,
                "tradeid": macs,
                "printfile": filename,
                "now": now,
                "print_copies": print_copies,
                "user_tel": user.Tel_Number
            }
            identifi = _is_mobile()
            return render_template('use_templates/layui_pay_demand.html', form=form, data=data, identifi=identifi)
        else:
            print_file = form.print_file.data
            print_place = form.print_place.data
            print_copies = form.print_copies.data
            print_type = form.print_type.data
            print_color = form.print_color.data
            print_size = form.print_size.data
            print_way = form.print_way.data
            print_time = form.print_time.data
            time_way = form.print_demand.data
            unit_p = _unit_price(print_color, print_way)
            print_cost = unit_p * int(print_copies)

            filename = print_file.filename
            index_point = filename.rindex('.')
            new_filename = str(current_user.Tel_Number) + '_' + now + filename[index_point:]
            basepath = os.path.abspath(os.path.dirname(__file__))  # 当前文件所在目录
            parentdir = os.path.dirname(basepath)  # 父级目录

            # 不需要转换的文件，pdf、jpg、png、jpeg
            if filename[index_point:].lower() in [".pdf", ".jpg", ".png", ".jpeg"]:
                upload_path = os.path.join(parentdir, 'static/Upload_Files', new_filename)
                print_file.save(upload_path)

                if filename[index_point:].lower() != '.pdf':
                    pageCount = 1
                    cost = pageCount * print_cost
                else:
                    pageCount = read_pdf_pages(upload_path)
                    cost = pageCount * print_cost

                # PDF/图片：直接创建订单跳支付页
                user = User.query.filter(User.Tel_Number == current_user.Tel_Number).first()
                order_forsql = Order()
                order_forsql.User_Id = user.Id
                order_forsql.File_Dir = new_filename
                order_forsql.File_Name = filename
                order_forsql.Print_Place = print_place
                order_forsql.Print_pages = pageCount
                order_forsql.Print_Copies = print_copies
                order_forsql.Print_Direction = print_type
                order_forsql.Print_Colour = print_color
                order_forsql.Print_size = print_size
                order_forsql.Print_way = print_way
                order_forsql.Print_Money = cost
                order_forsql.Print_Date = print_time
                order_forsql.Trade_Number = next_trade_number()
                order_forsql.Time_Way = time_way

                macs = save_order_atomic(order_forsql)

                data = {
                    "printfile": filename,
                    "new_filename": new_filename,
                    "print_place": print_place,
                    "print_copies": print_copies,
                    "pageCount": pageCount,
                    "tradeid": macs,
                    "user_tel": user.Tel_Number,
                    "cost": round(cost, 2),
                    "now": now
                }
                identifi = _is_mobile()
                return render_template('use_templates/layui_pay_form.html', form=form, data=data, identifi=identifi)

            # ========== 需要转换格式的文件：异步处理，立即返回 ==========
            else:
                upload_path = os.path.join(parentdir, 'static/Upload_Files/BeforeSwitchFile/', new_filename)
                print_file.save(upload_path)

                # 入队转换任务（RQ Worker 在后台执行 LibreOffice 转 PDF）
                que.enqueue(switch_topdf, upload_path, current_user.Id)

                # 把表单参数存入 session，转换完成后在 convert_status 里创建订单
                session['_convert'] = {
                    'original_filename': filename,
                    'new_filename': new_filename,
                    'print_place': print_place,
                    'print_copies': int(print_copies),
                    'print_type': print_type,
                    'print_color': print_color,
                    'print_size': print_size,
                    'print_way': print_way,
                    'print_time': str(print_time) if print_time else '',
                    'time_way': time_way,
                    'print_cost_per_copy': print_cost,
                    'now': now,
                    'started_at': time.time(),
                }

                # 立即返回转换等待页（不阻塞！）
                return render_template('use_templates/layui_converting.html',
                                       filename=filename)

    return render_template('use_templates/layui_orderForGoods.html', now=now, form=form, datas=datas,
                           user_datas=user_datas)


@printer.route('/convert_status')
@login_required
def convert_status():
    """前端轮询：检查 Office 文件是否转换完成，完成后创建订单并返回支付页数据。"""
    conv = session.get('_convert')
    if not conv:
        return jsonify({'status': 'error', 'msg': '没有正在进行的转换任务'})

    # 超时检查（60 秒）
    if time.time() - conv.get('started_at', 0) > 60:
        session.pop('_convert', None)
        return jsonify({'status': 'failed', 'msg': '文件转换超时，请重新上传'})

    # 检查转换后的 PDF 是否已生成
    new_filename = conv['new_filename']
    sz = new_filename.rindex('.')
    pdf_filename = new_filename[:sz] + '.pdf'
    failed_filename = new_filename[:sz] + '.failed'
    basepath = os.path.abspath(os.path.dirname(__file__))
    parentdir = os.path.dirname(basepath)
    pdf_path = os.path.join(parentdir, 'static/Upload_Files', secure_filename(pdf_filename))
    failed_path = os.path.join(parentdir, 'static/Upload_Files', secure_filename(failed_filename))

    # 先检查失败标记（worker 转换失败时写入）
    if os.path.exists(failed_path):
        session.pop('_convert', None)
        try:
            os.remove(failed_path)
        except Exception:
            pass
        return jsonify({'status': 'failed', 'msg': '文件转换失败，请重新上传 PDF 版本'})

    if not os.path.exists(pdf_path):
        return jsonify({'status': 'converting'})

    # PDF 已生成：读页数、算金额、建订单
    try:
        pageCount = read_pdf_pages(pdf_path)
    except Exception:
        session.pop('_convert', None)
        return jsonify({'status': 'failed', 'msg': '文件转换失败，请重新上传 PDF 版本'})

    cost = pageCount * conv['print_cost_per_copy']
    user = User.query.filter(User.Tel_Number == current_user.Tel_Number).first()

    order_forsql = Order()
    order_forsql.User_Id = user.Id
    order_forsql.File_Dir = pdf_filename
    order_forsql.File_Name = conv['original_filename']
    order_forsql.Print_Place = conv['print_place']
    order_forsql.Print_pages = pageCount
    order_forsql.Print_Copies = conv['print_copies']
    order_forsql.Print_Direction = conv['print_type']
    order_forsql.Print_Colour = conv['print_color']
    order_forsql.Print_size = conv['print_size']
    order_forsql.Print_way = conv['print_way']
    order_forsql.Print_Money = round(cost, 2)
    pt = conv['print_time']
    order_forsql.Print_Date = datetime.datetime.strptime(pt, '%Y-%m-%d').date() if pt else None
    order_forsql.Trade_Number = next_trade_number()
    order_forsql.Time_Way = conv['time_way']

    macs = save_order_atomic(order_forsql)

    # 清除 session 中的转换信息
    session.pop('_convert', None)

    return jsonify({
        'status': 'done',
        'tradeid': macs,
        'pageCount': pageCount,
        'cost': round(cost, 2),
        'printfile': conv['original_filename'],
        'new_filename': pdf_filename,
        'print_place': conv['print_place'],
        'print_copies': conv['print_copies'],
        'user_tel': user.Tel_Number,
        'now': conv['now'],
        'identifi': _is_mobile(),
    })


@printer.route('/pay_page')
@login_required
def pay_page():
    """转换完成后的支付页中转：接收 query 参数渲染支付页模板。"""
    data = {
        'tradeid': request.args.get('tradeid', ''),
        'printfile': request.args.get('printfile', ''),
        'new_filename': request.args.get('new_filename', ''),
        'print_place': request.args.get('print_place', ''),
        'print_copies': request.args.get('print_copies', ''),
        'pageCount': request.args.get('pageCount', ''),
        'cost': request.args.get('cost', ''),
        'user_tel': request.args.get('user_tel', ''),
        'now': request.args.get('now', ''),
    }
    identifi = _is_mobile()
    form = Print()
    return render_template('use_templates/layui_pay_form.html', form=form, data=data, identifi=identifi)


# ==================== 身份证照专属上传 ====================

def _compose_idcard_a4(front_path, back_path, output_pdf_path):
    """将身份证正反面照片拼版到 A4 纸上，输出 PDF。

    布局：A4 纸 (210×297mm)，正面在上半部分，反面在下半部分，
    每张身份证按标准尺寸 85.6×54mm 等比缩放后居中放置。
    """
    from PIL import Image

    # A4 尺寸 @300 DPI
    DPI = 300
    A4_W = int(210 / 25.4 * DPI)   # 2480px
    A4_H = int(297 / 25.4 * DPI)   # 3508px

    # 身份证标准尺寸 85.6 × 54mm → 打印时放大到约 1.5 倍更清晰
    CARD_W = int(85.6 * 1.5 / 25.4 * DPI)  # ~1516px
    CARD_H = int(54.0 * 1.5 / 25.4 * DPI)  # ~956px

    canvas = Image.new('RGB', (A4_W, A4_H), (255, 255, 255))

    for i, img_path in enumerate([front_path, back_path]):
        img = Image.open(img_path)
        img = img.convert('RGB')

        # 等比缩放到目标尺寸
        img.thumbnail((CARD_W, CARD_H), Image.LANCZOS)

        # 居中放置：正面在上半区域，反面在下半区域
        x = (A4_W - img.width) // 2
        if i == 0:
            y = A4_H // 4 - img.height // 2       # 上半部分居中
        else:
            y = A4_H * 3 // 4 - img.height // 2   # 下半部分居中

        canvas.paste(img, (x, y))

    # 加标注文字
    try:
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("msyh.ttc", 48)
        except Exception:
            font = ImageFont.load_default()
        draw.text((A4_W // 2 - 100, A4_H // 4 - CARD_H // 2 - 80),
                  "▼ 正面", fill=(100, 100, 100), font=font)
        draw.text((A4_W // 2 - 100, A4_H * 3 // 4 - CARD_H // 2 - 80),
                  "▼ 反面", fill=(100, 100, 100), font=font)
    except Exception:
        pass  # 字体加载失败不影响核心功能

    canvas.save(output_pdf_path, 'PDF', resolution=DPI)


@printer.route('/idcard', methods=['GET', 'POST'])
@login_required
def idcard_upload():
    """身份证照专属上传页：正反面两张图片 → 拼版 A4 → 直接支付。"""
    if request.method == 'GET':
        return render_template('use_templates/idcard_upload.html')

    # POST：处理上传
    front = request.files.get('front')
    back = request.files.get('back')

    if not front or not back:
        flash('请同时上传身份证正面和反面照片')
        return render_template('use_templates/idcard_upload.html')

    # 校验文件类型
    allowed = {'.jpg', '.jpeg', '.png'}
    for f, label in [(front, '正面'), (back, '反面')]:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in allowed:
            flash(f'{label}照片格式不支持（{ext}），请上传 JPG/PNG')
            return render_template('use_templates/idcard_upload.html')

    # 校验文件大小（单张 10MB）
    for f, label in [(front, '正面'), (back, '反面')]:
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > 10 * 1024 * 1024:
            flash(f'{label}照片超过 10MB 限制')
            return render_template('use_templates/idcard_upload.html')

    # 保存临时文件
    datetimes = datetime.datetime.now()
    ts = datetimes.strftime('%Y-%m-%d_%H-%M-%S')
    basepath = os.path.abspath(os.path.dirname(__file__))
    parentdir = os.path.dirname(basepath)
    upload_dir = os.path.join(parentdir, 'static', 'Upload_Files')

    tel = str(current_user.Tel_Number)
    front_name = f'{tel}_{ts}_idcard_front{os.path.splitext(front.filename)[1]}'
    back_name = f'{tel}_{ts}_idcard_back{os.path.splitext(back.filename)[1]}'
    front_path = os.path.join(upload_dir, 'BeforeSwitchFile', front_name)
    back_path = os.path.join(upload_dir, 'BeforeSwitchFile', back_name)
    front.save(front_path)
    back.save(back_path)

    # 拼版到 A4 生成 PDF
    pdf_name = f'{tel}_{ts}_idcard.pdf'
    pdf_path = os.path.join(upload_dir, pdf_name)
    try:
        _compose_idcard_a4(front_path, back_path, pdf_path)
    except Exception as e:
        flash(f'图片处理失败：{e}，请检查图片是否完整')
        return render_template('use_templates/idcard_upload.html')

    # 固定参数：彩色、单面、1 份、A4
    cost = 1.0  # 彩色单面 1.0 元/页 × 1 页
    copies = int(request.form.get('copies', '1') or '1')
    cost = cost * copies

    user = User.query.filter(User.Tel_Number == current_user.Tel_Number).first()
    order = Order()
    order.User_Id = user.Id
    order.File_Dir = pdf_name
    order.File_Name = '身份证照片.pdf'
    order.Print_Place = request.form.get('print_place', 'home')
    order.Print_pages = 1
    order.Print_Copies = copies
    order.Print_Direction = '3'        # 竖版
    order.Print_Colour = 'RGB'         # 彩色
    order.Print_size = 'A4'
    order.Print_way = 'one-sided'      # 单面
    order.Print_Money = round(cost, 2)
    order.Trade_Number = next_trade_number()
    order.Time_Way = '1'

    macs = save_order_atomic(order)

    data = {
        'printfile': '身份证照片.pdf',
        'new_filename': pdf_name,
        'print_place': order.Print_Place,
        'print_copies': copies,
        'pageCount': 1,
        'tradeid': macs,
        'user_tel': user.Tel_Number,
        'cost': round(cost, 2),
        'now': ts,
    }
    identifi = _is_mobile()
    form = Print()
    return render_template('use_templates/layui_pay_form.html', form=form, data=data, identifi=identifi)