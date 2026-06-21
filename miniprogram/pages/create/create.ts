import { createReportTask, ensureWechatLogin, LocalFile, uploadTaskFile } from '../../services/api'

const MAX_IMAGE_FILES = 50
const USER_PROFILE_STORAGE_KEY = 'lab_report_user_profile_v1'

interface CreatePageData {
  uploadMode: 'normal' | 'zip'
  reportFile: LocalFile | null
  guideFile: LocalFile | null
  materialZipFile: LocalFile | null
  imageFiles: ImageFile[]
  imageCategoryOptions: ImageCategoryOption[]
  experimentNo: string
  courseName: string
  teacherName: string
  offeringCollegeLab: string
  studentCollege: string
  studentName: string
  studentId: string
  className: string
  exportPdf: boolean
  submitting: boolean
}

interface UserProfile {
  courseName: string
  teacherName: string
  offeringCollegeLab: string
  studentCollege: string
  studentName: string
  studentId: string
  className: string
}

interface ImageFile extends LocalFile {
  category: string
  categoryLabel: string
  categoryIndex: number
}

interface ImageCategoryOption {
  label: string
  value: string
}

const IMAGE_CATEGORY_OPTIONS: ImageCategoryOption[] = [
  { label: '自动识别', value: 'auto' },
  { label: '接线图', value: 'wiring' },
  { label: '基础题程序', value: 'basic_program' },
  { label: '思考题1程序', value: 'thought1_program' },
  { label: '思考题2程序', value: 'thought2_program' },
  { label: '基础题现象', value: 'basic_result' },
  { label: '思考题1现象', value: 'thought1_result' },
  { label: '思考题2现象', value: 'thought2_result' },
  { label: '实验现象', value: 'result' },
  { label: '实物图', value: 'physical' },
  { label: '其他', value: 'other' },
  { label: '不插入', value: 'skip' },
]

