from __future__ import annotations

import os
from typing import Any

from .vision_image_recognizer import is_vision_recognition_enabled


def table_feature_enabled_from_env() -> bool:
    return _env_bool("TABLE_FEATURE_ENABLED", default=False) and _env_bool("ALLOW_UNSTABLE_TABLE_FEATURE", default=False)


def runtime_summary() -> dict[str, Any]:
    return {
        "cloudbaseRun": bool(os.getenv("K_SERVICE") or os.getenv("TCB_ENV") or os.getenv("CLOUDBASE_ENV_ID")),
        "appBuild": os.getenv("APP_BUILD", "local"),
        "port": os.getenv("PORT", ""),
        "storageDir": os.getenv("STORAGE_DIR", ""),
        "tableFeatureEnabled": table_feature_enabled_from_env(),
        "tableFeatureRequested": _env_bool("TABLE_FEATURE_ENABLED", default=False),
        "unstableTableFeatureAllowed": _env_bool("ALLOW_UNSTABLE_TABLE_FEATURE", default=False),
        "visionRecognitionEnabled": is_vision_recognition_enabled(),
        "visionRecognitionRequested": _env_bool("VISION_RECOGNITION_ENABLED"),
    }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
