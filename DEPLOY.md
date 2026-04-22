# 自助云打印（printyun）部署指南

> 一份覆盖 **本地开发、Docker、Linux 生产** 三种模式的完整部署手册。
> 最低可用配置只需：Python 3.9+、MySQL 5.7+、Redis 5+ 三项。

---

## 一、架构概览

项目由 **3 个进程** 协作，可分别起停：

| 进程 | 入口文件 | 职责 | 依赖 |
|---|---|---|---|
| Web 服务 | `app`（`flask run` / `gunicorn`） | 处理 HTTP 请求：上传、下单、支付、后台管理 | MySQL |
| RQ Worker | `worker.py` | 从 Redis 队列 `to_pdf` 领任务，把 Office 文档转成 PDF，通过 Pub/Sub 回传结果 | Redis、LibreOffice/soffice |
| 自动打印守护 | `printer_daemon.py` | 轮询 `Order` 表，把已支付订单送到本地打印机 | MySQL、SumatraPDF、物理打印机 |

> 只想看**在线上传 + 支付**功能：启动 Web + Worker 即可。
> 想要**全自动打印**：再启动 Printer Daemon。

---

## 二、环境要求

### 基础运行时
- **Python** 3.9 ～ 3.12（推荐 3.11）
- **MySQL** 5.7 / 8.0（或使用 `DATABASE_URL` 切 SQLite/PostgreSQL）
- **Redis** 5+（Worker 与文档转换 Pub/Sub 用）

