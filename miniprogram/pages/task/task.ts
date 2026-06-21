import {
  AiPlannerPreview,
  ImagePlanItem,
  ImagePlanOverrideItem,
  ManualTableItem,
  confirmReportTask,
  downloadTaskResult,
  getReportTask,
  ReportTask,
  TablePlanItem,
  TaskStatus,
  taskImageUrl,
  updateLayoutPlanSource,
  updateReportImagePlan,
  updateReportImageOverrides,
  updateTablePlan,
} from '../../services/api'


interface StatusStep {
  key: TaskStatus
  title: string
}

interface DropCardRect {
  left: number
  right?: number
  top: number
  bottom?: number
  width: number
  height: number
  dataset?: {
    imageIndex?: string | number
    sectionIndex?: string | number
  }
}

interface TaskPageData {
  taskId: string
  task: ReportTask | null
  loading: boolean
  confirming: boolean
  downloading: boolean
  draggingImageIndex: number
  draggingActive: boolean
  draggingImageUrl: string
  dragInsertSectionIndex: number
  dragInsertBeforeImageIndex: number
  dragInsertAtEnd: boolean
  dragStartX: number
  dragStartY: number
  dragX: number
  dragY: number
  pageScrollTop: number
  windowHeight: number
  dragMessage: string
  errorMessage: string
  savingTablePlan: boolean
  savingImagePlan: boolean
  manualTableDraftTitle: string
  manualTableDraftHeadersText: string
  unsavedSelectedTableCount: number
  unsavedSelectedTableTitles: string[]
  previewLayoutSourceIsAi: boolean
  aiPlannerView: {
      visible: boolean
      statusText: string
      statusClass: string
      currentSourceText: string
      adoptable: boolean
      usingAi: boolean
      adoptionBlockedReason: string
      summaryLines: string[]
      diffLines: string[]
      warningLines: string[]
      errorText: string
      note: string
  }
  imageCategoryOptions: { value: string; label: string }[]
  steps: StatusStep[]
}

interface LocalTablePlanItem extends TablePlanItem {
  dirty?: boolean
  saving?: boolean
  saveError?: string
}

interface LocalImagePlanItem extends ImagePlanItem {
  dirty?: boolean
  saving?: boolean
  saveError?: string
}

const POLL_INTERVAL = 2500
const AUTO_SCROLL_EDGE = 86
const AUTO_SCROLL_STEP = 34
const DRAG_HIT_TEST_INTERVAL = 80
let pollTimer = 0
let autoScrollTimer = 0
let autoScrollDirection = 0
let lastDragHitTestAt = 0

