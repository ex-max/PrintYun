   *********************************************************************************************************短信**********************************************************************************************************
 已系统检查项目。代码不完整，存在多处会导致运行失败或功能异常的问题。以下按严重度分类列出，并给出具体修改方式。                                                                                                                                                                                                       
                                                                                                                                                                                                                                                                                                                       
  ---
  一、会导致启动/运行直接报错的问题（必须修）                                                                                                                                                                                                                                                                          
                                                                                                                                                                                                                                                                                                                         1. PyPDF2 API 版本不兼容（app/utils.py）                                                                                                                                                                                                                                                                             
                                                                                                                                                                                                                                                                                                                         已安装 PyPDF2 3.0.1，但代码用的是 1.x 旧 API，PdfFileReader.numPages 实际已被移除。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         
  当前：
  def read_pdf_pages(file):
      with open(file, 'rb') as PdfFileObj:
          PdfReader = PyPDF2.PdfFileReader(PdfFileObj)
          return PdfReader.numPages
  改为：
  def read_pdf_pages(file):
      with open(file, 'rb') as PdfFileObj:
          reader = PyPDF2.PdfReader(PdfFileObj)
          return len(reader.pages)

  2. Flask-SQLAlchemy 3.x 分页调用方式变了（app/models.py）

  activites.paginate(page, per_page=...) 在 Flask-SQLAlchemy 3.1.1 中需要关键字参数，否则会报 TypeError。

  models.py:38-40 改为：
  return activites.paginate(page=page, per_page=current_app.config['POST_PER_PAGE'])
  models.py:124-126 改为：
  return activites.paginate(page=page, per_page=current_app.config['POST_PER_PAGE'])

  3. default=datetime.date.today() 是常见陷阱（app/models.py:20,51）

  写成带括号会在类定义时计算一次，导致所有新记录用的是同一个日期。

  改为（去掉括号，传入可调用对象）：
  Register_Date = db.Column(db.Date, default=datetime.date.today)
  Born_Date_Day = db.Column(db.Date, default=datetime.date.today)

  4. 上传目录不存在（运行时 FileNotFoundError）

  app/static/Upload_Files/、app/static/Upload_Files/BeforeSwitchFile/、app/static/pay_qrcode/ 都没有实际目录，printer.save(upload_path) 和 qrcode.make().save() 会直接崩。

  修复方式（任选其一）：
  - 手动在 app/static/ 下建上述三个子目录
  - 或在 app/__init__.py 末尾加：
  import os
  for sub in ('Upload_Files', 'Upload_Files/BeforeSwitchFile', 'pay_qrcode'):
      os.makedirs(os.path.join(app.static_folder, sub), exist_ok=True)

  5. python-alipay-sdk 新旧版本 API 差异（app/test/ali_pay.py）

  安装的是 3.4.0，但旧版 AliPay(appid=..., debug=True) 初始化参数基本兼容，主要风险点在：
  - debug=True 在 3.x 里要用 verbose=True 或保持 debug=True（3.4 仍可用，但建议确认）
  - 沙箱网关 URL 已变更为 https://openapi-sandbox.dl.alipaydev.com/gateway.do（已是新地址，但该接口近年又改过，需验证）

  建议： 若用真实沙箱测试，查阅当前 python-alipay-sdk 文档并确认 appid、sandbox/prod 开关。

  6. app/test/ali_pay.py 在模块导入阶段就读密钥，任何环节失败整个应用启动失败

  app_private_key_string = open(private).read() 若密钥内容不合法（比如 zhifubaogongyao.txt 不是 PEM 格式）将触发异常。

  建议： 用 try/except 包起来，或做懒加载（第一次调用时再读）。

  ---
  二、逻辑错误（功能跑不通但不崩）

  7. 短信验证码永远相同（app/test/ali_sms.py:8）

  code = random.randrange(1000, 10000)
  这是模块级变量，Flask 进程启动后就固定了。任何用户任何时候获取的验证码都一样。

  改为在 send_sms 内部生成并保存到 session/Redis：
  def send_sms(phone_number):
      code = str(random.randint(1000, 9999))
      # ...
      # 发送 code，同时保存：session[f'sms_{phone_number}'] = code, 并加过期时间
      return code, smsResponse

  def verify_code(form_code, phone_number):
      return str(form_code) == session.get(f'sms_{phone_number}')
  同步修改 app/control/login.py 里 register / findpassword 对 ali_sms.code 的调用。

  8. 前端变量 g.current_userphone 从未赋值（layui_orderForGoods.html:55）

  模板里 var UserName = '{{ g.current_userphone }}' 始终是空字符串。

  改为：
  var UserName = '{{ current_user.Tel_Number }}';

  9. app/control/printer.py 文件扩展名白名单大小写敏感

  if filename[index_point:] in [".pdf", ".jpg", ".png", ".jpeg"]:
  用户上传 .PDF、.JPG 会走到转换分支。

  改为：
  if filename[index_point:].lower() in [".pdf", ".jpg", ".png", ".jpeg"]:

  10. /jsons/delete 无登录校验、无订单归属校验（app/control/json.py:75）

  任何人（包括未登录）都能传订单号删除他人订单 + 删除服务器文件。

  至少加：
  @jsons.route('/delete', methods=['POST'])
  @login_required
  def delete_data():
      g_id = request.form['trade_id'][6:]
      one = Order.query.filter(Order.Trade_Number == g_id).first()
      if not one or (current_user.Role != 'admin' and one.User_Id != current_user.Id):
          return jsonify({'status': 'forbidden'}), 403
      # ... 原有删除逻辑

  11. 同步阻塞 Redis Pub/Sub（app/control/printer.py:144-165）

  在 HTTP 请求内 ps.listen() 死等转换结果，单 worker 会阻塞整个进程。如果 worker.py 没启动，请求会永久挂住。

  短期修复：加超时并显式关闭订阅：
  import time
  ps = conn.pubsub()
  ps.subscribe(str(current_user.Id))
  deadline = time.time() + 30
  try:
      for msg in ps.listen():
          if time.time() > deadline:
              flash('转换超时，请重试')
              return render_template('use_templates/layui_orderForGoods.html', now=now, error=1, form=form)
          if msg['type'] == 'message':
              ...
  finally:
      ps.unsubscribe()
      ps.close()
  长期方案： 改异步 — 转换完成后通过 AJAX 轮询或 WebSocket 通知前端，不在 HTTP 线程里等。

  12. app/__init__.py:40 冗余且有误导

  from app import print, models, printer, admin
  - models、printer、admin 在上面已经间接导入
  - printer 在 app 命名空间内被同名覆盖为蓝图对象 vs 模块

  改为只导入真正需要注册路由的模块：
  from app import print  # 仅为了让 print.py 中的 @app.route 装饰器生效

  13. app/sms.py 和 app/test/ali_sms.py 功能重复

  README 说明修改 app/sms.py，但实际 login.py 里引用的是 app/test/ali_sms.py。
  建议： 删除 app/sms.py，或把它合并到 app/test/ali_sms.py 统一管理。

  ---
  三、配置/凭据安全问题（必须在部署前修）

  14. app/config.py 硬编码敏感信息

  SECRET_KEY = os.getenv('SECRET_KEY','SECRET KEY')
  SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:123456@localhost:3306/print?charset=utf8mb4'
  改为从环境变量读取，且不提供默认：
  SECRET_KEY = os.environ['SECRET_KEY']  # 没设置直接报错
  SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']

  15. app/test/ali_sms.py 泄露了阿里云 AccessKey

  client = AcsClient('LTAI5t9qarBoXiScENVmE4Lg', 'strVyzsoBgHTlzXBQn3odKe45GiE5sTQuing', 'default')
  必须立即：
  1. 登录阿里云控制台 禁用/删除这对 AccessKey
  2. 新建后通过环境变量注入：
  import os
  client = AcsClient(os.environ['ALIYUN_AK'], os.environ['ALIYUN_SK'], 'default')

  16. app/control/json.py:40 硬编码签名密钥

  '55ab2edb80e34ae3bee47b4b32c7e1e5'
  同样改为 os.environ['XORPAY_SECRET']。

  17. app/control/admin.py 文件预览路由未校验路径

  @admin.route("/look_picture/<string:picture>")
  def look_picture(picture):
      return render_template('use_templates/view.html', picture=picture)
  若 view.html 直接把 picture 作为文件路径插入 URL，可被构造成 ../../../etc/passwd 型路径穿越。应做白名单校验：只允许访问当前登录用户的订单文件。

  ---
  四、清理类（不影响运行但该删）

  ┌────────────────────────────────────┬───────────────────────────────────────────────────────────┐
  │                文件                │                           问题                            │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ cookies.txt                        │ 本地 curl 测试遗留的 Cookie，含 session                   │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ test_login.py                      │ 临时测试脚本                                              │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ __pycache__/worker.cpython-312.pyc │ 构建产物                                                  │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ venv/                              │ 不该入仓                                                  │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ app/test/xorpay_vx.py              │ 定义了 vx_pay 蓝图但从未在 __init__.py 注册               │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ app/sms.py                         │ 与 app/test/ali_sms.py 重复                               │
  ├────────────────────────────────────┼───────────────────────────────────────────────────────────┤
  │ requirements.txt                   │ 版本全部是 2019 年的旧版，与当前系统实际运行的 3.x 不匹配 │
  └────────────────────────────────────┴───────────────────────────────────────────────────────────┘

  ---
  五、建议的修改顺序

  1. 先让它跑起来 — 改第 1、2、3、4 条（PyPDF2、分页、default、上传目录）
  2. 初始化数据库 — 运行 flask initdb --tel_number 123456 --password 123456
  3. 本地验证上传 → 转 PDF 流程 — 需同时 python worker.py 且本机装 LibreOffice/soffice 可执行
  4. 修第 7、9、11、12 条逻辑错误 — 让功能真正可用
  5. 安全加固 — 14、15、16、17 条（尤其第 15 条：AccessKey 已公开，必须立即吊销）
  6. 清理仓库 — 四类删除
  7. 更新依赖清单 — 生成新的 requirements.txt

  ---
  六、最紧急提醒

  ▎ app/test/ali_sms.py 中的阿里云 AccessKey LTAI5t9qarBoXiScENVmE4Lg 以明文存在于代码中。如果仓库曾经公开过 (GitHub/Gitee)，请立即去阿里云控制台禁用它，再在本地改成从环境变量读取。否则可能被人盗刷短信。

