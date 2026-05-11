# PrintYun 小程序 API 接口文档

## 概述

小程序 API 使用 `/api/mp` 前缀，不影响现有 Web 端接口。

**基础URL**: `https://your-domain.com/api/mp`

**认证方式**: JWT Token（请求头 `Authorization: Bearer <token>`）

**响应格式**: 
```json
{
  "code": 0,          // 0=成功，其他=失败
  "msg": "success",   // 提示信息
  "data": {}          // 响应数据
}
```

---

## 一、认证模块

### 1.1 微信一键登录

**POST** `/auth/login`

**说明**: 微信一键登录，通过静默登录 + 微信授权获取用户信息，无需绑定手机号。

**登录流程**:
1. 前端调用 `wx.login()` 获取 code
2. 前端调用 `wx.getUserProfile()` 获取用户信息
3. 将 code + userInfo 发送到后端
4. 后端用 code 换取 openid，保存/更新用户信息，返回 Token

**请求体**:
```json
{
  "code": "wx.login返回的code（必需）",
  "userInfo": {
    "nickName": "用户昵称（可选）",
    "avatarUrl": "头像URL（可选）"
  }
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "token": "JWT Token",
    "user": {
      "id": 1,
      "nickname": "微信昵称",
      "phone": "",
      "avatarUrl": "头像URL"
    },
    "isNewUser": true
  }
}
```

**字段说明**:
- `token`: JWT Token，后续请求需要在 Header 中携带
- `user`: 用户信息
  - `id`: 用户 ID
  - `nickname`: 微信昵称
  - `phone`: 手机号（微信登录用户为空）
  - `avatarUrl`: 头像 URL
- `isNewUser`: 是否为新用户

---

### 1.2 刷新 Token

**POST** `/auth/refresh`

**需要认证**: 是

**响应**:
```json
{
  "code": 0,
  "data": {
    "token": "新的JWT Token"
  }
}
```

---

### 1.3 退出登录

**POST** `/auth/logout`

**需要认证**: 是

---

### 1.4 绑定手机号

**POST** `/auth/bindPhone`

**需要认证**: 是

**请求体（方式一 - 微信授权）**:
```json
{
  "encryptedData": "微信加密数据",
  "iv": "加密算法初始向量"
}
```

**请求体（方式二 - 验证码）**:
```json
{
  "phone": "13800138000",
  "code": "123456"
}
```

---

## 二、用户模块

### 2.1 获取用户信息

**GET** `/user/info`

**需要认证**: 是

**响应**:
```json
{
  "code": 0,
  "data": {
    "user": {
      "id": 1,
      "nickname": "",
      "phone": "13800138000",
      "avatarUrl": ""
    },
    "totalOrders": 10,
    "totalAmount": 25.50,
    "monthOrders": 3,
    "monthAmount": 8.00
  }
}
```

---

## 三、文件上传模块

### 3.1 上传文件

**POST** `/upload`

**需要认证**: 是

**Content-Type**: `multipart/form-data`

**表单字段**:
- `file`: 文件（必需）
- `type`: 文件类型（可选，用于身份证打印）

**支持格式**: PDF, JPG, JPEG, PNG, DOC, DOCX, XLS, XLSX, PPT, PPTX

**最大大小**: 50MB

**响应**:
```json
{
  "code": 0,
  "data": {
    "fileId": "1_20260511_151234_file.pdf",
    "filePath": "1_20260511_151234_file.pdf",
    "fileName": "file.pdf",
    "fileSize": 102400,
    "pageCount": 5,
    "needConvert": false
  }
}
```

---

### 3.2 查询文件转换状态

**GET** `/upload/convertStatus?fileId=<fileId>`

**响应**:
```json
{
  "code": 0,
  "data": {
    "status": "success",  // pending/success/failed
    "pageCount": 5,
    "progress": 100
  }
}
```

---

## 四、订单模块

### 4.1 获取订单列表

**GET** `/orders?page=1&pageSize=20&status=0`

**需要认证**: 是

**参数**:
- `page`: 页码（默认 1）
- `pageSize`: 每页数量（默认 20）
- `status`: 状态筛选（可选）

**订单状态**:
- `-2`: 已取消
- `-1`: 打印失败
- `0`: 待支付
- `1`: 已支付
- `2`: 打印中
- `3`: 已完成

**响应**:
```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "tradeNumber": "20260511-1",
        "fileName": "document.pdf",
        "printPlace": "home",
        "printPlaceName": "数智维新工作室",
        "color": "CMYGray",
        "colorText": "黑白",
        "printWay": "one-sided",
        "printWayText": "单面",
        "copies": 1,
        "pages": 5,
        "amount": 1.50,
        "status": 3,
        "createdAt": "2026-05-11 15:12"
      }
    ],
    "total": 10,
    "page": 1,
    "pageSize": 20,
    "hasMore": false
  }
}
```

---

### 4.2 获取订单详情

**GET** `/orders/<trade_number>`

**需要认证**: 是

**响应**:
```json
{
  "code": 0,
  "data": {
    "tradeNumber": "20260511-1",
    "fileName": "document.pdf",
    "filePreviewUrl": "/static/Upload_Files/xxx.pdf",
    "printPlace": "home",
    "printPlaceName": "数智维新工作室",
    "color": "CMYGray",
    "colorText": "黑白",
    "printWay": "one-sided",
    "printWayText": "单面",
    "direction": "3",
    "directionText": "竖版",
    "paperSize": "A4",
    "copies": 1,
    "pages": 5,
    "amount": 1.50,
    "status": 3,
    "statusText": "已完成",
    "createdAt": "2026-05-11 15:12:34",
    "paidAt": "",
    "completedAt": ""
  }
}
```