Page({
  data: {
    taskId: '',
    task: null,
    loading: true,
    confirming: false,
    downloading: false,
    draggingImageIndex: -1,
    draggingActive: false,
    draggingImageUrl: '',
    dragInsertSectionIndex: -1,
    dragInsertBeforeImageIndex: -1,
    dragInsertAtEnd: false,
    dragStartX: 0,
    dragStartY: 0,
    dragX: 0,
    dragY: 0,
    pageScrollTop: 0,
    windowHeight: 0,
    dragMessage: '',
    errorMessage: '',
    savingTablePlan: false,
    savingImagePlan: false,
    manualTableDraftTitle: '',
    manualTableDraftHeadersText: '项目,内容,备注',
    unsavedSelectedTableCount: 0,
    unsavedSelectedTableTitles: [],
    previewLayoutSourceIsAi: false,
    aiPlannerView: {
      visible: false,
      statusText: '',
      statusClass: '',
      currentSourceText: '',
      adoptable: false,
      usingAi: false,
      adoptionBlockedReason: '',
      summaryLines: [],
      diffLines: [],
      warningLines: [],
      errorText: '',
      note: 'AI 规划仅为影子模式参考，不影响本次报告生成。',
    },
    imageCategoryOptions: [
      { value: 'program', label: '程序图' },
      { value: 'wiring', label: '接线图' },
      { value: 'device', label: '实物图' },
      { value: 'phenomenon', label: '实验现象图' },
      { value: 'document', label: '文档/截图' },
      { value: 'chart', label: '曲线/图表' },
      { value: 'instrument', label: '仪表图' },
      { value: 'unknown', label: '待确认' },
    ],
    steps: [
      { key: 'queued', title: '排队' },
      { key: 'uploading', title: '上传' },
      { key: 'previewing', title: '预览' },
      { key: 'preview_ready', title: '确认' },
      { key: 'processing', title: '生成' },
      { key: 'done', title: '完成' },
    ],
  } as TaskPageData,

  onLoad(options: Record<string, string | undefined>) {
    const taskId = options.taskId || ''
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ taskId, windowHeight: systemInfo.windowHeight || 0 })
    if (!taskId) {
      this.setData({ loading: false, errorMessage: '缺少任务编号' })
      return
    }
    this.refreshTask()
  },

  hasUnsavedSelectedTables() {
    return collectUnsavedSelectedTableTitles(this.data.task).length > 0
  },

  leaveTaskPage() {
    wx.navigateBack({
      delta: 1,
      fail: () => {
        wx.redirectTo({ url: '/pages/create/create' })
      },
    })
  },

  confirmLeaveIfNeeded(onConfirm: () => void) {
    if (!this.hasUnsavedSelectedTables()) {
      onConfirm()
      return
    }
    wx.showModal({
      title: '未保存修改',
      content: '还有未保存的表格修改，离开后这些修改不会写入报告。是否继续离开？',
      confirmText: '继续离开',
      cancelText: '留在当前页',
      success: (res) => {
        if (res.confirm) {
          onConfirm()
        }
      },
    })
  },

  attemptLeavePage() {
    this.confirmLeaveIfNeeded(() => {
      this.leaveTaskPage()
    })
  },

  onBackTap() {
    this.attemptLeavePage()
  },

  onHide() {
    if (this.hasUnsavedSelectedTables()) {
      console.warn('[task] unsaved selected table edits still exist on hide')
    }
  },

  onUnload() {
    if (this.hasUnsavedSelectedTables()) {
      console.warn('[task] unsaved selected table edits still exist on unload')
    }
    this.stopPolling()
    this.stopAutoScroll()
  },
  onPageScroll(event: { scrollTop: number }) {
    this.setData({ pageScrollTop: event.scrollTop })
  },

  async refreshTask() {
    if (!this.data.taskId) {
      return
    }

    try {
      const task = await getReportTask(this.data.taskId)
      setTaskWithDerivedState(this, this.withPreviewImageUrls(task), {
        loading: false,
        errorMessage: task.status === 'failed' ? task.message : '',
      })

      if (task.status === 'preview_ready' || task.status === 'done' || task.status === 'failed') {
        this.stopPolling()
        return
      }
      this.schedulePolling()
    } catch (error) {
      const message = error instanceof Error ? error.message : '查询任务失败'
      this.setData({ loading: false, errorMessage: message })
      this.schedulePolling()
    }
  },

  withPreviewImageUrls(task: ReportTask, preserveDirty = true, clearedTableIds: string[] = []): ReportTask {
    if (!task.preview || !this.data.taskId) {
      return task
    }
    const currentTask = this.data.task
    const currentTablePlan = currentTask && currentTask.preview && currentTask.preview.tablePlan
      ? currentTask.preview.tablePlan as LocalTablePlanItem[]
      : []
    return {
      ...task,
      preview: {
        ...task.preview,
        template: {
          ...task.preview.template,
          confidencePercent: `${Math.round((task.preview.template.confidence || 0) * 100)}%`,
        },
        sections: task.preview.sections.map((section) => ({
          ...section,
          images: (section.images || []).map((image) => ({
            ...image,
            imageUrl: taskImageUrl(this.data.taskId, image.imageIndex),
            confidencePercent: `${Math.round((Number(image.confidence || 0)) * 100)}%`,
            reviewReasonsText: Array.isArray(image.reviewReasons) ? image.reviewReasons.join('；') : '',
          })),
        })),
        tablePlan: mergeTablePlanState(
          (task.preview.tablePlan || []) as LocalTablePlanItem[],
          currentTablePlan,
          preserveDirty,
          clearedTableIds,
        ).map((table) => ({
          ...table,
          headersText: (table.headers || []).join(' / '),
        })),
        imagePlan: task.preview.imagePlan.map((image) => ({
          ...image,
          imageUrl: taskImageUrl(this.data.taskId, image.imageIndex),
        })),
      },
    }
  },

  previewSectionImage(event: WechatMiniprogram.TouchEvent) {
    const current = String(event.currentTarget.dataset.url || '')
    const task = this.data.task
    const preview = task && task.preview ? task.preview : null
    const urls = (preview ? preview.imagePlan : [])
      .filter((image) => image.type !== 'skip')
      .map((image) => image.imageUrl || '')
      .filter((url) => !!url)
    if (!current || !urls.length) {
      return
    }
    wx.previewImage({ current, urls })
  },

  onImageDragStart(event: WechatMiniprogram.TouchEvent) {
    const imageIndex = Number(event.currentTarget.dataset.imageIndex)
    const touch = event.touches[0]
    if (Number.isNaN(imageIndex) || !touch) {
      return
    }
    const task = this.data.task
    const preview = task && task.preview ? task.preview : null
    const image = preview ? preview.imagePlan.find((item) => item.imageIndex === imageIndex) : null
    this.setData({
      draggingImageIndex: imageIndex,
      draggingActive: false,
      draggingImageUrl: image ? image.imageUrl || '' : '',
      dragInsertSectionIndex: -1,
      dragInsertBeforeImageIndex: -1,
      dragInsertAtEnd: false,
      dragStartX: touch.clientX,
      dragStartY: touch.clientY,
      dragX: touch.clientX - 56,
      dragY: touch.clientY - 56,
      dragMessage: '',
    })
  },

  onImageDragMove(event: WechatMiniprogram.TouchEvent) {
    if (this.data.draggingImageIndex < 0) {
      return
    }
    const touch = event.touches[0]
    if (!touch) {
      return
    }
    const deltaX = touch.clientX - this.data.dragStartX
    const deltaY = touch.clientY - this.data.dragStartY
    const shouldActivate = this.data.draggingActive || Math.abs(deltaX) + Math.abs(deltaY) > 10
    this.setData({
      draggingActive: shouldActivate,
      dragX: touch.clientX - 56,
      dragY: touch.clientY - 56,
      dragMessage: shouldActivate ? '松手后移动到当前章节' : '',
    })
    if (shouldActivate) {
      this.updateAutoScroll(touch.clientY)
      this.updateDragInsertHint(touch.clientX, touch.clientY)
    } else {
      this.stopAutoScroll()
    }
  },

  onImageDragEnd(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (this.data.draggingImageIndex < 0 || !task || !task.preview) {
      this.clearDragState()
      return
    }
    if (!this.data.draggingActive) {
      this.clearDragState()
      return
    }
    const touch = event.changedTouches[0]
    if (!touch) {
      this.clearDragState()
      return
    }
    const draggingImageIndex = this.data.draggingImageIndex
    wx.createSelectorQuery()
      .in(this)
      .selectAll('.preview-section')
      .boundingClientRect((rects) => {
        this.resolveDropTarget(
          touch.clientX,
          touch.clientY,
          draggingImageIndex,
          rects as WechatMiniprogram.BoundingClientRectCallbackResult[],
          (target) => {
            if (!target) {
              this.clearDragState()
              return
            }
            this.movePreviewImageToSection(draggingImageIndex, target.sectionTitle, target.insertIndex)
          },
        )
      })
      .exec()
  },

  async movePreviewImageToSection(imageIndex: number, targetSection: string, insertIndex?: number) {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId) {
      this.clearDragState()
      return
    }
    const movedImage = task.preview.imagePlan.find((image) => image.imageIndex === imageIndex)
    if (!movedImage || movedImage.type === 'skip') {
      this.clearDragState()
      return
    }

    const nextSections = task.preview.sections.map((section) => ({
      ...section,
      images: section.images.filter((image) => image.imageIndex !== imageIndex),
    }))
    const target = nextSections.find((section) => section.title === targetSection)
    if (!target) {
      this.clearDragState()
      return
    }
    const targetInsertIndex = typeof insertIndex === 'number' ? insertIndex : target.images.length
    const boundedIndex = Math.max(0, Math.min(targetInsertIndex, target.images.length))
    target.images.splice(boundedIndex, 0, { ...movedImage, section: targetSection })
    const updates = flattenSectionImages(nextSections)

    this.setData({
      task: {
        ...task,
        preview: {
          ...task.preview,
          sections: nextSections,
        },
      },
      dragMessage: '正在保存图片位置',
    })

    try {
      const updatedTask = await updateReportImagePlan(this.data.taskId, updates)
      this.setData({
        task: this.withPreviewImageUrls(updatedTask),
      })
      this.clearDragState()
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存图片位置失败'
      wx.showToast({ title: message, icon: 'none', duration: 2400 })
      this.clearDragState()
      this.refreshTask()
    }
  },

  clearDragState() {
    this.stopAutoScroll()
    lastDragHitTestAt = 0
    this.setData({
      draggingImageIndex: -1,
      draggingActive: false,
      draggingImageUrl: '',
      dragInsertSectionIndex: -1,
      dragInsertBeforeImageIndex: -1,
      dragInsertAtEnd: false,
      dragStartX: 0,
      dragStartY: 0,
      dragX: 0,
      dragY: 0,
      dragMessage: '',
    })
  },

  updateDragInsertHint(clientX: number, clientY: number) {
    const now = Date.now()
    if (now - lastDragHitTestAt < DRAG_HIT_TEST_INTERVAL) {
      return
    }
    lastDragHitTestAt = now
    const draggingImageIndex = this.data.draggingImageIndex
    wx.createSelectorQuery()
      .in(this)
      .selectAll('.preview-section')
      .boundingClientRect((rects) => {
        this.resolveDropTarget(
          clientX,
          clientY,
          draggingImageIndex,
          rects as WechatMiniprogram.BoundingClientRectCallbackResult[],
          (target) => {
            if (!target) {
              this.setData({
                dragInsertSectionIndex: -1,
                dragInsertBeforeImageIndex: -1,
                dragInsertAtEnd: false,
              })
              return
            }
            this.setData({
              dragInsertSectionIndex: target.sectionIndex,
              dragInsertBeforeImageIndex: target.beforeImageIndex,
              dragInsertAtEnd: target.insertAtEnd,
            })
          },
        )
      })
      .exec()
  },

  resolveDropTarget(
    clientX: number,
    clientY: number,
    draggingImageIndex: number,
    sectionRects: WechatMiniprogram.BoundingClientRectCallbackResult[],
    callback: (target: { sectionIndex: number; sectionTitle: string; insertIndex: number; beforeImageIndex: number; insertAtEnd: boolean } | null) => void,
  ) {
    const task = this.data.task
    const sections = task && task.preview ? task.preview.sections : []
    const sectionIndex = sectionRects.findIndex((rect) => clientY >= rect.top && clientY <= rect.bottom)
    const section = sections[sectionIndex]
    if (sectionIndex < 0 || !section) {
      callback(null)
      return
    }

    wx.createSelectorQuery()
      .in(this)
      .selectAll('.section-image-card')
      .fields({ rect: true, dataset: true }, (cardRects) => {
        const cards = ((cardRects || []) as DropCardRect[])
          .filter((rect) => Number(rect.dataset ? rect.dataset.sectionIndex : undefined) === sectionIndex)
          .filter((rect) => Number(rect.dataset ? rect.dataset.imageIndex : undefined) !== draggingImageIndex)
          .sort((a, b) => (a.top === b.top ? a.left - b.left : a.top - b.top))
        const insertIndex = countCardsBeforePointer(cards, clientX, clientY)
        const beforeImageIndex = insertIndex < cards.length ? Number(cards[insertIndex].dataset ? cards[insertIndex].dataset.imageIndex : undefined) : -1

        callback({
          sectionIndex,
          sectionTitle: section.title,
          insertIndex,
          beforeImageIndex,
          insertAtEnd: beforeImageIndex < 0,
        })
      })
      .exec()
  },

  updateAutoScroll(clientY: number) {
    let nextDirection = 0
    if (clientY < AUTO_SCROLL_EDGE) {
      nextDirection = -1
    } else if (this.data.windowHeight && clientY > this.data.windowHeight - AUTO_SCROLL_EDGE) {
      nextDirection = 1
    }

    if (!nextDirection) {
      this.stopAutoScroll()
      return
    }
    if (autoScrollTimer && autoScrollDirection === nextDirection) {
      return
    }

    this.stopAutoScroll()
    autoScrollDirection = nextDirection
    autoScrollTimer = setInterval(() => {
      const nextScrollTop = Math.max(0, this.data.pageScrollTop + autoScrollDirection * AUTO_SCROLL_STEP)
      wx.pageScrollTo({ scrollTop: nextScrollTop, duration: 0 })
      this.setData({ pageScrollTop: nextScrollTop })
    }, 60) as unknown as number
  },

  stopAutoScroll() {
    if (autoScrollTimer) {
      clearInterval(autoScrollTimer)
      autoScrollTimer = 0
      autoScrollDirection = 0
    }
  },

  schedulePolling() {
    this.stopPolling()
    pollTimer = setTimeout(() => {
      this.refreshTask()
    }, POLL_INTERVAL)
  },

  stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = 0
    }
  },

  async confirmGenerate() {
    const task = this.data.task
    if (!this.data.taskId || !task || task.status !== 'preview_ready') {
      return
    }
    if (this.hasUnsavedSelectedTables()) {
      wx.showToast({
        title: '还有未保存的表格修改，请先保存后再生成',
        icon: 'none',
        duration: 2600,
      })
      return
    }

    this.setData({ confirming: true })
    wx.showLoading({ title: '开始生成' })

    try {
      const nextTask = await confirmReportTask(this.data.taskId)
      setTaskWithDerivedState(this, this.withPreviewImageUrls(nextTask), { errorMessage: '' })
      this.schedulePolling()
    } catch (error) {
      const message = error instanceof Error ? error.message : '确认生成失败'
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
    } finally {
      wx.hideLoading()
      this.setData({ confirming: false })
    }
  },

  async downloadDocx() {
    const task = this.data.task
    if (!this.data.taskId || !task || task.status !== 'done') {
      return
    }

    this.setData({ downloading: true })
    wx.showLoading({ title: '下载中' })

    try {
      const filePath = await downloadTaskResult(this.data.taskId, 'docx')
      wx.openDocument({
        filePath,
        fileType: 'docx',
        showMenu: true,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '下载失败'
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
    } finally {
      wx.hideLoading()
      this.setData({ downloading: false })
    }
  },

  async onTableSelectionChange(event: WechatMiniprogram.CustomEvent<{ value: boolean }>) {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId || this.data.savingTablePlan) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    if (!tableId) {
      return
    }
    const selected = !!(event.detail && event.detail.value)
    const previousTask = task
    const nextTablePlan = (task.preview.tablePlan || []).map((item) => (
      item.tableId === tableId ? { ...item, selected } : item
    ))
    setTaskWithDerivedState(this, {
      ...task,
      preview: {
        ...task.preview,
        tablePlan: nextTablePlan,
      },
    }, { savingTablePlan: true })

    try {
      const updatedTask = await updateTablePlan(this.data.taskId, buildTableSelection(nextTablePlan))
      setTaskWithDerivedState(this, this.withPreviewImageUrls(updatedTask, true))
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存表格选择失败'
      setTaskWithDerivedState(this, previousTask)
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
    } finally {
      this.setData({ savingTablePlan: false })
    }
  },

  onTableCellInput(event: WechatMiniprogram.Input) {
    const task = this.data.task
    if (!task || !task.preview) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    const rowIndex = Number(event.currentTarget.dataset.rowIndex)
    const columnIndex = Number(event.currentTarget.dataset.columnIndex)
    if (!tableId || Number.isNaN(rowIndex) || Number.isNaN(columnIndex)) {
      return
    }
    const value = String(event.detail.value || '')
    const nextTablePlan = (task.preview.tablePlan || []).map((table) => {
      if (table.tableId !== tableId) {
        return table
      }
      const nextRows = cloneRows(table.rows || [])
      if (!nextRows[rowIndex]) {
        return table
      }
      nextRows[rowIndex][columnIndex] = value
      return {
        ...table,
        rows: nextRows,
        rowCount: nextRows.length,
        dirty: true,
        saveError: '',
      }
    })
    setTaskWithDerivedState(this, {
      ...task,
      preview: {
        ...task.preview,
        tablePlan: nextTablePlan,
      },
    })
  },

  onTableAddRow(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (!task || !task.preview) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    if (!tableId) {
      return
    }
    const nextTask = updateLocalTablePlan(task, tableId, (table) => {
      const nextRows = cloneRows(table.rows || [])
      const width = table.headers ? table.headers.length : table.columnCount
      const nextRow: string[] = []
      for (let index = 0; index < width; index += 1) {
        nextRow.push('')
      }
      nextRows.push(nextRow)
      return {
        ...table,
        rows: nextRows,
        rowCount: nextRows.length,
        dirty: true,
        saveError: '',
      }
    })
    setTaskWithDerivedState(this, nextTask)
  },

  onTableDeleteRow(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (!task || !task.preview) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    const rowIndex = Number(event.currentTarget.dataset.rowIndex)
    if (!tableId || Number.isNaN(rowIndex)) {
      return
    }
    const nextTask = updateLocalTablePlan(task, tableId, (table) => {
      const nextRows = cloneRows(table.rows || [])
      if (rowIndex < 0 || rowIndex >= nextRows.length) {
        return table
      }
      nextRows.splice(rowIndex, 1)
      if (!nextRows.length) {
        const fallbackRow: string[] = []
        const width = table.headers ? table.headers.length : table.columnCount
        for (let index = 0; index < width; index += 1) {
          fallbackRow.push('')
        }
        nextRows.push(fallbackRow)
      }
      return {
        ...table,
        rows: nextRows,
        rowCount: nextRows.length,
        dirty: true,
        saveError: '',
      }
    })
    setTaskWithDerivedState(this, nextTask)
  },

  onManualTableTitleInput(event: WechatMiniprogram.Input) {
    this.setData({ manualTableDraftTitle: String(event.detail.value || '') })
  },

  onManualTableHeadersInput(event: WechatMiniprogram.Input) {
    this.setData({ manualTableDraftHeadersText: String(event.detail.value || '') })
  },

  onAddManualTable() {
    const task = this.data.task
    if (!task || !task.preview) {
      return
    }
    const title = String(this.data.manualTableDraftTitle || '').trim() || '自定义表格'
    const headers = parseManualHeaders(this.data.manualTableDraftHeadersText)
    if (!headers.length) {
      wx.showToast({ title: '请填写表头', icon: 'none', duration: 2200 })
      return
    }
    if (headers.length > 6) {
      wx.showToast({ title: '最多 6 列', icon: 'none', duration: 2200 })
      return
    }
    const nextTable: LocalTablePlanItem = {
      tableId: `manual_table_local_${Date.now()}`,
      sectionKey: 'manual',
      sectionTitle: '实验结果',
      schema: 'custom_table',
      title,
      rowCount: 1,
      columnCount: headers.length,
      headers,
      rows: [headers.map(() => '')],
      selected: true,
      edited: true,
      autoPlanned: false,
      headersText: headers.join(' / '),
      dirty: true,
      saving: false,
      saveError: '',
      source: 'manual',
    }
    const tablePlan = ((task.preview.tablePlan || []) as LocalTablePlanItem[]).concat(nextTable)
    setTaskWithDerivedState(this, {
      ...task,
      preview: {
        ...task.preview,
        tablePlan,
      },
    })
    this.setData({ manualTableDraftTitle: '', manualTableDraftHeadersText: this.data.manualTableDraftHeadersText })
  },

  onDeleteManualTable(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (!task || !task.preview) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    if (!tableId) {
      return
    }
    const tablePlan = ((task.preview.tablePlan || []) as LocalTablePlanItem[]).filter((item) => item.tableId !== tableId)
    setTaskWithDerivedState(this, {
      ...task,
      preview: {
        ...task.preview,
        tablePlan,
      },
    })
  },

  async onSaveManualTables() {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId || this.data.savingTablePlan) {
      return
    }
    const manualTables = buildManualTablesPayload((task.preview.tablePlan || []) as LocalTablePlanItem[])
    this.setData({ savingTablePlan: true })
    try {
      const updatedTask = await updateTablePlan(this.data.taskId, undefined, undefined, manualTables)
      setTaskWithDerivedState(this, this.withPreviewImageUrls(updatedTask, true))
      wx.showToast({ title: '手动表格已保存', icon: 'success', duration: 1800 })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存手动表格失败'
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
      this.refreshTask()
    } finally {
      this.setData({ savingTablePlan: false })
    }
  },

  async onSaveTableEdits(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId || this.data.savingTablePlan) {
      return
    }
    const tableId = String(event.currentTarget.dataset.tableId || '')
    if (!tableId) {
      return
    }
    const table = (task.preview.tablePlan || []).find((item) => item.tableId === tableId)
    if (!table) {
      return
    }
    if (!table.selected) {
      wx.showToast({ title: '不插入的表格无需保存', icon: 'none', duration: 2200 })
      return
    }
    if (!table.dirty) {
      wx.showToast({ title: '没有需要保存的修改', icon: 'none', duration: 2200 })
      return
    }
    const previousTask = task
    setTaskWithDerivedState(this, updateLocalTablePlan(task, tableId, (current) => ({
        ...current,
        saving: true,
        saveError: '',
      })), { savingTablePlan: true })
    try {
      const updatedTask = await updateTablePlan(this.data.taskId, undefined, { [tableId]: table.rows || [] })
      setTaskWithDerivedState(this, this.withPreviewImageUrls(updatedTask, true, [tableId]))
      wx.showToast({ title: '已保存', icon: 'success', duration: 1600 })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存表格内容失败'
      setTaskWithDerivedState(this, updateLocalTablePlan(previousTask, tableId, (current) => ({
          ...current,
          dirty: true,
          saving: false,
          saveError: message,
        })))
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
      this.refreshTask()
    } finally {
      this.setData({ savingTablePlan: false })
    }
  },

  onImageCategoryChange(event: WechatMiniprogram.CustomEvent<{ value: number }>) {
    const imageIndex = Number(event.currentTarget.dataset.imageIndex)
    if (Number.isNaN(imageIndex)) {
      return
    }
    const category = IMAGE_CATEGORY_OPTIONS[Number(event.detail.value) || 0]
    if (!category) {
      return
    }
    setTaskWithDerivedState(this, updateLocalImagePlan(this.data.task, imageIndex, (image) => ({
      ...image,
      category,
      categoryCn: IMAGE_CATEGORY_LABELS[category] || image.categoryCn,
      category_cn: IMAGE_CATEGORY_LABELS[category] || image.category_cn,
      dirty: true,
      saveError: '',
    })))
  },

  onImageCaptionInput(event: WechatMiniprogram.Input) {
    const imageIndex = Number(event.currentTarget.dataset.imageIndex)
    if (Number.isNaN(imageIndex)) {
      return
    }
    const caption = String(event.detail.value || '')
    setTaskWithDerivedState(this, updateLocalImagePlan(this.data.task, imageIndex, (image) => ({
      ...image,
      caption,
      dirty: true,
      saveError: '',
    })))
  },

  onImageSectionChange(event: WechatMiniprogram.CustomEvent<{ value: number }>) {
    const imageIndex = Number(event.currentTarget.dataset.imageIndex)
    if (Number.isNaN(imageIndex)) {
      return
    }
    const task = this.data.task
    const sections = getSectionTitles(task)
    const insertSection = sections[Number(event.detail.value) || 0]
    if (!insertSection) {
      return
    }
    setTaskWithDerivedState(this, updateLocalImagePlan(task, imageIndex, (image) => ({
      ...image,
      section: insertSection,
      insertSection,
      dirty: true,
      saveError: '',
    })))
  },

  async onSaveImageOverride(event: WechatMiniprogram.TouchEvent) {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId || this.data.savingImagePlan) {
      return
    }
    const imageIndex = Number(event.currentTarget.dataset.imageIndex)
    if (Number.isNaN(imageIndex)) {
      return
    }
    const image = findImageByIndex(task, imageIndex)
    if (!image) {
      return
    }
    const imageRef = String(image.image_ref || image.imageRef || `image_${imageIndex}`)
    const overrides: Record<string, ImagePlanOverrideItem> = {}
    overrides[imageRef] = {
      category: image.category,
      caption: image.caption,
      insertSection: image.insertSection || image.section,
      sizePolicy: image.sizePolicy,
    }
    this.setData({ savingImagePlan: true })
    try {
      const updatedTask = await updateReportImageOverrides(this.data.taskId, overrides)
      setTaskWithDerivedState(this, this.withPreviewImageUrls(updatedTask, true))
      wx.showToast({ title: '图片信息已保存', icon: 'success', duration: 1800 })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存图片信息失败'
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
      this.refreshTask()
    } finally {
      this.setData({ savingImagePlan: false })
    }
  },

  async onAdoptAiLayoutPlan() {
    await this.updateLayoutPlanSource('ai')
  },

  async onRestoreRuleLayoutPlan() {
    await this.updateLayoutPlanSource('rule')
  },

  async updateLayoutPlanSource(source: 'rule' | 'ai') {
    const task = this.data.task
    if (!task || !task.preview || !this.data.taskId || this.data.savingTablePlan) {
      return
    }
    wx.showLoading({ title: source === 'ai' ? '采用 AI 布局' : '恢复规则布局' })
    try {
      const response = await updateLayoutPlanSource(this.data.taskId, source)
      const nextTask = response.task ? response.task : task
      setTaskWithDerivedState(this, this.withPreviewImageUrls(nextTask, true))
    } catch (error) {
      const message = error instanceof Error ? error.message : '更新布局来源失败'
      wx.showToast({ title: message, icon: 'none', duration: 2600 })
      this.refreshTask()
    } finally {
      wx.hideLoading()
    }
  },

  createAnother() {
    this.confirmLeaveIfNeeded(() => {
      wx.redirectTo({
        url: '/pages/create/create',
      })
    })
  },
})

