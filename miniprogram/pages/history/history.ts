import { ensureWechatLogin, listReportTasks, ReportTask, TaskStatus } from '../../services/api'

interface HistoryTask extends ReportTask {
  statusText: string
  updatedText: string
}

interface HistoryPageData {
  tasks: HistoryTask[]
  loading: boolean
  errorMessage: string
}

const POLL_INTERVAL = 3000
let pollTimer = 0

Page({
  data: {
    tasks: [],
    loading: true,
    errorMessage: '',
  } as HistoryPageData,

  onLoad() {
    this.refreshTasks()
  },

  onShow() {
    this.refreshTasks()
  },

  onUnload() {
    this.stopPolling()
  },

  async refreshTasks() {
    try {
      await ensureWechatLogin()
      const response = await listReportTasks()
      const tasks = response.tasks.map((task) => ({
        ...task,
        statusText: statusLabel(task.status),
        updatedText: formatTaskTime(task.updatedAt || task.createdAt || 0),
      }))
      this.setData({ tasks, loading: false, errorMessage: '' })
      if (tasks.some((task) => isActiveStatus(task.status))) {
        this.schedulePolling()
      } else {
        this.stopPolling()
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '读取任务历史失败'
      this.setData({ loading: false, errorMessage: message })
      this.schedulePolling()
    }
  },

  openTask(event: WechatMiniprogram.TouchEvent) {
    const taskId = String(event.currentTarget.dataset.taskId || '')
    if (!taskId) {
      return
    }
    wx.navigateTo({
      url: `/pages/task/task?taskId=${encodeURIComponent(taskId)}`,
    })
  },

  createTask() {
    wx.navigateTo({
      url: '/pages/create/create',
    })
  },

  schedulePolling() {
    this.stopPolling()
    pollTimer = setTimeout(() => {
      this.refreshTasks()
    }, POLL_INTERVAL)
  },

  stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = 0
    }
  },
})

function statusLabel(status: TaskStatus) {
  const labels: Record<TaskStatus, string> = {
    queued: '排队中',
    uploading: '上传中',
    previewing: '生成预览',
    preview_ready: '等待确认',
    processing: '生成中',
    done: '已完成',
    failed: '失败',
  }
  return labels[status] || status
}

function isActiveStatus(status: TaskStatus) {
  return status === 'queued' || status === 'uploading' || status === 'previewing' || status === 'processing'
}

function formatTaskTime(timestamp: number) {
  if (!timestamp) {
    return ''
  }
  const date = new Date(timestamp * 1000)
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hour = pad(date.getHours())
  const minute = pad(date.getMinutes())
  return `${month}-${day} ${hour}:${minute}`
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}
