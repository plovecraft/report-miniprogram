from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .image_classifier import image_width_cm
from .layout_validator import LayoutValidationError, validate_layout_plan
from .table_schema import get_table_schema, validate_table_block
from .table_writer import append_table_block


logger = logging.getLogger("report-backend.layout-executor")
_TEMP_CAPTION_PATTERN = re.compile(
    r"(wxfile:|\\uploads\\|/uploads/|[A-Za-z]:\\|/tmp/|\\tmp\\|^image[_\-]?\d+|^wxfile[_\-]|^tmp[_\-])",
    re.IGNORECASE,
)
_SEMANTIC_STEM_PATTERN = re.compile(r"(程序|梯形|接线|现象|实物|结果|仪表|图表|program|wiring|device|phenomenon|result|chart|instrument)", re.IGNORECASE)


def append_layout_plan_content(container, layout_plan: dict[str, Any], image_files: list[Path]) -> dict[str, Any]:
    result = {
        "used": True,
        "fallbackUsed": False,
        "fallbackReason": None,
        "writtenBlocks": 0,
        "writtenImages": 0,
        "degradedImages": 0,
        "imageRows": 0,
        "pairedImages": 0,
        "writtenTables": 0,
        "tableRows": 0,
        "warnings": [],
        "errors": [],
    }
    try:
        validate_layout_plan(layout_plan, set(range(len(image_files))))
    except LayoutValidationError as exc:
        result["errors"].append(str(exc))
        return result
    container.add_paragraph("")
    caption_index = 1
    for section in layout_plan.get("sections") or []:
        _append_heading(container, str(section.get("title") or ""))
        blocks = list(section.get("blocks") or [])
        block_index = 0
        while block_index < len(blocks):
            block = blocks[block_index]
            if not isinstance(block, dict):
                block_index += 1
                continue
            block_type = str(block.get("type") or "")
            if block_type == "paragraph":
                content = str(block.get("content") or "").strip()
                if not content:
                    block_index += 1
                    continue
                _append_paragraph(container, content)
                result["writtenBlocks"] += 1
                block_index += 1
                continue

            if block_type == "image":
                image_group = []
                while block_index < len(blocks):
                    current = blocks[block_index]
                    if not isinstance(current, dict) or str(current.get("type") or "") != "image":
                        break
                    image_group.append(current)
                    block_index += 1
                caption_index, image_result = _append_image_group(container, image_group, image_files, caption_index)
                result["writtenBlocks"] += len(image_group)
                result["writtenImages"] += int(image_result.get("writtenImages") or 0)
                result["degradedImages"] += int(image_result.get("degradedImages") or 0)
                result["imageRows"] += int(image_result.get("imageRows") or 0)
                result["pairedImages"] += int(image_result.get("pairedImages") or 0)
                result["warnings"].extend(list(image_result.get("warnings") or []))
                continue

            if block_type == "warning":
                message = str(block.get("message") or "").strip()
                if message:
                    result["warnings"].append(message)
                block_index += 1
                continue

            if block_type == "table":
                table_errors = validate_table_block(block)
                if table_errors:
                    result["errors"].extend(table_errors)
                    block_index += 1
                    continue
                try:
                    schema = get_table_schema(str(block.get("schema") or "").strip())
                except KeyError:
                    result["errors"].append(f"unknown table schema: {block.get('schema')}")
                    block_index += 1
                    continue
                table_result = append_table_block(
                    container,
                    block,
                    schema,
                    table_index=result["writtenTables"] + 1,
                )
                result["writtenBlocks"] += 1
                result["writtenTables"] += 1
                result["tableRows"] += int(table_result.get("rows") or 0)
                result["warnings"].extend(list(table_result.get("warnings") or []))
                result["errors"].extend(list(table_result.get("errors") or []))
                block_index += 1

    return result


def _append_heading(container, title: str) -> None:
    paragraph = container.add_paragraph()
    paragraph.paragraph_format.line_spacing = 1.15
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(title)
    run.bold = True
    _set_run_font(run)


def _append_paragraph(container, content: str) -> None:
    paragraph = container.add_paragraph(content)
    paragraph.paragraph_format.line_spacing = 1.15
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.first_line_indent = Cm(0.74)
    for run in paragraph.runs:
        _set_run_font(run)


