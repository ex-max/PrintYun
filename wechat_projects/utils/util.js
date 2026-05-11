/**
 * utils/util.js - 工具函数库
 */

/**
 * 格式化时间
 */
const formatTime = (date) => {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  const hour = date.getHours()
  const minute = date.getMinutes()
  const second = date.getSeconds()

  return `${[year, month, day].map(formatNumber).join('-')} ${[hour, minute, second].map(formatNumber).join(':')}`
}

const formatNumber = n => {
  n = n.toString()
  return n[1] ? n : `0${n}`
}

/**
 * 格式化日期（不含时间）
 */
const formatDate = (date) => {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  return `${[year, month, day].map(formatNumber).join('-')}`
}

/**
 * 格式化金额
 */
const formatPrice = (price) => {
  return parseFloat(price).toFixed(2)
}

/**
 * 计算打印价格
 * @param {string} color - CMYGray | RGB
 * @param {string} printWay - one-sided | two-sided-long-edge | two-sided-short-edge
 * @param {number} pages - 页数
 * @param {number} copies - 份数
 */
const calculatePrice = (color, printWay, pages, copies) => {
  const priceTable = {
    'CMYGray': {
      'one-sided': 0.30,
      'two-sided-long-edge': 0.50,
      'two-sided-short-edge': 0.50
    },
    'RGB': {
      'one-sided': 1.00,
      'two-sided-long-edge': 1.70,
      'two-sided-short-edge': 1.70
    }
  }
  
  const unitPrice = priceTable[color]?.[printWay] || 0.30
  const total = unitPrice * pages * copies
  return {
    unitPrice,
    total: total.toFixed(2)
  }
}

/**
 * 获取订单状态文字
 */
const getOrderStatusText = (status) => {
  const statusMap = {
    '-2': '已取消',
    '-1': '打印失败',
    '0': '待支付',
    '1': '已支付',
    '2': '打印中',
    '3': '已完成'
  }
  return statusMap[String(status)] || '未知状态'
}

/**
 * 获取订单状态样式类
 */
const getOrderStatusClass = (status) => {
  const classMap = {
    '-2': 'status-cancelled',
    '-1': 'status-cancelled',
    '0': 'status-pending',
    '1': 'status-paid',
    '2': 'status-printing',
    '3': 'status-completed'
  }
  return classMap[String(status)] || ''
}

/**
 * 获取打印方式文字
 */
const getPrintWayText = (printWay) => {
  const map = {
    'one-sided': '单面',
    'two-sided-long-edge': '双面长边',
    'two-sided-short-edge': '双面短边'
  }
  return map[printWay] || printWay
}

/**
 * 获取颜色文字
 */
const getColorText = (color) => {
  const map = {
    'CMYGray': '黑白',
    'RGB': '彩色'
  }
  return map[color] || color
}

/**
 * 获取打印方向文字
 */
const getDirectionText = (direction) => {
  const map = {
    '3': '竖版',
    '4': '横版'
  }
  return map[direction] || direction
}

/**
 * 显示加载中
 */
const showLoading = (title = '加载中...') => {
  wx.showLoading({
    title,
    mask: true
  })
}

/**
 * 隐藏加载中
 */
const hideLoading = () => {
  wx.hideLoading()
}

/**
 * 显示提示
 */
const showToast = (title, icon = 'none', duration = 2000) => {
  wx.showToast({
    title,
    icon,
    duration
  })
}

/**
 * 显示成功提示
 */
const showSuccess = (title) => {
  wx.showToast({
    title,
    icon: 'success',
    duration: 2000
  })
}

/**
 * 显示错误提示
 */
const showError = (title) => {
  wx.showToast({
    title,
    icon: 'error',
    duration: 2000
  })
}

/**
 * 显示确认对话框
 */
const showConfirm = (content, title = '提示') => {
  return new Promise((resolve, reject) => {
    wx.showModal({
      title,
      content,
      success: (res) => {
        if (res.confirm) {
          resolve(true)
        } else {
          resolve(false)
        }
      },
      fail: reject
    })
  })
}

/**
 * 防抖函数
 */
const debounce = (fn, delay = 500) => {
  let timer = null
  return function (...args) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn.apply(this, args)
    }, delay)
  }
}

/**
 * 节流函数
 */
const throttle = (fn, delay = 500) => {
  let last = 0
  return function (...args) {
    const now = Date.now()
    if (now - last > delay) {
      last = now
      fn.apply(this, args)
    }
  }
}

/**
 * 检查文件类型
 */
const checkFileType = (fileName) => {
  const ext = fileName.split('.').pop().toLowerCase()
  const typeMap = {
    pdf: { type: 'pdf', needConvert: false },
    jpg: { type: 'image', needConvert: false },
    jpeg: { type: 'image', needConvert: false },
    png: { type: 'image', needConvert: false },
    doc: { type: 'word', needConvert: true },
    docx: { type: 'word', needConvert: true },
    xls: { type: 'excel', needConvert: true },
    xlsx: { type: 'excel', needConvert: true },
    ppt: { type: 'ppt', needConvert: true },
    pptx: { type: 'ppt', needConvert: true }
  }
  return typeMap[ext] || null
}

/**
 * 格式化文件大小
 */
const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

/**
 * 深拷贝
 */
const deepClone = (obj) => {
  return JSON.parse(JSON.stringify(obj))
}

/**
 * 手机号脱敏
 */
const maskPhone = (phone) => {
  if (!phone || phone.length < 7) return phone
  return phone.slice(0, 3) + '****' + phone.slice(-4)
}

/**
 * 倒计时格式化
 */
const formatCountdown = (seconds) => {
  if (seconds <= 0) return '00:00'
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

module.exports = {
  formatTime,
  formatDate,
  formatPrice,
  calculatePrice,
  getOrderStatusText,
  getOrderStatusClass,
  getPrintWayText,
  getColorText,
  getDirectionText,
  showLoading,
  hideLoading,
  showToast,
  showSuccess,
  showError,
  showConfirm,
  debounce,
  throttle,
  checkFileType,
  formatFileSize,
  deepClone,
  maskPhone,
  formatCountdown
}
