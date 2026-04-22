# 优先加载 .env 文件，必须在任何 config/模块导入之前
try:
    from dotenv import load_dotenv
    import os
    _ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.control.printer import printer
from app.control.login import login
from app.control.admin import admin
from app.control.json import jsons
from app.test.test_route import test
from app.test.ali_pay import cloud_pay
from app.models import db, User
from flask_login import LoginManager
from flask_bootstrap import Bootstrap


app = Flask(__name__)
# 识别 cpolar/nginx 等反向代理的 X-Forwarded-* 头
# 让 Flask 知道真实的 scheme(https)、host 和 remote_addr
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
bootstrap = Bootstrap(app)



app.config.from_pyfile('config.py')
app.register_blueprint(printer, url_prefix='/printer')
app.register_blueprint(login, url_prefix='/login')
app.register_blueprint(test, url_prefix='/test')
app.register_blueprint(cloud_pay, url_prefix='/cloud_pay')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(jsons, url_prefix='/jsons')

db.init_app(app)
login_manager = LoginManager(app)
login_manager.init_app(app)
login_manager.login_view = 'login.back_login'
login_manager.login_message = u'请先登录！'

# 启动时确保 Order.Trade_Number 上有 UNIQUE 索引。
# 这是撞号的最终防线：即使应用层生成逻辑失误，也能由 DB 拦住并触发重试。
# 幂等设计：已存在就静默跳过；若老库里已经有重复值，记录一条警告但不影响启动。
def _ensure_trade_number_unique_index():
    from sqlalchemy import text, inspect
    with app.app_context():
        try:
            insp = inspect(db.engine)
            existing = {ix['name'] for ix in insp.get_indexes('Order')}
            if 'idx_order_trade_number_unique' in existing:
                return
            with db.engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX idx_order_trade_number_unique "
                    "ON `Order` (`Trade_Number`)"
                ))
            print('[init] 已为 Order.Trade_Number 建立 UNIQUE 索引')
        except Exception as e:
            # 常见原因：老库里存在重复的 Trade_Number。不阻塞启动，只警告。
            print('[init][警告] 建立 Trade_Number 唯一索引失败：{}. '
                  '可先运行 utils.cleanup_duplicate_trade_numbers() 清理后再启动。'.format(e))


_ensure_trade_number_unique_index()


def _ensure_user_is_active_column():
    """老库兼容：若 User 表缺少 Is_Active 列，启动时补上，默认 True.
    幂等：已存在则跳过，失败只警告不阻塞.
    """
    from sqlalchemy import text, inspect
    with app.app_context():
        try:
            insp = inspect(db.engine)
            cols = {c['name'] for c in insp.get_columns('User')}
            if 'Is_Active' in cols:
                return
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE `User` ADD COLUMN `Is_Active` TINYINT(1) NOT NULL DEFAULT 1"
                ))
            print('[init] 已为 User 表补充 Is_Active 列')
        except Exception as e:
            print('[init][警告] 添加 User.Is_Active 列失败：{}'.format(e))


_ensure_user_is_active_column()


def _ensure_new_tables_and_seed():
    """启动时幂等：
    - 自动创建 PrintPlace / OrderLog 新表（db.create_all 不会影响已有表）
    - 若 PrintPlace 为空，seed 一条默认"数智维新工作室"
    """
    with app.app_context():
        try:
            db.create_all()
            from app.models import PrintPlace
            if PrintPlace.query.count() == 0:
                db.session.add(PrintPlace(
                    Key='home', Name='数智维新工作室',
                    Address='', Sort=0, Is_Active=True,
                ))
                db.session.commit()
                print('[init] 已 seed 默认打印点 home=数智维新工作室')
        except Exception as e:
            print('[init][警告] 新表初始化失败：{}'.format(e))


_ensure_new_tables_and_seed()


@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user


from app import print

import os
for sub in ('Upload_Files', 'Upload_Files/BeforeSwitchFile', 'pay_qrcode'):
    os.makedirs(os.path.join(app.static_folder, sub), exist_ok=True)