### 文档转换
- **LibreOffice / soffice**（把 doc/docx/ppt/xlsx 转 PDF）
  - Windows：安装 [LibreOffice](https://www.libreoffice.org/) 后把 `program\soffice.exe` 所在目录加入 `PATH`
  - Ubuntu：`sudo apt-get install -y libreoffice --no-install-recommends`
  - Docker 镜像默认未安装，见第 5 节

### 可选：真机打印
- **SumatraPDF**（Windows 下用命令行静默打印）
  - 下载 https://www.sumatrapdfreader.org/download-free-pdf-viewer
  - 记下 `SumatraPDF.exe` 的完整路径，填到 `.env` 的 `SUMATRA_PATH`

### 可选：短信 / 支付
- 阿里云 SMS（手机号验证码）— [开通指南](https://help.aliyun.com/product/44282.html)
- 微信支付：本项目使用第三方 [xorpay](https://xorpay.com) 聚合，也可自行接入官方
- 支付宝：需要 3 份密钥文件放在 `app/certs/`

---

## 三、配置文件：`.env`

在项目根目录创建 `.env`（**不要提交到 git**），按模块填写：

```ini
# ============ 应用密钥 ============
# 生成：python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=请替换为你自己的 64 位随机字符串

# ============ 数据库 ============
DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/print?charset=utf8mb4
# SQLite（调试用，无需装 MySQL）
# DATABASE_URL=sqlite:///dev.db

# ============ Redis（Worker / 支付通知需要）============
REDISTOGO_URL=redis://:123456@localhost:6379
# 无密码：redis://localhost:6379

# ============ Session Cookie（开发 HTTP 场景必须）============
# 本地 HTTP 必须 False，否则浏览器拒绝保存 session 导致"登录不上"
SESSION_COOKIE_SECURE=false
# 生产 HTTPS 再设 true + SameSite=None（方便支付回跳带 session）
# SESSION_COOKIE_SECURE=true
# SESSION_COOKIE_SAMESITE=None
SESSION_COOKIE_SAMESITE=Lax

# ============ 阿里云短信（注册验证码）============
ALIYUN_AK=LTAI5txxxxxxxxxxxxxxxx
ALIYUN_SK=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALIYUN_SMS_SIGN=你的签名
ALIYUN_SMS_TEMPLATE=SMS_123456789

# ============ xorpay 微信支付签名密钥 ============
XORPAY_SECRET=你在 xorpay.com 拿到的 secret

# ============ 自动打印守护（只在真机打印时需要）============
# PowerShell 查本机打印机：Get-Printer | Select Name
PRINTER_NAME=TOSHIBA e-STUDIO5015AC-13461781
SUMATRA_PATH=C:\Users\YourName\AppData\Local\SumatraPDF\SumatraPDF.exe
PRINTER_POLL_SECONDS=3
PRINTER_TIMEOUT_SECONDS=120

# ============ Flask 开发配置 ============
FLASK_APP=app
FLASK_ENV=development
FLASK_DEBUG=1
```

> **支付宝** 还需把 3 份密钥放到 `app/certs/`（应用私钥、公钥、支付宝公钥），文件名见 `app/test/ali_pay.py` 里的 `load_key_from_file` 调用。

---

## 四、本地开发部署

### 4.1 通用步骤（Windows / Linux / macOS）

```bash
# 1. 拉代码
git clone <仓库地址> printyun
cd printyun

# 2. 建虚拟环境
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. 装依赖
pip install -r requirements.txt

# 4. 启动 MySQL / Redis（用 Docker 最快）
docker run -d --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=123456 -e MYSQL_DATABASE=print mysql:8
docker run -d --name redis -p 6379:6379 redis:7 redis-server --requirepass 123456

# 5. 配置 .env（复制第 3 节模板，填真实值）
# 建议：本地开发把 SESSION_COOKIE_SECURE=false

# 6. 初始化数据库 + 创建管理员账号
flask initdb
# 按提示输入管理员手机号（11 位）和密码（两遍）
# 完成后会在 User 表插入一条 Role='admin' 的记录

# 7. 启动 Web（第一个终端）
flask run --host=0.0.0.0 --port=8001

# 8. 启动 Worker（第二个终端，用于 Office 转 PDF）
python worker.py

# 9. (可选) 启动自动打印守护（第三个终端）
python printer_daemon.py
```

打开 <http://127.0.0.1:8001/index> 即可访问前台首页。

### 4.2 Windows 一键脚本

项目根目录已自带三个 `.bat`：

| 脚本 | 作用 |
|---|---|
| `run.bat` | 启动 Flask Web 服务 |
| `run_worker.bat` | 启动 RQ Worker（Office→PDF 转换） |
| `run_daemon.bat` | 启动自动打印守护进程 |

**首次启动顺序**：
1. 先执行 `run.bat`（会自动建 venv、装 python-dotenv、检查 .env）
2. 再开一个 cmd 跑 `run_worker.bat`
3. 真机打印再跑 `run_daemon.bat`

### 4.3 数据库表结构升级

如果从老版本升级（`Password_Hash` 列是 `VARCHAR(128)`），在 MySQL 里执行：

```sql
ALTER TABLE `User` MODIFY COLUMN `Password_Hash` VARCHAR(255);
```

> 老版本 Werkzeug 默认 `scrypt` 会生成 >160 字节的哈希，被 `VARCHAR(128)` 截断后密码验证必失败。新版代码已固定 `pbkdf2:sha256`（长度 ~103 字节），但**扩列依然建议做**，避免第三方升级 Werkzeug 时再次踩坑。

---

## 五、Docker 部署

### 5.1 自带 Dockerfile（单容器）

仓库自带的 `dockerfile` 基于 `ubuntu:16.04`，只打包了 Web + Worker 两个进程（supervisord 统一托管），**不含 MySQL / Redis / LibreOffice**，需要外部提供。

```bash
# 构建镜像
docker build -t printyun .

# 运行（依赖的 MySQL / Redis 请自行开容器，并把 .env 里的 host 改成对应容器名）
docker run -d --name printyun \
  -p 8001:8001 \
  --env-file .env \
  -v $(pwd)/app/static/Upload_Files:/usr/src/app/app/static/Upload_Files \
  printyun
```

进入容器查看进程：`docker exec -it printyun supervisorctl status`

### 5.2 推荐：docker-compose 编排

新建 `docker-compose.yml`：

```yaml
version: '3.8'
services:
  mysql:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: '123456'
      MYSQL_DATABASE: 'print'
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

  redis:
    image: redis:7
    command: redis-server --requirepass 123456
    ports:
      - "6379:6379"

  web:
    build: .
    env_file: .env
    environment:
      DATABASE_URL: mysql+pymysql://root:123456@mysql:3306/print?charset=utf8mb4
      REDISTOGO_URL: redis://:123456@redis:6379
    depends_on:
      - mysql
      - redis
    ports:
      - "8001:8001"
    volumes:
      - ./app/static/Upload_Files:/usr/src/app/app/static/Upload_Files
      - ./app/certs:/usr/src/app/app/certs:ro

volumes:
  mysql_data:
```

启动：

```bash
docker compose up -d
# 首次启动后进入 Web 容器建表 + 建管理员
docker compose exec web flask initdb
```

### 5.3 Dockerfile 升级建议

原生 `ubuntu:16.04` + `python3-pip` 版本过老且无法装 LibreOffice 的最新版。生产可改为：

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice --no-install-recommends \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY supervisord.conf /etc/supervisord.conf
COPY printyun.conf /etc/supervisor/
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8001
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
```

---

## 六、Linux 生产部署（Gunicorn + Supervisor + Nginx）

### 6.1 系统依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
                    mysql-server redis-server nginx supervisor \
                    libreoffice --no-install-recommends
```

### 6.2 部署代码

```bash
sudo mkdir -p /opt/printyun && sudo chown $USER /opt/printyun
git clone <仓库> /opt/printyun
cd /opt/printyun

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn

# 配置 .env
vim .env     # 参照第 3 节

# 初始化数据库
export FLASK_APP=app
flask initdb
```

### 6.3 Supervisor 托管 Web + Worker

把仓库里 `printyun.conf` 拷到 `/etc/supervisor/conf.d/printyun.conf`，路径按实际调整：

```ini
[program:printyun-web]
command=/opt/printyun/venv/bin/gunicorn -w 4 -b 127.0.0.1:8001 app:app
directory=/opt/printyun
autostart=true
autorestart=true
stdout_logfile=/var/log/printyun/web.log
stderr_logfile=/var/log/printyun/web.err
environment=PATH="/opt/printyun/venv/bin:%(ENV_PATH)s"

[program:printyun-worker]
command=/opt/printyun/venv/bin/python worker.py
directory=/opt/printyun
autostart=true
autorestart=true
stdout_logfile=/var/log/printyun/worker.log
stderr_logfile=/var/log/printyun/worker.err
environment=PATH="/opt/printyun/venv/bin:%(ENV_PATH)s"
```

加载配置：

```bash
sudo mkdir -p /var/log/printyun
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
```

### 6.4 Nginx 反向代理（HTTPS）

```nginx
server {
    listen 80;
    server_name print.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name print.example.com;

    ssl_certificate     /etc/letsencrypt/live/print.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/print.example.com/privkey.pem;

    client_max_body_size 50M;   # 允许上传大文件

    location /static/ {
        alias /opt/printyun/app/static/;
        expires 7d;
    }

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

**HTTPS 部署后** 把 `.env` 里 Session Cookie 切成：

```ini
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=None
```

这样支付宝/微信支付回跳时 session 才会被浏览器带回来。

### 6.5 HTTPS 证书

免费方案：[certbot](https://certbot.eff.org/) + Let's Encrypt

```bash
sudo snap install --classic certbot
sudo certbot --nginx -d print.example.com
```

---

## 七、常用运维命令

| 操作 | 命令 |
|---|---|
| 初始化数据库 + 建 admin | `flask initdb` |
| 查看 Web 进程日志 | `sudo supervisorctl tail -f printyun-web` |
| 查看 Worker 日志 | `sudo supervisorctl tail -f printyun-worker` |
| 重启 Web | `sudo supervisorctl restart printyun-web` |
| 手动触发转换（测试 Worker） | `rq info -u redis://localhost:6379` |
| Redis 队列清空 | `redis-cli -a 123456 flushdb`（谨慎）|
| 备份 MySQL | `mysqldump -uroot -p print > print_$(date +%F).sql` |

---

## 八、常见问题

### Q1 登录提示密码错误但密码没问题
**原因**：`Password_Hash` 列只有 `VARCHAR(128)`，Werkzeug 新版 scrypt 哈希 >160 字节被截断。
**修复**：执行 `ALTER TABLE User MODIFY COLUMN Password_Hash VARCHAR(255);` 并重置密码（新代码已固定用 pbkdf2:sha256，长度 ≤ 128）。

### Q2 本地 HTTP 登录后马上"不认识"，跳回登录页
**原因**：`.env` 里 `SESSION_COOKIE_SECURE=true` 导致 HTTP 下浏览器拒绝保存 session cookie。
**修复**：本地开发改成 `SESSION_COOKIE_SECURE=false`。

### Q3 上传 Word/PPT 一直卡在转换
**原因**：Worker 没起、`soffice` 不在 `PATH`、Redis 连不上。
**修复**：
- 本地执行 `soffice --version` 能输出就 OK；
- `python worker.py` 看是否报错；
- 检查 `REDISTOGO_URL` 密码。

### Q4 `flask initdb` 报 `ModuleNotFoundError: No module named 'app'`
**原因**：`FLASK_APP` 未设置。
**修复**：
```bash
# Linux / macOS
export FLASK_APP=app
# Windows PowerShell
$env:FLASK_APP="app"
# Windows cmd
set FLASK_APP=app
```
或者在 `.env` 里写 `FLASK_APP=app`，然后 `flask` 命令会自动识别。

### Q5 普通用户登录后被带到了 "后台管理系统"
**原因**：老代码 `next_page` 优先级高于角色分流；或者 `/admin/*` 没有角色守卫。
**修复**：已在最新代码中修复：
- `/admin/*` 强制 `Role=='admin'`
- 普通用户登录后 `next` 被完全忽略，强制回前台首页 `/index`

### Q6 支付成功页一直转圈 / 回跳 401
**原因**：HTTPS 上 session cookie 没写 `SameSite=None; Secure`。
**修复**：`.env` 设 `SESSION_COOKIE_SECURE=true` + `SESSION_COOKIE_SAMESITE=None`，并确保 Nginx 传了 `X-Forwarded-Proto https`（`app/__init__.py` 的 `ProxyFix` 会识别）。

### Q7 打印机不工作 / 订单卡在状态 1
**原因**：`printer_daemon.py` 没启、打印机名不对、SumatraPDF 路径错。
**修复**：
- `Get-Printer | Select Name` 确认打印机名与 `.env` 中 `PRINTER_NAME` 一致；
- `SUMATRA_PATH` 指向真实 `SumatraPDF.exe`；
- 看 daemon 日志：`tail -f` 或控制台输出。

---

## 九、路由边界速查

| 分类 | URL 前缀 | 访问控制 |
|---|---|---|
| 云打印**平台**（前台） | `/`, `/index`, `/text`, `/pphoto`, `/zphoto`, `/sphoto`, `/vx`, `/todi`, `/user`, `/service` | 任何人可访问 |
| 登录/注册/找回 | `/login/*` | 任何人可访问 |
| 上传下单 | `/printer/select` | 登录即可 |
| 云打印**后台管理系统** | `/admin/*` | **仅 Role=admin** |
| 支付/订单 JSON 接口 | `/jsons/*` | 登录即可 |
| 静态资源 | `/static/*` | 任何人可访问 |

---

## 十、安全上线 Checklist

部署到公网前请逐条确认：

- [ ] `.env` 里 `SECRET_KEY` 已替换为真实随机值（≥ 32 字节）
- [ ] MySQL / Redis 密码已改，且**不开放公网端口**
- [ ] `SESSION_COOKIE_SECURE=true` + HTTPS 证书配好
- [ ] 至少有 1 个管理员账号，测试账号已删除或改强密码
- [ ] `app/certs/` 密钥文件**没有提交到 git**（`.gitignore`）
- [ ] 支付回调 URL 已在 xorpay/支付宝后台注册
- [ ] `client_max_body_size` 设置合理（默认 50MB 够大部分文档）
- [ ] Nginx / Gunicorn / Supervisor 日志轮转配置就绪
- [ ] MySQL 定期备份脚本已上（`mysqldump` + cron）
- [ ] 监控：健康检查脚本 `curl https://your-host/index | grep "云打印"`

---

**部署中遇到新坑，欢迎补充。**
