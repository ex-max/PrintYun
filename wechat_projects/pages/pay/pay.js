// pages/pay/pay.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    tradeNumber: '',
    tradeNumbers: [],    // 批量订单号列表
    isBatch: false,      // 是否批量订单
    orderInfo: {
      tradeNumber: '',
      fileName: '',
      printPlaceName: '',
      printDesc: '',
      amount: '0.00',
      pages: 0,
      copies: 1
    },
    countdown: 0,          // 倒计时秒数
    countdownText: '30:00',
    paying: false
  },

  timer: null,

  onLoad(options) {
    const { tradeNumber, tradeNumbers, amount } = options
    
    // 支持单个订单和批量订单
    if (tradeNumbers) {
      // 批量订单
      const numbers = tradeNumbers.split(',').filter(n => n)
      if (numbers.length === 0) {
        util.showToast('订单信息错误')
        setTimeout(() => wx.navigateBack(), 1500)
        return
      }
      
      this.setData({ 
        tradeNumber: numbers[0],
        tradeNumbers: numbers,
        isBatch: numbers.length > 1,
        'orderInfo.amount': amount || '0.00',
        'orderInfo.fileName': numbers.length > 1 ? `${numbers.length} 个文件` : ''
      })
      
      // 批量订单不需要加载详情，直接显示金额
      if (numbers.length > 1) {
        this.setData({
          orderInfo: {
            tradeNumber: numbers.join(','),
            fileName: `${numbers.length} 个文件`,
            printPlaceName: '',
            printDesc: '',
            amount: amount || '0.00',
            pages: 0,
            copies: 1
          }
        })
        // 启动默认倒计时
        this.startDefaultCountdown()
      } else {
        this.loadOrderDetail()
      }
    } else if (tradeNumber) {
      // 单个订单
      this.setData({ 
        tradeNumber, 
        'orderInfo.amount': amount || '0.00' 
      })
      this.loadOrderDetail()
    } else {
      util.showToast('订单信息错误')
      setTimeout(() => wx.navigateBack(), 1500)
    }
  },

  onUnload() {
    // 清除定时器
    if (this.timer) {
      clearInterval(this.timer)
    }
  },

  // 加载订单详情
  async loadOrderDetail() {
    try {
      const res = await api.getOrderDetail(this.data.tradeNumber)
      if (res.code === 0) {
        const data = res.data
        const printDesc = this.buildPrintDesc(data)
        
        this.setData({
          orderInfo: {
            tradeNumber: data.tradeNumber,
            fileName: data.fileName,
            printPlaceName: data.printPlaceName || data.printPlace,
            printDesc,
            amount: util.formatPrice(data.amount),
            pages: data.pages,
            copies: data.copies
          }
        })
        
        // 如果订单已支付，跳转到成功页
        if (data.status >= 1) {
          wx.redirectTo({
            url: `/pages/pay/success?tradeNumber=${data.tradeNumber}`
          })
          return
        }
        
        // 启动倒计时
        this.startCountdown(data.createdAt, data.expireAt)
      }
    } catch (error) {
      console.error('加载订单详情失败:', error)
    }
  },

  // 构建打印参数描述
  buildPrintDesc(order) {
    const parts = []
    parts.push(util.getColorText(order.color))
    parts.push(util.getPrintWayText(order.printWay))
    if (order.paperSize) parts.push(order.paperSize)
    return parts.join(' · ')
  },

  // 启动倒计时
  startCountdown(createdAt, expireAt) {
    const expireTime = new Date(expireAt).getTime()
    const now = Date.now()
    const initialRemain = Math.floor((expireTime - now) / 1000)
    
    // 设置初始倒计时
    this.setData({
      countdown: initialRemain,
      countdownText: util.formatCountdown(initialRemain)
    })
    
    this.timer = setInterval(() => {
      const currentTime = Date.now()
      const remain = Math.floor((expireTime - currentTime) / 1000)
      
      if (remain <= 0) {
        clearInterval(this.timer)
        this.timer = null
        this.setData({
          countdown: 0,
          countdownText: '00:00'
        })
        // 订单超时
        wx.showModal({
          title: '订单超时',
          content: '订单已超时取消，请重新下单',
          showCancel: false,
          success: () => {
            wx.switchTab({
              url: '/pages/index/index'
            })
          }
        })
        return
      }
      
      this.setData({
        countdown: remain,
        countdownText: util.formatCountdown(remain)
      })
    }, 1000)
  },

  // 启动默认倒计时（批量订单使用）
  startDefaultCountdown() {
    // 默认30分钟倒计时
    const expireTime = Date.now() + 30 * 60 * 1000
    const initialRemain = 30 * 60
    
    this.setData({
      countdown: initialRemain,
      countdownText: util.formatCountdown(initialRemain)
    })
    
    this.timer = setInterval(() => {
      const now = Date.now()
      const remain = Math.floor((expireTime - now) / 1000)
      
      if (remain <= 0) {
        clearInterval(this.timer)
        this.timer = null
        this.setData({
          countdown: 0,
          countdownText: '00:00'
        })
        wx.showModal({
          title: '订单超时',
          content: '订单已超时取消，请重新下单',
          showCancel: false,
          success: () => {
            wx.switchTab({
              url: '/pages/index/index'
            })
          }
        })
        return
      }
      
      this.setData({
        countdown: remain,
        countdownText: util.formatCountdown(remain)
      })
    }, 1000)
  },

  // 发起支付
  async doPay() {
    if (this.data.paying) return
    
    this.setData({ paying: true })
    util.showLoading('发起支付...')
    
    try {
      // 获取支付参数
      const res = await api.getWechatPayParams(this.data.tradeNumber)
      
      if (res.code !== 0) {
        util.hideLoading()
        util.showToast(res.msg || '发起支付失败')
        this.setData({ paying: false })
        return
      }
      
      util.hideLoading()
      
      const payParams = res.data
      
      // 调起微信支付
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        success: () => {
          // 支付成功，轮询确认
          this.pollPayStatus()
        },
        fail: (err) => {
          this.setData({ paying: false })
          if (err.errMsg.includes('cancel')) {
            util.showToast('支付已取消')
          } else {
            util.showToast('支付失败，请重试')
          }
        }
      })
    } catch (error) {
      util.hideLoading()
      console.error('发起支付失败:', error)
      util.showToast('支付失败，请重试')
      this.setData({ paying: false })
    }
  },

  // 轮询支付状态
  async pollPayStatus() {
    util.showLoading('确认支付结果...')
    
    let retryCount = 0
    const maxRetry = 10
    
    const check = async () => {
      try {
        const res = await api.getOrderStatus(this.data.tradeNumber)
        
        if (res.code === 0 && res.data.paid) {
          util.hideLoading()
          util.showSuccess('支付成功')
          
          setTimeout(() => {
            wx.redirectTo({
              url: `/pages/pay/success?tradeNumber=${this.data.tradeNumber}`
            })
          }, 1500)
          return
        }
        
        retryCount++
        if (retryCount < maxRetry) {
          setTimeout(check, 2000)
        } else {
          util.hideLoading()
          util.showToast('确认支付结果超时，请在订单列表查看')
          this.setData({ paying: false })
          
          setTimeout(() => {
            wx.switchTab({
              url: '/pages/order/list'
            })
          }, 1500)
        }
      } catch (error) {
        console.error('查询支付状态失败:', error)
        retryCount++
        if (retryCount < maxRetry) {
          setTimeout(check, 2000)
        } else {
          util.hideLoading()
          util.showToast('确认支付结果失败')
          this.setData({ paying: false })
        }
      }
    }
    
    check()
  },

  // 取消订单
  async cancelOrder() {
    const confirm = await util.showConfirm('确定要取消此订单吗？取消后无法恢复')
    if (!confirm) return
    
    util.showLoading('取消中...')
    
    try {
      const res = await api.cancelOrder(this.data.tradeNumber)
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('订单已取消')
        setTimeout(() => {
          wx.switchTab({
            url: '/pages/index/index'
          })
        }, 1500)
      } else {
        util.showToast(res.msg || '取消失败')
      }
    } catch (error) {
      util.hideLoading()
      console.error('取消订单失败:', error)
      util.showToast('取消失败，请重试')
    }
  }
})