function setTaskWithDerivedState(page: WechatMiniprogram.Page.Instance<TaskPageData, Record<string, never>>, task: ReportTask | null, extra: Partial<TaskPageData> = {}) {
  const unsavedSelectedTableTitles = collectUnsavedSelectedTableTitles(task)
  const aiPlannerView = buildAiPlannerView(task)
  page.setData({
    task,
    unsavedSelectedTableCount: unsavedSelectedTableTitles.length,
    unsavedSelectedTableTitles,
    previewLayoutSourceIsAi: isAiLayoutSource(task),
    aiPlannerView,
    ...extra,
  })
}

function collectUnsavedSelectedTableTitles(task: ReportTask | null | undefined) {
  const preview = task && task.preview ? task.preview : null
  const tablePlan = preview && preview.tablePlan ? preview.tablePlan as LocalTablePlanItem[] : []
  return tablePlan
    .filter((item) => item.selected && item.dirty)
    .map((item) => item.title || '未命名表格')
}
function flattenSectionImages(sections: { title: string; images: ImagePlanItem[] }[]) {
  const updates: { filename: string; section: string; sortOrder: number; caption?: string }[] = []
  sections.forEach((section) => {
    section.images.forEach((image, index) => {
      updates.push({
        filename: image.filename,
        section: section.title,
        sortOrder: index,
        caption: image.caption,
      })
    })
  })
  return updates
}

