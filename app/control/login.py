import datetime, logging
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, flash, session, redirect, url_for, jsonify, abort
from app.test import ali_sms
from app.models import db, User, Order
from app.utils import next_trade_number, save_order_atomic
from app.forms import LoginForm, Register, Findpassword, Change_Password, Print as PrintForm
from flask_login import login_user, current_user, logout_user, login_required

login = Blueprint(
    'login',
    __name__
)

logger = logging.getLogger(__name__)


def _safe_next(next_page, role):
    """过滤 next 参数，防止开放重定向和权限逃逸。

    策略：
    - 普通用户（role != 'admin'）**完全忽略** next：登录后强制回前台首页，
      确保"云打印平台=前台、云打印后台管理=后台"的边界不会被 next 打破。
    - 管理员：只允许站内相对 URL（防止 //evil.com / https://xxx 开放重定向）。
    """
    if role != 'admin':
        return None
    if not next_page:
        return None
    if not next_page.startswith('/') or next_page.startswith('//'):
        return None
    parsed = urlparse(next_page)
    if parsed.netloc or parsed.scheme:
        return None
    return next_page


def _role_redirect(role, next_page=None):
    """按角色分流：
       - admin  → 后台管理系统（admin.inded_select），next 安全时优先采用
       - 普通用户 → 前台首页（platform_home），忽略 next
    """
    safe = _safe_next(next_page, role)
    if safe:
        return redirect(safe)
    if role == 'admin':
        return redirect(url_for('admin.inded_select'))
    return redirect(url_for('platform_home'))


@login.route("/register", methods=['POST', 'GET'])
def register():
    if current_user.is_authenticated:
        return _role_redirect(current_user.Role)

    form = Register()

    # AJAX: 获取验证码
    phone_number = request.args.get('mobile_phone_number')
    if phone_number is not None and request.method == 'GET':
        ok, msg = ali_sms.send_sms(phone_number)
        return jsonify({'success': ok, 'msg': msg})

    if form.validate_on_submit():
        tel = str(form.tel.data)
        v_code = form.v_code.data
        password = form.password1.data
        if ali_sms.verify_code(tel, v_code):
            user = User(Tel_Number=tel)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login.back_login'))
        return render_template('use_templates/c_register.html',
                               error_msg='验证码不正确或已过期', form=form)
    # POST 到这里说明 validate_on_submit 失败：CSRF、必填、密码一致性等
    if request.method == 'POST':
        errors = []
        for field_name, msgs in form.errors.items():
            label = getattr(getattr(form, field_name, None), 'label', None)
            label_text = label.text if label else field_name
            for m in msgs:
                errors.append(f'{label_text}: {m}')
        logger.warning('表单校验失败：%s', form.errors)
        error_msg = ' | '.join(errors) if errors else '表单校验失败'
        return render_template('use_templates/c_register.html',
                               error_msg=error_msg, form=form)
    return render_template('use_templates/c_register.html', form=form)


# 找回密码
@login.route("/findpassword", methods=['POST', 'GET'])
def findpassword():
    form = Findpassword()

    # AJAX: 获取验证码（需校验用户已注册）
    phone_number = request.args.get('mobile_phone_number')
    if phone_number is not None and request.method == 'GET':
        if not User.query.filter_by(Tel_Number=phone_number).first():
            return jsonify({'success': False, 'msg': '手机号未注册'})
        ok, msg = ali_sms.send_sms(phone_number)
        return jsonify({'success': ok, 'msg': msg})

    if form.validate_on_submit():
        tel = str(form.tel.data)
        v_code = form.v_code.data
        password = form.password1.data
        if ali_sms.verify_code(tel, v_code):
            user = User.query.filter_by(Tel_Number=tel).first()
            if user:
                user.set_password(password)
                db.session.commit()
                return redirect(url_for('login.back_login'))
            return render_template('use_templates/c_findpassword.html',
                                   error_msg='手机号未注册', form=form)
        return render_template('use_templates/c_findpassword.html',
                               error_msg='验证码不正确或已过期', form=form)
    return render_template('use_templates/c_findpassword.html', form=form)