Page({
  data: {
    uploadMode: 'normal',
    reportFile: null,
    guideFile: null,
    materialZipFile: null,
    imageFiles: [],
    imageCategoryOptions: IMAGE_CATEGORY_OPTIONS,
    experimentNo: '',
    courseName: '',
    teacherName: '',
    offeringCollegeLab: '',
    studentCollege: '',
    studentName: '',
    studentId: '',
    className: '',
    exportPdf: false,
    submitting: false,
  } as CreatePageData,

  onLoad() {
    this.loadUserProfile()
  },

  selectUploadMode(event: WechatMiniprogram.TouchEvent) {
    const mode = String(event.currentTarget.dataset.mode || 'normal') as 'normal' | 'zip'
    this.setData({ uploadMode: mode })
  },

  chooseReportFile() {
    this.chooseSingleFile('reportFile', ['docx'])
  },

  chooseGuideFile() {
    this.chooseSingleFile('guideFile', ['doc', 'docx', 'pdf'])
  },

  chooseMaterialZipFile() {
    this.chooseSingleFile('materialZipFile', ['zip'])
  },

  chooseImages() {
    const remaining = MAX_IMAGE_FILES - this.data.imageFiles.length
    if (remaining <= 0) {
      wx.showToast({ title: `最多选择 ${MAX_IMAGE_FILES} 张图片`, icon: 'none' })
      return
    }

    wx.chooseMessageFile({
      count: remaining,
      type: 'image',
      success: (res) => {
        const existingKeys = new Set(this.data.imageFiles.map((file) => `${file.name}:${file.size || 0}`))
        const newFiles = res.tempFiles
          .map((file) => ({
            path: file.path,
            name: file.name,
            size: file.size,
            ...inferImageCategory(file.name),
          }))
          .filter((file) => !existingKeys.has(`${file.name}:${file.size || 0}`))

        this.setData({
          imageFiles: this.data.imageFiles.concat(newFiles).slice(0, MAX_IMAGE_FILES),
        })
      },
    })
  },

  previewImage(event: WechatMiniprogram.TouchEvent) {
    const index = Number(event.currentTarget.dataset.index || 0)
    const current = this.data.imageFiles[index]
    if (!current) {
      return
    }
    wx.previewImage({
      current: current.path,
      urls: this.data.imageFiles.map((file) => file.path),
    })
  },

  onImageCategoryChange(event: WechatMiniprogram.PickerChange) {
    const imageIndex = Number(event.currentTarget.dataset.index)
    const optionIndex = Number(event.detail.value)
    const option = IMAGE_CATEGORY_OPTIONS[optionIndex]
    if (!option || Number.isNaN(imageIndex)) {
      return
    }
    const imageFiles = this.data.imageFiles.slice()
    if (!imageFiles[imageIndex]) {
      return
    }
    imageFiles[imageIndex] = {
      ...imageFiles[imageIndex],
      category: option.value,
      categoryLabel: option.label,
      categoryIndex: optionIndex,
    }
    this.setData({ imageFiles })
  },

  chooseSingleFile(key: 'reportFile' | 'guideFile' | 'materialZipFile', extension: string[]) {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension,
      success: (res) => {
        const file = res.tempFiles[0]
        this.setData({
          [key]: {
            path: file.path,
            name: file.name,
            size: file.size,
          },
        })
      },
    })
  },

  onExperimentNoInput(event: WechatMiniprogram.Input) {
    this.setData({ experimentNo: event.detail.value })
  },

  onCourseNameInput(event: WechatMiniprogram.Input) {
    this.setData({ courseName: event.detail.value })
  },

  onTeacherNameInput(event: WechatMiniprogram.Input) {
    this.setData({ teacherName: event.detail.value })
  },

  onOfferingCollegeLabInput(event: WechatMiniprogram.Input) {
    this.setData({ offeringCollegeLab: event.detail.value })
  },

  onStudentCollegeInput(event: WechatMiniprogram.Input) {
    this.setData({ studentCollege: event.detail.value })
  },

  onStudentNameInput(event: WechatMiniprogram.Input) {
    this.setData({ studentName: event.detail.value })
  },

  onStudentIdInput(event: WechatMiniprogram.Input) {
    this.setData({ studentId: event.detail.value })
  },

  onClassNameInput(event: WechatMiniprogram.Input) {
    this.setData({ className: event.detail.value })
  },

  onExportPdfChange(event: WechatMiniprogram.SwitchChange) {
    this.setData({ exportPdf: event.detail.value })
  },

  loadUserProfile() {
    try {
      const profile = wx.getStorageSync(USER_PROFILE_STORAGE_KEY) as Partial<UserProfile> | ''
      if (!profile || typeof profile !== 'object') {
        return
      }
      this.setData({
        courseName: String(profile.courseName || ''),
        teacherName: String(profile.teacherName || ''),
        offeringCollegeLab: String(profile.offeringCollegeLab || ''),
        studentCollege: String(profile.studentCollege || ''),
        studentName: String(profile.studentName || ''),
        studentId: String(profile.studentId || ''),
        className: String(profile.className || ''),
      })
    } catch (error) {
      wx.showToast({ title: '读取常用信息失败', icon: 'none' })
    }
  },

  saveUserProfileAction() {
    this.saveUserProfile()
    wx.showToast({ title: '已保存常用信息', icon: 'success' })
  },

  clearUserProfileAction() {
    wx.showModal({
      title: '清空常用信息',
      content: '会清空本机保存的姓名、学号、班级、学院、课程和老师信息。',
      confirmText: '清空',
      success: (res) => {
        if (!res.confirm) {
          return
        }
        wx.removeStorageSync(USER_PROFILE_STORAGE_KEY)
        this.setData({
          courseName: '',
          teacherName: '',
          offeringCollegeLab: '',
          studentCollege: '',
          studentName: '',
          studentId: '',
          className: '',
        })
        wx.showToast({ title: '已清空', icon: 'success' })
      },
    })
  },

  saveUserProfile() {
    const profile: UserProfile = {
      courseName: this.data.courseName.trim(),
      teacherName: this.data.teacherName.trim(),
      offeringCollegeLab: this.data.offeringCollegeLab.trim(),
      studentCollege: this.data.studentCollege.trim(),
      studentName: this.data.studentName.trim(),
      studentId: this.data.studentId.trim(),
      className: this.data.className.trim(),
    }
    wx.setStorageSync(USER_PROFILE_STORAGE_KEY, profile)
  },

  validateForm() {
    if (this.data.uploadMode === 'zip') {
      if (!this.data.materialZipFile) {
        return '请先选择实验材料 ZIP 压缩包'
      }
      if (!this.data.experimentNo.trim()) {
        return '请输入实验序号'
      }
      return ''
    }
    if (!this.data.reportFile) {
      return '请先选择原始实验报告 DOCX'
    }
    if (!this.data.guideFile) {
      return '请先选择实验指导书'
    }
    if (!this.data.experimentNo.trim()) {
      return '请输入实验序号'
    }
    return ''
  },

  async submitTask() {
    const errorMessage = this.validateForm()
    if (errorMessage) {
      wx.showToast({ title: errorMessage, icon: 'none' })
      return
    }

    this.setData({ submitting: true })
    wx.showLoading({ title: '正在提交' })
    let toastMessage = ''

    try {
      await ensureWechatLogin()
      this.saveUserProfile()
      const task = await createReportTask({
        experimentNo: this.data.experimentNo.trim(),
        courseName: this.data.courseName.trim(),
        teacherName: this.data.teacherName.trim(),
        offeringCollegeLab: this.data.offeringCollegeLab.trim(),
        studentCollege: this.data.studentCollege.trim(),
        studentName: this.data.studentName.trim(),
        studentId: this.data.studentId.trim(),
        className: this.data.className.trim(),
        exportPdf: this.data.exportPdf,
        imageCount: this.data.uploadMode === 'zip' ? 0 : this.data.imageFiles.length,
        imageMetas: this.data.uploadMode === 'zip' ? [] : this.data.imageFiles.map((file) => ({
          filename: file.name,
          category: file.category,
        })),
      })

      if (this.data.uploadMode === 'zip') {
        await uploadTaskFile(task.taskId, 'materialZip', this.data.materialZipFile as LocalFile)
      } else {
        const reportFile = this.data.reportFile as LocalFile
        const guideFile = this.data.guideFile as LocalFile
        await uploadTaskFile(task.taskId, 'report', reportFile)
        await uploadTaskFile(task.taskId, 'guide', guideFile)

        for (const imageFile of this.data.imageFiles) {
          await uploadTaskFile(task.taskId, 'image', imageFile)
        }
      }

      wx.navigateTo({
        url: `/pages/task/task?taskId=${encodeURIComponent(task.taskId)}`,
      })
    } catch (error) {
      toastMessage = error instanceof Error ? error.message : '提交任务失败'
    } finally {
      wx.hideLoading()
      this.setData({ submitting: false })
      if (toastMessage) {
        wx.showToast({ title: toastMessage, icon: 'none', duration: 2600 })
      }
    }
  },
})