function buildTableSelection(tablePlan: TablePlanItem[]) {
  const selection: Record<string, boolean> = {}
  tablePlan.forEach((item) => {
    if (item.tableId) {
      selection[item.tableId] = !!item.selected
    }
  })
  return selection
}

function mergeTablePlanState(
  nextTablePlan: LocalTablePlanItem[],
  currentTablePlan: LocalTablePlanItem[],
  preserveDirty: boolean,
  clearedTableIds: string[],
) {
  const currentById: Record<string, LocalTablePlanItem> = {}
  currentTablePlan.forEach((item) => {
    if (item.tableId) {
      currentById[item.tableId] = item
    }
  })
  const cleared: Record<string, boolean> = {}
  clearedTableIds.forEach((tableId) => {
    cleared[tableId] = true
  })
  return nextTablePlan.map((item) => {
    const current = item.tableId ? currentById[item.tableId] : null
    if (current && preserveDirty && current.dirty && !cleared[item.tableId]) {
      return {
        ...item,
        rows: cloneRows(current.rows || item.rows || []),
        dirty: true,
        saving: false,
        saveError: current.saveError || '',
      }
    }
    return {
      ...item,
      rows: cloneRows(item.rows || []),
      dirty: false,
      saving: false,
      saveError: '',
    }
  })
}

