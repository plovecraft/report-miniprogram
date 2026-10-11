from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import requests
from requests import RequestException


PostFn = Callable[..., Any]
logger = logging.getLogger("report-backend.vision")

ALLOWED_CATEGORIES = {
    "program",
    "wiring",
    "device",
    "phenomenon",
    "document",
    "instrument",
    "chart",
    "unknown",
}

CATEGORY_CN = {
    "program": "程序图",
    "wiring": "接线图",
    "device": "实物图",
    "phenomenon": "实验现象图",
    "document": "文档/截图",
    "instrument": "仪表图",
    "chart": "曲线/图表",
    "unknown": "待确认",
}

DEFAULT_SUGGESTED = {
    "program": {"insert_section": "实验过程", "caption": "PLC 控制程序图", "size_policy": "program_small"},
    "wiring": {"insert_section": "实验过程", "caption": "PLC 接线图", "size_policy": "wiring"},
    "device": {"insert_section": "实验结果", "caption": "实验实物图", "size_policy": "device"},
    "phenomenon": {"insert_section": "实验结果", "caption": "实验现象图", "size_policy": "phenomenon"},
    "document": {"insert_section": "实验结果", "caption": "实验截图", "size_policy": "document"},
    "instrument": {"insert_section": "实验结果", "caption": "仪表读数图", "size_policy": "instrument"},
    "chart": {"insert_section": "实验结果", "caption": "曲线/图表", "size_policy": "chart"},
    "unknown": {"insert_section": "实验过程", "caption": "实验图片", "size_policy": "default"},
}


