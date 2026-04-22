import os

SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-secret-key-change-me'
SQLALCHEMY_TRACK_MODIFICATIONS = False
# 数据库自行配置：优先环境变量 DATABASE_URL
SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    'mysql+pymysql://root:123456@localhost:3306/print?charset=utf8mb4',
)

POST_PER_PAGE = 5

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