function inferImageCategory(filename: string): Pick<ImageFile, 'category' | 'categoryLabel' | 'categoryIndex'> {
  const name = filename.toLowerCase()
  let category = 'auto'
  if (name.includes('接线') || name.includes('面板') || name.includes('wiring')) {
    category = 'wiring'
  } else if (name.includes('实物') || name.includes('现场')) {
    category = 'physical'
  } else if (name.includes('基础') && (name.includes('现象') || name.includes('结果'))) {
    category = 'basic_result'
  } else if ((name.includes('思考题1') || name.includes('思考1')) && (name.includes('现象') || name.includes('结果'))) {
    category = 'thought1_result'
  } else if ((name.includes('思考题2') || name.includes('思考2')) && (name.includes('现象') || name.includes('结果'))) {
    category = 'thought2_result'
  } else if (name.includes('程序图1')) {
    category = 'basic_program'
  } else if (name.includes('程序图2')) {
    category = 'thought1_program'
  } else if (name.includes('程序图3')) {
    category = 'thought2_program'
  } else if (name.includes('程序') || name.includes('梯形')) {
    category = 'auto'
  } else if (name.includes('现象') || name.includes('结果')) {
    category = 'result'
  }

  const categoryIndex = Math.max(0, IMAGE_CATEGORY_OPTIONS.findIndex((item) => item.value === category))
  const option = IMAGE_CATEGORY_OPTIONS[categoryIndex] || IMAGE_CATEGORY_OPTIONS[0]
  return {
    category: option.value,
    categoryLabel: option.label,
    categoryIndex,
  }
}
