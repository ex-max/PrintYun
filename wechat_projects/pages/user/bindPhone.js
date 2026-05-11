// pages/user/bindPhone.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    phone: '',
    code: '',
    sendingCode: false,
    countdown: 0,
    canSubmit: false,
    submitting: false
  },

  timer: null,

  onUnload() {
    if (this.timer) {
      clearInterval(this.timer)
    }
  },

  // 手机号输入
  onPhoneInput(e) {
    const phone = e.detail.value
    this.setData({ phone })
    this.checkCanSubmit()
  },

  // 验证码输入
  onCodeInput(e) {
    const code = e.detail.value
    this.setData({ code })
    this.checkCanSubmit()
  },

  // 检查是否可提交
  checkCanSubmit() {
    const { phone, code } = this.data
    const isValidPhone = /^1[3-9]\d{9}$/.test(phone)
    const isValidCode = /^\d{6}$/.test(code)
    
    this.setData({
      canSubmit: isValidPhone && isValidCode
    })
  },

  // 发送验证码
  async sendCode() {
    const { phone, sendingCode, countdown } = this.data
    
    if (sendingCode || countdown > 0) return
    
    // 校验手机号
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      util.showToast('请输入正确的手机号')
      return
    }
    
    this.setData({ sendingCode: true })
    
    try {
      // TODO: 调用发送验证码接口
      // const res = await api.sendSmsCode(phone)
      
      util.showSuccess('验证码已发送')
      
      // 开始倒计时
      this.startCountdown()
    } catch (error) {
      console.error('发送验证码失败:', error)
      util.showToast('发送失败，请重试')
    } finally {
      this.setData({ sendingCode: false })
    }
  },

  // 开始倒计时
  startCountdown() {
    this.setData({ countdown: 60 })
    
    this.timer = setInterval(() => {
      const countdown = this.data.countdown - 1
      if (countdown <= 0) {
        clearInterval(this.timer)
        this.setData({ countdown: 0 })
      } else {
        this.setData({ countdown })
      }
    }, 1000)
  },

  // 微信手机号授权
  async getPhoneNumber(e) {
    if (e.detail.errMsg !== 'getPhoneNumber:ok') {
      console.log('用户拒绝授权手机号')
      return
    }
    
    util.showLoading('绑定中...')
    
    try {
      const { encryptedData, iv } = e.detail
      const res = await api.bindPhone(encryptedData, iv)
      
      util.hideLoading()
      
      if (res.code === 0) {
        util.showSuccess('绑定成功')
        
        // 更新全局用户信息
        const app = getApp()
        app.globalData.userInfo = {
          ...app.globalData.userInfo,
          phone: res.data.phone
        }
        
        setTimeout(() => {
          wx.navigateBack()
        }, 1500)
      } else {
        util.showToast(res.msg || '绑定失败')
      }
    } catch (error) {
      util.hideLoading()
      console.error('绑定手机号失败:', error)
      util.showToast('绑定失败，请重试')
    }
  },

  // 手动绑定
  async submitBind() {
    const { phone, code, canSubmit, submitting } = this.data
    
    if (!canSubmit || submitting) return
    
    this.setData({ submitting: true })
    util.showLoading('绑定中...')
    
    try {
      // TODO: 调用验证码绑定接口
      // const res = await api.bindPhoneWithCode(phone, code)
      
      util.hideLoading()
      util.showSuccess('绑定成功')
      
      // 更新全局用户信息
      const app = getApp()
      app.globalData.userInfo = {
        ...app.globalData.userInfo,
        phone
      }
      
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } catch (error) {
      util.hideLoading()
      console.error('绑定手机号失败:', error)
      util.showToast('绑定失败，请重试')
      this.setData({ submitting: false })
    }
  }
})