@login.route("/login", methods=['POST', 'GET'])
def back_login():
    if current_user.is_authenticated:
        # 已登录访问登录页：按角色 + next 分流
        next_page = request.args.get('next')
        return _role_redirect(current_user.Role, next_page)

    form = LoginForm()
    if form.validate_on_submit():
        tel = form.tel.data
        password = form.password.data
        remember = form.remember.data
        user = User.query.filter_by(Tel_Number=tel).first()
        if user and user.validate_password(password):
            # 账号被管理员禁用时拒绝登录
            if not user.is_active:
                flash('该账号已被禁用，请联系管理员', 'error')
                return render_template('use_templates/c_login.html',
                                       form=form, error_msg='该账号已被禁用')
            login_user(user, remember)
            # 按角色分流：admin → 后台；guest → 前台。
            # next_page 仅在对当前角色安全时才会被采纳（见 _safe_next）。
            next_page = request.args.get('next') or request.form.get('next')
            return _role_redirect(user.Role, next_page)
        return render_template('use_templates/c_login.html',
                               form=form, error_msg='手机号或密码错误')
    return render_template('use_templates/c_login.html', form=form)


@login.route("/logout")
@login_required
def logout():
    logout_user()
    flash('logout success', 'info')
    return redirect(url_for('login.back_login'))


# 修改密码
@login.route("/change_password", methods=['GET', 'POST'])
@login_required
def change_password():
    form = Change_Password()
    user = User.query.filter_by(Tel_Number=current_user.Tel_Number).first()
    if request.method == 'POST':
        old_password = form.old_password.data
        if user and user.validate_password(old_password):
            user.set_password(form.password1.data)
            db.session.commit()
            flash('修改成功,请使用新密码登录')
            return redirect(url_for('login.change_password'))
        else:
            error = "密码校验失败"
            return render_template('use_templates/layui_admin-info.html', form=form, user=user, error=error)
    return render_template('use_templates/layui_admin-info.html', form=form, user=user)


# ---------- 个人中心 ----------

