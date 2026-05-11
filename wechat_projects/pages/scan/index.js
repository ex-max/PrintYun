// pages/scan/index.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    tradeNumber: '',
    recentOrders: []
  },

  onLoad() {
    this.loadRecentOrders()
  },

  onShow() {
    this.loadRecentOrders()
  },

  // 加载最近订单
  async loadRecentOrders() {
    try {
      const res = await api.getOrderList({ page: 1, pageSize: 5 })
      if (res.code === 0 && res.data && res.data.list) {
        const recentOrders = res.data.list.map(item => ({
          ...item,
          statusText: util.getOrderStatusText(item.status),
          statusClass: util.getOrderStatusClass(item.status)
        }))
        this.setData({ recentOrders })
      }
    } catch (error) {
      console.error('加载最近订单失败:', error)
    }
  },

  // 扫码
  async scanCode() {
    try {
      const res = await wx.scanCode({
        scanType: ['qrCode', 'barCode']
      })
      
      // 从扫码结果中提取订单号
      let tradeNumber = res.result
      
      // 如果是链接，尝试提取订单号参数
      if (tradeNumber.includes('tradeNumber=')) {
        const match = tradeNumber.match(/tradeNumber=([^&]+)/)
        if (match) {
          tradeNumber = match[1]
        }
      }
      
      this.setData({ tradeNumber })
      this.queryOrder()
    } catch (error) {
      console.log('扫码取消或失败:', error)
    }
  },

  // 输入订单号
  onInput(e) {
    this.setData({
      tradeNumber: e.detail.value.trim()
    })
  },

  // 查询订单
  async queryOrder() {
    const { tradeNumber } = this.data
    
    if (!tradeNumber) {
      util.showToast('请输入订单号')
      return
    }
    
    util.showLoading('查询中...')
    
    try {
      const res = await api.getOrderDetail(tradeNumber)
      util.hideLoading()
      
      if (res.code === 0) {
        // 跳转到订单详情
        wx.navigateTo({
          url: `/pages/order/detail?tradeNumber=${tradeNumber}`
        })
      } else {
        util.showToast(res.msg || '订单不存在')
      }
    } catch (error) {
      util.hideLoading()
      console.error('查询订单失败:', error)
      util.showToast('查询失败，请重试')
    }
  },

  // 跳转到订单详情
  goToDetail(e) {
    const tradeNumber = e.currentTarget.dataset.tradenum
    wx.navigateTo({
      url: `/pages/order/detail?tradeNumber=${tradeNumber}`
    })
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 扫码查订单',
      path: '/pages/index/index'
    }
  }
})
