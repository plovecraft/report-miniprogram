import { CurrentUser, getCurrentUser, hasAuthToken } from '../../services/api'

Page({
  data: {
    loggedIn: false,
    userLabel: '',
    requirements: [
      '原始实验报告 DOCX',
      '实验指导书 DOC/DOCX/PDF',
      '程序图、接线图、现象图等实验图片',
    ],
    steps: ['上传材料', '后端生成', '下载 DOCX'],
  },

  onShow() {
    this.refreshLoginState()
  },

  async refreshLoginState() {
    if (!hasAuthToken()) {
      this.setData({ loggedIn: false, userLabel: '' })
      return
    }
    const user = await getCurrentUser()
    this.setLoginUser(user)
  },

  setLoginUser(user: CurrentUser | null) {
    if (!user) {
      this.setData({ loggedIn: false, userLabel: '' })
      return
    }
    this.setData({
      loggedIn: true,
      userLabel: shortUserId(user.userId),
    })
  },

  startCreate() {
    wx.navigateTo({
      url: '/pages/create/create',
    })
  },

  openHistory() {
    wx.navigateTo({
      url: '/pages/history/history',
    })
  },

  openProfile() {
    wx.navigateTo({
      url: '/pages/profile/profile',
    })
  },
})

function shortUserId(userId: string) {
  if (!userId) {
    return ''
  }
  return userId.length > 10 ? `${userId.slice(0, 6)}...${userId.slice(-4)}` : userId
}
