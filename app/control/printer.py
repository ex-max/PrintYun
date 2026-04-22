from flask import Blueprint, request, render_template, flash
import os, datetime, time
from werkzeug.utils import secure_filename
from app.utils import read_pdf_pages, next_trade_number, save_order_atomic
from flask_login import login_required, current_user
from app.models import User, Order, db
from app.forms import Print
from worker import que, switch_topdf, conn
# from app.utils import switch_topdf

printer = Blueprint('printer', __name__)


@printer.route('/print')
@login_required
def print1():
    return 'sss'


@printer.route('/select', methods=['GET', 'POST'])
@login_required
def select():
    # # 多文件上传
    # money = 0
    # page_count = 0
    # new_filenames = []
    # old_filenames = []
    #

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
            identifi = ''
            agent = request.environ.get('HTTP_USER_AGENT', '')
            if ('AppleWebKit' in agent and 'Mobile' in agent):
                identifi = 1
            return render_template('use_templates/layui_pay_demand.html', form=form, data=data, identifi=identifi)
        else:
            # all_file = request.files.getlist('print_file')
            print_file = form.print_file.data
            print_place = form.print_place.data
            print_copies = form.print_copies.data
            print_type = form.print_type.data
            print_color = form.print_color.data
            print_size = form.print_size.data
            print_way = form.print_way.data
            print_time = form.print_time.data
            time_way = form.print_demand.data
            # 单价表（元/页）：按 颜色 × 单/双面 四档定价
            #   黑白 单面 0.3  / 双面 0.5
            #   彩色 单面 1.0  / 双面 1.7
            is_duplex = print_way != 'one-sided'   # one-sided 为单面，其余视为双面
            if print_color == 'CMYGray':
                unit_price = 0.5 if is_duplex else 0.3
            else:
                unit_price = 1.7 if is_duplex else 1.0
            print_cost = unit_price * int(print_copies)

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

            # 需要转换格式的文件
            else:


                upload_path = os.path.join(parentdir, 'static/Upload_Files/BeforeSwitchFile/', new_filename)
                print_file.save(upload_path)

                switchs = que.enqueue(switch_topdf, upload_path, current_user.Id)
                ps = conn.pubsub()
                ps.subscribe(str(current_user.Id))
                deadline = time.time() + 30
                converted = False
                try:
                    for i in ps.listen():
                        if time.time() > deadline:
                            flash('文件转换超时，请重试')
                            return render_template('use_templates/layui_orderForGoods.html',
                                                   now=now, error=1, form=form)
                        print(i)
                        if i['type'] == 'message':
                            if i['data'] == b'OK':
                                sz = new_filename.rindex('.')
                                new_filename = new_filename[:sz] + '.pdf'
                                switched_dir = os.path.join(parentdir, 'static/Upload_Files',
                                                            secure_filename(new_filename))
                                pageCount = read_pdf_pages(switched_dir)
                                cost = pageCount * print_cost
                                converted = True
                                break
                            else:
                                flash('上传文件格式错误')
                                error = 1
                                return render_template('use_templates/layui_orderForGoods.html',
                                                       now=now, error=error, form=form)
                finally:
                    try:
                        ps.unsubscribe()
                        ps.close()
                    except Exception:
                        pass

                if not converted:
                    flash('文件转换超时，请重试')
                    return render_template('use_templates/layui_orderForGoods.html',
                                           now=now, error=1, form=form)



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
            identifi = ''
            agent = request.environ.get('HTTP_USER_AGENT', '')
            if ('AppleWebKit' in agent and 'Mobile' in agent):
                identifi = 1
            return render_template('use_templates/layui_pay_form.html', form=form, data=data, identifi=identifi)
    return render_template('use_templates/layui_orderForGoods.html', now=now, form=form, datas=datas,
                           user_datas=user_datas)