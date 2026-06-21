# Experiment Report Backend MVP

This is the local FastAPI backend used by the WeChat Mini Program MVP.

## Run

From the project root:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

## Test

```powershell
python -m pytest backend\tests -q
```

## API

- `POST /api/reports/tasks`
- `POST /api/reports/tasks/{task_id}/files`
- `GET /api/reports/tasks/{task_id}`
- `GET /api/reports/tasks/{task_id}/download?format=docx`

## MVP Behavior

The backend preserves the uploaded original DOCX and writes a revised copy under:

```text
backend/storage/tasks/<task_id>/outputs/
```

When an LLM is configured, the backend extracts the guide/report text, sends the task context to an OpenAI-compatible chat completions API, receives structured JSON sections, and writes those sections into the revised DOCX copy. When no LLM is configured, it keeps a deterministic local fallback so upload/poll/download development still works.

## LLM Configuration

Copy the example file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Then edit `backend\.env`.

OpenAI:

```text
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-key
LLM_MODEL=gpt-4.1-mini
```

DeepSeek:

```text
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-key
LLM_MODEL=deepseek-chat
```

Other OpenAI-compatible providers can be used by changing only `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`.

After changing `.env`, restart `uvicorn`.

## WeChat Developer Tools Notes

The mini program currently uses:

```text
http://127.0.0.1:8000
```

When testing in WeChat Developer Tools, enable local development settings such as "do not verify legal domain name, web-view domain name, TLS version and HTTPS certificate" if requests to localhost are blocked.

For real-device testing, replace `miniprogram/config.ts` with the computer's LAN IP address and make sure the firewall allows the port.
