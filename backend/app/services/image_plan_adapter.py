from __future__ import annotations

from pathlib import Path
from typing import Any

from .experiment_config_loader import ExperimentConfig
from .image_classifier import classify_image_info


CATEGORY_TO_LEGACY_TYPE = {
    "program": "program",
    "wiring": "wiring",
    "device": "physical",
    "phenomenon": "result",
    "document": "other",
    "instrument": "result",
    "meter": "result",
    "chart": "result",
    "unknown": "other",
}

CATEGORY_DISPLAY = {
    "program": "程序图",
    "basic_program": "程序图",
    "thought1_program": "程序图",
    "thought2_program": "程序图",
    "wiring": "接线图",
    "device": "实物图",
    "physical": "实物图",
    "phenomenon": "实验现象图",
    "result": "实验现象图",
    "basic_result": "实验现象图",
    "thought1_result": "实验现象图",
    "thought2_result": "实验现象图",
    "document": "文档/截图",
    "instrument": "仪表图",
    "meter": "仪表图",
    "chart": "曲线/图表",
    "unknown": "待确认",
    "skip": "不插入",
}

TYPE_TO_CATEGORY = {
    "program": "program",
    "wiring": "wiring",
    "physical": "device",
    "result": "phenomenon",
    "other": "unknown",
}


def adapt_recognition_to_image_plan(
    *,
    image_index: int,
    filename: str,
    recognition: dict[str, Any],
    meta: dict[str, Any] | None,
    experiment_config: ExperimentConfig,
) -> dict[str, Any]:
    meta = dict(meta or {})
    review_level = str(recognition.get("review_level") or "review").strip() or "review"
    category = str(recognition.get("category") or "unknown").strip() or "unknown"
    category_cn = (
        str(recognition.get("category_cn") or "").strip()
        or CATEGORY_DISPLAY.get(category)
        or "待确认"
    )
    suggested = dict(recognition.get("suggested") or {})
    quality = dict(recognition.get("quality") or {})
    needs_review = bool(quality.get("needs_review")) or review_level == "review"
    manual_category = str(meta.get("category") or "").strip()
    manual_override = manual_category not in {"", "auto", "unknown"}

    if manual_override:
        manual_info = classify_image_info(filename, manual_category)
        if manual_info is None:
            return _build_skip_result(
                image_index=image_index,
                filename=filename,
                recognition=recognition,
                section=str(meta.get("section") or "").strip(),
                caption=str(meta.get("caption") or "不插入").strip() or "不插入",
                sort_order=_coerce_int(meta.get("sortOrder"), image_index),
            )
        return _build_result(
            image_index=image_index,
            filename=filename,
            recognition=recognition,
            category=manual_category,
            category_cn=CATEGORY_DISPLAY.get(manual_category, manual_info.caption),
            type_name=manual_info.type,
            section=str(meta.get("section") or manual_info.section).strip(),
            caption=str(meta.get("caption") or manual_info.caption).strip(),
            size_policy=_default_size_policy(manual_info.type),
            review_level="ok",
            review_reasons=[],
            needs_review=False,
            quality={"readable": True, "needs_review": False},
            sort_order=_coerce_int(meta.get("sortOrder"), image_index),
        )

    fallback_info = classify_image_info(filename)
    if _should_fallback_to_filename(recognition, fallback_info):
        fallback_type = fallback_info.type if fallback_info is not None else "other"
        fallback_category = TYPE_TO_CATEGORY.get(fallback_type, "unknown")
        fallback_review_level = "review" if review_level == "reject" else review_level
        fallback_reasons = list(recognition.get("review_reasons") or [])
        if not fallback_reasons and fallback_review_level == "review":
            fallback_reasons = ["filename heuristic used after recognition fallback"]
        fallback_quality = dict(quality)
        fallback_quality["needs_review"] = fallback_review_level == "review"
        return _build_result(
            image_index=image_index,
            filename=filename,
            recognition=recognition,
            category=fallback_category,
            category_cn=CATEGORY_DISPLAY.get(fallback_category, "待确认"),
            type_name=fallback_type,
            section=str(meta.get("section") or fallback_info.section).strip(),
            caption=str(meta.get("caption") or fallback_info.caption).strip(),
            size_policy=_default_size_policy(fallback_type),
            review_level=fallback_review_level,
            review_reasons=fallback_reasons,
            needs_review=fallback_review_level == "review",
            quality=fallback_quality,
            sort_order=_coerce_int(meta.get("sortOrder"), image_index),
        )

    type_name = "skip" if review_level == "reject" else _legacy_type_for_category(category)
    section = str(meta.get("section") or "").strip() or _normalize_insert_section(
        str(suggested.get("insert_section") or "").strip(),
        type_name,
        experiment_config,
    )
    caption = (
        str(meta.get("caption") or "").strip()
        or str(suggested.get("caption") or "").strip()
        or _default_caption(category, filename)
    )
    size_policy = str(
        suggested.get("size_policy") or meta.get("sizePolicy") or _default_size_policy(type_name)
    ).strip() or _default_size_policy(type_name)
    return _build_result(
        image_index=image_index,
        filename=filename,
        recognition=recognition,
        category=category,
        category_cn=category_cn,
        type_name=type_name,
        section=section,
        caption=caption,
        size_policy=size_policy,
        review_level=review_level,
        review_reasons=list(recognition.get("review_reasons") or []),
        needs_review=needs_review,
        quality=quality,
        sort_order=_coerce_int(meta.get("sortOrder"), image_index),
    )