def _append_image_block(container, block: dict[str, Any], image_files: list[Path], caption_index: int) -> tuple[int, int, int]:
    image_index = int(block.get("imageIndex"))
    image_path = image_files[image_index]
    caption_text = get_safe_image_caption(block, image_path=image_path)
    image_type = str(block.get("imageType") or "")
    size_policy = str(block.get("sizePolicy") or "").strip() or image_type
    try:
        paragraph = container.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        run.add_picture(str(image_path), width=Cm(image_width_cm(size_policy)))

        caption = container.add_paragraph(f"Figure {caption_index} {caption_text}")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for caption_run in caption.runs:
            _set_caption_font(caption_run)
        return caption_index + 1, 1, 0
    except Exception:
        logger.warning("layout image insert failed image_index=%s path=%s", image_index, image_path, exc_info=True)
        _append_paragraph(
            container,
            f"{caption_text}: {image_path.name} (image file received but could not be inserted directly)",
        )
        return caption_index, 0, 1


def _append_image_group(
    container,
    blocks: list[dict[str, Any]],
    image_files: list[Path],
    caption_index: int,
) -> tuple[int, dict[str, Any]]:
    result = {
        "writtenImages": 0,
        "degradedImages": 0,
        "imageRows": 0,
        "pairedImages": 0,
        "warnings": [],
    }
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if index + 1 < len(blocks) and is_inline_pair_candidate(block, image_files):
            next_block = blocks[index + 1]
            if is_inline_pair_candidate(next_block, image_files):
                caption_index, inserted, degraded = _append_image_pair(
                    container,
                    block,
                    next_block,
                    image_files,
                    caption_index,
                )
                result["writtenImages"] += inserted
                result["degradedImages"] += degraded
                result["pairedImages"] += 2 if inserted == 2 and degraded == 0 else 0
                result["imageRows"] += 1 if inserted == 2 and degraded == 0 else 0
                if degraded:
                    result["warnings"].append(
                        f"image pair degraded to single/text: imageIndex={block.get('imageIndex')},{next_block.get('imageIndex')}"
                    )
                index += 2
                continue

        caption_index, inserted, degraded = _append_image_block(container, block, image_files, caption_index)
        result["writtenImages"] += inserted
        result["degradedImages"] += degraded
        if degraded:
            result["warnings"].append(
                f"image block degraded to text: imageIndex={block.get('imageIndex')}"
            )
        index += 1
    return caption_index, result


def is_inline_pair_candidate(image_block: dict[str, Any], image_files: list[Path] | None = None) -> bool:
    if not isinstance(image_block, dict) or str(image_block.get("type") or "") != "image":
        return False
    if str(image_block.get("reviewLevel") or image_block.get("review_level") or "").strip() == "reject":
        return False
    if bool(image_block.get("needsReview")):
        return False
    if str(image_block.get("sizePolicy") or "").strip().lower() in {
        "small",
        "narrow",
        "program_small",
        "device_small",
        "default_small",
    }:
        return True
    if bool(image_block.get("allowInlinePair")):
        return True
    image_type = str(image_block.get("imageType") or "").strip()
    if image_type in {"result", "phenomenon", "physical", "device", "wiring"}:
        return False
    size_policy = str(image_block.get("sizePolicy") or image_block.get("imageType") or "").strip()
    if size_policy and image_width_cm(size_policy) <= 8.0:
        return True
    image_path = _image_path_for_block(image_block, image_files or [])
    if image_path is None:
        return False
    dimensions = _read_image_dimensions(image_path)
    if dimensions is None:
        return False
    width_px, height_px = dimensions
    if width_px <= 0 or height_px <= 0:
        return False
    aspect_ratio = width_px / float(height_px)
    if aspect_ratio > 1.2:
        return False
    estimated_height_cm = 7.2 / aspect_ratio if aspect_ratio > 0 else 99.0
    return estimated_height_cm <= 10.0