✻ Sautéed for 13m 19s

❯ 检查短信服务是否配置完成，正确的短信配置服务在ali_sms.py文件中，在网页中是否能否实现                                                                                                                                                                                                                                 

  Searched for 2 patterns, read 3 files (ctrl+o to expand)                                                                                                                                                                                                                                                             
                                                                                                                                                                                                                                                                                                                       
● Bash("E:/Project/Print/printyun-master/venv/Scripts/python.exe" -c "from aliyunsdkcore.client import AcsClient" 2>&1; python -c "from aliyunsdkcore.client import Acs…)
  ⎿  Traceback (most recent call last):                                                                                                                                                                                                                                                                                
       File "<string>", line 1, in <module>                                                                                                                                                                                                                                                                            
     ModuleNotFoundError: No module named 'aliyunsdkcore'                                                                                                                                                                                                                                                              
     ok                                                                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                                                       
● 已对照前端 c_register.html、c_findpassword.html、后端 login.py、app/test/ali_sms.py 完整走了一遍短信流程。结论：当前的短信服务无法在网页上正常工作。既有功能缺陷也有安全隐患。以下按「端到端调用链」指出每一环的问题和修复方式。                                                                                     
                                                                                                                                                                                                                                                                                                                       
  ---                                                                                                                                                                                                                                                                                                                  
  一、现有调用链与断点分析                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    
  前端（c_register.html:163-215）                                                                                                                                                                                                                                                                                      
  1. 用户点「获取验证码」→ JS send_message()                                                                                                                                                                                                                                                                           
  2. 读取 #phone，做正则校验
  3. 启倒计时，调 loadXMLDoc()
  4. loadXMLDoc 发 AJAX GET register?mobile_phone_number=<phone> → 但不处理响应（没绑 onreadystatechange）

  后端（app/control/login.py:24-31）
  elif request.method == 'GET':
      phone_number = request.args.get('mobile_phone_number')
      if phone_number is not None:
          if ali_sms.send_sms(phone_number, ali_sms.code):
              return render_template('forms.html', error_msg=error_msg, form=form)
          else:
              error_msg = 'Failed to get the verification code!'   # ← 没 return，直接掉到最后

  短信模块（app/test/ali_sms.py）
  client = AcsClient('LTAI5t9qarBoXiScENVmE4Lg', 'strVyzsoBgHTlzXBQn3odKe45GiE5sTQuing', 'default')
  code = random.randrange(1000, 10000)   # ← 模块级，进程启动后永远不变

  def send_sms(phpne_number, code):
      ...
      smsResponse = client.do_action(request)
      return smsResponse                  # ← 返回字节流，永远 truthy

  ---
  二、具体问题（按严重度）

  ┌─────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────┐
  │  #  │                                                                   问题                                                                   │                     所在文件                     │                                   影响                                    │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 1   │ AccessKey 明文写死，且已随源码公开                                                                                                       │ ali_sms.py:7                                     │ 严重安全漏洞。需立即到阿里云控制台吊销                                    │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 2   │ 验证码全局共享：code = random.randrange(1000, 10000) 是模块级，Flask 进程启动一次，所有用户都拿到同一个 4 位数字                         │ ali_sms.py:8                                     │ 任何注册过的人都知道"万能验证码"，注册/改密形同虚设                       │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 3   │ send_sms 返回值永远真：client.do_action() 返回 bytes，即使 {"Code":"isv.BUSINESS_LIMIT_CONTROL"} 也是 truthy                             │ ali_sms.py:29、login.py:28                       │ 无法判断短信是否真的发送成功                                              │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 4   │ SMS 模板/签名不合法：SignName="速通互联验证码"、TemplateCode="100001" 必须是该阿里云账号下已审核通过的签名和模板 ID，100001 明显是占位符 │ ali_sms.py:25-26                                 │ 阿里云会直接拒绝，返回如 isv.SMS_TEMPLATE_ILLEGAL                         │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 5   │ AJAX 无响应处理：前端 loadXMLDoc() 没绑 onreadystatechange，用户完全不知道是否发送成功                                                   │ c_register.html:209-216、c_findpassword.html:219 │ 用户体验差，失败也显示"倒计时中"                                          │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 6   │ 后端发送成功后返回整张 HTML 页面，而不是 JSON                                                                                            │ login.py:29                                      │ 前端 AJAX 拿到一整坨 HTML，完全没用                                       │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 7   │ 失败分支不返回：error_msg = '...' 后穿透到最底行 return render_template('use_templates/c_register.html', form=form)，丢失错误信息        │ login.py:30-31                                   │ 短信服务故障时用户看到的是空表单                                          │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 8   │ findpassword 页 AJAX 硬编码 register URL                                                                                                 │ c_findpassword.html:223                          │ 找回密码页按钮实际调用注册接口。靠"全局 code 共享"这个 BUG 才歪打正着能用 │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 9   │ verify_code 和 send_sms 通过模块全局变量传递：login.py 调用时写的是 ali_sms.code，而不是"这个手机号本次收到的验证码"                     │ login.py:28,36,57                                │ 没有手机号↔验证码的绑定，A 手机号拿到的码可以通过 B 手机号验证            │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 10  │ 无过期时间、无频率限制、无一次性使用：code 不过期、没有 60 秒冷却（只是前端 JS 做了个倒计时）、不会用后失效                              │ ali_sms.py                                       │ 短信轰炸风险 + 老验证码永远有效                                           │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 11  │ 参数名拼写错误 phpne_number → phone_number                                                                                               │ ali_sms.py:12                                    │ 代码可读性差                                                              │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 12  │ IntegerField vs 字符串对比：form.v_code.data 是 int，ali_sms.code 也是 int，这个目前靠类型巧合一致，正规做法应统一用字符串               │ forms.py:19, 65、ali_sms.py:33                   │ 改成字符串也更稳妥                                                        │
  ├─────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ 13  │ venv 里没装 aliyunsdkcore：系统 Python 装了，但 venv 是空的；从 venv 启动会 ModuleNotFoundError: aliyunsdkcore                           │ venv/Lib/site-packages 为空                      │ 一启动就崩                                                                │
  └─────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────┘

  ---
  三、结论：当前在网页上不能正常发送短信

  - 如果 AccessKey 还有效 → 会走到阿里云 API，但因模板 ID 100001 不合法，阿里云返回错误；前端又不显示，用户看到倒计时结束但什么都没发生
  - 如果用全局 code 巧合一致，注册/改密能走通——但任意手机号都能用相同的 4 位数通过，等于没验证
  - 如果你在 venv 里运行 flask run，连启动都失败

  ---
  四、如何修（给出可直接替换的代码）

  修复 1：重写 app/test/ali_sms.py

  # -*- coding: utf-8 -*-
  import os, json, random, time
  from aliyunsdkcore.client import AcsClient
  from aliyunsdkcore.request import CommonRequest
  from flask import session

  _AK = os.environ.get('ALIYUN_AK')
  _SK = os.environ.get('ALIYUN_SK')
  _SIGN = os.environ.get('ALIYUN_SMS_SIGN', '速通互联')
  _TEMPLATE = os.environ.get('ALIYUN_SMS_TEMPLATE')   # 必须是阿里云已审批的模板ID，如 SMS_xxxxxxxxx
  _TTL = 300   # 验证码有效期 5 分钟
  _COOLDOWN = 60  # 同一手机号 60 秒内不能重复发

  _client = AcsClient(_AK, _SK, 'default') if (_AK and _SK) else None


  def send_sms(phone_number):
      """给指定手机号发送验证码，返回 (ok: bool, msg: str)"""
      if not _client or not _TEMPLATE:
          return False, '短信服务未配置'

      # 冷却判断
      last = session.get(f'sms_last_{phone_number}', 0)
      if time.time() - last < _COOLDOWN:
          return False, f'请 {_COOLDOWN} 秒后再试'

      code = str(random.randint(1000, 9999))
      req = CommonRequest()
      req.set_accept_format('json')
      req.set_domain('dysmsapi.aliyuncs.com')
      req.set_method('POST')
      req.set_protocol_type('https')
      req.set_version('2017-05-25')
      req.set_action_name('SendSms')
      req.add_query_param('PhoneNumbers', phone_number)
      req.add_query_param('SignName', _SIGN)
      req.add_query_param('TemplateCode', _TEMPLATE)
      req.add_query_param('TemplateParam', json.dumps({'code': code}))

      try:
          raw = _client.do_action_with_exception(req)
          resp = json.loads(raw)
      except Exception as e:
          return False, f'发送失败: {e}'

      if resp.get('Code') != 'OK':
          return False, resp.get('Message', '发送失败')

      session[f'sms_code_{phone_number}'] = code
      session[f'sms_expire_{phone_number}'] = time.time() + _TTL
      session[f'sms_last_{phone_number}'] = time.time()
      return True, 'OK'


  def verify_code(phone_number, form_code):
      saved = session.get(f'sms_code_{phone_number}')
      expire = session.get(f'sms_expire_{phone_number}', 0)
      if not saved or time.time() > expire:
          return False
      if str(form_code).strip() != saved:
          return False
      # 一次性
      session.pop(f'sms_code_{phone_number}', None)
      session.pop(f'sms_expire_{phone_number}', None)
      session.pop(f'sms_last_{phone_number}', None)
      return True

  修复 2：重写 app/control/login.py 的 register / findpassword

  from flask import jsonify
  # 其他 import 保持

  @login.route("/register", methods=['POST', 'GET'])
  def register():
      if current_user.is_authenticated:
          return redirect(url_for('admin.inded_select'))
      form = Register()

      # AJAX 获取验证码
      phone_number = request.args.get('mobile_phone_number')
      if phone_number is not None and request.method == 'GET':
          ok, msg = ali_sms.send_sms(phone_number)
          return jsonify({'success': ok, 'msg': msg})

      if form.validate_on_submit():
          tel = str(form.tel.data)
          if ali_sms.verify_code(tel, form.v_code.data):
              user = User(Tel_Number=tel)
              user.set_password(form.password1.data)
              db.session.add(user)
              db.session.commit()
              return redirect(url_for('login.back_login'))
          return render_template('use_templates/c_register.html',
                                 error_msg='验证码不正确或已过期', form=form)
      return render_template('use_templates/c_register.html', form=form)


  @login.route("/findpassword", methods=['POST', 'GET'])
  def findpassword():
      form = Findpassword()

      phone_number = request.args.get('mobile_phone_number')
      if phone_number is not None and request.method == 'GET':
          ok, msg = ali_sms.send_sms(phone_number)
          return jsonify({'success': ok, 'msg': msg})

      if form.validate_on_submit():
          tel = str(form.tel.data)
          if ali_sms.verify_code(tel, form.v_code.data):
              user = User.query.filter_by(Tel_Number=tel).first()
              if user:
                  user.set_password(form.password1.data)
                  db.session.commit()
                  return redirect(url_for('login.back_login'))
          return render_template('use_templates/c_findpassword.html',
                                 error_msg='验证码不正确或已过期', form=form)
      return render_template('use_templates/c_findpassword.html', form=form)

  修复 3：前端 c_register.html 和 c_findpassword.html 的 loadXMLDoc()

  function loadXMLDoc() {
      var xmlhttp = new XMLHttpRequest();
      xmlhttp.onreadystatechange = function () {
          if (xmlhttp.readyState === 4) {
              var ok = false, msg = '';
              try {
                  var r = JSON.parse(xmlhttp.responseText);
                  ok = r.success; msg = r.msg;
              } catch (e) { msg = '服务器响应异常'; }
              if (!ok) {
                  alert(msg || '发送失败');
                  // 立即恢复按钮
                  window.clearInterval(InterValObj);
                  document.getElementById("getCode").removeAttribute("disabled");
                  document.getElementById("getCode").value = "获取验证码";
              }
          }
      };
      xmlhttp.open("GET", "register?mobile_phone_number=" + phone_number, true);
      xmlhttp.send();
  }

  ▎ c_findpassword.html 里同样要修，并把 URL 改成 "findpassword?mobile_phone_number=" + phone_number（当前代码是 register?...，调用错了接口）。

  修复 4：环境准备

  1. 立即吊销 LTAI5t9qarBoXiScENVmE4Lg 这对 AccessKey（已公开）
  2. 到阿里云控制台：
    - 短信服务 → 国内消息 → 签名管理：申请一个签名（如"速通互联"），等待审核通过
    - 短信服务 → 国内消息 → 模板管理：申请一个验证码模板，内容类似 您的验证码是${code}，5分钟内有效，拿到模板 ID（形如 SMS_123456789）
  3. 在运行环境注入环境变量：
  # Windows CMD
  set ALIYUN_AK=新的AccessKeyId
  set ALIYUN_SK=新的AccessKeySecret
  set ALIYUN_SMS_SIGN=速通互联
  set ALIYUN_SMS_TEMPLATE=SMS_123456789
  4. 在 venv 里补装依赖：
  venv\Scripts\pip install aliyun-python-sdk-core aliyun-python-sdk-dysmsapi flask flask-login flask-wtf flask-sqlalchemy flask-bootstrap pymysql redis rq pypdf2 qrcode pillow python-alipay-sdk requests

  修复 5：SECRET_KEY 必须真实设置

  Session 依赖 SECRET_KEY 才能加密，当前 config.py 是硬编码 'SECRET KEY'——验证码现在存 session 里，若 SECRET_KEY 泄露或为空，攻击者可伪造 session 绕过验证。改为：
  SECRET_KEY = os.environ['SECRET_KEY']   # 启动时必须提供，如 openssl rand -hex 32

  ---
  五、最小验证步骤

  1. 完成修复 1~4
  2. flask run 启动后访问 /login/register
  3. 输入手机号 → 点"获取验证码"
  4. 浏览器 DevTools Network 面板：应看到 register?mobile_phone_number=... 返回 {"success":true,"msg":"OK"}
  5. 手机真收到短信（首次可用阿里云控制台的短信测试或自己的手机号）
  6. 填入验证码、密码 → 提交 → 跳转到登录页
  7. 用新账号登录成功

  任一步失败，按上表对应编号排查。

  ---
  一句话总结：SMS 模块是"能编译但不能用"的状态——关键的验证码生成、绑定、返回值判断、前端回调、模板 ID 全是占位或错的。按上面 1~5 步改完后即可真正可用。


  设置环境变量（Windows CMD 示例）

  set SECRET_KEY=运行下面这条命令生成：python -c "import secrets;print(secrets.token_hex(32))"
  set DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/print?charset=utf8mb4
  set ALIYUN_AK=新的AccessKeyId
  set ALIYUN_SK=新的AccessKeySecret
  set ALIYUN_SMS_SIGN=你申请通过的签名名称
  set ALIYUN_SMS_TEMPLATE=SMS_xxxxxxxxx
  set XORPAY_SECRET=你的xorpay签名密钥


  *********************************************************************************************************短信**********************************************************************************************************


  *****************************************************************************支付后被拦截，无法跳转回来*************************************************************************************************
                                                                                                                                                                                                                                                                                                                      
● cpolar 没装。需要你操作几步（大约 3 分钟），装完把公网 URL 告诉我，后续改代码+重启我来搞。                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                                                       
  你需要做的                                                                                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                                                         1. 下载安装                                                                                                                                                                                                                                                                                                          
                                                                                                                                                                                                                                                                                                                         打开 https://www.cpolar.com/download，下载 Windows 64-bit，双击安装。                                                                                                                                                                                                                                                

  2. 注册 + 拿 authtoken

  - 注册：https://dashboard.cpolar.com/signup
  - 拿 token：https://dashboard.cpolar.com/auth （复制一长串字符）

  3. 在新开的 cmd 窗口里执行（两条命令）

  cpolar authtoken 你刚才复制的token
  cpolar http 8001

  第二条命令会一直占着窗口，不要关。你会看到这样的输出：

  Forwarding     http://xxx.cpolar.io -> http://localhost:8001
  Forwarding     https://xxx.cpolar.io -> http://localhost:8001

  4. 把那个 https://xxx.cpolar.io 贴给我

  拿到之后我会：
  1. 把 app/test/ali_pay.py 里 4 处 http://localhost:8001 替换成你的公网 URL
  2. 重启 Flask
  3. 你再次发起支付，跳转和异步回调都会通

  ---

  ▎ 提示：免费版 cpolar 给的是随机二级域名，每次启动会变，所以别关那个窗口。如果你想要固定域名需要付费。对开发测试完全够用。


 *****************************************************************************支付后被拦截，无法跳转回来*************************************************************************************************



   ┌─────────────┬──────────┬───────┬───────────────────────────┐
  │   手机号    │   密码   │ 角色  │        登录后跳转         │
  ├─────────────┼──────────┼───────┼───────────────────────────┤
  │ 13800000001 │ admin123 │ admin │ /admin/select（后台管理） │
  ├─────────────┼──────────┼───────┼───────────────────────────┤
  │ 13800000002 │ guest123 │ guest │ /toindex（前台首页）      │
  └─────────────┴──────────┴───────┴───────────────────────────┘