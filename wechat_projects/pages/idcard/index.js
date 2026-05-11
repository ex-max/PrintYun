// pages/idcard/index.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    frontImage: null,    // 正面图片路径
    backImage: null,     // 反面图片路径
    frontFileId: null,   // 正面文件 ID
    backFileId: null,    // 反面文件 ID
    copies: 1,
    totalPrice: '1.00',
    submitting: false
  },

  // 上传正面
  uploadFront() {
    this.chooseImage('front')
  },

  // 上传反面
  uploadBack() {
    this.chooseImage('back')
  },

  // 选择图片
  async chooseImage(side) {
    try {
      const res = await wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera']
      })
      
      const tempFilePath = res.tempFiles[0].tempFilePath
      
      util.showLoading('上传中...')
      
      // 上传图片
      const uploadRes = await api.uploadFile(tempFilePath, { type: 'idcard' })
      util.hideLoading()
      
      if (uploadRes.code === 0) {
        const data = {
          [`${side}Image`]: tempFilePath,
          [`${side}FileId`]: uploadRes.data.fileId
        }
        this.setData(data)
      } else {
        util.showToast(uploadRes.msg || '上传失败')
      }
    } catch (error) {
      util.hideLoading()
      console.error('选择图片失败:', error)
    }
  },

  // 份数减少
  onCopiesMinus() {
    const { copies } = this.data
    if (copies > 1) {
      this.setData({
        copies: copies - 1,
        totalPrice: (copies - 1).toFixed(2)
      })
    }
  },

  // 份数增加
  onCopiesPlus() {
    const { copies } = this.data
    if (copies < 10) {
      this.setData({
        copies: copies + 1,
        totalPrice: (copies + 1).toFixed(2)
      })
    }
  },

  // 份数输入
  onCopiesInput(e) {
    let value = parseInt(e.detail.value) || 1
    value = Math.max(1, Math.min(10, value))
    this.setData({
      copies: value,
      totalPrice: value.toFixed(2)
    })
  },

  // 提交订单
  async submitOrder() {
    const { frontImage, backImage, frontFileId, backFileId, copies, submitting } = this.data
    
    if (submitting) return
    
    if (!frontFileId || !backFileId) {
      util.showToast('请上传身份证正反面')
      return
    }
    
    this.setData({ submitting: true })
    util.showLoading('提交中...')
    
    try {
      const res = await api.createIdCardOrder({
        frontFileId,
        backFileId,
        copies
      })
      
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('订单创建成功')
        
        wx.redirectTo({
          url: `/pages/pay/pay?tradeNumber=${res.data.tradeNumber}&amount=${res.data.amount}`
        })
      } else {
        util.showToast(res.msg || '订单创建失败')
        this.setData({ submitting: false })
      }
    } catch (error) {
      util.hideLoading()
      console.error('提交订单失败:', error)
      util.showToast('提交失败，请重试')
      this.setData({ submitting: false })
    }
  },

  // 分享
  onShareAppMessage() {
    return {
      title: 'PrintYun云打印 - 身份证打印',
      path: '/pages/index/index'
    }
  }
})
