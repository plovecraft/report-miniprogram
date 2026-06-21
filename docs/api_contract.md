# API Contract

This document is the contract between the WeChat Mini Program frontend and the FastAPI backend.

Source of truth at the time of writing:

- Frontend caller: `miniprogram/services/api.ts`
- Backend routes: `backend/app/main.py`

Any API path, method, field, status enum, or response shape change must update this document before frontend and backend implementation proceed.

## Shared Rules

- Base URL is environment-specific. Development may use `http://8.145.50.84`; production must use a WeChat-approved HTTPS domain.
- Authenticated JSON requests send `Authorization: Bearer <token>`.
- Image preview URLs may use `?access_token=<token>` because `wx.previewImage` loads URLs directly.
- Timestamps are Unix seconds as floating-point numbers.
- Error responses are FastAPI error bodies:

```json
{
  "detail": "error message"
}
```

## Shared Types

### TaskStatus

```ts
type TaskStatus =
  | 'queued'
  | 'uploading'
  | 'previewing'
  | 'preview_ready'
  | 'processing'
  | 'done'
  | 'failed'
```

### ReportTask

```ts
interface ReportTask {
  taskId: string
  status: TaskStatus
  message: string
  progress: number
  experimentNo?: string
  userId?: string
  createdAt?: number
  updatedAt?: number
  resultName?: string
  preview?: ReportPreview
  qualityReport?: QualityReport
}
```

### ReportPreview

```ts
interface ReportPreview {
  experimentType?: string
  experimentTypeName?: string
  experimentName: string
  sections: PreviewSection[]
  imagePlan: ImagePlanItem[]
  insertedImageCount: number
  template: TemplateInfo
}
```

`experimentType` 和 `experimentTypeName` 是 P1 配置化后新增的可选字段。当前默认值为 `plc` / `PLC 实验报告`，旧任务或手工构造的预览结果可能没有这两个字段。

### PreviewSection

```ts
interface PreviewSection {
  title: string
  paragraphs: string[]
  images: ImagePlanItem[]
}
```

### ImagePlanItem

```ts
interface ImagePlanItem {
  imageIndex: number
  filename: string
  type: string
  section: string
  caption: string
  sortOrder?: number
  recognized: boolean
  imageUrl?: string
}
```

`imageUrl` is added by the frontend and is not required from the backend.

### QualityReport

```ts
interface QualityReport {
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
```

## Health

### GET `/health`

Frontend use:

- Manual server health check.
- Deployment verification.

Request:

- No body.
- No auth required.

Response:

```json
{
  "status": "ok",
  "llmConfigured": true,
  "llmBaseUrl": "https://api.deepseek.com/v1",
  "llmModel": "deepseek-v4-pro"
}
```

Compatibility:

- `llmBaseUrl` and `llmModel` are present only when an LLM config is available.

## Auth and User

### POST `/api/auth/wechat-login`

Frontend use:

- Called by `ensureWechatLogin()` after `wx.login`.
- Stores returned `token` in local storage.

Request:

```json
{
  "code": "wx-login-code",
  "devOpenid": "local-device-id"
}
```

Fields:

- `code`: required. WeChat login code.
- `devOpenid`: optional. Stable development identifier. Backend uses it only when real WeChat app credentials are not configured.

Response:

```json
{
  "token": "session-token",
  "user": {
    "userId": "uuid",
    "openid": "wechat-or-dev-openid"
  }
}
```

Errors:

- `400`: missing `code` or WeChat login resolution failed.

Compatibility:

- Existing clients may omit `devOpenid`; backend falls back to `code` in development mode.

### GET `/api/users/me`

Frontend use:

- Profile page.
- Home avatar/login state refresh.

Request:

- Header: `Authorization: Bearer <token>`.

Response:

```json
{
  "user": {
    "userId": "uuid",
    "openid": "openid",
    "createdAt": 1770000000.0,
    "lastLoginAt": 1770000000.0
  }
}
```

Errors:

- `401`: missing or invalid token.

### GET `/api/users/me/usage`

Frontend use:

- Profile usage record list.

Request:

- Header: `Authorization: Bearer <token>`.

Response:

```json
{
  "records": [
    {
      "taskId": "task-id",
      "event": "task_created",
      "metadata": "{'experimentNo': '实验三'}",
      "createdAt": 1770000000.0
    }
  ]
}
```

Errors:

- `401`: missing or invalid token.

Compatibility:

- `metadata` is currently a string representation of a Python dict, not JSON.

## Tasks

### POST `/api/reports/tasks`

Frontend use:

- Create page creates a task before uploading files.

Request:

```json
{
  "experimentNo": "实验三",
  "courseName": "可编程控制器实验",
  "teacherName": "李老师",
  "offeringCollegeLab": "机械与电气工程学院",
  "studentCollege": "机械与电气工程学院",
  "studentName": "吴梓添",
  "studentId": "32307700156",
  "className": "机器234",
  "exportPdf": false,
  "imageCount": 9,
  "imageMetas": [
    {
      "filename": "程序图1_1.png",
      "category": "basic_program"
    }
  ]
}
```

Fields:

- `experimentNo`: target experiment label or number. User input has priority over file names.
- `imageCount`: expected number of normal image uploads. For ZIP material packages this may be `0` and later replaced by extracted images.
- `imageMetas`: optional category hints from frontend selection or ZIP folder classification.

Response:

- `ReportTask`.

Initial response values:

```json
{
  "taskId": "task-id",
  "status": "queued",
  "message": "Task created, waiting for uploads",
  "progress": 5,
  "experimentNo": "实验三",
  "userId": "uuid-or-empty",
  "createdAt": 1770000000.0,
  "updatedAt": 1770000000.0
}
```

