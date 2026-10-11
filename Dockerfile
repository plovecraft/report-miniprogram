FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    APP_BUILD=cloudbase-20260712-table-guard \
    TABLE_FEATURE_ENABLED=0 \
    ALLOW_UNSTABLE_TABLE_FEATURE=0 \
    LLM_BASE_URL=https://node-hk.sssaicodeapi.com/api/v1 \
    LLM_MODEL=gpt-5.4-mini \
    VISION_RECOGNITION_ENABLED=0 \
    VISION_RECOGNITION_TIMEOUT=60 \
    VISION_RECOGNITION_TEMPERATURE=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY backend /app/backend

RUN mkdir -p /app/backend/storage

CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
