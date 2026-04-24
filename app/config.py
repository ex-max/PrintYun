import os

SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-secret-key-change-me'
SQLALCHEMY_TRACK_MODIFICATIONS = False
# 数据库自行配置：优先环境变量 DATABASE_URL
SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    'mysql+pymysql://root:123456@localhost:3306/print?charset=utf8mb4',
)

# ---- 连接池调优 ----
SQLALCHEMY_POOL_SIZE = 10           # 连接池大小（默认 5 太小）
SQLALCHEMY_MAX_OVERFLOW = 20        # 峰值溢出连接
SQLALCHEMY_POOL_RECYCLE = 3600      # 1 小时回收，避免 MySQL 8 小时断连
SQLALCHEMY_POOL_PRE_PING = True     # 取连接前先 ping，防死连接

POST_PER_PAGE = 5

# ---- 上传限制 ----
MAX_CONTENT_LENGTH = 20 * 1024 * 1024   # 最大上传 20MB

# ---- 静态资源浏览器缓存 ----
SEND_FILE_MAX_AGE_DEFAULT = 86400       # 静态文件缓存 24 小时

# Session cookie 跨站放行：支付宝/xorpay 跳回时需要带 session
# 通过环境变量显式控制，避免在本地 HTTP 开发时浏览器因 Secure=True 拒绝保存 cookie
# 生产部署 HTTPS 时在 .env 里设 SESSION_COOKIE_SECURE=true
def _env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')

SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', default=False)
SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