function updateLocalTablePlan(
  task: ReportTask,
  tableId: string,
  updater: (table: LocalTablePlanItem) => LocalTablePlanItem,
): ReportTask {
  if (!task.preview) {
    return task
  }
  return {
    ...task,
    preview: {
      ...task.preview,
      tablePlan: ((task.preview.tablePlan || []) as LocalTablePlanItem[]).map((table) => (
        table.tableId === tableId ? updater(table) : table
      )),
    },
  }
}

function cloneRows(rows: string[][]) {
  return rows.map((row) => row.slice())
}

const IMAGE_CATEGORY_OPTIONS = ['program', 'wiring', 'device', 'phenomenon', 'document', 'chart', 'instrument', 'unknown']
const IMAGE_CATEGORY_LABELS: Record<string, string> = {
  program: '程序图',
  wiring: '接线图',
  device: '实物图',
  phenomenon: '实验现象图',
  document: '文档/截图',
  chart: '曲线/图表',
  instrument: '仪表图',
  unknown: '待确认',
}

function parseManualHeaders(text: string) {
  return String(text || '')
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter((item) => !!item)
}

function buildManualTablesPayload(tablePlan: LocalTablePlanItem[]): ManualTableItem[] {
  return tablePlan
    .filter((item) => item.schema === 'custom_table' || item.source === 'manual')
    .map((item) => ({
      tableId: item.tableId,
      type: 'table',
      schema: 'custom_table',
      title: item.title,
      headers: (item.headers || []).slice(),
      data: {
        rows: cloneRows(item.rows || []),
      },
      selected: !!item.selected,
      source: 'manual',
    }))
}

