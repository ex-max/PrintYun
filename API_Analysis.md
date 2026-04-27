# PrintYun 项目接口完整分析

---

## 一、外部调用接口（项目 → 第三方服务）

项目中通过 `requests` 库或 SDK 主动调用的外部 API：

### 1. XORPay（微信支付聚合平台）

| 文件 | 接口 URL | 方法 | 用途 |
|------|----------|------|------|
| `app/control/json.py:50` | `https://xorpay.com/api/pay/xxxx` | POST | **创建微信支付订单**：将订单信息发送到 XORPay 生成微信支付二维码 |
| `app/control/json.py:143` | `https://xorpay.com/api/query/{aoid}` | GET | **查询支付状态**：根据 aoid 查询微信支付订单是否已付款 |
| `app/utils.py:130` | `https://xorpay.com/api/query/{aoid}` | GET | **查询支付状态**（工具函数封装，被 `native_url` 回调使用） |

### 2. 支付宝（通过 python-alipay-sdk）

| 文件 | SDK 方法 | 用途 |
|------|----------|------|
| `app/test/ali_pay.py:114` | `alipay.api_alipay_trade_wap_pay()` | **手机 H5 支付**：生成手机端支付宝付款链接，用户跳转到支付宝付款 |
| `app/test/ali_pay.py:136` | `alipay.api_alipay_trade_page_pay()` | **电脑网页支付**：生成 PC 端支付宝付款页面链接 |
| `app/test/ali_pay.py:159` | `alipay.verify()` | **验签**：验证支付宝回调参数的签名合法性 |
| `app/control/local_print.py:167` | `alipay.api_alipay_trade_precreate()` | **当面付（扫码付）**：为本地打印订单生成支付宝二维码 |
| `app/control/local_print.py:178` | `alipay.api_alipay_trade_wap_pay()` | **降级 H5 支付**：扫码付不可用时降级为手机网页支付 |
| `app/control/local_print.py:228` | `alipay.api_alipay_trade_query()` | **主动查询订单**：桌面端轮询时主动查询支付宝确认是否已付款 |

### 3. 阿里云短信（Dypnsapi 号码认证服务）

| 文件 | SDK 方法 | 用途 |
|------|----------|------|
| `app/test/ali_sms.py:128` | `client.send_sms_verify_code_with_options()` | **发送短信验证码**：通过阿里云向手机发送验证码（注册/找回密码） |
| `app/test/ali_sms.py:167` | `client.check_sms_verify_code_with_options()` | **校验短信验证码**：向阿里云验证用户输入的验证码是否正确 |

### 4. LeanCloud 短信（旧版，已弃用）

| 文件 | 接口 URL | 方法 | 用途 |
|------|----------|------|------|
| `app/sms.py:34` | `https://api.avoscloud.com/1.1/requestSmsCode` | POST | **发送验证码**（旧版 LeanCloud，已被阿里云短信替代） |
| `app/sms.py:57` | `https://api.avoscloud.com/1.1/verifySmsCode/{code}` | POST | **校验验证码**（旧版 LeanCloud，已被替代） |

### 5. 本地打印守护进程 → Flask 后端

桌面端守护程序（`local_printer/`）通过 HTTP 调用自身 Flask 后端的 `/local/*` 接口：

| 文件 | 接口路径 | 方法 | 用途 |
|------|----------|------|------|
| `local_printer/web_consumer.py:41` | `/local/claim_web_order` | POST | **领取 Web 订单**：从 Redis 拿到订单 ID 后，原子领取订单（状态 1→2） |
| `local_printer/web_consumer.py:57` | `/local/update_status` | POST | **更新订单状态**：打印成功(3)/失败(-1) 后回报后端 |
| `local_printer/job_processor.py:28` | `/local/create_order` | POST | **创建本地打印订单**：本地拦截打印任务后创建付费订单 |
| `local_printer/job_processor.py:52` | `/local/pay_url` | GET | **获取支付链接**：获取支付宝二维码数据，桌面弹窗展示 |
| `local_printer/job_processor.py:69` | `/local/check_status` | GET | **轮询付款状态**：桌面弹窗轮询是否已付款 |
| `local_printer/job_processor.py:85` | `/local/update_status` | POST | **更新订单状态**：本地打印完成/取消后更新 |

---

## 二、内部 Flask 路由接口（项目对外暴露）

### 1. 前台页面路由（无前缀）

