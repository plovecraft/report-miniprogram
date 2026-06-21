from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docx import Document

from .layout_executor import append_layout_plan_content
from .layout_validator import LayoutValidationError, validate_layout_plan


logger = logging.getLogger("report-backend.layout-shadow")

LOW_CONFIDENCE_THRESHOLD = 0.5


def build_layout_shadow_summary(layout_plan: dict[str, Any], image_files: list[Path]) -> dict[str, Any]:
    doc = Document()
    section_summaries = _build_section_summaries(layout_plan)
    base_warnings = _layout_warning_messages(layout_plan)
    try:
        executor_result = append_layout_plan_content(doc, layout_plan, image_files)
        rendered_text = _document_text(doc)
        rendered_images = len(doc.inline_shapes)
        degraded_images = max(0, _image_block_count(layout_plan) - rendered_images)
        executor_warnings = list(executor_result.get("warnings") or [])
        executor_errors = list(executor_result.get("errors") or [])
        merged_warnings = _dedupe_strings(list(base_warnings) + executor_warnings)
        if executor_errors:
            return {
                "ok": False,
                "sectionCount": _section_count(layout_plan),
                "inlineShapeCount": rendered_images,
                "warningCount": len(merged_warnings),
                "text": rendered_text,
                "renderedText": rendered_text,
                "error": "; ".join(executor_errors),
                "errors": executor_errors,
                "warnings": merged_warnings,
                "sections": section_summaries,
                "summary": {
                    "section_count": _section_count(layout_plan),
                    "block_count": _block_count(layout_plan),
                    "paragraph_count": _paragraph_block_count(layout_plan),
                    "image_count": rendered_images,
                    "table_count": int(executor_result.get("writtenTables") or 0),
                    "warning_count": len(merged_warnings),
                    "degraded_image_count": degraded_images,
                },
            }
        return {
            "ok": True,
            "sectionCount": _section_count(layout_plan),
            "inlineShapeCount": rendered_images,
            "warningCount": len(merged_warnings),
            "text": rendered_text,
            "renderedText": rendered_text,
            "error": "",
            "errors": [],
            "warnings": merged_warnings,
            "sections": section_summaries,
            "summary": {
                "section_count": _section_count(layout_plan),
                "block_count": _block_count(layout_plan),
                "paragraph_count": _paragraph_block_count(layout_plan),
                "image_count": rendered_images,
                "table_count": int(executor_result.get("writtenTables") or 0),
                "warning_count": len(merged_warnings),
                "degraded_image_count": degraded_images,
            },
        }
    except Exception as exc:
        logger.warning("layout shadow summary failed", exc_info=True)
        return {
            "ok": False,
            "sectionCount": _section_count(layout_plan),
            "inlineShapeCount": 0,
            "warningCount": len(base_warnings),
            "text": "",
            "renderedText": "",
            "error": str(exc),
            "errors": [str(exc)],
            "warnings": list(base_warnings),
            "sections": section_summaries,
            "summary": {
                "section_count": _section_count(layout_plan),
                "block_count": _block_count(layout_plan),
                "paragraph_count": _paragraph_block_count(layout_plan),
                "image_count": 0,
                "table_count": 0,
                "warning_count": len(base_warnings),
                "degraded_image_count": 0,
            },
        }


