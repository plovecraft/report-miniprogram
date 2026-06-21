import { API_BASE_URL } from '../config'

export type TaskStatus = 'queued' | 'uploading' | 'previewing' | 'preview_ready' | 'processing' | 'done' | 'failed'

export interface CreateTaskPayload {
  experimentNo: string
  courseName: string
  teacherName: string
  offeringCollegeLab: string
  studentCollege: string
  studentName: string
  studentId: string
  className: string
  exportPdf: boolean
  imageCount: number
  imageMetas: ImageMeta[]
}

export interface ImageMeta {
  filename: string
  category: string
}

export interface ReportTask {
  taskId: string
  status: TaskStatus
  message: string
  progress: number
  experimentNo?: string
  createdAt?: number
  updatedAt?: number
  resultName?: string
  preview?: ReportPreview
  qualityReport?: QualityReport
}

export interface ReportPreview {
  experimentType?: string
  experimentTypeName?: string
  experimentName: string
  sections: PreviewSection[]
  imagePlan: ImagePlanItem[]
  tablePlan?: TablePlanItem[]
  aiPlannerPreview?: AiPlannerPreview
  layoutPlanSource?: 'rule' | 'ai'
  insertedImageCount: number
  template: TemplateInfo
}

export interface AiPlannerPreviewSummary {
  sectionCount: number
  blockCount: number
  paragraphBlocks: number
  imageBlocks: number
  tableBlocks: number
  warningBlocks: number
  sectionTitles: string[]
  tableSchemas: string[]
  imageRefs: string[]
}

export interface AiPlannerPreviewComparison {
  sectionCountDelta: number
  imageBlockDelta: number
  tableBlockDelta: number
  warningBlockDelta: number
  missingInAi: string[]
  extraInAi: string[]
  tableSchemasInRule: string[]
  tableSchemasInAi: string[]
  imageRefsInRule: string[]
  imageRefsInAi: string[]
}

export interface AiPlannerPreview {
  enabled: boolean
  ok: boolean
  validationPassed: boolean
  status: string
  adoptable?: boolean
  adoptionBlockedReason?: string | null
  summary?: AiPlannerPreviewSummary | null
  comparison?: AiPlannerPreviewComparison | null
  warnings?: string[]
  error?: string | null
}

export interface TablePlanItem {
  tableId: string
  sectionKey: string
  sectionTitle: string
  schema: string
  title: string
  rowCount: number
  columnCount: number
  headers: string[]
  rows: string[][]
  selected: boolean
  edited: boolean
  source?: string
  autoPlanned?: boolean
  headersText?: string
  dirty?: boolean
  saving?: boolean
  saveError?: string
}

export interface TemplateInfo {
  templateId: string
  displayName: string
  confidence: number
  confidencePercent?: string
  bodyLocation: string
}

export interface PreviewSection {
  key?: string
  title: string
  paragraphs: string[]
  images: ImagePlanItem[]
  blockCount?: number
  imageCount?: number
  tableCount?: number
  warningCount?: number
}

export interface ImagePlanItem {
  imageIndex: number
  filename: string
  type: string
  section: string
  caption: string
  insertSection?: string
  sizePolicy?: string
  sortOrder?: number
  recognized: boolean
  imageUrl?: string
  confidencePercent?: string
  reviewReasonsText?: string
  category?: string
  categoryCn?: string
  category_cn?: string
  confidence?: number
  reviewLevel?: string
  reviewReasons?: string[]
  needsReview?: boolean
  overridden?: boolean
  image_ref?: string
  imageRef?: string
  dirty?: boolean
  saving?: boolean
  saveError?: string
}

export interface ImagePlanUpdateItem {
  filename: string
  section: string
  sortOrder: number
  category?: string
  caption?: string
}

export interface ImagePlanOverrideItem {
  category?: string
  caption?: string
  insertSection?: string
  sizePolicy?: string
}

export interface TablePlanSelection {
  [tableId: string]: boolean
}

export interface TablePlanEdits {
  [tableId: string]: string[][]
}

