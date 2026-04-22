import datetime
from io import BytesIO

from flask import Blueprint, request, render_template, abort, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from openpyxl import Workbook
from app.models import db, User, Order, PrintPlace, OrderLog
from app.forms import Print as PrintForm

admin = Blueprint('admin', __name__)

# 文件预览接口对所有登录用户开放；其它 /admin/* 仅 Role=admin
_PREVIEW_ENDPOINTS = {'admin.look_media', 'admin.look_picture'}


@admin.before_request
@login_required
def _require_admin():
    """蓝图级守卫：除文件预览外，/admin/* 仅对 Role='admin' 开放。"""
    if request.endpoint in _PREVIEW_ENDPOINTS:
        return None
    if current_user.Role != 'admin':
        return redirect(url_for('platform_home'))


# ---------- 小工具 ----------

# 订单状态常量（与 models.py 注释一致）
ST_CANCELLED = -2
ST_FAILED    = -1
ST_UNPAID    = 0
ST_PAID      = 1   # 旧状态：已支付未打印；新流程默认跳过，但保留兼容
ST_PRINTING  = 2   # 正在打印/待取件（支付回调自动置为此状态）
ST_DONE      = 3

STATUS_LABELS = {
    ST_CANCELLED: '已取消',
    ST_FAILED:    '打印失败',
    ST_UNPAID:    '未支付',
    ST_PAID:      '已支付',
    ST_PRINTING:  '正在打印',
    ST_DONE:      '已完成',
}
STATUS_BADGES = {
    ST_CANCELLED: 'gray',
    ST_FAILED:    'red',
    ST_UNPAID:    'orange',
    ST_PAID:      'blue',
    ST_PRINTING:  'purple',
    ST_DONE:      'green',
}
# 有限状态机：管理员可以把订单从 key 状态转到 value 里的任一目标状态
#   已支付(1) / 正在打印(2) → 完成/失败/(回到打印队列)
#   未支付(0) → 可手动标记失败（异常情况）
#   终态（完成/已取消/失败）不能再动
ADMIN_TRANSITIONS = {
    ST_UNPAID:   {ST_FAILED},                                    # 未支付 -> 标记失败
    ST_PAID:     {ST_PRINTING, ST_DONE, ST_FAILED},              # 已支付 -> 打印中/完成/失败
    ST_PRINTING: {ST_DONE, ST_FAILED, ST_PAID},                  # 打印中 -> 完成/失败/退回已支付
    ST_FAILED:   {ST_PRINTING},                                  # 失败 -> 重新打印
}


def _place_labels():
    """打印点 key → 展示名 映射（复用下单表单的 choices，单一事实源）"""
    return dict(PrintForm().print_place.choices)


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


def _apply_order_filters(q, status_arg, date_from, date_to, tel):
    if status_arg == 'all':
        pass
    elif status_arg == 'active':
        q = q.filter(Order.Print_Status != ST_CANCELLED)
    elif status_arg == 'unpaid':
        q = q.filter(Order.Print_Status == ST_UNPAID)
    elif status_arg == 'printing':
        q = q.filter(Order.Print_Status.in_([ST_PAID, ST_PRINTING]))
    elif status_arg == 'done':
        q = q.filter(Order.Print_Status == ST_DONE)
    elif status_arg == 'failed':
        q = q.filter(Order.Print_Status == ST_FAILED)
    elif status_arg == 'cancelled':
        q = q.filter(Order.Print_Status == ST_CANCELLED)

    if date_from:
        q = q.filter(Order.Born_Date_Day >= date_from)
    if date_to:
        q = q.filter(Order.Born_Date_Day <= date_to)
    if tel:
        uids = [u.Id for u in User.query.filter(User.Tel_Number.like('%' + tel + '%')).all()]
        if uids:
            q = q.filter(Order.User_Id.in_(uids))
        else:
            q = q.filter(Order.Id == -1)
    return q


def _write_order_log(order, action, from_status=None, to_status=None, note=''):
    db.session.add(OrderLog(
        Order_Id=order.Id,
        Operator_Id=getattr(current_user, 'Id', None) if getattr(current_user, 'is_authenticated', False) else None,
        Action=action,
        From_Status=from_status,
        To_Status=to_status,
        Note=note or '',
    ))


def _place_options_from_db():
    return (PrintPlace.query
            .order_by(PrintPlace.Sort.asc(), PrintPlace.Id.asc())
            .all())


# ---------- 旧路由兼容：重定向到新导航结构 ----------

@admin.route('/select')
def inded_select():
    return redirect(url_for('admin.dashboard'))


