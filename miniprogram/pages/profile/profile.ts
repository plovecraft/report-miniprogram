import { clearAuthToken, CurrentUser, ensureWechatLogin, getCurrentUser, getCurrentUserUsage, UsageRecord } from '../../services/api'

interface ProfileUsageRecord extends UsageRecord {
  eventText: string
  timeText: string
}

interface ProfilePageData {
  loggedIn: boolean
  loginLoading: boolean
  usageLoading: boolean
  user: CurrentUser | null
  userLabel: string
  usageRecords: ProfileUsageRecord[]
  errorMessage: string
}

Page({
  data: {
    loggedIn: false,
    loginLoading: false,
    usageLoading: false,
    user: null,
    userLabel: '',
    usageRecords: [],
    errorMessage: '',
  } as ProfilePageData,

  onShow() {
    this.refreshProfile()
  },

  async refreshProfile() {
    const user = await getCurrentUser()
    if (!user) {
      this.setData({
        loggedIn: false,
        user: null,
        userLabel: '',
        usageRecords: [],
        errorMessage: '',
      })
      return
    }
    this.setData({
      loggedIn: true,
      user,
      userLabel: shortUserId(user.userId),
      errorMessage: '',
    })
    this.loadUsageRecords()
  },

  async loginWithWechat() {
    this.setData({ loginLoading: true })
    try {
      await ensureWechatLogin()
      await this.refreshProfile()
      wx.showToast({ title: '登录成功', icon: 'success' })
    } catch (error) {
      const message = error instanceof Error ? error.message : '登录失败'
      wx.showToast({ title: message, icon: 'none', duration: 2400 })
    } finally {
      this.setData({ loginLoading: false })
    }
  },

  logout() {
    clearAuthToken()
    this.setData({
      loggedIn: false,
      user: null,
      userLabel: '',
      usageRecords: [],
      errorMessage: '',
    })
    wx.showToast({ title: '已退出本机登录', icon: 'success' })
  },

  async loadUsageRecords() {
    this.setData({ usageLoading: true })
    try {
      const response = await getCurrentUserUsage()
      this.setData({
        usageRecords: response.records.map((record) => ({
          ...record,
          eventText: usageEventLabel(record.event),
          timeText: formatTime(record.createdAt),
        })),
        errorMessage: '',
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '读取使用记录失败'
      this.setData({ errorMessage: message })
    } finally {
      this.setData({ usageLoading: false })
    }
  },

  openHistory() {
    wx.navigateTo({
      url: '/pages/history/history',
    })
  },
})

function shortUserId(userId: string) {
  if (!userId) {
    return ''
  }
  return userId.length > 10 ? `${userId.slice(0, 6)}...${userId.slice(-4)}` : userId
}

function usageEventLabel(event: string) {
  const labels: Record<string, string> = {
    task_created: '创建任务',
    task_done: '生成完成',
    task_failed: '生成失败',
  }
  return labels[event] || event
}

function formatTime(timestamp: number) {
  if (!timestamp) {
    return ''
  }
  const date = new Date(timestamp * 1000)
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}
