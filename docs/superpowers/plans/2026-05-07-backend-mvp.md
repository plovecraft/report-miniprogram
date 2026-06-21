# Backend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI backend that lets the mini program create a report task, upload files, poll status, and download a revised DOCX copy.

**Architecture:** Use a small synchronous FastAPI app with in-memory task state and local task folders under `backend/storage/tasks`. Keep transport code in `app/main.py`, task/storage code in `app/services/task_store.py`, and DOCX copy/revision logic in `app/services/docx_builder.py`. The DOCX builder follows the PLC lab report reviser principle: preserve the original report, write a revised copy, and keep the template structure intact.

**Tech Stack:** Python 3.11, FastAPI, python-docx, pytest, FastAPI TestClient.

---

### Task 1: Test API Contract

**Files:**
- Create: `backend/tests/test_api.py`

- [x] Write a test that creates a task, uploads a report DOCX, uploads guide/images, queries status, and downloads the output.
- [x] Verify the first run fails because `backend.app.main` does not exist yet.

### Task 2: Implement Task Store

**Files:**
- Create: `backend/app/services/task_store.py`

- [x] Create task records with `taskId`, status, message, progress, metadata, and paths.
- [x] Save uploaded files into `storage/tasks/<task_id>/uploads`.
- [x] Track uploaded report, guide, and image count.

### Task 3: Implement DOCX Builder

**Files:**
- Create: `backend/app/services/docx_builder.py`

- [x] Copy the uploaded report to `outputs/<original_stem>_revised.docx`.
- [x] Open the copy with python-docx.
- [x] Append an MVP generation summary without changing the original file.
- [x] Save and return the output path.

### Task 4: Implement FastAPI App

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/requirements.txt`

- [x] Add CORS for local mini program development.
- [x] Implement create task, upload file, get task, and download endpoints matching the mini program contract.
- [x] Trigger DOCX generation after report and guide files are uploaded.

### Task 5: Verify

**Files:**
- Read: `backend/tests/test_api.py`

- [x] Run `python -m pytest backend/tests -q`.
- [x] Provide backend startup command and mini program base URL note.