---

### 4.3 创建订单

**POST** `/orders`

**需要认证**: 是

**请求体**:
```json
{
  "fileId": "1_20260511_151234_file.pdf",
  "fileName": "document.pdf",
  "printPlace": "home",
  "copies": 1,
  "paperSize": "A4",
  "direction": "3",
  "printWay": "one-sided",
  "color": "CMYGray",
  "pages": 5
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "tradeNumber": "20260511-1",
    "amount": "1.50"
  }
}
```

---

### 4.4 取消订单

**POST** `/orders/<trade_number>/cancel`

**需要认证**: 是

**说明**: 只能取消待支付状态的订单

---

### 4.5 再次打印

**POST** `/orders/<trade_number>/reprint`

**需要认证**: 是

**说明**: 基于已完成的订单创建新订单

**响应**:
```json
{
  "code": 0,
  "data": {
    "tradeNumber": "20260511-2",
    "amount": "1.50"
  }
}
```

---

### 4.6 查询订单状态

**GET** `/orders/<trade_number>/status`

**需要认证**: 是

**说明**: 用于支付后轮询确认

**响应**:
```json
{
  "code": 0,
  "data": {
    "status": 1,
    "paid": true
  }
}
```

---

### 4.7 创建身份证打印订单

**POST** `/orders/idcard`

**需要认证**: 是

**请求体**:
```json
{
  "frontFileId": "idcard_front.jpg",
  "backFileId": "idcard_back.jpg",
  "copies": 1
}
```

**说明**: 身份证打印固定价格 1元/份

---

## 五、支付模块

### 5.1 获取微信支付参数

**POST** `/pay/wechat`

**需要认证**: 是

**请求体**:
```json
{
  "tradeNumber": "20260511-1"
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "timeStamp": "1715413155",
    "nonceStr": "abc123",
    "package": "prepay_id=wx123",
    "signType": "MD5",
    "paySign": "ABCD1234"
  }
}
```

**说明**: 返回的参数可直接传给 `wx.requestPayment()`

---

## 六、打印点模块

### 6.1 获取打印点列表

**GET** `/printPlaces`

**需要认证**: 否

**响应**:
```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "key": "home",
        "name": "数智维新工作室",
        "address": "北京市朝阳区xxx",
        "phone": "010-12345678",
        "businessHours": "09:00-18:00",
        "latitude": 39.9042,
        "longitude": 116.4074,
        "status": "open"
      }
    ]
  }
}
```

---

## 七、打印参数模块

### 7.1 获取打印参数选项

**GET** `/printOptions`

**需要认证**: 否

**响应**:
```json
{
  "code": 0,
  "data": {
    "paperSizes": ["A4"],
    "colors": [
      {"value": "CMYGray", "label": "黑白"},
      {"value": "RGB", "label": "彩色"}
    ],
    "printWays": [
      {"value": "one-sided", "label": "单面"},
      {"value": "two-sided-long-edge", "label": "双面长边"},
      {"value": "two-sided-short-edge", "label": "双面短边"}
    ],
    "directions": [
      {"value": "3", "label": "竖版"},
      {"value": "4", "label": "横版"}
    ],
    "prices": {
      "CMYGray": {"one-sided": 0.30, "two-sided": 0.50},
      "RGB": {"one-sided": 1.00, "two-sided": 1.70}
    }
  }
}
```

---

## 八、错误码说明

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未登录或登录已过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 九、配置说明

### 环境变量

在 `.env` 文件中配置以下变量：

```env
# 小程序配置
MP_APPID=你的小程序AppID
MP_SECRET=你的小程序AppSecret

# JWT 配置
JWT_SECRET=你的JWT密钥

# 已有配置
SECRET_KEY=Flask密钥
DATABASE_URL=数据库连接
```

### 微信小程序后台配置

1. **服务器域名**：添加后端域名到 `request` 合法域名
2. **业务域名**：如需 WebView，添加到业务域名
3. **订阅消息**：申请订单通知模板

---

## 十、开发说明

### 文件结构

```
app/control/mp_api.py  # 小程序 API 蓝图
```

### 路由前缀

所有小程序接口使用 `/api/mp` 前缀，不会与现有 `/printer`、`/login` 等冲突。

### 认证方式

使用简单的 JWT Token 实现，Token 在登录时生成，客户端存储后每次请求携带。

### 价格计算

```python
def _unit_price(color, print_way):
    """
    黑白单面: 0.30 元/页
    黑白双面: 0.50 元/页
    彩色单面: 1.00 元/页
    彩色双面: 1.70 元/页
    """
    is_duplex = print_way != 'one-sided'
    if color == 'CMYGray':
        return 0.5 if is_duplex else 0.3
    else:
        return 1.7 if is_duplex else 1.0
```

### 注意事项

1. **微信登录**：需要配置 `MP_APPID` 和 `MP_SECRET`
2. **微信支付**：需要开通微信支付商户号并配置相关参数
3. **文件转换**：Office 文件转换依赖 LibreOffice/soffice
4. **短信验证**：绑定手机号功能需要对接短信服务（已有阿里云配置）
