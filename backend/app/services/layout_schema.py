from __future__ import annotations

from typing import Any


LAYOUT_SCHEMA_VERSION = 1


def build_layout_plan_from_preview(preview: dict[str, Any]) -> dict[str, Any]:
    image_plan = preview.get("imagePlan")
    image_indices = _valid_image_indices(image_plan)
    sections = []
    for section_index, section in enumerate(preview.get("sections") or [], start=1):
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        sections.append(
            {
                "key": f"section_{section_index}",
                "title": title,
                "blocks": _blocks_from_preview_section(section, image_indices),
            }
        )

    return {
        "schemaVersion": LAYOUT_SCHEMA_VERSION,
        "experimentType": str(preview.get("experimentType") or ""),
        "experimentTypeName": str(preview.get("experimentTypeName") or ""),
        "experimentName": str(preview.get("experimentName") or ""),
        "sections": sections,
        "warnings": [],
    }


def _blocks_from_preview_section(section: dict[str, Any], valid_image_indices: set[int]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for paragraph in section.get("paragraphs") or []:
        content = str(paragraph or "").strip()
        if content:
            blocks.append({"type": "paragraph", "content": content})

    for image in section.get("images") or []:
        if not isinstance(image, dict):
            continue
        image_index = _coerce_int(image.get("imageIndex"))
        if image_index is None or image_index not in valid_image_indices:
            continue
        block = {
            "type": "image",
            "imageIndex": image_index,
            "caption": str(image.get("caption") or "").strip(),
            "imageType": str(image.get("type") or "").strip(),
        }
        size_policy = str(image.get("sizePolicy") or "").strip()
        review_level = str(image.get("reviewLevel") or image.get("review_level") or "").strip()
        needs_review = bool(image.get("needsReview"))
        if size_policy:
            block["sizePolicy"] = size_policy
        if review_level:
            block["reviewLevel"] = review_level
        if needs_review:
            block["needsReview"] = True
        blocks.append(block)
        if needs_review:
            caption = str(image.get("caption") or image.get("filename") or f"image_{image_index}").strip()
            blocks.append(
                {
                    "type": "warning",
                    "message": f"Image needs review: {caption}",
                }
            )
    return blocks


def _valid_image_indices(image_plan: Any) -> set[int]:
    indices: set[int] = set()
    if not isinstance(image_plan, list):
        return indices
    for image in image_plan:
        if not isinstance(image, dict) or image.get("type") == "skip":
            continue
        image_index = _coerce_int(image.get("imageIndex"))
        if image_index is not None:
            indices.add(image_index)
    return indices


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
