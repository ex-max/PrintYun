/**
 * utils/api.js - API 接口封装
 */

const app = getApp()

/**
 * 基础请求方法
 */
const request = (options) => {
  return app.request(options)
}

/**
 * ==================== 认证模块 ====================
 */

// 微信登录
const authLogin = (code) => {
  return request({
    url: '/api/mp/auth/login',
    method: 'POST',
    data: { code }
  })
}

// 刷新 Token
const refreshToken = () => {
  return request({
    url: '/api/mp/auth/refresh',
    method: 'POST'
  })
}

// 退出登录
const logout = () => {
  return request({
    url: '/api/mp/auth/logout',
    method: 'POST'
  })
}

// 绑定手机号
const bindPhone = (encryptedData, iv) => {
  return request({
    url: '/api/mp/auth/bindPhone',
    method: 'POST',
    data: { encryptedData, iv }
  })
}

/**
 * ==================== 文件上传模块 ====================
 */

// 上传文件
const uploadFile = (filePath, formData = {}) => {
  return app.uploadFile({
    filePath,
    formData
  })
}

// 查询文件转换状态
const getConvertStatus = (fileId) => {
  return request({
    url: '/api/mp/upload/convertStatus',
    data: { fileId }
  })
}

// 上传身份证正面
const uploadIdCardFront = (filePath) => {
  return app.uploadFile({
    filePath,
    name: 'file',
    formData: { type: 'idcard_front' }
  })
}

// 上传身份证反面
const uploadIdCardBack = (filePath) => {
  return app.uploadFile({
    filePath,
    name: 'file',
    formData: { type: 'idcard_back' }
  })
}

/**
 * ==================== 订单模块 ====================
 */

// 获取订单列表
const getOrderList = (params = {}) => {
  const { status, page = 1, pageSize = 20 } = params
  return request({
    url: '/api/mp/orders',
    data: { status, page, pageSize }
  })
}

// 获取订单详情
const getOrderDetail = (tradeNumber) => {
  return request({
    url: `/api/mp/orders/${tradeNumber}`
  })
}

// 创建订单
const createOrder = (data) => {
  return request({
    url: '/api/mp/orders',
    method: 'POST',
    data
  })
}

// 批量创建订单
const createBatchOrders = (data) => {
  return request({
    url: '/api/mp/orders/batch',
    method: 'POST',
    data
  })
}

// 取消订单
const cancelOrder = (tradeNumber) => {
  return request({
    url: `/api/mp/orders/${tradeNumber}/cancel`,
    method: 'POST'
  })
}

// 再次打印
const reprintOrder = (tradeNumber) => {
  return request({
    url: `/api/mp/orders/${tradeNumber}/reprint`,
    method: 'POST'
  })
}

// 查询订单状态（支付轮询）
const getOrderStatus = (tradeNumber) => {
  return request({
    url: `/api/mp/orders/${tradeNumber}/status`
  })
}

// 身份证打印订单
const createIdCardOrder = (data) => {
  return request({
    url: '/api/mp/orders/idcard',
    method: 'POST',
    data
  })
}

/**
 * ==================== 支付模块 ====================
 */

// 获取微信支付参数
const getWechatPayParams = (tradeNumber) => {
  return request({
    url: '/api/mp/pay/wechat',
    method: 'POST',
    data: { tradeNumber }
  })
}

/**
 * ==================== 用户模块 ====================
 */

// 获取用户信息
const getUserInfo = () => {
  return request({
    url: '/api/mp/user/info'
  })
}

/**
 * ==================== 打印点模块 ====================
 */

// 获取打印点列表
const getPrintPlaces = () => {
  return request({
    url: '/api/mp/printPlaces'
  })
}

/**
 * ==================== 打印参数模块 ====================
 */

// 获取打印参数选项
const getPrintOptions = () => {
  return request({
    url: '/api/mp/printOptions'
  })
}

/**
 * ==================== 消息模块 ====================
 */

// 发送订阅消息
const sendSubscribeMessage = (data) => {
  return request({
    url: '/api/mp/msg/subscribe',
    method: 'POST',
    data
  })
}

/**
 * ==================== 导出 ====================
 */

module.exports = {
  // 认证
  authLogin,
  refreshToken,
  logout,
  bindPhone,
  
  // 文件上传
  uploadFile,
  getConvertStatus,
  uploadIdCardFront,
  uploadIdCardBack,
  
  // 订单
  getOrderList,
  getOrderDetail,
  createOrder,
  createBatchOrders,
  cancelOrder,
  reprintOrder,
  getOrderStatus,
  createIdCardOrder,
  
  // 支付
  getWechatPayParams,
  
  // 用户
  getUserInfo,
  
  // 打印点
  getPrintPlaces,
  
  // 打印参数
  getPrintOptions,
  
  // 消息
  sendSubscribeMessage
}
