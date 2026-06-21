# Report Generator Mini Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-page WeChat Mini Program MVP for creating experiment report generation tasks through a backend service.

**Architecture:** Keep mini program page state in page files and backend transport in `miniprogram/services/api.ts`. Store the backend URL in `miniprogram/config.ts`. Avoid CloudBase and direct LLM calls in this version.

**Tech Stack:** WeChat native Mini Program, TypeScript, Less, `wx.chooseMessageFile`, `wx.uploadFile`, `wx.request`, `wx.downloadFile`.

---

### Task 1: App Structure

**Files:**
- Modify: `miniprogram/app.json`
- Modify: `miniprogram/app.less`
- Modify: `miniprogram/app.ts`
- Create: `miniprogram/config.ts`

- [x] Replace template page list with `index`, `create`, and `task`.
- [x] Set a normal navigation title and background.
- [x] Add shared utility styles and remove template login behavior.
- [x] Add backend base URL config.

### Task 2: API Service

**Files:**
- Create: `miniprogram/services/api.ts`

- [x] Define task, file, and status types.
- [x] Implement request wrapper with JSON parsing and failure messages.
- [x] Implement create task, upload task file, get task status, and download result.

### Task 3: Home Page

**Files:**
- Modify: `miniprogram/pages/index/index.ts`
- Modify: `miniprogram/pages/index/index.wxml`
- Modify: `miniprogram/pages/index/index.less`
- Modify: `miniprogram/pages/index/index.json`

- [x] Replace template login UI with product entry.
- [x] Add concise workflow and required-file summary.
- [x] Navigate to the create page.

### Task 4: Create Page

**Files:**
- Create: `miniprogram/pages/create/create.ts`
- Create: `miniprogram/pages/create/create.wxml`
- Create: `miniprogram/pages/create/create.less`
- Create: `miniprogram/pages/create/create.json`

- [x] Add report, guide, and image selectors.
- [x] Add student metadata fields and PDF switch.
- [x] Validate required input.
- [x] Create the task, upload files, and navigate to the task page.

### Task 5: Task Page

**Files:**
- Create: `miniprogram/pages/task/task.ts`
- Create: `miniprogram/pages/task/task.wxml`
- Create: `miniprogram/pages/task/task.less`
- Create: `miniprogram/pages/task/task.json`

- [x] Read `taskId` from route params.
- [x] Poll backend status.
- [x] Render status steps and errors.
- [x] Download and open generated DOCX.

### Task 6: Verification

**Files:**
- Read: `project.config.json`
- Read: `miniprogram/app.json`

- [x] Parse JSON files with Node.
- [x] Check that declared pages have `.ts`, `.wxml`, `.less`, and `.json`.
- [x] Report that WeChat Developer Tools preview is still required for runtime validation.
