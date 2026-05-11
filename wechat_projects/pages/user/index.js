// pages/user/index.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    userInfo: null,
    stats: {
      totalOrders: 0,
      totalAmount: '0.00',
      monthOrders: 0,
      monthAmount: '0.00'
    }
  },

  onLoad() {
    this.checkLogin()
  },

  onShow() {
    this.loadUserInfo()
  },

  // 检查登录状态
  checkLogin() {
    const app = getApp()
    if (!app.checkLoginStatus()) {
      wx.navigateTo({
        url: '/pages/index/index'
      })
    }
  },

  // 加载用户信息
  async loadUserInfo() {
    const app = getApp()
    
    // 检查登录状态
    if (!app.checkLoginStatus()) {
      return
    }
    
    const userInfo = app.globalData.userInfo
    this.setData({ userInfo })
    
    try {
      const res = await api.getUserInfo()
      if (res.code === 0) {
        this.setData({
          userInfo: res.data.user,
          stats: {
            totalOrders: res.data.totalOrders || 0,
            totalAmount: util.formatPrice(res.data.totalAmount || 0),
            monthOrders: res.data.monthOrders || 0,
            monthAmount: util.formatPrice(res.data.monthAmount || 0)
          }
        })
      }
    } catch (error) {
      console.error('加载用户信息失败:', error)
    }
  },

  // 更新头像昵称（微信授权）
  async updateProfile() {
    util.showLoading('正在授权...')
    try {
      const app = getApp()
      await app.loginWithWechat(true)
      this.setData({
        userInfo: app.globalData.userInfo
      })
      util.hideLoading()
      util.showSuccess('授权成功')
    } catch (error) {
      util.hideLoading()
      console.error('授权失败:', error)
      util.showError('授权失败，请重试')
    }
  },

  // 我的订单
  goToOrders() {
    wx.switchTab({
      url: '/pages/order/list'
    })
  },

  // 打印点列表
  goToPrintPlaces() {
    wx.navigateTo({
      url: '/pages/printplaces/list'
    })
  },

  // 联系客服
  contactService() {
    wx.showModal({
      title: '联系客服',
      content: '如有问题请联系打印点工作人员，或拨打客服电话',
      confirmText: '拨打电话',
      success: (res) => {
        if (res.confirm) {
          wx.makePhoneCall({
            phoneNumber: '400-000-0000' // TODO: 替换为实际客服电话
          })
        }
      }
    })
  },

  // 用户协议
  goToAgreement() {
    wx.navigateTo({
      url: '/pages/webview/index?url=https://your-domain.com/agreement&title=用户协议'
    })
  },

  // 关于我们
  goToAbout() {
    wx.showModal({
      title: '关于 PrintYun云打印',
      content: 'PrintYun云打印是一款便捷的自助打印服务平台，为您提供手机一点，到店即取的优质打印体验。\n\n版本：v1.0.0',
      showCancel: false
    })
  },

  // 退出登录
  async logout() {
    const confirm = await util.showConfirm('确定要退出登录吗？')
    if (!confirm) return
    
    try {
      await api.logout()
    } catch (error) {
      console.error('退出登录失败:', error)
    }
    
    const app = getApp()
    app.logout()
    
    util.showSuccess('已退出登录')
    
    setTimeout(() => {
      wx.switchTab({
        url: '/pages/index/index'
      })
    }, 1500)
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 手机一点，到店即取',
      path: '/pages/index/index'
    }
  }
})
