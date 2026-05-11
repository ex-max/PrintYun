// pages/upload/upload.js
const api = require('../../utils/api')
const util = require('../../utils/util')

Page({
  data: {
    fileList: [],          // 文件列表 [{id, path, name, size, sizeBytes, type, needConvert, pages, fileId, filePath, uploading, converting}]
    totalPages: 0,         // 总页数
    hasUploading: false,   // 是否有文件正在上传
    
    printPlaces: [],       // 打印点列表
    printPlaceIndex: 0,    // 选中的打印点索引
    
    formData: {
      paperSize: 'A4',
      direction: '3',        // 3=竖版，4=横版
      printWay: 'one-sided',
      color: 'CMYGray',
      copies: 1
    },
    
    priceInfo: {
      unitPrice: 0.30,
      total: '0.00'
    },
    
    submitting: false,
    
    // 预设配置
    presets: [],
    showPresetPicker: false
  },

  onLoad() {
    this.loadPrintPlaces()
    this.loadPresets()
  },

  // 加载打印点
  async loadPrintPlaces() {
    try {
      const res = await api.getPrintPlaces()
      if (res.code === 0 && res.data && res.data.list) {
        this.setData({
          printPlaces: res.data.list
        })
      }
    } catch (error) {
      console.error('加载打印点失败:', error)
    }
  },

  // 加载预设配置
  loadPresets() {
    try {
      const presets = wx.getStorageSync('printPresets') || []
      this.setData({ presets })
    } catch (error) {
      console.error('加载预设配置失败:', error)
    }
  },

  // ============ 文件选择 ============

  /**
   * 从微信聊天记录选择文件（支持多选）
   */
  chooseFromChat() {
    this.selectFiles('chat')
  },

  /**
   * 从手机选择文件（支持多选）
   */
  chooseFromFile() {
    this.selectFiles('file')
  },

  /**
   * 选择文件
   */
  selectFiles(source) {
    const that = this
    wx.chooseMessageFile({
      count: 10, // 最多选择10个文件
      type: source === 'chat' ? 'all' : 'file',
      extension: ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'],
      success: (res) => {
        const files = res.tempFiles
        that.processSelectedFiles(files)
      },
      fail: (error) => {
        console.log('选择文件取消或失败:', error)
      }
    })
  },

  /**
   * 添加更多文件
   */
  addMoreFiles() {
    this.selectFiles('file')
  },

  /**
   * 处理选中的多个文件
   */
  processSelectedFiles(files) {
    const validFiles = []
    
    for (const file of files) {
      // 检查文件大小
      if (file.size > 50 * 1024 * 1024) {
        util.showToast(`${file.name} 超过50MB，已跳过`)
        continue
      }
      
      // 检查文件类型
      const typeInfo = util.checkFileType(file.name)
      if (!typeInfo) {
        util.showToast(`${file.name} 格式不支持，已跳过`)
        continue
      }
      
      // 检查是否已存在
      const exists = this.data.fileList.some(f => f.name === file.name && f.sizeBytes === file.size)
      if (exists) {
        util.showToast(`${file.name} 已添加，已跳过`)
        continue
      }
      
      validFiles.push({
        id: Date.now() + Math.random().toString(36).substr(2, 9),
        path: file.path,
        name: file.name,
        size: util.formatFileSize(file.size),
        sizeBytes: file.size,
        type: typeInfo.type,
        needConvert: typeInfo.needConvert,
        pages: 0,
        fileId: null,
        filePath: null,
        uploading: false,
        converting: false
      })
    }
    
    if (validFiles.length === 0) return
    
    // 添加到文件列表
    const fileList = [...this.data.fileList, ...validFiles]
    this.setData({ fileList })
    
    // 依次上传文件
    this.uploadFilesSequentially(validFiles)
  },

  /**
   * 依次上传文件
   */
  async uploadFilesSequentially(files) {
    for (const file of files) {
      await this.uploadSingleFile(file.id)
    }
  },

  /**
   * 上传单个文件
   */
  async uploadSingleFile(fileId) {
    const file = this.data.fileList.find(f => f.id === fileId)
    if (!file) return
    
    // 标记上传中
    this.updateFileStatus(fileId, { uploading: true })
    this.setData({ hasUploading: true })
    
    try {
      const res = await api.uploadFile(file.path)
      
      if (res.code === 0) {
        const data = res.data
        const updateData = {
          fileId: data.fileId,
          filePath: data.filePath,
          pages: data.pageCount || 0,
          uploading: false
        }
        
        this.updateFileStatus(fileId, updateData)
        
        // 如果需要转换
        if (file.needConvert) {
          this.startConvert(fileId, data.fileId)
        } else {
          this.calculateTotals()
        }
      } else {
        this.updateFileStatus(fileId, { uploading: false })
        util.showToast(`${file.name} 上传失败`)
      }
    } catch (error) {
      console.error('上传失败:', error)
      this.updateFileStatus(fileId, { uploading: false })
      util.showToast(`${file.name} 上传失败`)
    }
    
    // 检查是否还有文件在上传
    this.checkUploadingStatus()
  },

  /**
   * 开始转换
   */
  async startConvert(fileId, uploadFileId) {
    this.updateFileStatus(fileId, { converting: true })
    
    let retryCount = 0
    const maxRetry = 20
    
    const checkConvert = async () => {
      try {
        const res = await api.getConvertStatus(uploadFileId)
        
        if (res.code === 0) {
          const { status, pageCount } = res.data
          
          if (status === 'success') {
            this.updateFileStatus(fileId, { 
              converting: false, 
              pages: pageCount 
            })
            this.calculateTotals()
            return
          } else if (status === 'failed') {
            this.updateFileStatus(fileId, { converting: false })
            util.showToast('文件转换失败')
            return
          }
        }
        
        retryCount++
        if (retryCount < maxRetry) {
          setTimeout(checkConvert, 3000)
        } else {
          this.updateFileStatus(fileId, { converting: false })
          util.showToast('转换超时')
        }
      } catch (error) {
        console.error('查询转换状态失败:', error)
        retryCount++
        if (retryCount < maxRetry) {
          setTimeout(checkConvert, 3000)
        } else {
          this.updateFileStatus(fileId, { converting: false })
        }
      }
    }
    
    checkConvert()
  },

  /**
   * 更新文件状态
   */
  updateFileStatus(fileId, updates) {
    const fileList = this.data.fileList.map(f => {
      if (f.id === fileId) {
        return { ...f, ...updates }
      }
      return f
    })
    this.setData({ fileList })
  },

  /**
   * 检查上传状态
   */
  checkUploadingStatus() {
    const hasUploading = this.data.fileList.some(f => f.uploading || f.converting)
    this.setData({ hasUploading })
  },

  /**
   * 计算总数
   */
  calculateTotals() {
    const totalPages = this.data.fileList.reduce((sum, f) => sum + (f.pages || 0), 0)
    this.setData({ totalPages })
    this.calculatePrice()
  },

  /**
   * 移除文件
   */
  removeFile(e) {
    const index = e.currentTarget.dataset.index
    const fileList = this.data.fileList.filter((_, i) => i !== index)
    this.setData({ fileList })
    this.calculateTotals()
    this.checkUploadingStatus()
  },

  /**
   * 清空所有文件
   */
  async clearAllFiles() {
    const confirm = await util.showConfirm('确定要清空所有文件吗？')
    if (!confirm) return
    
    this.setData({ 
      fileList: [],
      totalPages: 0,
      priceInfo: { unitPrice: 0.30, total: '0.00' }
    })
  },

  /**
   * 预览文件
   */
  previewFile(e) {
    const index = e.currentTarget.dataset.index
    const file = this.data.fileList[index]
    if (!file) return
    
    if (file.type === 'image') {
      wx.previewImage({
        urls: [file.path],
        current: file.path
      })
    } else if (file.type === 'pdf') {
      if (file.filePath) {
        const app = getApp()
        const baseUrl = app.globalData.baseUrl || ''
        const fileUrl = `${baseUrl}/static/Upload_Files/${file.filePath}`
        
        wx.showLoading({ title: '加载中...' })
        wx.downloadFile({
          url: fileUrl,
          success: (res) => {
            wx.hideLoading()
            if (res.statusCode === 200) {
              wx.openDocument({
                filePath: res.tempFilePath,
                fileType: 'pdf',
                fail: (err) => {
                  console.error('打开文档失败:', err)
                  util.showToast('打开文档失败')
                }
              })
            }
          },
          fail: () => {
            wx.hideLoading()
            util.showToast('文件加载失败')
          }
        })
      } else {
        wx.openDocument({
          filePath: file.path,
          fileType: 'pdf',
          fail: () => util.showToast('打开文档失败')
        })
      }
    } else {
      util.showToast('该文件类型不支持预览')
    }
  },

  // ============ 打印参数 ============

  onPrintPlaceChange(e) {
    this.setData({ printPlaceIndex: e.detail.value })
  },

  onPaperSizeChange(e) {
    this.setData({ 'formData.paperSize': e.currentTarget.dataset.value })
  },

  onDirectionChange(e) {
    this.setData({ 'formData.direction': e.currentTarget.dataset.value })
  },

  onPrintWayChange(e) {
    this.setData({ 'formData.printWay': e.currentTarget.dataset.value })
    this.calculatePrice()
  },

  onColorChange(e) {
    this.setData({ 'formData.color': e.currentTarget.dataset.value })
    this.calculatePrice()
  },

  onCopiesMinus() {
    const { copies } = this.data.formData
    if (copies > 1) {
      this.setData({ 'formData.copies': copies - 1 })
      this.calculatePrice()
    }
  },

  onCopiesPlus() {
    const { copies } = this.data.formData
    if (copies < 99) {
      this.setData({ 'formData.copies': copies + 1 })
      this.calculatePrice()
    }
  },

  onCopiesInput(e) {
    let value = parseInt(e.detail.value) || 1
    value = Math.max(1, Math.min(99, value))
    this.setData({ 'formData.copies': value })
    this.calculatePrice()
  },

  // 计算价格
  calculatePrice() {
    const { formData, totalPages, fileList } = this.data
    
    // 如果没有文件或总页数为0，不计算价格
    if (fileList.length === 0 || totalPages === 0) {
      this.setData({ 
        priceInfo: { unitPrice: 0.30, total: '0.00' }
      })
      return
    }
    
    const result = util.calculatePrice(
      formData.color,
      formData.printWay,
      totalPages,
      formData.copies
    )
    
    this.setData({ priceInfo: result })
  },

  // ============ 预设配置 ============

  /**
   * 显示预设选择器
   */
  showPresetPicker() {
    if (this.data.presets.length === 0) {
      util.showToast('暂无预设配置')
      return
    }
    this.setData({ showPresetPicker: true })
  },

  /**
   * 隐藏预设选择器
   */
  hidePresetPicker() {
    this.setData({ showPresetPicker: false })
  },

  /**
   * 选择预设
   */
  selectPreset(e) {
    const index = e.currentTarget.dataset.index
    const preset = this.data.presets[index]
    
    this.setData({
      formData: {
        paperSize: preset.paperSize || 'A4',
        direction: preset.direction || '3',
        printWay: preset.printWay || 'one-sided',
        color: preset.color || 'CMYGray',
        copies: preset.copies || 1
      },
      showPresetPicker: false
    })
    
    this.calculatePrice()
    util.showSuccess(`已应用「${preset.name}」`)
  },

  /**
   * 保存当前配置为预设
   */
  async saveAsPreset() {
    const { formData, presets } = this.data
    
    const name = await this.showInputModal('请输入预设名称')
    if (!name) return
    
    const newPreset = {
      id: Date.now().toString(),
      name,
      ...formData
    }
    
    const newPresets = [...presets, newPreset]
    this.setData({ presets: newPresets })
    
    try {
      wx.setStorageSync('printPresets', newPresets)
      util.showSuccess('预设已保存')
    } catch (error) {
      console.error('保存预设失败:', error)
      util.showToast('保存失败')
    }
  },

  /**
   * 删除预设
   */
  deletePreset(e) {
    const id = e.currentTarget.dataset.id
    const presets = this.data.presets.filter(p => p.id !== id)
    this.setData({ presets })
    wx.setStorageSync('printPresets', presets)
    util.showSuccess('已删除')
  },

  /**
   * 输入弹窗
   */
  showInputModal(title) {
    return new Promise((resolve) => {
      wx.showModal({
        title,
        editable: true,
        placeholderText: '例如：黑白双面',
        success: (res) => {
          if (res.confirm && res.content) {
            resolve(res.content.trim())
          } else {
            resolve(null)
          }
        }
      })
    })
  },

  // ============ 提交订单 ============

  async submitOrder() {
    const { fileList, formData, printPlaces, printPlaceIndex, submitting, hasUploading } = this.data
    
    if (submitting) return
    if (hasUploading) {
      util.showToast('文件上传中，请稍候')
      return
    }
    if (fileList.length === 0) {
      util.showToast('请先添加文件')
      return
    }
    
    // 检查文件是否都上传完成
    const notUploaded = fileList.filter(f => !f.fileId)
    if (notUploaded.length > 0) {
      util.showToast('部分文件未上传完成')
      return
    }
    
    // 检查页数
    if (this.data.totalPages === 0) {
      util.showToast('无法获取文件页数')
      return
    }
    
    if (printPlaces.length === 0) {
      util.showToast('暂无可用打印点')
      return
    }
    
    this.setData({ submitting: true })
    util.showLoading('提交中...')
    
    try {
      // 批量创建订单（每个文件一个订单，统一打印参数）
      const orders = fileList.map(file => ({
        fileId: file.fileId,
        fileName: file.name,
        filePath: file.filePath,
        printPlace: printPlaces[printPlaceIndex].key || printPlaces[printPlaceIndex].name,
        copies: formData.copies,
        paperSize: formData.paperSize,
        direction: formData.direction,
        printWay: formData.printWay,
        color: formData.color,
        pages: file.pages
      }))
      
      const res = await api.createBatchOrders({ orders })
      
      util.hideLoading()
      
      if (res.code === 0) {
        // 跳转到支付页
        wx.redirectTo({
          url: `/pages/pay/pay?tradeNumbers=${res.data.tradeNumbers.join(',')}&amount=${res.data.totalAmount}`
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
      title: 'PrintYun云打印 - 上传文件立即下单',
      path: '/pages/index/index'
    }
  }
})
