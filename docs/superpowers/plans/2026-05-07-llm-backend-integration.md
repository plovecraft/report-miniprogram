# LLM Backend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backend capable of calling configurable LLM APIs to revise uploaded experiment report DOCX files.

**Architecture:** Add an OpenAI-compatible model adapter in `llm_writer.py`, text extraction helpers in `guide_parser.py` and `report_reader.py`, and route DOCX building through model-generated structured sections when LLM environment variables are configured. The mini program API contract remains unchanged.

**Tech Stack:** Python 3.11, FastAPI, python-docx, requests, python-dotenv, pytest.

---

### Task 1: LLM Adapter

**Files:**
- Create: `backend/app/services/llm_writer.py`
- Test: `backend/tests/test_llm_writer.py`

- [x] Parse OpenAI-compatible environment settings.
- [x] Build `/chat/completions` requests using configurable `base_url`, `api_key`, and `model`.
- [x] Parse JSON returned from `choices[0].message.content`.
- [x] Normalize JSON into report sections.

### Task 2: Context Extraction

**Files:**
- Create: `backend/app/services/guide_parser.py`
- Create: `backend/app/services/report_reader.py`

- [x] Extract DOCX guide/report text.
- [x] Decode plain text fallback for DOC/PDF in MVP.
- [x] Keep extraction bounded so large uploads do not overfill prompts.

### Task 3: DOCX Builder Integration

**Files:**
- Modify: `backend/app/services/docx_builder.py`

- [x] Use LLM-generated sections when available.
- [x] Preserve deterministic fallback when no model API is configured.
- [x] Keep image insertion and original DOCX preservation behavior.

### Task 4: Runtime Configuration

**Files:**
- Create: `backend/.env.example`
- Modify: `backend/README.md`
- Modify: `backend/app/main.py`

- [x] Load `.env` at backend startup.
- [x] Document provider examples for OpenAI-compatible vendors.

### Task 5: Verification

**Files:**
- Read: `backend/tests`

- [x] Run `python -m pytest backend\tests -q`.
- [x] Restart `uvicorn` after changes for manual mini program testing.
