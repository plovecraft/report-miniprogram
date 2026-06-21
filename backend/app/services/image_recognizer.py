from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs" / "experiment_types"

DEFAULT_THRESHOLDS = {
    "confidence": 0.55,
    "visual_only_confidence": 0.40,
    "margin": 0.08,
}

BLUR_THRESHOLD = 100.0
TOO_DARK_RATIO_THRESHOLD = 0.35
TOO_BRIGHT_RATIO_THRESHOLD = 0.75
DARK_PIXEL_MAX = 40
BRIGHT_PIXEL_MIN = 240

_CONFIG_CACHE: dict[str, dict[str, Any]] = {}

SEMANTIC_FILENAME_KEYWORDS = [
    "程序",
    "梯形",
    "ladder",
    "program",
    "awl",
    "接线",
    "wiring",
    "现象",
    "结果",
    "实物",
    "设备",
    "输入输出",
    "i/o",
]


def recognize_image_file(
    image_path: Path,
    *,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
) -> dict[str, Any]:
    normalized_type = normalize_experiment_type(experiment_type)
    try:
        bgr = _read_image_file(image_path)
    except UnidentifiedImageError:
        return _error_result(
            code="UNSUPPORTED_FORMAT",
            message="Unsupported image format",
            filename=image_path.name,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    except Exception:
        return _error_result(
            code="IMAGE_RECOGNITION_FAILED",
            message="Image recognition failed",
            filename=image_path.name,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    if bgr is None:
        return _error_result(
            code="INVALID_IMAGE",
            message="Image data is unreadable",
            filename=image_path.name,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    return _classify_array(
        bgr,
        filename=image_path.name,
        experiment_type=normalized_type,
        image_ref=image_ref,
        image_index=image_index,
    )


def recognize_image_bytes(
    image_bytes: bytes,
    filename: str,
    *,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
) -> dict[str, Any]:
    normalized_type = normalize_experiment_type(experiment_type)
    if not image_bytes:
        return _error_result(
            code="INVALID_IMAGE",
            message="Image payload is empty",
            filename=filename,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    try:
        bgr = _read_image_bytes(image_bytes)
    except UnidentifiedImageError:
        return _error_result(
            code="UNSUPPORTED_FORMAT",
            message="Unsupported image format",
            filename=filename,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    except Exception:
        return _error_result(
            code="IMAGE_RECOGNITION_FAILED",
            message="Image recognition failed",
            filename=filename,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    if bgr is None:
        return _error_result(
            code="INVALID_IMAGE",
            message="Image data is unreadable",
            filename=filename,
            experiment_type=normalized_type,
            image_ref=image_ref,
            image_index=image_index,
        )
    return _classify_array(
        bgr,
        filename=filename,
        experiment_type=normalized_type,
        image_ref=image_ref,
        image_index=image_index,
    )


def classify_image(
    path: Path,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
) -> dict[str, Any]:
    return recognize_image_file(
        path,
        experiment_type=experiment_type,
        image_ref=image_ref,
        image_index=image_index,
    )


def classify_from_bytes(
    data: bytes,
    filename: str,
    experiment_type: str = "plc",
    image_ref: str | None = None,
    image_index: int | None = None,
) -> dict[str, Any]:
    return recognize_image_bytes(
        data,
        filename,
        experiment_type=experiment_type,
        image_ref=image_ref,
        image_index=image_index,
    )


def normalize_experiment_type(raw: str) -> str:
    mode = (raw or "plc").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "control": "modern_control",
        "modern": "modern_control",
        "moderncontrol": "modern_control",
    }
    normalized = aliases.get(mode, mode)
    if _config_path(normalized).exists():
        return normalized
    return "generic" if _config_path("generic").exists() else normalized


def load_experiment_config(experiment_type: str) -> dict[str, Any]:
    normalized = normalize_experiment_type(experiment_type)
    if normalized in _CONFIG_CACHE:
        return _CONFIG_CACHE[normalized]
    path = _config_path(normalized)
    if not path.exists():
        if normalized != "generic":
            return load_experiment_config("generic")
        raise FileNotFoundError(f"missing recognition config: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = dict(raw.get("imageRecognition") or raw)
    _CONFIG_CACHE[normalized] = data
    return data


def _config_path(experiment_type: str) -> Path:
    return CONFIG_ROOT / f"{experiment_type}.json"


def _classify_array(
    bgr: np.ndarray,
    *,
    filename: str,
    experiment_type: str,
    image_ref: str | None,
    image_index: int | None,
) -> dict[str, Any]:
    config = load_experiment_config(experiment_type)
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(dict(config.get("thresholds") or {}))

    quality = detect_quality(bgr)
    if not bool(quality.get("readable")):
        return _error_result(
            code="INVALID_IMAGE",
            message="Image data is unreadable",
            filename=filename,
            experiment_type=experiment_type,
            image_ref=image_ref,
            image_index=image_index,
        )

    features = extract_features(bgr)
    category_map = _category_map(config)
    visual_scores = {
        key: _visual_score_v2(features, category.get("visual_rules") or [])
        for key, category in category_map.items()
    }
    semantic_filename = is_semantic_filename(filename)
    name_scores = {
        key: _filename_score(filename, category.get("keywords") or [], semantic_filename=semantic_filename)
        for key, category in category_map.items()
    }

    candidates: list[tuple[str, float, float, float]] = []
    has_filename_signal = semantic_filename and any(score > 0 for score in name_scores.values())
    for key in category_map:
        filename_score = float(name_scores.get(key) or 0.0)
        visual_score = float(visual_scores.get(key) or 0.0)
        final_score = (
            (0.45 * filename_score) + (0.55 * visual_score)
            if has_filename_signal
            else visual_score
        )
        candidates.append((key, filename_score, visual_score, round(final_score, 4)))
    candidates.sort(key=lambda item: item[3], reverse=True)

    best_key, best_filename_score, best_visual_score, best_score = candidates[0]
    second_score = candidates[1][3] if len(candidates) > 1 else 0.0
    margin = round(best_score - second_score, 4)
    document_visual_score = float(visual_scores.get("document") or 0.0)
    chart_visual_score = float(visual_scores.get("chart") or 0.0)
    program_visual_score = float(visual_scores.get("program") or 0.0)
    if (
        best_key in {"document", "chart"}
        and program_visual_score >= max(0.42, max(document_visual_score, chart_visual_score) - 0.04)
        and float(features.get("horizontal_line_count") or 0.0) >= 4
        and float(features.get("vertical_line_count") or 0.0) >= 2
        and float(features.get("colorfulness") or 0.0) <= 32.0
    ):
        best_key = "program"
        best_filename_score = float(name_scores.get("program") or 0.0)
        best_visual_score = program_visual_score
        best_score = round((0.45 * best_filename_score) + (0.55 * best_visual_score), 4) if has_filename_signal else program_visual_score
        margin = round(best_score - max(document_visual_score, chart_visual_score, second_score), 4)
    elif (
        best_key == "chart"
        and not has_filename_signal
        and float(features.get("light_bg_ratio") or 0.0) >= 0.75
        and float(features.get("horizontal_line_count") or 0.0) >= 5
        and float(features.get("vertical_line_count") or 0.0) >= 3
        and float(features.get("colorfulness") or 0.0) <= 25.0
    ):
        best_key = "program"
        best_filename_score = 0.0
        best_visual_score = max(program_visual_score, best_visual_score)
        best_score = best_visual_score
        margin = round(best_score - max(document_visual_score, chart_visual_score, second_score), 4)
    elif (
        best_key == "document"
        and program_visual_score >= 0.55
        and float(features.get("light_bg_ratio") or 0.0) >= 0.9
        and float(features.get("colorfulness") or 0.0) <= 15.0
        and (
            (
                float(features.get("horizontal_line_count") or 0.0) >= 10
                and float(features.get("avg_line_length") or 0.0) >= 140.0
            )
            or (
                float(features.get("line_count") or 0.0) >= 25.0
                and float(features.get("edge_density") or 0.0) >= 0.012
            )
        )
    ):
        best_key = "program"
        best_filename_score = float(name_scores.get("program") or 0.0)
        best_visual_score = program_visual_score
        best_score = round((0.45 * best_filename_score) + (0.55 * best_visual_score), 4) if has_filename_signal else program_visual_score
        margin = round(best_score - max(document_visual_score, second_score), 4)

    review_level = "ok"
    review_reasons: list[str] = []
    threshold_used = float(thresholds["confidence"] if has_filename_signal else thresholds["visual_only_confidence"])

    if best_key == "unknown":
        review_level = "review"
        review_reasons.append("unknown category requires manual review")
    elif best_score < threshold_used:
        review_level = "review"
        review_reasons.append(
            f"confidence below threshold ({best_score:.2f} < {threshold_used:.2f})"
        )
    elif margin < float(thresholds["margin"]):
        review_level = "review"
        review_reasons.append(
            f"top-two category margin too small ({margin:.2f} < {float(thresholds['margin']):.2f})"
        )

    if bool(quality.get("needs_review")):
        review_level = "review"
        if bool(quality.get("blur")):
            review_reasons.append("image is blurry")
        if bool(quality.get("too_dark")):
            review_reasons.append("image is too dark")
        if bool(quality.get("too_bright")):
            review_reasons.append("image is too bright")

    category = category_map.get(best_key) or {
        "en_label": "unknown",
        "cn_label": "待确认",
        "suggested": {},
    }
    suggested = dict(category.get("suggested") or {})
    if not suggested:
        suggested = {
            "insert_section": "实验结果",
            "caption": "待确认图片",
            "size_policy": "other",
        }

    if best_key == "unknown":
        if not str(suggested.get("insert_section") or "").strip():
            suggested["insert_section"] = "实验过程"
        if not str(suggested.get("caption") or "").strip():
            suggested["caption"] = "实验图片"
        if not str(suggested.get("size_policy") or "").strip():
            suggested["size_policy"] = "default"

    return {
        "schema_version": "image-plan.v1",
        "experiment_type": experiment_type,
        "image_ref": image_ref or filename,
        "imageIndex": image_index,
        "filename": filename,
        "category": str(category.get("en_label") or best_key or "unknown"),
        "category_cn": str(category.get("cn_label") or "待确认"),
        "confidence": float(best_score),
        "review_level": review_level,
        "review_reasons": _dedupe(review_reasons),
        "quality": quality,
        "suggested": suggested,
        "features": features,
        "score_detail": {
            "filename_score": float(best_filename_score),
            "visual_score": float(best_visual_score),
            "final_score": float(best_score),
            "matched_keywords": matched_keywords(filename, category.get("keywords") or []),
            "top_candidates": [
                {
                    "category": str(category_map.get(key, {}).get("en_label") or key),
                    "category_cn": str(category_map.get(key, {}).get("cn_label") or "待确认"),
                    "score": float(score),
                }
                for key, _, _, score in candidates[:3]
            ],
            "semantic_filename": semantic_filename,
            "has_filename_signal": has_filename_signal,
            "weights": {
                "filename": 0.45 if has_filename_signal else 0.0,
                "visual": 0.55 if has_filename_signal else 1.0,
            },
            "threshold_used": threshold_used,
            "margin": margin,
        },
    }


def _error_result(
    *,
    code: str,
    message: str,
    filename: str,
    experiment_type: str,
    image_ref: str | None,
    image_index: int | None,
) -> dict[str, Any]:
    return {
        "schema_version": "image-plan.v1",
        "experiment_type": experiment_type,
        "image_ref": image_ref or filename,
        "imageIndex": image_index,
        "filename": filename,
        "category": "unknown",
        "category_cn": "待确认",
        "confidence": 0.0,
        "review_level": "reject",
        "review_reasons": [code],
        "quality": {
            "readable": False,
            "blur": False,
            "too_dark": False,
            "too_bright": False,
            "needs_review": True,
        },
        "suggested": {
            "insert_section": "实验结果",
            "caption": "待确认图片",
            "size_policy": "other",
        },
        "features": {},
        "score_detail": {},
        "error": {
            "code": code,
            "message": message,
        },
    }


def _read_image_file(path: Path) -> np.ndarray | None:
    with path.open("rb") as handle:
        return _read_image_bytes(handle.read())


def _read_image_bytes(data: bytes) -> np.ndarray | None:
    image = Image.open(BytesIO(data))
    rgb = np.array(image.convert("RGB"))
    if rgb.size == 0:
        return None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def detect_quality(bgr: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv_v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2]

    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    total_pixels = max(1, int(hsv_v.size))
    too_dark_ratio = float(np.sum(hsv_v < DARK_PIXEL_MAX) / total_pixels)
    too_bright_ratio = float(np.sum(hsv_v > BRIGHT_PIXEL_MIN) / total_pixels)
    dark_text_ratio = float(np.mean(gray < 140))
    edge_density = float(np.mean(cv2.Canny(gray, 50, 150) > 0))

    is_blur = blur_score < BLUR_THRESHOLD
    is_too_dark = too_dark_ratio > TOO_DARK_RATIO_THRESHOLD
    is_text_like_bright_screen = dark_text_ratio >= 0.01 and edge_density >= 0.005
    is_too_bright = too_bright_ratio > TOO_BRIGHT_RATIO_THRESHOLD and not is_text_like_bright_screen

    return {
        "readable": True,
        "blur": is_blur,
        "too_dark": is_too_dark,
        "too_bright": is_too_bright,
        "needs_review": is_blur or is_too_dark or is_too_bright,
        "blur_score": blur_score,
        "dark_text_ratio": dark_text_ratio,
    }


def extract_features(bgr: np.ndarray) -> dict[str, float]:
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    v_channel = hsv[:, :, 2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

    rg = np.abs(rgb[:, :, 0] - rgb[:, :, 1])
    yb = np.abs(0.5 * (rgb[:, :, 0] + rgb[:, :, 1]) - rgb[:, :, 2])
    colorfulness = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))

    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.mean(edges > 0))

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=25, maxLineGap=8)
    line_segments = lines[:, 0, :] if lines is not None else np.empty((0, 4), dtype=np.int32)
    lengths: list[float] = []
    horizontal_lines = 0
    vertical_lines = 0
    long_line_count = 0
    for x1, y1, x2, y2 in line_segments:
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = float(np.hypot(dx, dy))
        lengths.append(length)
        if abs(dy) <= max(2.0, abs(dx) * 0.2):
            horizontal_lines += 1
        if abs(dx) <= max(2.0, abs(dy) * 0.2):
            vertical_lines += 1
        if length >= max(width, height) * 0.18:
            long_line_count += 1

    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    component_areas = stats[1:, cv2.CC_STAT_AREA] if component_count > 1 else np.array([], dtype=np.int32)
    component_density = float(component_areas.size)
    small_component_ratio = (
        float(np.mean(component_areas < 80)) if component_areas.size else 0.0
    )
    large_component_ratio = (
        float(np.mean(component_areas > max(200.0, 0.002 * width * height))) if component_areas.size else 0.0
    )

    aspect_ratio = float(width / height) if height else 1.0
    brightness = float(np.mean(v_channel) / 255.0)
    light_bg_ratio = float(np.mean(gray > 210))
    highlight_ratio = float(np.mean(v_channel > 245))
    dark_text_ratio = float(np.mean(gray < 140))
    line_count = int(len(lengths))
    avg_line_length = float(sum(lengths) / max(1, len(lengths)))
    long_line_ratio = float(long_line_count / max(1, line_count))

    return {
        "width": float(width),
        "height": float(height),
        "aspect_ratio": aspect_ratio,
        "abs_ar_diff": abs(aspect_ratio - 1.25),
        "light_bg_ratio": light_bg_ratio,
        "highlight_ratio": highlight_ratio,
        "dark_text_ratio": dark_text_ratio,
        "edge_density": edge_density,
        "line_count": float(line_count),
        "horizontal_lines": float(horizontal_lines),
        "vertical_lines": float(vertical_lines),
        "horizontal_line_count": float(horizontal_lines),
        "vertical_line_count": float(vertical_lines),
        "hl_minus_vl": float(max(horizontal_lines, vertical_lines) - min(horizontal_lines, vertical_lines)),
        "max_hl_vl": float(max(horizontal_lines, vertical_lines)),
        "avg_line_length": avg_line_length,
        "long_line_ratio": long_line_ratio,
        "colorfulness": colorfulness,
        "brightness": brightness,
        "blur_score": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "small_component_ratio": float(small_component_ratio),
        "large_component_ratio": float(large_component_ratio),
        "component_density": float(component_density),
    }


def is_semantic_filename(filename: str) -> bool:
    stem = Path(filename).stem.lower().strip()
    if not stem:
        return False
    if any(keyword in stem for keyword in SEMANTIC_FILENAME_KEYWORDS):
        return True
    if _looks_like_nonsemantic_filename(stem):
        return False
    return False


def matched_keywords(filename: str, keywords: list[str]) -> list[str]:
    name = Path(filename).stem.lower()
    normalized_keywords = [str(item).strip().lower() for item in keywords if str(item).strip()]
    return [keyword for keyword in normalized_keywords if keyword in name]


def _filename_score(filename: str, keywords: list[str], *, semantic_filename: bool) -> float:
    if not semantic_filename:
        return 0.0
    hits = len(matched_keywords(filename, keywords))
    if hits <= 0:
        return 0.0
    return min(1.0, 0.55 + (0.15 * hits))


def _looks_like_nonsemantic_filename(stem: str) -> bool:
    if stem.startswith("wxfile") or stem.startswith("tmp") or stem.startswith("image_"):
        return True
    compact = stem.replace("-", "").replace("_", "")
    if compact.isdigit() and len(compact) >= 6:
        return True
    if len(compact) >= 12 and all(ch in "0123456789abcdef" for ch in compact):
        return True
    return False


def _visual_score_v2(features: dict[str, float], rules: list[dict[str, Any]]) -> float:
    total_weight = 0.0
    score = 0.0
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        feature_name = str(rule.get("feature") or "").strip()
        fn_name = str(rule.get("fn") or "").strip()
        weight = float(rule.get("weight") or 0.0)
        if not feature_name or not fn_name or weight <= 0:
            continue
        value = float(features.get(feature_name) or 0.0)
        if fn_name == "ramp":
            component = _ramp(value, float(rule.get("low") or 0.0), float(rule.get("high") or 0.0))
        elif fn_name == "inverse_ramp":
            component = _inverse_ramp(value, float(rule.get("low") or 0.0), float(rule.get("high") or 0.0))
        elif fn_name == "band":
            component = _band_score(
                value,
                float(rule.get("low") or 0.0),
                float(rule.get("ideal_low") or 0.0),
                float(rule.get("ideal_high") or 0.0),
                float(rule.get("high") or 0.0),
            )
        else:
            continue
        total_weight += weight
        score += component * weight
    if total_weight <= 0:
        return 0.0
    return round(score / total_weight, 4)


def _ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _inverse_ramp(value: float, low: float, high: float) -> float:
    return 1.0 - _ramp(value, low, high)


def _band_score(value: float, low: float, ideal_low: float, ideal_high: float, high: float) -> float:
    if value < low or value > high:
        return 0.0
    if ideal_low <= value <= ideal_high:
        return 1.0
    if value < ideal_low:
        return _ramp(value, low, ideal_low)
    return _inverse_ramp(value, ideal_high, high)


def _category_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    categories = config.get("categories")
    if not isinstance(categories, list):
        return {
            "unknown": {
                "key": "unknown",
                "en_label": "unknown",
                "cn_label": "待确认",
                "keywords": [],
                "suggested": {
                    "insert_section": "实验结果",
                    "caption": "待确认图片",
                    "size_policy": "other",
                },
                "visual_rules": [],
            }
        }
    result: dict[str, dict[str, Any]] = {}
    for item in categories:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key:
            result[key] = dict(item)
    result.setdefault(
        "unknown",
        {
            "key": "unknown",
            "en_label": "unknown",
            "cn_label": "待确认",
            "keywords": [],
            "suggested": {
                "insert_section": "实验结果",
                "caption": "待确认图片",
                "size_policy": "other",
            },
            "visual_rules": [],
        },
    )
    return result


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