@login.route('/me')
@login_required
def me():
    """个人中心：账户信息 + 我的订单（按状态过滤 + 分页）。"""
    # 状态过滤：all / unpaid(0) / paid(1,2) / done(3) / cancelled(-2)
    status_filter = request.args.get('status', 'all')
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 20

    q = Order.query.filter_by(User_Id=current_user.Id)
    if status_filter == 'unpaid':
        q = q.filter(Order.Print_Status == 0)
    elif status_filter == 'paid':
        q = q.filter(Order.Print_Status.in_([1, 2]))
    elif status_filter == 'done':
        q = q.filter(Order.Print_Status == 3)
    elif status_filter == 'cancelled':
        q = q.filter(Order.Print_Status == -2)
    else:  # all：默认不显示已取消（软删）
        q = q.filter(Order.Print_Status != -2)
    pagination = q.order_by(Order.Id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items

    # 统计（用 SQL 聚合，比全量加载快得多）
    count_rows = (
        db.session.query(Order.Print_Status, db.func.count(Order.Id))
        .filter_by(User_Id=current_user.Id)
        .group_by(Order.Print_Status)
        .all()
    )
    status_counts = dict(count_rows)
    counts = {
        'all':       sum(v for k, v in status_counts.items() if k != -2),
        'unpaid':    status_counts.get(0, 0),
        'paid':      status_counts.get(1, 0) + status_counts.get(2, 0),
        'done':      status_counts.get(3, 0),
        'cancelled': status_counts.get(-2, 0),
    }
    total_paid_row = (
        db.session.query(db.func.coalesce(db.func.sum(Order.Print_Money), 0))
        .filter(Order.User_Id == current_user.Id, Order.Print_Status >= 1)
        .scalar()
    )
    total_paid = float(total_paid_row)

    # 手机号脱敏：138****0002
    tel = current_user.Tel_Number or ''
    tel_masked = (tel[:3] + '****' + tel[-4:]) if len(tel) >= 7 else tel

    # 打印点 key → 展示名 映射（与下单表单使用同一份 choices，保持单一事实源）
    place_labels = dict(PrintForm().print_place.choices)

    return render_template(
        'use_templates/personal_center.html',
        orders=orders,
        pagination=pagination,
        counts=counts,
        total_paid=total_paid,
        tel_masked=tel_masked,
        active_status=status_filter,
        place_labels=place_labels,
    )


@login.route('/me/status_check')
@login_required
def me_status_check():
    """AJAX: 前端轮询订单状态变化。

    请求：?ids=TN1,TN2,TN3&statuses=0,1,0  （当前页可见订单号和状态）
    响应：{changes: [{trade_number, old_status, new_status, label}, ...]}
    """
    ids_str = request.args.get('ids', '')
    statuses_str = request.args.get('statuses', '')
    if not ids_str:
        return jsonify({'changes': []})

    trade_numbers = [s.strip() for s in ids_str.split(',') if s.strip()]
    try:
        old_statuses = [int(s) for s in statuses_str.split(',')]
    except (ValueError, TypeError):
        old_statuses = []

    if len(trade_numbers) != len(old_statuses):
        return jsonify({'changes': []})

    # 查询当前状态
    orders = (
        Order.query
        .filter(Order.Trade_Number.in_(trade_numbers), Order.User_Id == current_user.Id)
        .all()
    )
    status_map = {o.Trade_Number: o.Print_Status for o in orders}

    STATUS_TEXT = {
        -2: '已取消', -1: '打印失败', 0: '未支付',
        1: '已支付', 2: '正在打印', 3: '已完成',
    }

    changes = []
    for tn, old in zip(trade_numbers, old_statuses):
        new = status_map.get(tn)
        if new is not None and new != old:
            changes.append({
                'trade_number': tn,
                'old_status': old,
                'new_status': new,
                'label': STATUS_TEXT.get(new, f'状态 {new}'),
            })

    return jsonify({'changes': changes})

@login.route('/order/<trade_number>/cancel', methods=['POST'])
@login_required
def cancel_order(trade_number):
    """取消未支付订单：只有归属当前用户且状态=0 的订单可取消。

    采用软删除（Print_Status=-2），订单号保留在表中参与唯一性校验，
    确保"一号一单一码"——取消过的号码永不被新订单复用。
    """
    o = Order.query.filter_by(
        Trade_Number=trade_number, User_Id=current_user.Id
    ).first_or_404()
    if o.Print_Status != 0:
        flash('该订单已支付或正在处理，无法取消')
        return redirect(url_for('login.me'))
    old_status = o.Print_Status
    o.Print_Status = -2
    db.session.add(OrderLog(
        Order_Id=o.Id,
        Operator_Id=current_user.Id,
        Action='cancel',
        From_Status=old_status,
        To_Status=-2,
        Note='用户在个人中心取消未支付订单',
    ))
    db.session.commit()
    flash(f'订单 {trade_number} 已取消')
    return redirect(url_for('login.me'))


@login.route('/order/<trade_number>/reprint', methods=['POST'])
@login_required
def reprint_order(trade_number):
    """再次打印：复制原订单的参数，生成一张新的待支付订单。"""
    old = Order.query.filter_by(
        Trade_Number=trade_number, User_Id=current_user.Id
    ).first_or_404()

    new_o = Order(
        File_Dir=old.File_Dir,
        File_Name=old.File_Name,
        Print_Place=old.Print_Place,
        Print_pages=old.Print_pages,
        Print_Copies=old.Print_Copies,
        Print_Direction=old.Print_Direction,
        Print_Colour=old.Print_Colour,
        Print_size=old.Print_size,
        Print_way=old.Print_way,
        Print_Money=old.Print_Money,
        Print_Status=0,
        Trade_Number=next_trade_number(),
        Time_Way=old.Time_Way,
        User_Id=current_user.Id,
    )
    macs = save_order_atomic(new_o)
    db.session.add(OrderLog(
        Order_Id=old.Id,
        Operator_Id=current_user.Id,
        Action='reprint_source',
        From_Status=old.Print_Status,
        To_Status=old.Print_Status,
        Note='用户发起再次打印，生成新订单 {}'.format(macs),
    ))
    db.session.add(OrderLog(
        Order_Id=new_o.Id,
        Operator_Id=current_user.Id,
        Action='reprint_created',
        From_Status=None,
        To_Status=0,
        Note='由订单 {} 复制生成的新待支付订单'.format(old.Trade_Number),
    ))
    db.session.commit()
    flash(f'已为您创建同参数新订单 {macs}，请继续支付')
    return redirect(url_for('login.me', status='unpaid'))