def _build_result(
    *,
    image_index: int,
    filename: str,
    recognition: dict[str, Any],
    category: str,
    category_cn: str,
    type_name: str,
    section: str,
    caption: str,
    size_policy: str,
    review_level: str,
    review_reasons: list[str],
    needs_review: bool,
    quality: dict[str, Any],
    sort_order: int,
) -> dict[str, Any]:
    suggested = dict(recognition.get("suggested") or {})
    suggested["insert_section"] = section
    suggested["caption"] = caption
    suggested["size_policy"] = size_policy
    return {
        "schema_version": recognition.get("schema_version") or "image-plan.v1",
        "experiment_type": recognition.get("experiment_type") or "plc",
        "image_ref": recognition.get("image_ref") or f"image_{image_index}",
        "imageIndex": image_index,
        "filename": filename,
        "type": type_name,
        "category": category,
        "categoryCn": category_cn,
        "category_cn": category_cn,
        "section": section,
        "insertSection": section,
        "caption": caption,
        "suggestedCaption": caption,
        "sizePolicy": size_policy,
        "sortOrder": sort_order,
        "recognized": type_name not in {"skip", "other"},
        "confidence": float(recognition.get("confidence") or 0.0),
        "reviewLevel": review_level,
        "review_level": review_level,
        "reviewReasons": list(review_reasons),
        "review_reasons": list(review_reasons),
        "needsReview": bool(needs_review),
        "quality": dict(quality),
        "suggested": suggested,
        "features": dict(recognition.get("features") or {}),
        "score_detail": dict(recognition.get("score_detail") or {}),
    }


def _build_skip_result(
    *,
    image_index: int,
    filename: str,
    recognition: dict[str, Any],
    section: str,
    caption: str,
    sort_order: int,
) -> dict[str, Any]:
    return _build_result(
        image_index=image_index,
        filename=filename,
        recognition=recognition,
        category="skip",
        category_cn="不插入",
        type_name="skip",
        section=section,
        caption=caption,
        size_policy="skip",
        review_level="ok",
        review_reasons=[],
        needs_review=False,
        quality={"readable": True, "needs_review": False},
        sort_order=sort_order,
    )


def _should_fallback_to_filename(recognition: dict[str, Any], fallback_info) -> bool:
    if fallback_info is None or fallback_info.type == "other":
        return False
    category = str(recognition.get("category") or "").strip()
    review_level = str(recognition.get("review_level") or "").strip()
    if not recognition:
        return True
    if review_level == "reject":
        return isinstance(recognition.get("error"), dict)
    return category in {"", "unknown"}


def _normalize_insert_section(
    suggested_section: str,
    type_name: str,
    experiment_config: ExperimentConfig,
) -> str:
    configured = str(experiment_config.image_types.get(type_name, {}).get("section") or "").strip()
    if configured:
        return configured
    hint = suggested_section.strip()
    if hint:
        for section in experiment_config.default_sections:
            if hint in section or section in hint:
                return section
    if type_name == "program":
        return experiment_config.default_sections[4]
    if type_name == "wiring":
        return experiment_config.default_sections[3]
    return experiment_config.default_sections[5]


def _legacy_type_for_category(category: str) -> str:
    return CATEGORY_TO_LEGACY_TYPE.get(category, "other")


def _default_size_policy(type_name: str) -> str:
    if type_name in {"program", "wiring"}:
        return type_name
    if type_name in {"physical", "result"}:
        return "phenomenon"
    return "other"


def _default_caption(category: str, filename: str) -> str:
    return CATEGORY_DISPLAY.get(category, Path(filename).stem or "待确认图片")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