function updateLocalImagePlan(
  task: ReportTask | null,
  imageIndex: number,
  updater: (image: LocalImagePlanItem) => LocalImagePlanItem,
): ReportTask | null {
  if (!task || !task.preview) {
    return task
  }
  const imagePlan = (task.preview.imagePlan || []).map((image) => (
    image.imageIndex === imageIndex ? updater({ ...(image as LocalImagePlanItem) }) : image
  ))
  const sections = task.preview.sections.map((section) => ({
    ...section,
    images: section.images.map((image) => (
      image.imageIndex === imageIndex ? updater({ ...(image as LocalImagePlanItem) }) : image
    )),
  }))
  return {
    ...task,
    preview: {
      ...task.preview,
      imagePlan,
      sections,
    },
  }
}

function findImageByIndex(task: ReportTask | null | undefined, imageIndex: number): LocalImagePlanItem | null {
  const preview = task && task.preview ? task.preview : null
  const imagePlan = preview ? preview.imagePlan : []
  for (let index = 0; index < imagePlan.length; index += 1) {
    if (imagePlan[index].imageIndex === imageIndex) {
      return imagePlan[index] as LocalImagePlanItem
    }
  }
  return null
}

function getSectionTitles(task: ReportTask | null | undefined) {
  const preview = task && task.preview ? task.preview : null
  return (preview ? preview.sections : [])
    .map((section) => String(section.title || '').trim())
    .filter((title) => !!title)
}

