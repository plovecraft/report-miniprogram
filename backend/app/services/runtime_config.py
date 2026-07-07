from __future__ import annotations

import os
from typing import Any


def runtime_summary() -> dict[str, Any]:
    return {
        "cloudbaseRun": bool(os.getenv("K_SERVICE") or os.getenv("TCB_ENV") or os.getenv("CLOUDBASE_ENV_ID")),
        "port": os.getenv("PORT", ""),
        "storageDir": os.getenv("STORAGE_DIR", ""),
        "tableFeatureEnabled": _env_bool("TABLE_FEATURE_ENABLED", default=True),
        "visionRecognitionEnabled": _env_bool("VISION_RECOGNITION_ENABLED"),
    }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
