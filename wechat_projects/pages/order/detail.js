// pages/order/detail.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    tradeNumber: '',
    orderInfo: null,
    printPlace: null,
    statusIcon: '',
    statusHint: ''
  },

  onLoad(options) {
    const { tradeNumber } = options
    if (!tradeNumber) {
      util.showToast('订单信息错误')
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
      return
    }
    
    this.setData({ tradeNumber })
    this.loadOrderDetail()
  },

  // 加载订单详情
  async loadOrderDetail() {
    try {
      const res = await api.getOrderDetail(this.data.tradeNumber)
      
      if (res.code === 0) {
        const data = res.data
        
        const orderInfo = {
          ...data,
          statusText: util.getOrderStatusText(data.status),
          colorText: util.getColorText(data.color),
          printWayText: util.getPrintWayText(data.printWay),
          directionText: util.getDirectionText(data.direction),
          amount: util.formatPrice(data.amount)
        }
        
        // 状态图标和提示
        const { icon, hint } = this.getStatusInfo(data.status)
        
        this.setData({
          orderInfo,
          statusIcon: icon,
          statusHint: hint
        })
        
        // 加载打印点信息
        this.loadPrintPlace(data.printPlace)
      } else {
        util.showToast(res.msg || '加载失败')
      }
    } catch (error) {
      console.error('加载订单详情失败:', error)
      util.showToast('加载失败，请重试')
    }
  },

  // 预览文件
  previewFile() {
    const { orderInfo } = this.data
    if (!orderInfo || !orderInfo.filePreviewUrl) {
      util.showToast('文件不可预览')
      return
    }
    
    const app = getApp()
    const baseUrl = app.globalData.baseUrl || ''
    const fileUrl = `${baseUrl}${orderInfo.filePreviewUrl}`
    
    // 判断文件类型
    const ext = orderInfo.fileName.split('.').pop().toLowerCase()
    
    if (['jpg', 'jpeg', 'png', 'gif'].includes(ext)) {
      // 图片预览
      wx.previewImage({
        urls: [fileUrl],
        current: fileUrl
      })
    } else if (ext === 'pdf') {
      // PDF 预览
      wx.showLoading({ title: '加载中...' })
      wx.downloadFile({
        url: fileUrl,
        success: (res) => {
          wx.hideLoading()
          if (res.statusCode === 200) {
            wx.openDocument({
              filePath: res.tempFilePath,
              fileType: 'pdf',
              success: () => {},
              fail: (err) => {
                console.error('打开文档失败:', err)
                util.showToast('打开文档失败')
              }
            })
          } else {
            util.showToast('文件加载失败')
          }
        },
        fail: (err) => {
          wx.hideLoading()
          console.error('下载文件失败:', err)
          util.showToast('文件加载失败')
        }
      })
    } else {
      util.showToast('该文件类型不支持预览')
    }
  },

  // 获取状态图标和提示
  getStatusInfo(status) {
    const statusMap = {
      '-2': {
        icon: '/assets/icons/status-cancelled.png',
        hint: '订单已取消'
      },
      '-1': {
        icon: '/assets/icons/status-failed.png',
        hint: '打印过程中出现异常，请联系打印点'
      },
      '0': {
        icon: '/assets/icons/status-pending.png',
        hint: '订单待支付，请在30分钟内完成支付'
      },
      '1': {
        icon: '/assets/icons/status-paid.png',
        hint: '支付成功，正在等待打印'
      },
      '2': {
        icon: '/assets/icons/status-printing.png',
        hint: '您的文件正在打印中，请稍候取件'
      },
      '3': {
        icon: '/assets/icons/status-completed.png',
        hint: '打印完成，请到店取件'
      }
    }
    
    return statusMap[String(status)] || {
      icon: '/assets/icons/status-pending.png',
      hint: ''
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

  // 复制订单号
  copyTradeNumber() {
    wx.setClipboardData({
      data: this.data.tradeNumber,
      success: () => {
        util.showSuccess('已复制订单号')
      }
    })
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
        this.loadOrderDetail()
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
  goToPay() {
    const { orderInfo } = this.data
    wx.redirectTo({
      url: `/pages/pay/pay?tradeNumber=${orderInfo.tradeNumber}&amount=${orderInfo.amount}`
    })
  },

  // 再次打印
  async reprintOrder() {
    util.showLoading('处理中...')
    
    try {
      const res = await api.reprintOrder(this.data.tradeNumber)
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('已创建新订单')
        
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

  // 分享
  onShareAppMessage() {
    return {
      title: `PrintYun云打印 - 订单${this.data.tradeNumber}`,
      path: '/pages/index/index'
    }
  }
})