function buildAiPlannerView(task: ReportTask | null | undefined) {
  const preview = task && task.preview ? task.preview : null
  const aiPlannerPreview = preview && preview.aiPlannerPreview ? preview.aiPlannerPreview as AiPlannerPreview : null
  const layoutPlanSource = preview && preview.layoutPlanSource ? String(preview.layoutPlanSource) : 'rule'
  const base = {
    visible: false,
    statusText: '',
    statusClass: '',
    currentSourceText: '',
    adoptable: false,
    usingAi: false,
    adoptionBlockedReason: '',
    summaryLines: [] as string[],
    diffLines: [] as string[],
    warningLines: [] as string[],
    errorText: '',
    note: 'AI 规划仅为影子模式参考，不影响本次报告生成。',
  }
  if (!aiPlannerPreview) {
    return base
  }

  const status = String(aiPlannerPreview.status || '')
  const summary = aiPlannerPreview.summary ? aiPlannerPreview.summary : null
  const comparison = aiPlannerPreview.comparison ? aiPlannerPreview.comparison : null
  const warnings = Array.isArray(aiPlannerPreview.warnings) ? aiPlannerPreview.warnings.filter((item) => !!item) : []
  const summaryLines: string[] = []
  const diffLines: string[] = []

  if (summary) {
    summaryLines.push(`章节数量：${Number(summary.sectionCount || 0)}`)
    summaryLines.push(`总块数：${Number(summary.blockCount || 0)}`)
    summaryLines.push(`图片块：${Number(summary.imageBlocks || 0)}`)
    summaryLines.push(`表格块：${Number(summary.tableBlocks || 0)}`)
    summaryLines.push(`警告块：${Number(summary.warningBlocks || 0)}`)
  }

  if (status === 'valid' && comparison) {
    diffLines.push(`章节差异：${formatDelta(Number(comparison.sectionCountDelta || 0))}`)
    diffLines.push(`图片块差异：${formatDelta(Number(comparison.imageBlockDelta || 0))}`)
    diffLines.push(`表格块差异：${formatDelta(Number(comparison.tableBlockDelta || 0))}`)
    if (Array.isArray(comparison.extraInAi) && comparison.extraInAi.length) {
      diffLines.push(`AI 多出章节：${comparison.extraInAi.join(' / ')}`)
    }
    if (Array.isArray(comparison.missingInAi) && comparison.missingInAi.length) {
      diffLines.push(`AI 缺少章节：${comparison.missingInAi.join(' / ')}`)
    }
    if (Array.isArray(comparison.tableSchemasInAi) && Array.isArray(comparison.tableSchemasInRule)) {
      const tableRule = comparison.tableSchemasInRule.join(' / ')
      const tableAi = comparison.tableSchemasInAi.join(' / ')
      if (tableRule !== tableAi) {
        diffLines.push(`表格 Schema：规则[${tableRule || '-'}] / AI[${tableAi || '-'}]`)
      }
    }
  }

  return {
    visible: true,
    statusText: aiPlannerStatusText(status),
    statusClass: aiPlannerStatusClass(status),
    currentSourceText: layoutPlanSource === 'ai' ? '当前使用：AI 方案' : '当前使用：规则方案',
    adoptable: !!aiPlannerPreview.adoptable,
    usingAi: layoutPlanSource === 'ai',
    adoptionBlockedReason: String(aiPlannerPreview.adoptionBlockedReason || ''),
    summaryLines,
    diffLines,
    warningLines: warnings,
    errorText: status === 'invalid'
      ? (String(aiPlannerPreview.error || '') || 'AI 规划结果未通过校验，本次仅使用规则方案。')
      : String(aiPlannerPreview.error || ''),
    note: base.note,
  }
}

