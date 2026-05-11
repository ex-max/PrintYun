// pages/printplaces/list.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    places: [],
    loading: false
  },

  onLoad() {
    this.loadPlaces()
  },

  // 加载打印点列表
  async loadPlaces() {
    this.setData({ loading: true })
    
    try {
      const res = await api.getPrintPlaces()
      
      if (res.code === 0 && res.data && res.data.list) {
        this.setData({
          places: res.data.list,
          loading: false
        })
      } else {
        util.showToast(res.msg || '加载失败')
        this.setData({ loading: false })
      }
    } catch (error) {
      console.error('加载打印点失败:', error)
      util.showToast('加载失败，请重试')
      this.setData({ loading: false })
    }
  },

  // 拨打电话
  makePhoneCall(e) {
    const phone = e.currentTarget.dataset.phone
    if (!phone) return
    
    wx.makePhoneCall({
      phoneNumber: phone
    })
  },

  // 打开地图导航
  openLocation(e) {
    const place = e.currentTarget.dataset.place
    if (!place || !place.latitude || !place.longitude) {
      util.showToast('打印点暂无位置信息')
      return
    }
    
    wx.openLocation({
      latitude: place.latitude,
      longitude: place.longitude,
      name: place.name,
      address: place.address,
      scale: 16
    })
  },

  // 去打印
  goToPrint(e) {
    const placeKey = e.currentTarget.dataset.place
    wx.navigateTo({
      url: `/pages/upload/upload?placeKey=${placeKey}`
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadPlaces().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 打印点列表',
      path: '/pages/index/index'
    }
  }
})