def run_layout_shadow_check(preview: dict[str, Any], layout_plan: dict[str, Any], image_files: list[Path]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    preview_data = preview if isinstance(preview, dict) else {}
    valid_image_indices = _preview_image_indices(preview_data) or set(range(len(image_files)))
    review_image_indices = _review_image_indices(preview_data)

    checks = {
        "section_titles_match": _section_titles(preview_data) == _section_titles(layout_plan),
        "image_block_count_matches_preview": _image_block_count(layout_plan) == _expected_image_count(preview_data),
        "image_references_valid": True,
        "executor_completed": True,
        "key_text_rendered": True,
        "warning_blocks_recorded": True,
        "review_images_degraded": True,
        "rendered_image_count_matches_expected": True,
        "inserted_images": 0,
        "expected_images": _expected_image_count(preview_data),
        "expected_rendered_images": _expected_rendered_image_count(preview_data),
    }

    if not checks["section_titles_match"]:
        warnings.append("layout section titles do not match preview sections")
    if not checks["image_block_count_matches_preview"]:
        warnings.append(
            f"layout image block count {_image_block_count(layout_plan)} does not match preview insertedImageCount {_expected_image_count(preview_data)}"
        )

    try:
        validate_layout_plan(layout_plan, valid_image_indices)
    except LayoutValidationError as exc:
        message = str(exc)
        checks["executor_completed"] = False
        checks["image_references_valid"] = "imageIndex" not in message and "unknown imageIndex" not in message
        errors.append(message)
        logger.warning("layout shadow validation failed", exc_info=True)
        return {
            "passed": False,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "summary": _empty_shadow_summary(layout_plan),
            "sections": _build_section_summaries(layout_plan),
        }

    effective_image_files = _shadow_image_files(image_files, review_image_indices)
    summary = build_layout_shadow_summary(layout_plan, effective_image_files)
    warnings.extend(summary.get("warnings") or [])
    errors.extend(summary.get("errors") or [])
    checks["executor_completed"] = bool(summary.get("ok"))
    checks["inserted_images"] = int(summary.get("summary", {}).get("image_count") or 0)

    rendered_text = str(summary.get("renderedText") or summary.get("text") or "")
    expected_texts = _expected_key_texts(preview_data, layout_plan)
    checks["key_text_rendered"] = all(text in rendered_text for text in expected_texts)
    if not checks["key_text_rendered"]:
        warnings.append("shadow render missing expected paragraph content")

    checks["warning_blocks_recorded"] = int(summary.get("summary", {}).get("warning_count") or 0) >= _warning_block_count(layout_plan)
    if not checks["warning_blocks_recorded"]:
        warnings.append("warning blocks were not recorded in shadow summary")

    expected_rendered_images = _expected_rendered_image_count(preview_data)
    checks["rendered_image_count_matches_expected"] = int(summary.get("summary", {}).get("image_count") or 0) == expected_rendered_images
    if not checks["rendered_image_count_matches_expected"]:
        warnings.append(
            f"shadow rendered image count {summary.get('summary', {}).get('image_count', 0)} does not match expected rendered image count {expected_rendered_images}"
        )

    degraded_image_count = int(summary.get("summary", {}).get("degraded_image_count") or 0)
    checks["review_images_degraded"] = degraded_image_count >= len(review_image_indices)
    if review_image_indices:
        warnings.extend(_review_image_warnings(preview_data, review_image_indices))
    if not checks["review_images_degraded"]:
        warnings.append("images marked for review were not degraded in shadow rendering")

    passed = not errors and all(bool(value) for key, value in checks.items() if isinstance(value, bool))
    return {
        "passed": passed,
        "checks": checks,
        "warnings": _dedupe_strings(warnings),
        "errors": _dedupe_strings(errors),
        "summary": summary.get("summary") or _empty_shadow_summary(layout_plan),
        "sections": summary.get("sections") or _build_section_summaries(layout_plan),
    }


def _empty_shadow_summary(layout_plan: dict[str, Any]) -> dict[str, int]:
    return {
        "section_count": _section_count(layout_plan),
        "block_count": _block_count(layout_plan),
        "paragraph_count": _paragraph_block_count(layout_plan),
        "image_count": 0,
        "table_count": 0,
        "warning_count": len(_layout_warning_messages(layout_plan)),
        "degraded_image_count": 0,
    }


def _build_section_summaries(layout_plan: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section_index, section in enumerate(_iter_sections(layout_plan), start=1):
        key = str(section.get("key") or f"section_{section_index}")
        blocks = section.get("blocks")
        block_list = blocks if isinstance(blocks, list) else []
        image_refs = []
        text_parts = []
        for block in block_list:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "image":
                image_index = _coerce_int(block.get("imageIndex"))
                if image_index is not None:
                    image_refs.append(f"image_{image_index}")
            if block.get("type") == "paragraph":
                content = str(block.get("content") or "").strip()
                if content:
                    text_parts.append(content)
            if block.get("type") == "warning":
                message = str(block.get("message") or "").strip()
                if message:
                    text_parts.append(message)
        sections.append(
            {
                "key": key,
                "title": str(section.get("title") or "").strip(),
                "block_count": len(block_list),
                "image_refs": image_refs,
                "text_preview": "\n".join(text_parts)[:240],
            }
        )
    return sections


def _section_titles(value: dict[str, Any]) -> list[str]:
    return [
        str(section.get("title") or "").strip()
        for section in _iter_sections(value)
        if str(section.get("title") or "").strip()
    ]


def _iter_sections(value: dict[str, Any]) -> list[dict[str, Any]]:
    sections = value.get("sections")
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def _section_count(layout_plan: dict[str, Any]) -> int:
    return len(_section_titles(layout_plan))


def _block_count(layout_plan: dict[str, Any]) -> int:
    count = 0
    for section in _iter_sections(layout_plan):
        blocks = section.get("blocks")
        if isinstance(blocks, list):
            count += len(blocks)
    return count


def _paragraph_block_count(layout_plan: dict[str, Any]) -> int:
    count = 0
    for section in _iter_sections(layout_plan):
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "paragraph":
                count += 1
    return count


def _warning_block_count(layout_plan: dict[str, Any]) -> int:
    count = 0
    for section in _iter_sections(layout_plan):
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "warning":
                count += 1
    return count


def _layout_warning_messages(layout_plan: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    warnings = layout_plan.get("warnings")
    if isinstance(warnings, list):
        messages.extend(str(message).strip() for message in warnings if str(message).strip())
    for section in _iter_sections(layout_plan):
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "warning":
                message = str(block.get("message") or "").strip()
                if message:
                    messages.append(message)
    return _dedupe_strings(messages)


def _document_text(doc: Document) -> str:
    parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    return "\n".join(parts)


def _image_block_count(layout_plan: dict[str, Any]) -> int:
    count = 0
    for section in _iter_sections(layout_plan):
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                count += 1
    return count


def _expected_image_count(preview: dict[str, Any]) -> int:
    try:
        return int(preview.get("insertedImageCount") or 0)
    except (TypeError, ValueError):
        return 0


def _expected_rendered_image_count(preview: dict[str, Any]) -> int:
    image_plan = preview.get("imagePlan")
    if not isinstance(image_plan, list):
        return _expected_image_count(preview)
    return sum(
        1
        for image in image_plan
        if isinstance(image, dict) and image.get("type") != "skip" and not _image_needs_review(image)
    )


def _expected_key_texts(preview: dict[str, Any], layout_plan: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for section in preview.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for paragraph in section.get("paragraphs") or []:
            content = str(paragraph or "").strip()
            if content:
                texts.append(content)
    if texts:
        return _dedupe_strings(texts)
    for section in _iter_sections(layout_plan):
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "paragraph":
                content = str(block.get("content") or "").strip()
                if content:
                    texts.append(content)
    return _dedupe_strings(texts)


def _preview_image_indices(preview: dict[str, Any]) -> set[int]:
    indices: set[int] = set()
    for image in preview.get("imagePlan") or []:
        if not isinstance(image, dict) or image.get("type") == "skip":
            continue
        image_index = _coerce_int(image.get("imageIndex"))
        if image_index is not None:
            indices.add(image_index)
    return indices


def _review_image_indices(preview: dict[str, Any]) -> set[int]:
    indices: set[int] = set()
    for image in preview.get("imagePlan") or []:
        if not isinstance(image, dict):
            continue
        image_index = _coerce_int(image.get("imageIndex"))
        if image_index is None:
            continue
        if _image_needs_review(image):
            indices.add(image_index)
    return indices


def _image_needs_review(image: dict[str, Any]) -> bool:
    quality = image.get("quality")
    if isinstance(quality, dict) and bool(quality.get("needs_review")):
        return True
    confidence = image.get("confidence")
    try:
        if confidence is not None and float(confidence) < LOW_CONFIDENCE_THRESHOLD:
            return True
    except (TypeError, ValueError):
        return False
    return False


def _shadow_image_files(image_files: list[Path], review_image_indices: set[int]) -> list[Path]:
    if not review_image_indices:
        return image_files
    shadow_files = list(image_files)
    for index in review_image_indices:
        if 0 <= index < len(shadow_files):
            shadow_files[index] = Path(f"__shadow_review_blocked__/image_{index}.png")
    return shadow_files


def _review_image_warnings(preview: dict[str, Any], review_image_indices: set[int]) -> list[str]:
    warnings: list[str] = []
    by_index = {
        _coerce_int(image.get("imageIndex")): image
        for image in preview.get("imagePlan") or []
        if isinstance(image, dict)
    }
    for index in sorted(review_image_indices):
        image = by_index.get(index) or {}
        caption = str(image.get("caption") or image.get("filename") or f"image_{index}").strip()
        warnings.append(f"image {index} needs review and was degraded in shadow render: {caption}")
    return warnings


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
