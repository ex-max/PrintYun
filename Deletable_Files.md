# PrintYun 可删除文件分析

根据对整个项目的代码引用关系和文件用途分析，以下文件可以安全删除。
按风险等级从低到高排列。

---

## 🟢 强烈建议删除（完全无用/垃圾文件）

| 文件/目录 | 大小 | 说明 |
|-----------|------|------|
| `s.html` | 9B | 内容只有 "Not Found"，无任何引用 |
| `resp.html` | 2.5KB | cpolar 的 404 错误页面缓存，不属于项目代码 |
| `t.json` | 0B | 空文件 |
| `tunnels.json` | 0B | 空文件（cpolar 隧道配置残留） |
| `cpolar.log` | 0B | cpolar 日志文件（空） |
| `cpolar.log.20260422` | 430KB | cpolar 历史日志 |
| `cpolar.log.master.log` | 0B | cpolar 日志文件（空） |
| `cpolar.log.master.log.20260422` | 430KB | cpolar 历史日志 |
| `dump.rdb` | 2.7KB | Redis 持久化快照文件，不应入仓 |
| `__pycache__/` | 整个目录 | Python 编译缓存，已在 .gitignore 中 |
| `instance/test_login_debug.db` | 12KB | 临时测试用 SQLite 数据库 |
| `instance/test_route_guard.db` | 12KB | 临时测试用 SQLite 数据库 |
| `logs/` | 整个目录 | 运行时日志，不应入仓（建议加入 .gitignore） |
| `.workbuddy/` | 整个目录 | 第三方工具生成的缓存目录 |

---

## 🟡 建议删除（一次性脚本，任务已完成）

| 文件 | 大小 | 说明 |
|------|------|------|
| `_fix_placeholders.py` | 3.3KB | 一次性修复模板中 `�` 乱码的脚本（第一轮），修复工作已完成 |
| `_fix_placeholders2.py` | 2.5KB | 第二轮修复乱码脚本，已完成 |
| `_fix_placeholders3.py` | 1.1KB | 第三轮修复乱码脚本，已完成 |
| `_mark_paid.py` | 1.2KB | 手动把卡住订单标记为已支付的临时脚本 |
| `_check_local.py` | 576B | 检查本地打印机是否存在的一次性诊断脚本 |
| `_serve.py` | 184B | 使用 waitress 启动服务的测试脚本（正式启动用 run.bat） |
| `test_login.py` | 494B | 临时测试登录接口的脚本 |

---

## 🟠 可以删除（废弃/未使用的代码模块）

| 文件 | 大小 | 说明 |
|------|------|------|
| `app/sms.py` | 1.9KB | **旧版 LeanCloud 短信模块**，项目中无任何文件引用它。实际使用的是 `app/test/ali_sms.py`（阿里云短信） |
| `app/test/xorpay_vx.py` | 1.1KB | **未注册的蓝图**：定义了 `vx_pay` 蓝图但从未在 `__init__.py` 中注册，完全死代码 |
| `app/test/test_route.py` | 1.1KB | 测试用蓝图（`/test/select_pay`），虽然在 `__init__.py` 中注册了，但功能完全是 `printer.py` 的简化版，生产环境不需要。**删除后需同步移除 `__init__.py` 中的注册代码** |

> ⚠️ 删除 `test_route.py` 后需要修改 `app/__init__.py`，移除以下两行：
> ```python
> from app.test.test_route import test     # 第 18 行
> app.register_blueprint(test, url_prefix='/test')  # 第 61 行
> ```

---

## 🔵 可选删除（文档类，按需保留）

| 文件 | 大小 | 说明 |
|------|------|------|
| `question.md` | 51KB | 之前 AI 对话生成的问题诊断和修复记录，内容已过时（修复已完成），可归档或删除 |
| `printyun_md.md` | 18.7KB | 项目早期分析文档，部分信息已过时（如价格、路由等），与 `API.md` / `API_Analysis.md` 存在重复 |
| `API.md` | 20KB | 如果你已有更新的 `API_Analysis.md`，可以考虑合并后删除旧版 |
| `Pipfile` / `Pipfile.lock` | 18.8KB | 如果你只使用 `requirements.txt` 管理依赖，这两个 pipenv 配置文件可以删除 |

---

## ❌ 不建议删除（虽然看起来可删但有用途）

| 文件 | 说明 |
|------|------|
| `venv/` | 虚拟环境目录，已在 .gitignore 中，不会入仓，本地开发需要 |
| `.idea/` | JetBrains IDE 配置，已在 .gitignore 中 |
| `.env` | 环境变量配置，已在 .gitignore 中，包含运行所需的密钥 |
| `.env.example` | 环境变量模板，供新开发者参考 |
| `cleanup_files.py` | 定时清理上传文件的工具脚本，生产环境有用 |
| `worker.py` | RQ Worker 启动入口，核心文件 |
| `printer_daemon.py` | 打印守护进程入口，核心文件 |

---

## 建议同步更新 `.gitignore`

删除文件后，建议在 `.gitignore` 中补充以下规则，防止类似文件再次入仓：

```gitignore
# Redis
dump.rdb

# 日志
logs/

# cpolar
cpolar.log*
tunnels.json

# 临时测试
instance/*.db

# 第三方工具
.workbuddy/
```

---

## 汇总

| 类别 | 文件数 | 可释放空间 |
|------|--------|-----------|
| 🟢 强烈建议删除 | 14 个文件/目录 | ~875 KB + 日志 |
| 🟡 建议删除 | 7 个文件 | ~9.4 KB |
| 🟠 可以删除 | 3 个代码文件 | ~4.1 KB |
| 🔵 可选删除 | 4 个文档文件 | ~108 KB |
| **合计** | **~28 项** | **~1 MB** |
