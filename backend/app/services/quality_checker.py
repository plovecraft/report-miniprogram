from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document

from .report_inspector import find_body_cell


FILENAME_PATTERN = re.compile(r"\.(?:jpg|jpeg|png|gif|bmp|webp)\b", re.IGNORECASE)
EXPERIMENT_PATTERN = re.compile(r"实验\s*([一二三四五六七八九十]|\d+)")


def build_quality_report(
    *,
    source_file: Path | None,
    output_file: Path | None,
    expected_image_count: int,
    target_experiment: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    source_doc = _open_docx(source_file)
    output_doc = _open_docx(output_file)

    source_table_count = len(source_doc.tables) if source_doc else 0
    output_table_count = len(output_doc.tables) if output_doc else 0
    body_cell = find_body_cell(output_doc) if output_doc else None
    body_text = body_cell.text.strip() if body_cell is not None else _document_text(output_doc)
    images_inserted = len(output_doc.inline_shapes) if output_doc else 0

    checks: dict[str, Any] = {
        "template_preserved": output_table_count > 0,
        "table_count_preserved": source_doc is not None and output_doc is not None and source_table_count == output_table_count,
        "body_cell_found": body_cell is not None,
        "body_not_empty": bool(body_text),
        "body_replaced": _body_replaced(source_doc, body_text),
        "images_inserted": images_inserted,
        "expected_images": expected_image_count,
        "filename_reference_found": bool(FILENAME_PATTERN.search(body_text)),
        "stale_experiment_text_found": _has_stale_experiment_text(body_text, target_experiment),
    }

    if not checks["template_preserved"]:
        warnings.append("未检测到保留的表格模板。")
    if not checks["table_count_preserved"]:
        warnings.append("表格数量发生变化，请检查模板是否被破坏。")
    if not checks["body_cell_found"]:
        warnings.append("未找到正文大单元格。")
    if not checks["body_not_empty"]:
        warnings.append("正文区域为空。")
    if not checks["body_replaced"]:
        warnings.append("正文可能未成功替换。")
    if expected_image_count > 0 and images_inserted <= 0:
        warnings.append("未检测到插入图片。")
    elif expected_image_count > 0 and images_inserted < expected_image_count:
        warnings.append(f"图片插入数量少于上传数量：已插入 {images_inserted} 张，上传 {expected_image_count} 张。")
    if checks["filename_reference_found"]:
        warnings.append("正文中仍包含图片文件名或扩展名。")
    if checks["stale_experiment_text_found"]:
        warnings.append("疑似存在旧实验内容残留。")

    return {
        "passed": len(warnings) == 0,
        "checks": checks,
        "warnings": warnings,
    }


def _open_docx(path: Path | None):
    if path is None or not path.exists() or path.suffix.lower() != ".docx":
        return None
    return Document(path)


def _body_replaced(source_doc, output_body_text: str) -> bool:
    if source_doc is None:
        return bool(output_body_text)
    source_body = find_body_cell(source_doc)
    if source_body is None:
        return bool(output_body_text) and output_body_text != _document_text(source_doc)
    source_text = source_body.text.strip()
    return bool(output_body_text) and output_body_text != source_text


def _has_stale_experiment_text(body_text: str, target_experiment: str) -> bool:
    target_number = _experiment_number(target_experiment)
    if target_number is None:
        return False
    for match in EXPERIMENT_PATTERN.finditer(body_text):
        number = _experiment_number(match.group(0))
        if number is not None and number != target_number:
            return True
    return False


def _experiment_number(text: str) -> int | None:
    match = EXPERIMENT_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        return int(value)
    return {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }.get(value)


def _document_text(doc) -> str:
    if doc is None:
        return ""
    parts = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    parts.append(text)
    return "\n".join(parts)
