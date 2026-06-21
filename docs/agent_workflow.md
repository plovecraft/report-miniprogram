# Multi-Agent Development Workflow

This document defines how agents collaborate on this project. It is binding for future frontend, backend, planning, and review work.

## Project Context

This project is an experiment report generation system:

- Frontend: WeChat Mini Program under `miniprogram/`.
- Backend: FastAPI service under `backend/`.
- Output: revised DOCX experiment reports generated from uploaded templates, guidebooks, images, and ZIP material packages.
- Architecture principle: AI may understand, plan, and decide, but deterministic backend tools execute Word writing, image insertion, table insertion, validation, and quality checks.

## Agent Roles

### Main Controller

Responsibilities:

- Break down tasks.
- Write task cards.
- Control file boundaries.
- Review API contracts.
- Assign frontend/backend/planning/review work.
- Decide whether a task is ready for implementation.
- Run final integration verification.

Default behavior:

- Does not directly perform large business-code changes unless the task is small and explicitly scoped.

### Frontend Agent

Owns:

- Mini Program pages, components, styles, and interaction.
- Upload, preview, generation, download, history, account, and error UI.
- Frontend API wrapper and TypeScript types in `miniprogram/services/api.ts`.

Rules:

- Must use `docs/api_contract.md`.
- Must not modify `backend/`.
- Must not invent response fields or API paths.

### Backend Agent

Owns:

- FastAPI routes.
- Task state.
- DOCX generation.
- Image classification.
- Experiment configuration loading.
- `layout_plan`, table writing, and quality checks.
- Backend tests and backend requirements.

Rules:

- Must update `docs/api_contract.md` before changing public API behavior.
- Must not modify Mini Program pages.

### Planning Agent

Owns:

- Roadmaps.
- Module abstractions.
- Plugin/configuration strategy.
- Phase goals and risk analysis.

Rules:

- Read-only by default.
- May modify `docs/**` or README only after main-controller approval.
- Must not directly refactor implementation code.

### Review Agent

Owns:

- Review only.
- Checks boundary violations, API consistency, test coverage, compatibility, deployment risks, and security issues.

Rules:

- Read-only by default.
- Does not directly fix code.
- Reports blockers, risks, and recommendations.

## File Ownership

Frontend agent may modify:

```text
miniprogram/pages/**
miniprogram/components/**
miniprogram/services/api.ts
miniprogram/config.ts
miniprogram/app.json
miniprogram/app.ts
miniprogram/**/*.less
miniprogram/**/*.wxml
miniprogram/**/*.json
```

Backend agent may modify:

```text
backend/app/**
backend/tests/**
backend/requirements.txt
backend/.env.example
deploy/**
```

Planning agent may modify only after approval:

```text
docs/**
README.md
planning documents
```

Review agent:

- Does not modify files by default.

Shared high-risk files:

```text
miniprogram/services/api.ts
backend/app/main.py
backend/app/services/task_store.py
backend/app/services/user_store.py
backend/requirements.txt
project.config.json
package.json
```

Only one implementation agent should own a shared high-risk file in a task.

## Forbidden Cross-Modifications

- Frontend agent must not modify `backend/app/**`.
- Backend agent must not modify `miniprogram/pages/**`.
- Review agent must not directly repair code.
- Planning agent must not directly refactor implementation.
- No agent may silently modify `.env`, secrets, deployment credentials, SSH key files, or historical runtime data.
- No task may combine broad frontend UI, backend core generation, and deployment changes at once.

## Cross-End API Change Flow

When an API must be added or changed:

1. Backend agent drafts the API contract change in `docs/api_contract.md`.
2. Main controller reviews the contract.
3. Backend agent implements the route, data structure, and tests.
4. Frontend agent updates `miniprogram/services/api.ts` and UI callers according to the contract.
5. Review agent checks field consistency, compatibility, tests, and security.
6. Main controller runs final verification.