| 路由 | 文件 | 用途 |
|------|------|------|
| `GET /health` | `app/print.py:8` | **健康检查**：检测 DB + Redis + 磁盘状态 |
| `GET /` `/index` `/toindex` | `app/print.py:39` | **首页** |
| `GET /vx` | `app/print.py:47` | 微信页面 |
| `GET /pphoto` | `app/print.py:53` | 普通照片页面 |
| `GET /service` | `app/print.py:59` | 联系客服页面 |
| `GET /sphoto` | `app/print.py:65` | 身份证照页面 |
| `GET /text` | `app/print.py:71` | 文本打印页面 |
| `GET /todi` | `app/print.py:77` | 优惠专区页面 |
| `GET /user` | `app/print.py:83` | 用户页面 |
| `GET /zphoto` | `app/print.py:88` | 证件照页面 |

---

### 2. 用户认证（`/login/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/login/register` | GET/POST | `app/control/login.py:51` | **用户注册**（含短信验证码获取） |
| `/login/login` | GET/POST | `app/control/login.py:121` | **用户登录** |
| `/login/logout` | GET | `app/control/login.py:150` | **退出登录** |
| `/login/findpassword` | GET/POST | `app/control/login.py:92` | **找回密码**（短信验证） |
| `/login/change_password` | GET/POST | `app/control/login.py:159` | **修改密码** |
| `/login/me` | GET | `app/control/login.py:179` | **个人中心**：账户信息 + 我的订单列表 |
| `/login/me/status_check` | GET | `app/control/login.py:246` | **AJAX 轮询订单状态变化** |
| `/login/order/<tn>/cancel` | POST | `app/control/login.py:294` | **取消未支付订单**（软删除，状态→-2） |
| `/login/order/<tn>/reprint` | POST | `app/control/login.py:323` | **再次打印**：复制旧订单参数生成新待支付订单 |

---

### 3. 打印业务（`/printer/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/printer/select` | GET/POST | `app/control/printer.py:34` | **下单页面**：上传文件、选择参数、创建订单 |
| `/printer/convert_status` | GET | `app/control/printer.py:213` | **轮询文件转换**：前端轮询 Office→PDF 转换是否完成 |
| `/printer/pay_page` | GET | `app/control/printer.py:295` | **支付页中转**：转换完成后渲染支付页模板 |
| `/printer/idcard` | GET/POST | `app/control/printer.py:370` | **身份证照上传**：正反面拼版 A4 → 直接支付 |
| `/printer/print` | GET | `app/control/printer.py:28` | 测试接口（返回固定字符串） |

---

### 4. 支付相关 JSON 接口（`/jsons/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/jsons/js_pay` | POST | `app/control/json.py:18` | **创建微信支付**：调用 XORPay 生成微信支付二维码 |
| `/jsons/native` | GET/POST | `app/control/json.py:64` | **XORPay 支付回调**：支付成功后更新订单状态、推送 Redis 打印队列 |
| `/jsons/delete` | POST | `app/control/json.py:98` | **删除订单**：删除订单记录及关联文件 |
| `/jsons/query_status` | POST | `app/control/json.py:138` | **查询支付状态**：前端轮询 XORPay 支付是否成功 |
| `/jsons/date_times` | GET/POST | `app/control/json.py:153` | **订单查询**：按日期/手机号分页查询订单（layui 表格数据源） |

---

### 5. 支付宝支付（`/cloud_pay/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/cloud_pay/alipay1` | GET/POST | `app/test/ali_pay.py:102` | **手机支付宝跳转**：生成 H5 付款链接并 302 跳转 |
| `/cloud_pay/alipay2` | GET/POST | `app/test/ali_pay.py:124` | **PC 支付宝跳转**：生成 PC 端付款页面并 302 跳转 |
| `/cloud_pay/alipayresult1` | GET/POST | `app/test/ali_pay.py:147` | **支付宝同步回调**：用户付完款浏览器跳回，验签后更新订单 |
| `/cloud_pay/order_status` | GET | `app/test/ali_pay.py:186` | **AJAX 轮询订单状态**：支付页前端轮询是否已付 |
| `/cloud_pay/native` | POST | `app/test/ali_pay.py:208` | **支付宝异步通知**：支付宝服务器回调，验签后确认订单已支付 |

---

### 6. 本地打印守护 API（`/local/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/local/create_order` | POST | `app/control/local_print.py:72` | **创建本地打印订单**：桌面端守护程序创建订单 |
| `/local/pay_url` | GET | `app/control/local_print.py:136` | **获取支付链接**：生成支付宝二维码给桌面弹窗 |
| `/local/check_status` | GET | `app/control/local_print.py:200` | **查询订单状态**：桌面端轮询是否已付款（含主动查询支付宝） |
| `/local/update_status` | POST | `app/control/local_print.py:256` | **更新订单状态**：桌面端打印完成/失败/取消后更新 |
| `/local/claim_web_order` | POST | `app/control/local_print.py:279` | **原子领取 Web 订单**：Redis 消费者领取已付款订单（1→2）并获取打印参数 |