export interface ManualTableItem {
  tableId?: string
  type?: 'table'
  schema?: 'custom_table'
  title: string
  headers: string[]
  data: {
    rows: string[][]
  }
  selected?: boolean
  source?: 'manual'
}

export interface QualityReport {
  passed: boolean
  checks: {
    template_preserved?: boolean
    table_count_preserved?: boolean
    body_cell_found?: boolean
    body_not_empty?: boolean
    body_replaced?: boolean
    images_inserted?: number
    expected_images?: number
    filename_reference_found?: boolean
    stale_experiment_text_found?: boolean
  }
  warnings: string[]
}

export interface LocalFile {
  path: string
  name: string
  size?: number
}

export interface CurrentUser {
  userId: string
  openid: string
  createdAt?: number
  lastLoginAt?: number
}

export interface UsageRecord {
  taskId: string
  event: string
  metadata: string
  createdAt: number
}

type RequestMethod = 'GET' | 'POST' | 'PATCH'
const AUTH_TOKEN_STORAGE_KEY = 'lab_report_auth_token_v1'
const DEV_OPENID_STORAGE_KEY = 'lab_report_dev_openid_v1'

function normalizeBaseUrl() {
  return API_BASE_URL.replace(/\/$/, '')
}

function getAuthToken() {
  return String(wx.getStorageSync(AUTH_TOKEN_STORAGE_KEY) || '')
}

function getDevOpenid() {
  const existing = String(wx.getStorageSync(DEV_OPENID_STORAGE_KEY) || '')
  if (existing) {
    return existing
  }
  const value = `local_${Date.now()}_${Math.random().toString(16).slice(2)}`
  wx.setStorageSync(DEV_OPENID_STORAGE_KEY, value)
  return value
}

export function hasAuthToken(): boolean {
  return !!getAuthToken()
}

export function clearAuthToken(): void {
  wx.removeStorageSync(AUTH_TOKEN_STORAGE_KEY)
}

