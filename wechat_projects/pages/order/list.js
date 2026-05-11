// pages/order/list.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    currentTab: 'all',
    orders: [],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false
  },

  onLoad() {
    this.loadOrders()
  },

  onShow() {
    // 每次显示时刷新列表
    this.refreshOrders()
  },

  // 切换 Tab
  switchTab(e) {
    const tab = e.currentTarget.dataset.tab
    if (tab === this.data.currentTab) return
    
    this.setData({
      currentTab: tab,
      orders: [],
      page: 1,
      hasMore: true
    })
    
    this.loadOrders()
  },

  // 刷新订单列表
  async refreshOrders() {
    this.setData({
      page: 1,
      hasMore: true
    })
    await this.loadOrders()
  },

  // 加载订单列表
  async loadOrders() {
    if (this.data.loading) return
    
    this.setData({ loading: true })
    
    try {
      const { currentTab, page, pageSize } = this.data
      const params = {
        page,
        pageSize
      }
      
      // 筛选状态
      if (currentTab !== 'all') {
        params.status = currentTab
      }
      
      const res = await api.getOrderList(params)
      
      if (res.code === 0) {
        const list = res.data.list.map(item => this.formatOrder(item))
        
        this.setData({
          orders: page === 1 ? list : [...this.data.orders, ...list],
          hasMore: list.length >= pageSize,
          loading: false
        })
      } else {
        util.showToast(res.msg || '加载失败')
        this.setData({ loading: false })
      }
    } catch (error) {
      console.error('加载订单列表失败:', error)
      util.showToast('加载失败，请重试')
      this.setData({ loading: false })
    }
  },

  // 格式化订单数据
  formatOrder(item) {
    return {
      ...item,
      statusText: util.getOrderStatusText(item.status),
      statusClass: util.getOrderStatusClass(item.status),
      colorText: util.getColorText(item.color),
      printWayText: util.getPrintWayText(item.printWay),
      amount: util.formatPrice(item.amount)
    }
  },

  // 加载更多
  loadMore() {
    if (!this.data.hasMore || this.data.loading) return
    
    this.setData({
      page: this.data.page + 1
    })
    
    this.loadOrders()
  },

  // 跳转到订单详情
  goToDetail(e) {
    const tradeNumber = e.currentTarget.dataset.tradenum
    wx.navigateTo({
      url: `/pages/order/detail?tradeNumber=${tradeNumber}`
    })
  },

  // 取消订单
  async cancelOrder(e) {
    const tradeNumber = e.currentTarget.dataset.tradenum
    
    const confirm = await util.showConfirm('确定要取消此订单吗？')
    if (!confirm) return
    
    util.showLoading('取消中...')
    
    try {
      const res = await api.cancelOrder(tradeNumber)
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('订单已取消')
        this.refreshOrders()
      } else {
        util.showToast(res.msg || '取消失败')
      }
    } catch (error) {
      util.hideLoading()
      console.error('取消订单失败:', error)
      util.showToast('取消失败，请重试')
    }
  },

  // 去支付
  goToPay(e) {
    const { tradenum, amount } = e.currentTarget.dataset
    wx.redirectTo({
      url: `/pages/pay/pay?tradeNumber=${tradenum}&amount=${amount}`
    })
  },

  // 再次打印
  async reprintOrder(e) {
    const tradeNumber = e.currentTarget.dataset.tradenum
    
    util.showLoading('处理中...')
    
    try {
      const res = await api.reprintOrder(tradeNumber)
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('已创建新订单')
        
        // 跳转到新订单支付页
        wx.redirectTo({
          url: `/pages/pay/pay?tradeNumber=${res.data.tradeNumber}&amount=${res.data.amount}`
        })
      } else {
        util.showToast(res.msg || '操作失败')
      }
    } catch (error) {
      util.hideLoading()
      console.error('再次打印失败:', error)
      util.showToast('操作失败，请重试')
    }
  },

  // 去下单
  goToUpload() {
    wx.navigateTo({
      url: '/pages/upload/upload'
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.refreshOrders().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  // 上拉加载
  onReachBottom() {
    this.loadMore()
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 我的订单',
      path: '/pages/index/index'
    }
  }
})