Errors:

- No explicit validation errors beyond JSON parsing at this MVP stage.

Compatibility:

- Unknown metadata fields are preserved in the task metadata but may be ignored by generation code.

### GET `/api/reports/tasks`

Frontend use:

- History page.

Request:

- Optional header: `Authorization: Bearer <token>`.

Response:

```json
{
  "tasks": [
    {
      "taskId": "task-id",
      "status": "preview_ready",
      "message": "Preview is ready, please confirm before generating DOCX",
      "progress": 75,
      "experimentNo": "实验三",
      "userId": "uuid-or-empty",
      "createdAt": 1770000000.0,
      "updatedAt": 1770000000.0,
      "resultName": "report_revised.docx"
    }
  ]
}
```

Compatibility:

- With a valid token, only that user's tasks are returned.
- Without a token, current in-memory anonymous tasks are returned.

### GET `/api/reports/tasks/{task_id}`

Frontend use:

- Task detail page polling.
- Preview and result status display.

Request:

- Optional header: `Authorization: Bearer <token>`, required if the task belongs to a user.

Response:

- `ReportTask`.
- Includes `preview` after status becomes `preview_ready`.
- Includes `qualityReport` after status becomes `done`.

Errors:

- `403`: token missing or user does not own the task.
- `404`: task not found.

## Uploads

### POST `/api/reports/tasks/{task_id}/files`

Frontend use:

- Create page uploads original report, guide, individual images, or ZIP material package.

Request:

- `multipart/form-data`.
- File field name: `file`.
- Form fields:

```text
fieldName=report | guide | image | materialZip
filename=<original display filename>
```

Supported meanings:

- `report`: original report DOCX template.
- `guide`: experiment guide file, currently DOC/DOCX/PDF depending on backend parser support.
- `image`: one experiment image.
- `materialZip`: ZIP package containing report, guide, and classified image folders.

Response:

- `ReportTask`.
- Uploading all required materials may move the task to `previewing` or `preview_ready`.

Errors:

- `400`: invalid multipart request, missing file, unknown `fieldName`, invalid ZIP, unsafe ZIP path, unsupported ZIP content.
- `403`: token missing or user does not own the task.
- `404`: task not found.

Compatibility:

- Current backend uses a custom multipart parser. Frontend must keep the file field named `file`.

## Image Plan

### PATCH `/api/reports/tasks/{task_id}/image-plan`

Frontend use:

- Task preview page saves image drag/drop section and ordering changes.

Request:

```json
{
  "images": [
    {
      "filename": "程序图1_1.png",
      "section": "五、程序设计与梯形图",
      "sortOrder": 0,
      "category": "basic_program",
      "caption": "基础题梯形图程序"
    }
  ]
}
```

Fields:

- `filename`: required. Must match one uploaded image filename.
- `section`: required. Target section title.
- `sortOrder`: required. Order within the section.
- `category`: optional. Overrides or preserves image category metadata.
- `caption`: optional. Overrides caption metadata.

Response:

- Updated `ReportTask`, including rebuilt `preview`.

Errors:

- `400`: `images` is missing or is not a list.
- `403`: token missing or user does not own the task.
- `404`: task not found.
- `409`: generation has already started or output exists.

Compatibility:

- Unknown filenames are ignored rather than treated as fatal.

## Generation

### POST `/api/reports/tasks/{task_id}/confirm`

Frontend use:

- Task preview page confirms the current preview and starts DOCX generation.

Request:

- No body.
- Optional header: `Authorization: Bearer <token>`, required if the task belongs to a user.

Response:

- `ReportTask`.
- Usually status becomes `processing`; if output already exists, current task response is returned.

Errors:

- `403`: token missing or user does not own the task.
- `404`: task not found.
- `409`: preview is not ready.

Compatibility:

- This endpoint starts background generation. Frontend should keep polling `GET /api/reports/tasks/{task_id}`.

## Downloads and Images

### GET `/api/reports/tasks/{task_id}/download?format=docx`

Frontend use:

- Task page downloads and opens the generated DOCX.

Request:

- Query: `format=docx`.
- Optional header: `Authorization: Bearer <token>`, required if the task belongs to a user.

Response:

- Binary DOCX file.
- Content type: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.

Errors:

- `400`: any format other than `docx`. Current MVP does not support PDF output.
- `403`: token missing or user does not own the task.
- `404`: task not found or result file is not ready.

Compatibility:

- Frontend `downloadTaskResult()` currently accepts `docx | pdf`, but backend only supports `docx`. Calling `format=pdf` returns `400`.

### GET `/api/reports/tasks/{task_id}/images/{image_index}`

Frontend use:

- Task preview image thumbnails and `wx.previewImage`.

Request:

- Path `image_index` is zero-based and corresponds to the image order in task upload/extraction.
- Auth can be sent by header or query:
  - Header: `Authorization: Bearer <token>`
  - Query: `?access_token=<token>`

Response:

- Binary image file.
- Content type is inferred from suffix:
  - `.jpg`, `.jpeg`: `image/jpeg`
  - `.png`: `image/png`
  - `.gif`: `image/gif`
  - `.webp`: `image/webp`
  - `.bmp`: `image/bmp`
  - otherwise: `application/octet-stream`

Errors:

- `403`: token missing or user does not own the task.
- `404`: task not found, image index out of range, or image file missing.

## Future API Change Rule

Before adding P1/P2/P3 APIs such as `layout-plan`, experiment type selection, table schemas, or LLM planner endpoints:

1. Update this contract first.
2. State whether the change is backward-compatible.
3. Update backend tests.
4. Update `miniprogram/services/api.ts` types and callers.
5. Ask the监管代理 to review frontend/backend field consistency.
