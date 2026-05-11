// app.js
App({
  onLaunch() {
    // 初始化云打印服务
    this.initApp()
  },

  async initApp() {
    try {
      // 检查登录状态
      if (this.checkLoginStatus()) {
        console.log('已登录，用户信息:', this.globalData.userInfo)
        return
      }
      // 未登录，尝试静默登录（无用户信息）
      await this.silentLogin()
    } catch (error) {
      console.error('初始化失败:', error)
    }
  },

  /**
   * 微信一键登录（静默登录 + 授权获取用户信息）
   * 流程：wx.login() 获取 code + wx.getUserProfile() 获取用户信息
   * @param {boolean} withProfile - 是否同时获取用户信息（需要用户点击授权）
   */
  loginWithWechat(withProfile = true) {
    return new Promise(async (resolve, reject) => {
      try {
        // 1. 先调用 wx.login 获取 code
        const loginRes = await this.wxLogin()
        if (!loginRes.code) {
          reject({ code: -1, msg: '获取登录凭证失败' })
          return
        }

        // 2. 构建登录请求数据
        const loginData = { code: loginRes.code }

        // 3. 如果需要获取用户信息
        if (withProfile) {
          try {
            const profileRes = await this.wxGetUserProfile()
            if (profileRes) {
              // 转换字段名：nickName -> nickName, avatarUrl -> avatarUrl
              loginData.userInfo = {
                nickName: profileRes.nickName || '',
                avatarUrl: profileRes.avatarUrl || ''
              }
            }
          } catch (profileError) {
            // 用户拒绝授权，不影响登录
            console.log('用户拒绝授权获取个人信息')
          }
        }

        // 4. 发送登录请求到后端
        const result = await this.request({
          url: '/api/mp/auth/login',
          method: 'POST',
          data: loginData
        })

        if (result.code === 0) {
          // 存储 token 和用户信息
          this.globalData.token = result.data.token
          this.globalData.userInfo = result.data.user
          this.globalData.isLoggedIn = true

          // 持久化存储
          wx.setStorageSync('token', result.data.token)
          wx.setStorageSync('userInfo', result.data.user)

          resolve(result)
        } else {
          reject(result)
        }
      } catch (error) {
        reject(error)
      }
    })
  },

  // 微信静默登录（仅获取 code，不获取用户信息）
  silentLogin() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: async (res) => {
          if (res.code) {
            try {
              // 发送 code 到后端换取 token
              const result = await this.request({
                url: '/api/mp/auth/login',
                method: 'POST',
                data: { code: res.code }
              })

              if (result.code === 0) {
                // 存储 token 和用户信息
                this.globalData.token = result.data.token
                this.globalData.userInfo = result.data.user
                this.globalData.isLoggedIn = true

                // 持久化存储
                wx.setStorageSync('token', result.data.token)
                wx.setStorageSync('userInfo', result.data.user)

                resolve(result)
              } else {
                reject(result)
              }
            } catch (error) {
              reject(error)
            }
          } else {
            reject(new Error('wx.login 失败: ' + res.errMsg))
          }
        },
        fail: (error) => {
          reject(error)
        }
      })
    })
  },

  // wx.login Promise 封装
  wxLogin() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: resolve,
        fail: reject
      })
    })
  },

  // wx.getUserProfile Promise 封装
  // 注意：此接口需要用户主动点击按钮触发
  wxGetUserProfile() {
    return new Promise((resolve, reject) => {
      wx.getUserProfile({
        desc: '用于完善用户资料',
        success: resolve,
        fail: reject
      })
    })
  },

  // 检查登录状态
  checkLoginStatus() {
    const token = wx.getStorageSync('token')
    const userInfo = wx.getStorageSync('userInfo')
    
    if (token && userInfo) {
      this.globalData.token = token
      this.globalData.userInfo = userInfo
      this.globalData.isLoggedIn = true
      return true
    }
    return false
  },

  // 刷新 Token
  refreshToken() {
    // 防止重复刷新
    if (this._refreshing) {
      return this._refreshPromise
    }
    
    this._refreshing = true
    
    this._refreshPromise = new Promise((resolve, reject) => {
      this.request({
        url: '/api/mp/auth/refresh',
        method: 'POST',
        skipAuthRefresh: true  // 跳过自动刷新
      }).then(res => {
        if (res.code === 0) {
          this.globalData.token = res.data.token
          wx.setStorageSync('token', res.data.token)
          this._refreshing = false
          resolve(res)
        } else {
          this._refreshing = false
          reject(res)
        }
      }).catch(err => {
        this._refreshing = false
        reject(err)
      })
    })
    
    return this._refreshPromise
  },

  // 封装请求方法
  request(options) {
    const { url, method = 'GET', data = {}, header = {}, skipAuthRefresh = false } = options
    
    // 添加 token
    if (this.globalData.token) {
      header['Authorization'] = 'Bearer ' + this.globalData.token
    }
    
    return new Promise((resolve, reject) => {
      wx.request({
        url: this.globalData.baseUrl + url,
        method,
        data,
        header: {
          'Content-Type': 'application/json',
          ...header
        },
        success: (res) => {
          if (res.statusCode === 401 && !skipAuthRefresh) {
            // Token 过期，尝试刷新
            this.refreshToken().then(() => {
              // 重试原请求
              this.request(options).then(resolve).catch(reject)
            }).catch(() => {
              // 刷新失败，清除登录态
              this.logout()
              reject({ code: 401, msg: '登录已过期，请重新登录' })
            })
          } else {
            resolve(res.data)
          }
        },
        fail: (error) => {
          console.error('请求失败:', error)
          reject({ code: -1, msg: '网络请求失败', error })
        }
      })
    })
  },

  // 文件上传
  uploadFile(options) {
    const { filePath, name = 'file', formData = {} } = options
    
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: this.globalData.baseUrl + '/api/mp/upload/file',
        filePath,
        name,
        formData,
        header: {
          'Authorization': 'Bearer ' + this.globalData.token
        },
        success: (res) => {
          const data = JSON.parse(res.data)
          resolve(data)
        },
        fail: (error) => {
          console.error('上传失败:', error)
          reject({ code: -1, msg: '文件上传失败', error })
        }
      })
    })
  },

  // 退出登录
  logout() {
    this.globalData.token = null
    this.globalData.userInfo = null
    this.globalData.isLoggedIn = false
    wx.removeStorageSync('token')
    wx.removeStorageSync('userInfo')
  },

  globalData: {
    isLoggedIn: false,
    token: null,
    userInfo: null,
    baseUrl: 'https://your-domain.com', // TODO: 替换为实际后端地址
    
    // 打印参数选项
    printOptions: {
      paperSizes: ['A4'],
      directions: [
        { value: '3', label: '竖版' },
        { value: '4', label: '横版' }
      ],
      printWays: [
        { value: 'one-sided', label: '单面' },
        { value: 'two-sided-long-edge', label: '双面长边' },
        { value: 'two-sided-short-edge', label: '双面短边' }
      ],
      colors: [
        { value: 'CMYGray', label: '黑白' },
        { value: 'RGB', label: '彩色' }
      ]
    },
    
    // 价格表
    priceTable: {
      'CMYGray': {
        'one-sided': 0.30,
        'two-sided-long-edge': 0.50,
        'two-sided-short-edge': 0.50
      },
      'RGB': {
        'one-sided': 1.00,
        'two-sided-long-edge': 1.70,
        'two-sided-short-edge': 1.70
      }
    }
  }
})