function isAiLayoutSource(task: ReportTask | null | undefined) {
  const preview = task && task.preview ? task.preview : null
  return !!(preview && preview.layoutPlanSource === 'ai')
}

function aiPlannerStatusText(status: string) {
  if (status === 'valid') {
    return 'AI 规划结果有效，仅供参考'
  }
  if (status === 'invalid') {
    return 'AI 规划结果未通过校验'
  }
  if (status === 'failed') {
    return 'AI 规划生成失败'
  }
  if (status === 'disabled') {
    return 'AI 规划未启用'
  }
  return 'AI 规划状态未知'
}

function aiPlannerStatusClass(status: string) {
  if (status === 'valid' || status === 'invalid' || status === 'failed' || status === 'disabled') {
    return status
  }
  return 'disabled'
}

function formatDelta(value: number) {
  if (value > 0) {
    return `+${value}`
  }
  return String(value)
}

function countCardsBeforePointer(cards: DropCardRect[], clientX: number, clientY: number) {
  if (!cards.length) {
    return 0
  }

  const rowTolerance = Math.max(24, Math.min(...cards.map((card) => getCardHeight(card))) * 0.35)
  let insertIndex = 0

  cards.forEach((card) => {
    const centerX = card.left + getCardWidth(card) / 2
    const centerY = card.top + getCardHeight(card) / 2
    const isLowerRow = clientY > centerY + rowTolerance
    const isSameRowAfterCenter = Math.abs(clientY - centerY) <= rowTolerance && clientX > centerX

    if (isLowerRow || isSameRowAfterCenter) {
      insertIndex += 1
    }
  })

  return Math.max(0, Math.min(insertIndex, cards.length))
}

function getCardWidth(card: DropCardRect) {
  return card.width || Math.max(0, (card.right || card.left) - card.left)
}

function getCardHeight(card: DropCardRect) {
  return card.height || Math.max(0, (card.bottom || card.top) - card.top)
}


