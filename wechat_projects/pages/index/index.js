// pages/index/index.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    isLoggedIn: false,
    userInfo: null,
    printPlace: null
  },

  onLoad() {
    this.checkLogin()
    this.loadPrintPlace()
  },

  onShow() {
    this.checkLogin()
  },

  // 检查登录状态
  checkLogin() {
    const app = getApp()
    const isLoggedIn = app.checkLoginStatus()
    this.setData({
      isLoggedIn,
      userInfo: app.globalData.userInfo
    })
  },

  // 加载打印点信息
  async loadPrintPlace() {
    try {
      const res = await api.getPrintPlaces()
      if (res.code === 0 && res.data && res.data.list && res.data.list.length > 0) {
        // 默认显示第一个打印点
        this.setData({
          printPlace: res.data.list[0]
        })
      }
    } catch (error) {
      console.error('加载打印点失败:', error)
    }
  },

  // 跳转到上传页面
  goToUpload() {
    if (!this.checkLoginAndGuide()) return
    wx.navigateTo({
      url: '/pages/upload/upload'
    })
  },

  // 跳转到订单列表
  goToOrders() {
    if (!this.checkLoginAndGuide()) return
    wx.switchTab({
      url: '/pages/order/list'
    })
  },

  // 跳转到身份证打印
  goToIdCard() {
    if (!this.checkLoginAndGuide()) return
    wx.navigateTo({
      url: '/pages/idcard/index'
    })
  },

  // 跳转到扫码
  goToScan() {
    if (!this.checkLoginAndGuide()) return
    wx.navigateTo({
      url: '/pages/scan/index'
    })
  },

  // 跳转到个人中心
  goToUserCenter() {
    wx.switchTab({
      url: '/pages/user/index'
    })
  },

  // 检查登录并引导
  checkLoginAndGuide() {
    if (!this.data.isLoggedIn) {
      wx.showModal({
        title: '提示',
        content: '请先登录后再使用此功能',
        confirmText: '去登录',
        success: (res) => {
          if (res.confirm) {
            this.doLogin()
          }
        }
      })
      return false
    }
    return true
  },

  // 执行登录（微信一键登录）
  async doLogin() {
    util.showLoading('正在登录...')
    try {
      const app = getApp()
      // 使用微信一键登录，同时获取用户信息
      await app.loginWithWechat(true)
      this.setData({
        isLoggedIn: true,
        userInfo: app.globalData.userInfo
      })
      util.hideLoading()
      util.showSuccess('登录成功')
    } catch (error) {
      util.hideLoading()
      console.error('登录失败:', error)
      util.showError('登录失败，请重试')
    }
  },

  // 拨打电话
  makePhoneCall() {
    if (!this.data.printPlace || !this.data.printPlace.phone) return
    wx.makePhoneCall({
      phoneNumber: this.data.printPlace.phone
    })
  },

  // 打开地图导航
  openLocation() {
    if (!this.data.printPlace) return
    const { latitude, longitude, name, address } = this.data.printPlace
    
    if (!latitude || !longitude) {
      util.showToast('打印点暂无位置信息')
      return
    }

    wx.openLocation({
      latitude,
      longitude,
      name,
      address,
      scale: 16
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.checkLogin()
    this.loadPrintPlace().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 手机一点，到店即取',
      path: '/pages/index/index'
    }
  }
})
