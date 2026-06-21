# Report Generator Mini Program Design

## Goal

Build the first WeChat Mini Program MVP for generating revised experiment reports through a backend service. The mini program must not call any LLM API directly.

## Scope

The MVP has three pages:

- `pages/index/index`: entry page for the experiment report generator.
- `pages/create/create`: select the source report, guide document, experiment images, and basic metadata.
- `pages/task/task`: show task progress, poll the backend, and download the generated DOCX.

PDF export is represented as a user option, but DOCX download is the primary first-version output. Online Word preview, history, user accounts, and backend implementation are outside this mini program slice.

## Architecture

The mini program keeps backend communication in `services/api.ts`. Page files call this service instead of using raw request/upload/download APIs inline. `config.ts` stores the backend base URL so it can be changed without editing page logic.

The backend API contract is:

- `POST /api/reports/tasks`
- `POST /api/reports/tasks/{taskId}/files`
- `GET /api/reports/tasks/{taskId}`
- `GET /api/reports/tasks/{taskId}/download?format=docx`

## UX

The flow is operational and compact:

1. Home explains the workflow and opens the create page.
2. Create page has file cards for the report DOCX, guide document, and images.
3. Create page collects experiment number, name, student id, class name, and PDF preference.
4. Submitting creates a task, uploads selected files, and navigates to the task page.
5. Task page polls until done or failed, then shows a DOCX download button.

## Error Handling

The UI validates required files and experiment number before submission. Backend failures are shown with `wx.showToast` and inline task status text. If the backend is not running, the user sees a clear connection failure instead of a silent no-op.

## Verification

Since this project has no npm test script, verification uses:

- JSON parsing for `project.config.json` and `miniprogram/app.json`.
- Static path checks for all declared pages.
- WeChat Developer Tools preview for runtime behavior.
