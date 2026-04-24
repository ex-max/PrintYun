# 优先加载 .env 文件，必须在任何 config/模块导入之前
try:
    from dotenv import load_dotenv
    import os
    _ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass

import logging
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.control.printer import printer
from app.control.login import login
from app.control.admin import admin
from app.control.json import jsons
from app.test.test_route import test
from app.test.ali_pay import cloud_pay
from app.control.local_print import local_print
from app.models import db, User
from flask_login import LoginManager
from flask_bootstrap import Bootstrap
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


app = Flask(__name__)
# 识别 cpolar/nginx 等反向代理的 X-Forwarded-* 头
# 让 Flask 知道真实的 scheme(https)、host 和 remote_addr
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
bootstrap = Bootstrap(app)



app.config.from_pyfile('config.py')

# ---- 接口频率限制 ----
# 优先使用 Redis 做存储（多进程共享、重启不丢状态），不可用时回退到内存
_limiter_storage = 'memory://'
try:
    _redis_url = os.environ.get('REDISTOGO_URL', 'redis://:123456@localhost:6379')
    import redis as _r
    _r.Redis.from_url(_redis_url).ping()
    _limiter_storage = _redis_url
except Exception:
    pass
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=['200 per hour'],
    storage_uri=_limiter_storage,
)

# ---- 结构化日志 ----
from app.logging_config import setup_logging
setup_logging(app)

app.register_blueprint(printer, url_prefix='/printer')
app.register_blueprint(login, url_prefix='/login')
app.register_blueprint(test, url_prefix='/test')
app.register_blueprint(cloud_pay, url_prefix='/cloud_pay')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(jsons, url_prefix='/jsons')
app.register_blueprint(local_print, url_prefix='/local')

# ---- 蓝图注册完成后追加频率限制（避免循环引用）----
limiter.limit('5 per minute')(app.view_functions['login.register'])
limiter.limit('10 per minute')(app.view_functions['login.back_login'])
limiter.limit('5 per minute')(app.view_functions['login.findpassword'])

db.init_app(app)
login_manager = LoginManager(app)
login_manager.init_app(app)
login_manager.login_view = 'login.back_login'
login_manager.login_message = u'请先登录！'

# 启动时确保 Order.Trade_Number 上有 UNIQUE 索引。
# 这是撞号的最终防线：即使应用层生成逻辑失误，也能由 DB 拦住并触发重试。
# 幂等设计：已存在就静默跳过；若老库里已经有重复值，记录一条警告但不影响启动。
def _ensure_trade_number_unique_index():
    _log = logging.getLogger('init')
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
            _log.info('已为 Order.Trade_Number 建立 UNIQUE 索引')
        except Exception as e:
            # 常见原因：老库里存在重复的 Trade_Number。不阻塞启动，只警告。
            _log.warning('建立 Trade_Number 唯一索引失败：%s。可先运行 utils.cleanup_duplicate_trade_numbers() 清理后再启动。', e)


_ensure_trade_number_unique_index()


def _ensure_performance_indexes():
    """启动时幂等：为高频查询字段创建辅助索引。"""
    _log = logging.getLogger('init')
    from sqlalchemy import text, inspect
    indexes_to_create = [
        ('Order', 'idx_order_user_id', '`User_Id`'),
        ('Order', 'idx_order_status', '`Print_Status`'),
        ('Order', 'idx_order_born_date', '`Born_Date`'),
        ('OrderLog', 'idx_orderlog_order_id', '`Order_Id`'),
    ]
    with app.app_context():
        try:
            insp = inspect(db.engine)
            for table, idx_name, columns in indexes_to_create:
                try:
                    existing = {ix['name'] for ix in insp.get_indexes(table)}
                except Exception:
                    continue  # 表可能还不存在
                if idx_name in existing:
                    continue
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text(
                            f"CREATE INDEX {idx_name} ON `{table}` ({columns})"
                        ))
                    _log.info('已创建索引 %s', idx_name)
                except Exception as e:
                    _log.warning('创建索引 %s 失败：%s', idx_name, e)
        except Exception as e:
            _log.warning('索引检查失败：%s', e)


_ensure_performance_indexes()


def _ensure_user_is_active_column():
    """老库兼容：若 User 表缺少 Is_Active 列，启动时补上，默认 True.
    幂等：已存在则跳过，失败只警告不阻塞.
    """
    _log = logging.getLogger('init')
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
            _log.info('已为 User 表补充 Is_Active 列')
        except Exception as e:
            _log.warning('添加 User.Is_Active 列失败：%s', e)


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
                _log.info('已 seed 默认打印点 home=数智维新工作室')
        except Exception as e:
            _log.warning('新表初始化失败：%s', e)


_ensure_new_tables_and_seed()


@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user


from app import print

import os
for sub in ('Upload_Files', 'Upload_Files/BeforeSwitchFile', 'pay_qrcode'):
    os.makedirs(os.path.join(app.static_folder, sub), exist_ok=True)