@admin.route('/people')
def inded_people():
    return redirect(url_for('admin.dashboard'))


@admin.route('/query')
def inded_query():
    return redirect(url_for('admin.orders'))


@admin.route('/data')
def query_data():
    # 老的 layui 订单 iframe 接口，现在直接跳转到新订单页
    return redirect(url_for('admin.orders'))


# ---------- 文件预览 ----------

@admin.route("/look_pdf/<media>")
@login_required
def look_media(media):
    requested = request.args.get('file', '')
    if requested:
        if '..' in requested or '\\' in requested:
            abort(400)
        fname = requested.rsplit('/', 1)[-1]
        if current_user.Role != 'admin':
            owned = Order.query.filter_by(
                User_Id=current_user.Id, File_Dir=fname
            ).first()
            if not owned:
                abort(403)
    return render_template('use_templates/viewer.html')


@admin.route("/look_picture/<string:picture>")
@login_required
def look_picture(picture):
    if '/' in picture or '\\' in picture or '..' in picture:
        abort(400)
    if current_user.Role != 'admin':
        owned = Order.query.filter_by(User_Id=current_user.Id, File_Dir=picture).first()
        if not owned:
            abort(403)
    return render_template('use_templates/view.html', picture=picture)


# ---------- 仪表盘 ----------

@admin.route('/dashboard')
def dashboard():
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=6)

    # 今日指标
    today_orders = Order.query.filter(
        Order.Born_Date_Day == today,
        Order.Print_Status != ST_CANCELLED,
    ).all()
    today_paid = [o for o in today_orders if (o.Print_Status or 0) >= 1]
    today_revenue = sum((o.Print_Money or 0) for o in today_paid)
    today_pages = sum((o.Print_pages or 0) * (o.Print_Copies or 1) for o in today_paid)

    # 队列数量
    queue_count = Order.query.filter(Order.Print_Status == ST_PRINTING).count()
    unpaid_count = Order.query.filter(Order.Print_Status == ST_UNPAID).count()

    # 近 7 天趋势（按天聚合）
    trend_rows = (
        db.session.query(
            Order.Born_Date_Day,
            func.count(Order.Id),
            func.coalesce(func.sum(Order.Print_Money), 0),
        )
        .filter(Order.Born_Date_Day >= week_ago,
                Order.Print_Status >= ST_PAID)
        .group_by(Order.Born_Date_Day)
        .all()
    )
    trend_map = {r[0]: (r[1], float(r[2] or 0)) for r in trend_rows}
    trend = []
    for i in range(7):
        d = week_ago + datetime.timedelta(days=i)
        c, rev = trend_map.get(d, (0, 0.0))
        trend.append({'date': d.strftime('%m-%d'), 'count': c, 'revenue': round(rev, 2)})
    max_trend_count = max((t['count'] for t in trend), default=1) or 1

    # TOP10 活跃用户（按订单数）
    top_rows = (
        db.session.query(
            User.Id, User.Tel_Number,
            func.count(Order.Id).label('cnt'),
            func.coalesce(func.sum(Order.Print_Money), 0).label('rev'),
        )
        .join(Order, Order.User_Id == User.Id)
        .filter(Order.Print_Status >= ST_PAID)
        .group_by(User.Id, User.Tel_Number)
        .order_by(func.count(Order.Id).desc())
        .limit(10)
        .all()
    )
    top_users = [
        {'tel': r[1], 'orders': r[2], 'revenue': round(float(r[3] or 0), 2)}
        for r in top_rows
    ]

    # 颜色 / 单双面占比
    color_stats = (
        db.session.query(Order.Print_Colour, func.count(Order.Id))
        .filter(Order.Print_Status >= ST_PAID)
        .group_by(Order.Print_Colour).all()
    )
    way_stats = (
        db.session.query(Order.Print_way, func.count(Order.Id))
        .filter(Order.Print_Status >= ST_PAID)
        .group_by(Order.Print_way).all()
    )

    return render_template(
        'admin/dashboard.html',
        active='dashboard',
        today=today,
        today_orders_count=len(today_orders),
        today_paid_count=len(today_paid),
        today_revenue=round(today_revenue, 2),
        today_pages=today_pages,
        queue_count=queue_count,
        unpaid_count=unpaid_count,
        trend=trend,
        max_trend_count=max_trend_count,
        top_users=top_users,
        color_stats=color_stats,
        way_stats=way_stats,
    )


# ---------- 打印队列 ----------