> **注意**：`/local/*` 接口通过 `X-Local-Key` 请求头做机器密钥鉴权，不使用用户登录态。

---

### 7. 后台管理（`/admin/*`）

| 路由 | 方法 | 文件 | 用途 |
|------|------|------|------|
| `/admin/dashboard` | GET | `app/control/admin.py:132` | **仪表盘**：今日指标、7 天趋势、TOP10 用户、颜色/单双面统计 |
| `/admin/queue` | GET | `app/control/admin.py:221` | **打印队列**：查看正在打印/待取件的订单 |
| `/admin/orders` | GET | `app/control/admin.py:245` | **订单中心**：全量订单列表（支持状态/日期/手机号筛选） |
| `/admin/order/<tn>/status` | POST | `app/control/admin.py:309` | **改订单状态**：管理员手动流转订单状态（有限状态机校验） |
| `/admin/users` | GET | `app/control/admin.py:345` | **用户管理**：用户列表 + 消费统计 |
| `/admin/user/<uid>/toggle_active` | POST | `app/control/admin.py:386` | **启用/禁用用户** |
| `/admin/user/<uid>/role` | POST | `app/control/admin.py:398` | **修改用户角色**（admin/guest） |
| `/admin/places` | GET | `app/control/admin.py:416` | **打印点管理** |
| `/admin/look_pdf/<media>` | GET | `app/control/admin.py:101` | **PDF 预览** |
| `/admin/look_picture/<pic>` | GET | `app/control/admin.py:118` | **图片预览** |
| `/admin/check` | GET | `app/control/admin.py:431` | **设备类型检测**（mobile / computer） |

---

## 三、接口调用流程

### Web 云打印流程

```
用户浏览器
  │
  ├── GET /printer/select ───────── 上传文件、选择参数
  │     │
  │     ├── PDF/图片 → 直接创建订单 → 跳支付页
  │     └── Office 文档 → RQ Worker 异步转 PDF
  │           └── 前端轮询 GET /printer/convert_status → 转完后创建订单
  │
  ├── POST /cloud_pay/alipay1 ──── 手机支付宝跳转（H5）
  ├── POST /cloud_pay/alipay2 ──── PC 支付宝跳转（网页）
  ├── POST /jsons/js_pay ───────── 微信支付（XORPay）
  │
  ├── 支付宝回调 ─────────────────────────────────────┐
  │     ├── GET  /cloud_pay/alipayresult1（同步回调）  │→ 更新订单状态 0→1
  │     └── POST /cloud_pay/native（异步通知）         │→ 推送 Redis print_queue
  │                                                    │
  ├── XORPay 回调 ─────────────────────────────────────┤
  │     └── POST /jsons/native                         │→ 更新订单状态 0→1
  │                                                    │→ 推送 Redis print_queue
  │                                                    │
  └── 前端轮询状态                                      │
        ├── POST /jsons/query_status（XORPay 支付）     │
        └── GET  /cloud_pay/order_status（支付宝支付）   │
                                                       ▼
                                              Redis print_queue
                                                       │
                                              桌面守护进程 blpop
                                                       │
                                              POST /local/claim_web_order（原子领取 1→2）
                                                       │
                                              SumatraPDF 打印到物理打印机
                                                       │
                                              POST /local/update_status（3=完成 / -1=失败）
```

### 本地打印拦截流程

```
应用程序 → 虚拟打印机 → PS 文件 → job_processor
  │
  ├── PS → PDF 转换（Ghostscript）
  ├── 读取 PDF 页数
  ├── POST /local/create_order ──── 创建订单
  ├── GET  /local/pay_url ───────── 获取支付宝二维码
  ├── 桌面弹窗展示二维码
  ├── GET  /local/check_status ──── 轮询付款（含主动查询支付宝）
  ├── SumatraPDF 打印到真实打印机
  └── POST /local/update_status ─── 更新最终状态
```

---

## 四、总结

| 类别 | 数量 | 说明 |
|------|------|------|
| **外部第三方 API** | 8 类 | 支付宝 SDK (6)、XORPay (2)、阿里云短信 (2)、LeanCloud (2, 已弃用) |
| **内部 Flask 路由** | ~40 个 | 前台页面 (10)、用户认证 (9)、打印业务 (5)、支付回调 (5+5)、后台管理 (11)、本地打印 (5) |
| **守护进程→后端** | 6 个 | 本地打印组件通过 HTTP 调用 `/local/*` 接口 |