def _append_image_pair(
    container,
    left_block: dict[str, Any],
    right_block: dict[str, Any],
    image_files: list[Path],
    caption_index: int,
) -> tuple[int, int, int]:
    left_path = _image_path_for_block(left_block, image_files)
    right_path = _image_path_for_block(right_block, image_files)
    if left_path is None or right_path is None:
        next_index, inserted, degraded = _append_image_block(container, left_block, image_files, caption_index)
        final_index, inserted2, degraded2 = _append_image_block(container, right_block, image_files, next_index)
        return final_index, inserted + inserted2, degraded + degraded2

    try:
        table = container.add_table(rows=1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_no_borders(table)
        _append_image_to_cell(table.cell(0, 0), left_block, left_path, caption_index)
        _append_image_to_cell(table.cell(0, 1), right_block, right_path, caption_index + 1)
        container.add_paragraph("")
        return caption_index + 2, 2, 0
    except Exception:
        logger.warning(
            "layout image pair insert failed left=%s right=%s",
            left_block.get("imageIndex"),
            right_block.get("imageIndex"),
            exc_info=True,
        )
        next_index, inserted, degraded = _append_image_block(container, left_block, image_files, caption_index)
        final_index, inserted2, degraded2 = _append_image_block(container, right_block, image_files, next_index)
        return final_index, inserted + inserted2, degraded + degraded2


def _append_image_to_cell(cell, block: dict[str, Any], image_path: Path, caption_index: int) -> None:
    caption_text = get_safe_image_caption(block, image_path=image_path)
    image_type = str(block.get("imageType") or "")
    size_policy = str(block.get("sizePolicy") or "").strip() or image_type
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(image_path), width=Cm(_paired_image_width_cm(size_policy)))
    caption = cell.add_paragraph(f"Figure {caption_index} {caption_text}")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for caption_run in caption.runs:
        _set_caption_font(caption_run)


def normalize_caption_text(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return "实验图片"
    if _TEMP_CAPTION_PATTERN.search(value):
        return "实验图片"
    cleaned = "".join(ch for ch in value if ch >= " " or ch in "\n\t")
    cleaned = cleaned.replace("\ufeff", "").strip()
    if not cleaned:
        return "实验图片"
    return cleaned


def get_safe_image_caption(
    image_block: dict[str, Any],
    image_plan_item: dict[str, Any] | None = None,
    image_path: Path | None = None,
) -> str:
    candidates = []
    if isinstance(image_block, dict):
        candidates.extend(
            [
                image_block.get("captionOverride"),
                image_block.get("caption"),
            ]
        )
    if isinstance(image_plan_item, dict):
        suggested = image_plan_item.get("suggested")
        candidates.extend(
            [
                suggested.get("caption") if isinstance(suggested, dict) else None,
                image_plan_item.get("caption"),
                image_plan_item.get("suggestedCaption"),
            ]
        )
    if image_path is not None and _looks_like_semantic_stem(image_path.stem):
        candidates.append(image_path.stem)

    for candidate in candidates:
        normalized = normalize_caption_text(candidate)
        if normalized != "实验图片":
            return normalized

    fallback_type = str(
        (image_plan_item or {}).get("categoryCn")
        or (image_plan_item or {}).get("category_cn")
        or (image_plan_item or {}).get("category")
        or image_block.get("imageType")
        or ""
    ).strip()
    if fallback_type in {"程序图", "program"}:
        return "PLC 控制程序图"
    if fallback_type in {"接线图", "wiring"}:
        return "实验接线图"
    if fallback_type in {"实验现象图", "phenomenon", "result"}:
        return "实验现象图"
    if fallback_type in {"实物图", "device", "physical"}:
        return "实验实物图"
    return "实验图片"


def _looks_like_semantic_stem(stem: str) -> bool:
    value = str(stem or "").strip()
    if not value:
        return False
    if _TEMP_CAPTION_PATTERN.search(value):
        return False
    return bool(_SEMANTIC_STEM_PATTERN.search(value))


def _paired_image_width_cm(size_policy: str) -> float:
    base_width = image_width_cm(size_policy)
    return min(max(base_width, 7.0), 7.3)


def _image_path_for_block(block: dict[str, Any], image_files: list[Path]) -> Path | None:
    try:
        image_index = int(block.get("imageIndex"))
    except (TypeError, ValueError):
        return None
    if image_index < 0 or image_index >= len(image_files):
        return None
    return image_files[image_index]


def _read_image_dimensions(image_path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def set_table_no_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    tbl_borders = tbl_pr.first_child_found_in("w:tblBorders")
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tbl_borders.find(qn(f"w:{edge}"))
        if border is None:
            border = OxmlElement(f"w:{edge}")
            tbl_borders.append(border)
        border.set(qn("w:val"), "none")
        border.set(qn("w:sz"), "0")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), "auto")


def _set_run_font(run) -> None:
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(10.5)


def _set_caption_font(run) -> None:
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(9)
