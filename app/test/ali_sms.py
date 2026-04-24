# -*- coding: utf-8 -*-
"""阿里云号码认证服务 (Dypnsapi) 短信验证码。

对比旧版 (dysmsapi + CommonRequest) 的优势：
  - 验证码由阿里云生成、发送、校验：本地不再保存明文码，也不用担心一致性
  - 阿里云内置频率控制和"一码一使用"
  - 本地只保存 SendSmsVerifyCode 返回的 verify_code_id

依赖环境变量：
  ALIYUN_AK / ALIYUN_SK          访问密钥（会自动映射到官方 SDK 期望的变量名）
  ALIYUN_SMS_SIGN                短信签名（在号码认证服务控制台申请）
  ALIYUN_SMS_TEMPLATE            模板 code（在号码认证服务控制台申请，模板内容含 ##code## 占位符）

对外接口保持不变：
  send_sms(phone)  -> (ok: bool, msg: str)
  verify_code(phone, form_code) -> bool
"""

import os
import ssl
import time
import logging

logger = logging.getLogger(__name__)

# ---- TLS 1.2 兼容补丁 --------------------------------------------------
# 背景：本机若开了 Clash/V2Ray TUN 代理，对 TLS 1.3 的 ClientHello 可能
# 直接 RST（WinError 10054 / SSLEOFError UNEXPECTED_EOF_WHILE_READING），
# 但 TLS 1.2 能通过。阿里云 Dypnsapi SDK 底层用 urllib3/requests，默认
# 协商 TLS 1.3 → 短信发不出去。这里把 ssl.create_default_context 的
# maximum_version 钉到 TLS 1.2，仅影响本模块加载后新建的 SSLContext；
# 既有代码 (Flask/ProxyFix/alipay SDK) 不受影响，因为它们在更早就已经
# 建立好了 context。
_orig_create_default_context = ssl.create_default_context


def _tls12_create_default_context(*args, **kwargs):
    ctx = _orig_create_default_context(*args, **kwargs)
    try:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    except (AttributeError, ValueError):
        pass
    return ctx


ssl.create_default_context = _tls12_create_default_context
# -----------------------------------------------------------------------

from flask import session

from alibabacloud_dypnsapi20170525.client import Client as Dypnsapi20170525Client
from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models


def _get_credentials():
    """每次调用时读环境变量（避免模块导入时 .env 尚未加载）。"""
    ak = os.environ.get('ALIYUN_AK') or os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID')
    sk = os.environ.get('ALIYUN_SK') or os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    return ak, sk


def _config():
    return (
        os.environ.get('ALIYUN_SMS_SIGN', '速通互联验证码'),
        os.environ.get('ALIYUN_SMS_TEMPLATE', '100001'),
        int(os.environ.get('SMS_COOLDOWN_SECONDS', '60')),
        int(os.environ.get('SMS_VALID_SECONDS', '300')),
        int(os.environ.get('SMS_CODE_LENGTH', '4')),
    )


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    ak, sk = _get_credentials()
    if not (ak and sk):
        return None
    try:
        # 直接传 AK/SK，不用 CredentialClient（后者在工作线程里会触发
        # signal.signal() -> "signal only works in main thread" 错误）
        config = open_api_models.Config(
            access_key_id=ak,
            access_key_secret=sk,
            endpoint='dypnsapi.aliyuncs.com',
        )
        _client = Dypnsapi20170525Client(config)
    except Exception as e:
        logger.error('初始化 Dypnsapi 客户端失败: %s', e)
        _client = None
    return _client


def _key(phone_number, suffix):
    return f'sms_{suffix}_{phone_number}'


def send_sms(phone_number):
    """给指定手机号发送验证码，返回 (ok, msg)。"""
    client = _get_client()
    if client is None:
        return False, '短信服务未配置（ALIYUN_AK/SK）'

    sign, template, cooldown, valid_time, code_length = _config()
    phone_number = str(phone_number).strip()

    last = session.get(_key(phone_number, 'last'), 0)
    if time.time() - last < cooldown:
        return False, f'请 {cooldown} 秒后再试'

    req = dypnsapi_models.SendSmsVerifyCodeRequest(
        sign_name=sign,
        template_code=template,
        phone_number=phone_number,
        template_param='{"code":"##code##","min":"5"}',
        code_length=code_length,
        valid_time=valid_time,
        duplicate_policy=1,
        return_verify_code=False,
    )

    try:
        resp = client.send_sms_verify_code_with_options(req, util_models.RuntimeOptions())
    except Exception as e:
        msg = getattr(e, 'message', None) or str(e)
        return False, f'发送失败: {msg}'

    body = getattr(resp, 'body', None)
    if body is None:
        return False, '发送失败：响应异常'

    if body.code != 'OK':
        return False, body.message or f'发送失败（{body.code}）'

    # 新版 API 不需要本地保存 verify_code_id，阿里云按手机号内部跟踪
    # 只记录发送时间用于冷却判断
    session[_key(phone_number, 'sent')] = True
    session[_key(phone_number, 'last')] = time.time()
    return True, 'OK'


def verify_code(phone_number, form_code):
    """校验验证码。通过后立即失效（一次性）。"""
    client = _get_client()
    if client is None:
        return False

    phone_number = str(phone_number).strip()
    if form_code is None:
        return False

    # 必须之前发送过验证码才允许校验
    if not session.get(_key(phone_number, 'sent')):
        return False

    req = dypnsapi_models.CheckSmsVerifyCodeRequest(
        phone_number=phone_number,
        verify_code=str(form_code).strip(),
    )

    try:
        resp = client.check_sms_verify_code_with_options(req, util_models.RuntimeOptions())
    except Exception as e:
        logger.warning('验证码校验异常: %s', e)
        return False

    body = getattr(resp, 'body', None)
    if body is None or body.code != 'OK':
        return False

    model = getattr(body, 'model', None)
    verify_result = getattr(model, 'verify_result', None) if model else None
    if verify_result == 'PASS':
        session.pop(_key(phone_number, 'sent'), None)
        session.pop(_key(phone_number, 'last'), None)
        return True
    return False
