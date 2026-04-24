from app import app, db
import click, os, shutil
from datetime import datetime
from app.models import User
from flask import render_template, jsonify


@app.route('/health')
def health_check():
    """健康检查：DB + Redis + 磁盘空间。"""
    result = {'status': 'ok', 'db': False, 'redis': False, 'disk_free_mb': 0}
    # DB
    try:
        db.session.execute(db.text('SELECT 1'))
        result['db'] = True
    except Exception:
        result['status'] = 'degraded'
    # Redis
    try:
        from worker import conn as redis_conn
        redis_conn.ping()
        result['redis'] = True
    except Exception:
        result['status'] = 'degraded'
    # 磁盘
    try:
        usage = shutil.disk_usage(os.path.dirname(__file__))
        result['disk_free_mb'] = round(usage.free / 1024 / 1024)
        if result['disk_free_mb'] < 500:
            result['status'] = 'warning'
            result['disk_warning'] = '磁盘剩余不足 500MB'
    except Exception:
        pass
    code = 200 if result['status'] == 'ok' else 503
    return jsonify(result), code


# 云打印平台首页（前台）
@app.route('/')
@app.route('/index')
@app.route('/toindex')
def platform_home():
    return render_template('use_templates/stamp_toIndex.html', year=datetime.now().year)


# 微信
@app.route('/vx')
def vx_form():
    return render_template('use_templates/stamp_vx.html')


# 普通照片
@app.route('/pphoto')
def pphoto_form():
    return render_template('use_templates/stamp_pphoto.html')


# 联系客服
@app.route('/service')
def sercvice_form():
    return render_template('use_templates/stamp_service.html')


# 身份证照
@app.route('/sphoto')
def sphoto_form():
    return render_template('use_templates/stamp_sphoto.html')


# 文本打印
@app.route('/text')
def text_form():
    return render_template('use_templates/stamp_text.html')


# 优惠专区
@app.route('/todi')
def todi_format():
    return render_template('use_templates/stamp_todi.html')


#
@app.route('/user')
def user_form():
    return render_template('use_templates/stamp_user.html')


@app.route('/zphoto')
def zphoto_form():
    return render_template('use_templates/stamp_zphoto.html')


# 初始化数据库命令
@app.cli.command()
@click.option('--tel_number', prompt=True, help='tel_number')
@click.option('--password', prompt=True, confirmation_prompt=True, help='password')
def initdb(tel_number, password):
    db.create_all()
    click.echo('init db')
    admin = User(
        Tel_Number=tel_number,
        Role='admin'
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