def is_vision_recognition_enabled() -> bool:
    if os.getenv("LLM_DISABLE_FOR_TESTS") == "1":
        return False
    enabled = os.getenv("VISION_RECOGNITION_ENABLED", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False
    return bool(_api_key() and _model() and vision_recipient())


CONSENT_VERSION = "vision-images.v1"


def vision_recipient() -> str:
    try:
        url = urlsplit(_chat_completions_url())
    except ValueError:
        return ""
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        return ""
    return url.netloc


def vision_disclosure() -> dict[str, Any]:
    return {"enabled": is_vision_recognition_enabled(), "recipient": vision_recipient(),
            "version": CONSENT_VERSION}


def has_vision_consent(metadata: dict[str, Any]) -> bool:
    consent = metadata.get("visionRecognitionConsent")
    return (isinstance(consent, dict) and consent.get("accepted") is True
            and consent.get("version") == CONSENT_VERSION
            and bool(vision_recipient()) and consent.get("recipient") == vision_recipient())


def recognize_image_file_with_vision(
    image_path: Path,
    *,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
    allow_external: bool = False,
    post: PostFn | None = None,
) -> dict[str, Any] | None:
    if allow_external is not True or not is_vision_recognition_enabled():
        return None
    try:
        image_bytes = image_path.read_bytes()
    except OSError:
        return None
    return recognize_image_bytes_with_vision(
        image_bytes,
        image_path.name,
        experiment_type=experiment_type,
        image_ref=image_ref,
        image_index=image_index,
        allow_external=allow_external,
        post=post,
    )


def recognize_image_bytes_with_vision(
    image_bytes: bytes,
    filename: str,
    *,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
    allow_external: bool = False,
    post: PostFn | None = None,
) -> dict[str, Any] | None:
    if allow_external is not True or not image_bytes or not is_vision_recognition_enabled():
        return None

    post = post or requests.post
    started_url = _chat_completions_url()
    try:
        payload = _build_payload(image_bytes, filename, experiment_type)
        if _env_bool("LLM_STREAM"):
            response = post(
                started_url,
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                allow_redirects=False,
                timeout=int(os.getenv("VISION_RECOGNITION_TIMEOUT", "60")),
                stream=True,
            )
        else:
            response = post(
                started_url,
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                allow_redirects=False,
                timeout=int(os.getenv("VISION_RECOGNITION_TIMEOUT", "60")),
            )
        if 300 <= response.status_code < 400:
            raise RuntimeError("redirect refused")
        response.raise_for_status()
        content = _response_content(response, stream=_env_bool("LLM_STREAM"))
        parsed = _parse_json_content(str(content))
    except (KeyError, TypeError, ValueError, RequestException, RuntimeError) as exc:
        logger.warning("vision image recognition failed error_type=%s", type(exc).__name__)
        return None

    return _normalize_vision_result(
        parsed,
        filename=filename,
        experiment_type=experiment_type,
        image_ref=image_ref,
        image_index=image_index,
    )


def _build_payload(image_bytes: bytes, filename: str, experiment_type: str) -> dict[str, Any]:
    data_url = _data_url(image_bytes, filename)
    payload = {
        "model": _model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify PLC lab-report images. Return JSON only. "
                    "Allowed category values: program, wiring, device, phenomenon, "
                    "document, instrument, chart, unknown. Do not invent categories."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Classify this experiment image for report layout. "
                            f"experiment_type={experiment_type}. "
                            "Return JSON with category, category_cn, confidence, "
                            "review_level, review_reasons, suggested.insert_section, "
                            "suggested.caption, suggested.size_policy. "
                            "Use review_level ok/review/reject. Unknown or uncertain images "
                            "must be review, not reject."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    if _env_bool("LLM_SEND_TEMPERATURE", default=True):
        payload["temperature"] = float(os.getenv("VISION_RECOGNITION_TEMPERATURE", "0"))
    if _env_bool("LLM_STREAM"):
        payload["stream"] = True
    return payload


def _normalize_vision_result(
    data: dict[str, Any],
    *,
    filename: str,
    experiment_type: str,
    image_ref: str | None,
    image_index: int | None,
) -> dict[str, Any]:
    raw_category = str(data.get("category") or "unknown").strip().lower()
    category = raw_category if raw_category in ALLOWED_CATEGORIES else "unknown"
    confidence = _clamp_confidence(data.get("confidence"))
    raw_review_level = str(data.get("review_level") or data.get("reviewLevel") or "").strip().lower()
    review_level = raw_review_level if raw_review_level in {"ok", "review", "reject"} else "ok"
    review_reasons = _coerce_string_list(data.get("review_reasons") or data.get("reviewReasons"))

    if category == "unknown":
        review_level = "review"
        review_reasons.append("vision returned unknown or unsupported category")
    elif confidence < float(os.getenv("VISION_RECOGNITION_REVIEW_THRESHOLD", "0.55")) and review_level == "ok":
        review_level = "review"
        review_reasons.append("vision confidence below threshold")

    suggested = dict(DEFAULT_SUGGESTED.get(category) or DEFAULT_SUGGESTED["unknown"])
    raw_suggested = data.get("suggested")
    if isinstance(raw_suggested, dict):
        for key in ("insert_section", "caption", "size_policy"):
            value = str(raw_suggested.get(key) or "").strip()
            if value:
                suggested[key] = value

    needs_review = review_level in {"review", "reject"}
    return {
        "schema_version": "image-plan.v1",
        "experiment_type": experiment_type,
        "image_ref": image_ref or filename,
        "imageIndex": image_index,
        "filename": filename,
        "category": category,
        "category_cn": str(data.get("category_cn") or data.get("categoryCn") or CATEGORY_CN[category]).strip(),
        "confidence": confidence,
        "review_level": review_level,
        "review_reasons": _dedupe(review_reasons),
        "quality": {"readable": True, "needs_review": needs_review},
        "suggested": suggested,
        "features": {"vision_model": _model()},
        "score_detail": {
            "recognizer": "vision",
            "final_score": confidence,
            "raw_category": raw_category,
        },
    }


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("vision response must be a JSON object")
    return parsed


def _data_url(image_bytes: bytes, filename: str) -> str:
    mime = mimetypes.guess_type(filename)[0] or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if base_url == "https://api.deepseek.com":
        return "https://api.deepseek.com/v1"
    if base_url == "https://node-hk.sssaicodeapi.com/api":
        return "https://node-hk.sssaicodeapi.com/api/v1"
    return base_url


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _response_content(response, *, stream: bool) -> str:
    if not stream:
        return response.json()["choices"][0]["message"]["content"]
    chunks: list[str] = []
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")
        text = str(line).strip()
        if text.startswith("data:"):
            text = text[5:].strip()
        if text == "[DONE]":
            break
        if not text:
            continue
        data = json.loads(text)
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        message = choices[0].get("message") or {}
        piece = delta.get("content") if "content" in delta else message.get("content")
        if piece:
            chunks.append(str(piece))
    return "".join(chunks)


def _chat_completions_url() -> str:
    base_url = _normalize_base_url(os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _api_key() -> str:
    return os.getenv("LLM_API_KEY", "").strip()


def _model() -> str:
    return os.getenv("LLM_MODEL", "").strip()


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
