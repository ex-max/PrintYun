// pages/pay/success.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    tradeNumber: '',
    orderInfo: {
      tradeNumber: '',
      fileName: '',
      printPlaceName: '',
      amount: '0.00'
    },
    printPlace: null
  },

  onLoad(options) {
    const { tradeNumber, tradeNumbers } = options
    
    // 支持批量订单
    if (tradeNumbers) {
      const numbers = tradeNumbers.split(',').filter(n => n)
      if (numbers.length > 0) {
        this.setData({ 
          tradeNumber: numbers[0],
          'orderInfo.tradeNumber': numbers.join(','),
          'orderInfo.fileName': numbers.length > 1 ? `${numbers.length} 个文件` : ''
        })
        // 批量订单只加载第一个订单的详情用于显示打印点
        this.loadOrderDetail()
      }
    } else if (tradeNumber) {
      this.setData({ tradeNumber })
      this.loadOrderDetail()
    }
  },

  // 加载订单详情
  async loadOrderDetail() {
    try {
      const res = await api.getOrderDetail(this.data.tradeNumber)
      if (res.code === 0) {
        const data = res.data
        this.setData({
          orderInfo: {
            tradeNumber: data.tradeNumber,
            fileName: data.fileName,
            printPlaceName: data.printPlaceName || data.printPlace,
            amount: util.formatPrice(data.amount)
          }
        })
        
        // 加载打印点信息
        this.loadPrintPlace(data.printPlace)
      }
    } catch (error) {
      console.error('加载订单详情失败:', error)
    }
  },

  // 加载打印点信息
  async loadPrintPlace(placeKey) {
    if (!placeKey) return
    
    try {
      const res = await api.getPrintPlaces()
      if (res.code === 0 && res.data && res.data.list) {
        const place = res.data.list.find(p => p.key === placeKey)
        if (place) {
          this.setData({ printPlace: place })
        }
      }
    } catch (error) {
      console.error('加载打印点失败:', error)
    }
  },

  // 导航到打印点
  openLocation() {
    const { printPlace } = this.data
    if (!printPlace || !printPlace.latitude || !printPlace.longitude) {
      util.showToast('打印点暂无位置信息')
      return
    }
    
    wx.openLocation({
      latitude: printPlace.latitude,
      longitude: printPlace.longitude,
      name: printPlace.name,
      address: printPlace.address,
      scale: 16
    })
  },

  // 拨打电话
  makePhoneCall() {
    const { printPlace } = this.data
    if (!printPlace || !printPlace.phone) return
    
    wx.makePhoneCall({
      phoneNumber: printPlace.phone
    })
  },

  // 查看订单详情
  goToOrderDetail() {
    wx.redirectTo({
      url: `/pages/order/detail?tradeNumber=${this.data.tradeNumber}`
    })
  },

  // 返回首页
  goHome() {
    wx.switchTab({
      url: '/pages/index/index'
    })
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 支付成功',
      path: '/pages/index/index'
    }
  }
})