@admin.route('/queue')
def queue():
    """打印队列：列出 status=2（正在打印/待取件）的订单，兼容显示 status=1。"""
    orders = (
        Order.query
        .filter(Order.Print_Status.in_([ST_PAID, ST_PRINTING]))
        .order_by(Order.Born_Date.asc())
        .all()
    )
    # 附带订单人电话
    user_map = {u.Id: u.Tel_Number for u in User.query.all()}
    return render_template(
        'admin/queue.html',
        active='queue',
        orders=orders,
        user_map=user_map,
        place_labels=_place_labels(),
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
    )


# ---------- 订单中心 ----------

@admin.route('/orders')
def orders():
    """订单中心：支持状态、日期、手机号筛选。"""
    status_arg = request.args.get('status', 'active')  # active=非取消，all=全部
    date_from  = _parse_date(request.args.get('date_from'))
    date_to    = _parse_date(request.args.get('date_to'))
    tel        = (request.args.get('tel') or '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1
    per_page = 20

    q = _apply_order_filters(Order.query, status_arg, date_from, date_to, tel)

    pagination = q.order_by(Order.Id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    user_map = {u.Id: u.Tel_Number for u in User.query.all()}

    return render_template(
        'admin/orders.html',
        active='orders',
        orders=pagination.items,
        pagination=pagination,
        user_map=user_map,
        place_labels=_place_labels(),
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
        filters={
            'status': status_arg,
            'date_from': request.args.get('date_from', ''),
            'date_to': request.args.get('date_to', ''),
            'tel': tel,
        },
    )


@admin.route('/orders/export')
def export_orders():
    status_arg = request.args.get('status', 'active')
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'))
    tel = (request.args.get('tel') or '').strip()

    rows = (_apply_order_filters(Order.query, status_arg, date_from, date_to, tel)
            .order_by(Order.Id.desc())
            .all())
    user_map = {u.Id: u.Tel_Number for u in User.query.all()}
    place_labels = _place_labels()

    wb = Workbook()
    ws = wb.active
    ws.title = '订单导出'
    ws.append(['订单号', '手机号', '文件名', '打印点', '份数', '页数', '颜色', '单双面', '纸张', '金额', '状态', '下单时间'])

    for o in rows:
        ws.append([
            o.Trade_Number,
            user_map.get(o.User_Id, ''),
            o.File_Name,
            place_labels.get(o.Print_Place, o.Print_Place),
            o.Print_Copies,
            o.Print_pages,
            '黑白' if o.Print_Colour == 'CMYGray' else '彩色',
            '单面' if o.Print_way == 'one-sided' else ('双面长边' if o.Print_way == 'two-sided-long-edge' else '双面短边'),
            o.Print_size,
            float(o.Print_Money or 0),
            STATUS_LABELS.get(o.Print_Status, o.Print_Status),
            o.Born_Date.strftime('%Y-%m-%d %H:%M:%S') if o.Born_Date else '',
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    filename = 'orders_{}.xlsx'.format(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    return send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ---------- 订单状态改写（核心 API） ----------

@admin.route('/order/<trade_number>/status', methods=['POST'])
def change_order_status(trade_number):
    """管理员改订单状态，走有限状态机，拒绝非法跳转。
    重定向回 next 参数指向的页面（默认回订单中心）。
    """
    try:
        target = int(request.form.get('status', ''))
    except ValueError:
        flash('目标状态参数不合法', 'error')
        return redirect(request.form.get('next') or url_for('admin.orders'))

    o = Order.query.filter_by(Trade_Number=trade_number).first()
    if not o:
        flash('订单不存在', 'error')
        return redirect(request.form.get('next') or url_for('admin.orders'))

    cur = int(o.Print_Status or 0)
    allowed = ADMIN_TRANSITIONS.get(cur, set())
    if target not in allowed:
        flash(
            f'不允许的状态流转：{STATUS_LABELS.get(cur, cur)} → {STATUS_LABELS.get(target, target)}',
            'error'
        )
        return redirect(request.form.get('next') or url_for('admin.orders'))

    o.Print_Status = target
    _write_order_log(
        o,
        action='status_change',
        from_status=cur,
        to_status=target,
        note='管理员修改订单状态'
    )
    db.session.commit()
    flash(
        f'订单 {trade_number} 已从"{STATUS_LABELS.get(cur, cur)}"改为"{STATUS_LABELS.get(target, target)}"',
        'success'
    )
    return redirect(request.form.get('next') or url_for('admin.orders'))


@admin.route('/order/<trade_number>')
def order_detail(trade_number):
    order = Order.query.filter_by(Trade_Number=trade_number).first_or_404()
    logs = (OrderLog.query
            .filter_by(Order_Id=order.Id)
            .order_by(OrderLog.Created_At.desc(), OrderLog.Id.desc())
            .all())
    user_map = {u.Id: u.Tel_Number for u in User.query.all()}
    return render_template(
        'admin/order_detail.html',
        active='orders',
        order=order,
        logs=logs,
        user_map=user_map,
        place_labels=_place_labels(),
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
    )


# ---------- 用户管理 ----------

@admin.route('/users')
def users():
    kw = (request.args.get('kw') or '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1
    per_page = 20

    q = User.query
    if kw:
        q = q.filter(User.Tel_Number.like('%' + kw + '%'))
    pagination = q.order_by(User.Id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # 每个用户的订单数 + 消费总额
    uids = [u.Id for u in pagination.items]
    stats = {}
    if uids:
        rows = (
            db.session.query(
                Order.User_Id,
                func.count(Order.Id),
                func.coalesce(func.sum(Order.Print_Money), 0),
            )
            .filter(Order.User_Id.in_(uids),
                    Order.Print_Status >= ST_PAID)
            .group_by(Order.User_Id)
            .all()
        )
        stats = {r[0]: (r[1], round(float(r[2] or 0), 2)) for r in rows}

    return render_template(
        'admin/users.html',
        active='users',
        users=pagination.items,
        pagination=pagination,
        stats=stats,
        kw=kw,
    )


@admin.route('/user/<int:uid>/toggle_active', methods=['POST'])
def toggle_user_active(uid):
    u = User.query.get_or_404(uid)
    if u.Id == current_user.Id:
        flash('不能禁用当前登录的管理员账号', 'warning')
        return redirect(url_for('admin.users'))
    u.Is_Active = not bool(u.Is_Active)
    db.session.commit()
    flash(('已启用' if u.Is_Active else '已禁用') + ' ' + u.Tel_Number, 'success')
    return redirect(url_for('admin.users'))


@admin.route('/user/<int:uid>/role', methods=['POST'])
def change_user_role(uid):
    role = request.form.get('role', '').strip()
    if role not in ('admin', 'guest'):
        flash('角色参数不合法', 'error')
        return redirect(url_for('admin.users'))
    u = User.query.get_or_404(uid)
    if u.Id == current_user.Id and role != 'admin':
        flash('不能把自己降级为普通用户', 'warning')
        return redirect(url_for('admin.users'))
    u.Role = role
    db.session.commit()
    flash(f'已将 {u.Tel_Number} 的角色改为 {role}', 'success')
    return redirect(url_for('admin.users'))


# ---------- 打印点管理 ----------

@admin.route('/places')
def print_places():
    places = _place_options_from_db()
    return render_template(
        'admin/print_places.html',
        active='places',
        places=places,
    )


@admin.route('/places/add', methods=['POST'])
def add_place():
    key = (request.form.get('key') or '').strip()
    name = (request.form.get('name') or '').strip()
    address = (request.form.get('address') or '').strip()
    try:
        sort = int((request.form.get('sort') or '0').strip())
    except ValueError:
        sort = 0

    if not key or not name:
        flash('Key 和展示名不能为空', 'error')
        return redirect(url_for('admin.print_places'))
    if PrintPlace.query.filter_by(Key=key).first():
        flash('该 Key 已存在，请换一个', 'error')
        return redirect(url_for('admin.print_places'))

    db.session.add(PrintPlace(Key=key, Name=name, Address=address, Sort=sort, Is_Active=True))
    db.session.commit()
    flash('打印点已新增', 'success')
    return redirect(url_for('admin.print_places'))


@admin.route('/places/<int:pid>/update', methods=['POST'])
def update_place(pid):
    place = PrintPlace.query.get_or_404(pid)
    place.Name = (request.form.get('name') or '').strip() or place.Name
    place.Address = (request.form.get('address') or '').strip()
    try:
        place.Sort = int((request.form.get('sort') or place.Sort).strip())
    except ValueError:
        pass
    db.session.commit()
    flash('打印点已更新', 'success')
    return redirect(url_for('admin.print_places'))


@admin.route('/places/<int:pid>/toggle', methods=['POST'])
def toggle_place(pid):
    place = PrintPlace.query.get_or_404(pid)
    place.Is_Active = not bool(place.Is_Active)
    db.session.commit()
    flash(('已启用' if place.Is_Active else '已停用') + ' 打印点 ' + place.Name, 'success')
    return redirect(url_for('admin.print_places'))


# ---------- 其他 ----------

@admin.route('/check')
def check():
    agent = request.environ.get('HTTP_USER_AGENT', '')
    if 'AppleWebKit' in agent and 'Mobile' in agent:
        return 'mobile'
    return 'computer'