function authHeaders() {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function taskImageUrl(taskId: string, imageIndex: number): string {
  const token = getAuthToken()
  const tokenQuery = token ? `?access_token=${encodeURIComponent(token)}` : ''
  return `${normalizeBaseUrl()}/api/reports/tasks/${encodeURIComponent(taskId)}/images/${imageIndex}${tokenQuery}`
}

function request<T>(path: string, method: RequestMethod, data?: object): Promise<T> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${normalizeBaseUrl()}${path}`,
      method,
      data,
      header: {
        'content-type': 'application/json',
        ...authHeaders(),
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T)
          return
        }
        reject(new Error(`后端返回 ${res.statusCode}`))
      },
      fail(err) {
        reject(new Error(err.errMsg || '无法连接后端服务'))
      },
    })
  })
}

export function ensureWechatLogin(): Promise<void> {
  if (getAuthToken()) {
    return Promise.resolve()
  }
  return new Promise((resolve, reject) => {
    wx.login({
      success(loginRes) {
        if (!loginRes.code) {
          reject(new Error('微信登录失败'))
          return
        }
        wx.request({
          url: `${normalizeBaseUrl()}/api/auth/wechat-login`,
          method: 'POST',
          data: {
            code: loginRes.code,
            devOpenid: getDevOpenid(),
          },
          header: { 'content-type': 'application/json' },
          success(res) {
            if (res.statusCode >= 200 && res.statusCode < 300) {
              const body = res.data as { token?: string }
              if (!body.token) {
                reject(new Error('后端未返回登录凭证'))
                return
              }
              wx.setStorageSync(AUTH_TOKEN_STORAGE_KEY, body.token)
              resolve()
              return
            }
            reject(new Error(`登录失败：${res.statusCode}`))
          },
          fail(err) {
            reject(new Error(err.errMsg || '无法连接登录接口'))
          },
        })
      },
      fail(err) {
        reject(new Error(err.errMsg || '微信登录失败'))
      },
    })
  })
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  if (!getAuthToken()) {
    return null
  }
  try {
    const response = await request<{ user: CurrentUser }>('/api/users/me', 'GET')
    return response.user
  } catch (error) {
    clearAuthToken()
    return null
  }
}

export function getCurrentUserUsage(): Promise<{ records: UsageRecord[] }> {
  return request<{ records: UsageRecord[] }>('/api/users/me/usage', 'GET')
}

export function createReportTask(payload: CreateTaskPayload): Promise<ReportTask> {
  return request<ReportTask>('/api/reports/tasks', 'POST', payload)
}

export function getReportTask(taskId: string): Promise<ReportTask> {
  return request<ReportTask>(`/api/reports/tasks/${encodeURIComponent(taskId)}`, 'GET')
}

export function listReportTasks(): Promise<{ tasks: ReportTask[] }> {
  return request<{ tasks: ReportTask[] }>('/api/reports/tasks', 'GET')
}

export function updateReportImagePlan(taskId: string, images: ImagePlanUpdateItem[]): Promise<ReportTask> {
  return request<ReportTask>(`/api/reports/tasks/${encodeURIComponent(taskId)}/image-plan`, 'PATCH', { images })
}

export function updateReportImageOverrides(taskId: string, overrides: Record<string, ImagePlanOverrideItem>): Promise<ReportTask> {
  return request<ReportTask>(`/api/reports/tasks/${encodeURIComponent(taskId)}/image-plan`, 'PATCH', { overrides })
}

export function updateTablePlan(
  taskId: string,
  tableSelection?: TablePlanSelection,
  tableEdits?: TablePlanEdits,
  manualTables?: ManualTableItem[],
): Promise<ReportTask> {
  const payload: { tableSelection?: TablePlanSelection; tableEdits?: TablePlanEdits; manualTables?: ManualTableItem[] } = {}
  if (tableSelection) {
    payload.tableSelection = tableSelection
  }
  if (tableEdits) {
    payload.tableEdits = tableEdits
  }
  if (manualTables) {
    payload.manualTables = manualTables
  }
  return request<ReportTask>(`/api/reports/tasks/${encodeURIComponent(taskId)}/table-plan`, 'PATCH', payload)
}

export function updateLayoutPlanSource(taskId: string, source: 'rule' | 'ai'): Promise<{ ok: boolean; layoutPlanSource: 'rule' | 'ai'; preview: ReportPreview; task: ReportTask }> {
  return request<{ ok: boolean; layoutPlanSource: 'rule' | 'ai'; preview: ReportPreview; task: ReportTask }>(
    `/api/reports/tasks/${encodeURIComponent(taskId)}/layout-plan-source`,
    'PATCH',
    { source },
  )
}

export function confirmReportTask(taskId: string): Promise<ReportTask> {
  return request<ReportTask>(`/api/reports/tasks/${encodeURIComponent(taskId)}/confirm`, 'POST')
}

export function uploadTaskFile(taskId: string, fieldName: string, file: LocalFile): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${normalizeBaseUrl()}/api/reports/tasks/${encodeURIComponent(taskId)}/files`,
      filePath: file.path,
      name: 'file',
      formData: {
        fieldName,
        filename: file.name,
      },
      header: authHeaders(),
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve()
          return
        }
        reject(new Error(`上传 ${file.name} 失败：${res.statusCode}`))
      },
      fail(err) {
        reject(new Error(err.errMsg || `上传 ${file.name} 失败`))
      },
    })
  })
}

export function downloadTaskResult(taskId: string, format: 'docx' | 'pdf' = 'docx'): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${normalizeBaseUrl()}/api/reports/tasks/${encodeURIComponent(taskId)}/download?format=${format}`,
      header: authHeaders(),
      success(res) {
        if (res.statusCode === 200) {
          resolve(res.tempFilePath)
          return
        }
        reject(new Error(`下载失败：${res.statusCode}`))
      },
      fail(err) {
        reject(new Error(err.errMsg || '下载结果文件失败'))
      },
    })
  })
}