Frontend must not assume fields before the contract is written. Backend must not rename fields ad hoc during implementation.

## Task Card Template

Every implementation task starts with:

```text
Task name:
Goal:
User-visible effect:
Frontend scope:
Backend scope:
API changes:
Data structure changes:
Non-goals:
Acceptance criteria:
Test commands:
Risks:
Rollback plan:
```

## Current Roadmap

### P0: Stabilize Existing Online Version

Goals:

- Keep upload, preview, generation, and download stable.
- Fix DOCX template compatibility issues.
- Keep tests passing.
- Improve user-visible error messages.
- Fix WeChat real-device compatibility issues.

### P1: PLC Configuration

Goals:

- Move current fixed PLC behavior into configuration.
- Preserve current output behavior.
- Prepare for multiple experiment types.

Non-goals:

- No LLM layout planner.
- No circuit/hydraulics expansion yet.

### P2: First Layout Plan Executor

Goals:

- Establish a unified block execution mechanism.
- Convert current sections and image plan into blocks.
- Support `paragraph`, `image`, and `warning` blocks first.

Non-goals:

- No full LLM planner.
- Table block may be placeholder-only.

### P3: Table Schema and Table Writer

Goals:

- Add controlled table insertion.
- Tables must come from whitelisted schemas.
- Start with `io_assignment_table`, `phenomenon_record_table`, and `data_record_table`.

### P4: Multiple Experiment Types

Goals:

- Add `generic` and `circuit` configurations.
- Add low-confidence experiment type confirmation.
- Avoid course-specific hardcoding in the main pipeline.

### P5: LLM Layout Planner

Goals:

- Let LLM propose report structure with controlled JSON.
- Validate all planner output before execution.
- Fall back to deterministic templates on failure.

## Quality Gates

Backend completion requires:

```powershell
python -m pytest backend\tests -q --tb=short
python -m compileall backend\app backend\tests -q
```

If API behavior changes, also run focused API tests:

```powershell
python -m pytest backend\tests\test_api*.py -q
```

Frontend completion requires:

- WeChat Developer Tools compilation has no errors.
- Upload, preview, generation, download, history, and profile flows still work for the affected scenario.
- Real-device syntax risk scan has no unsupported optional chaining/nullish coalescing:

```powershell
Get-ChildItem -Path miniprogram -Recurse -Include *.ts,*.js | Select-String -Pattern '\?\.|\?\?'
```

Documentation tasks require secret scanning:

```powershell
Get-ChildItem -Path docs -Recurse | Select-String -Pattern '<project secret patterns>'
```

## Review Checklist

Review agent must check:

- Did the agent modify only its declared scope?
- Are frontend and backend API fields consistent?
- Are status enums still compatible?
- Are upload field names unchanged unless the contract changed?
- Is task ownership and user access isolation preserved?
- Are tests present for backend behavior changes?
- Are WeChat real-device syntax risks avoided?
- Are `.env`, runtime storage, secrets, SSH key files, and uploaded materials excluded?
- Is there any fake success where an API returns success but no file/result exists?
- Is there any silent failure where exceptions are swallowed without user feedback?
- Is there a fallback path for LLM or generation failure where appropriate?

## Agent Delivery Format

Each implementation or review response must include:

```text
Responsible scope:
Changed files:
Shared high-risk files touched:
API contract changes:
Tests run:
Manual verification:
Risks:
Dependencies on other agents:
Declaration about secrets/runtime data:
```

## Prohibited Actions

- Do not commit API keys.
- Do not modify real `.env` secrets.
- Do not delete existing tests to pass the suite.
- Do not bypass the task state machine and return success directly.
- Do not hardcode backend temporary file paths in the frontend.
- Do not let LLM output unvalidated table structures into DOCX.
- Do not expand one task across multiple roadmap phases.
- Do not change frontend and backend API fields without updating `docs/api_contract.md`.
- Do not perform broad formatting or unrelated refactors.
