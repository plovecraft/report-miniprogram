from __future__ import annotations

from typing import Any

from .table_schema import validate_table_block

ALLOWED_BLOCK_TYPES = {"paragraph", "image", "warning", "table"}
SUPPORTED_SCHEMA_VERSION = 1


class LayoutValidationError(ValueError):
    pass


def validate_layout_plan(layout_plan: dict[str, Any], valid_image_indices: set[int] | None = None) -> None:
    schema_version = layout_plan.get("schemaVersion")
    if type(schema_version) is not int:
        raise LayoutValidationError("layout_plan.schemaVersion is required")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise LayoutValidationError(f"unsupported schemaVersion: {schema_version}")

    valid_images = valid_image_indices or set()
    sections = layout_plan.get("sections")
    if not isinstance(sections, list):
        raise LayoutValidationError("layout_plan.sections must be a list")

    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise LayoutValidationError(f"section {section_index} must be an object")
        title = str(section.get("title") or "").strip()
        if not title:
            raise LayoutValidationError(f"section {section_index} missing title")
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            raise LayoutValidationError(f"section {section_index} blocks must be a list")
        for block_index, block in enumerate(blocks):
            _validate_block(block, valid_images, section_index, block_index)

    warnings = layout_plan.get("warnings", [])
    if not isinstance(warnings, list):
        raise LayoutValidationError("layout_plan.warnings must be a list")


def _validate_block(block: Any, valid_image_indices: set[int], section_index: int, block_index: int) -> None:
    if not isinstance(block, dict):
        raise LayoutValidationError(f"block {section_index}.{block_index} must be an object")
    block_type = str(block.get("type") or "").strip()
    if block_type not in ALLOWED_BLOCK_TYPES:
        raise LayoutValidationError(f"unsupported block type: {block_type}")

    if block_type == "paragraph" and not str(block.get("content") or "").strip():
        raise LayoutValidationError(f"paragraph block {section_index}.{block_index} missing content")
    if block_type == "warning" and not str(block.get("message") or "").strip():
        raise LayoutValidationError(f"warning block {section_index}.{block_index} missing message")
    if block_type == "image":
        image_index = _coerce_int(block.get("imageIndex"))
        if image_index is None:
            raise LayoutValidationError(f"image block {section_index}.{block_index} missing imageIndex")
        if image_index not in valid_image_indices:
            raise LayoutValidationError(f"unknown imageIndex: {image_index}")
    if block_type == "table":
        errors = validate_table_block(block)
        if errors:
            raise LayoutValidationError(
                f"table block {section_index}.{block_index} invalid: {'; '.join(errors)}"
            )


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
