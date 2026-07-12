from __future__ import annotations

import logging
import os
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .docx_reviser import clear_container_content
from .experiment_config_loader import load_experiment_config
from .experiment_selector import infer_experiment_label, select_experiment_section
from .guide_parser import MAX_TEXT_CHARS, extract_guide_text
from .image_classifier import (
    SECTION_OPERATION,
    SECTION_PROGRAM,
    SECTION_RESULT,
    ImagePlacement,
    classify_image_info,
    classify_images,
    group_images_by_section,
    image_categories_by_filename,
    image_metas_by_filename,
    image_width_cm,
)
from . import image_recognizer
from .ai_layout_planner import build_ai_planner_preview_summary, generate_ai_layout_plan_candidate
from .image_plan_adapter import CATEGORY_DISPLAY, adapt_recognition_to_image_plan
from .layout_executor import append_layout_plan_content, get_safe_image_caption, normalize_caption_text
from .layout_schema import build_layout_plan_from_preview
from .layout_shadow import run_layout_shadow_check
from .layout_validator import LayoutValidationError, validate_layout_plan
from .llm_writer import LLMConfig, ReportDraft, SectionList, generate_report_sections
from .report_reader import extract_report_text
from .report_templates import resolve_report_template
from .runtime_config import table_feature_enabled_from_env
from .table_planner import inject_planned_tables
from .table_schema import get_table_schema, validate_table_block
from .task_store import TaskRecord


logger = logging.getLogger("report-backend.docx")

IMAGE_OVERRIDE_CATEGORIES = {
    "program",
    "wiring",
    "device",
    "phenomenon",
    "document",
    "chart",
    "instrument",
    "unknown",
}



def table_feature_enabled() -> bool:
    return table_feature_enabled_from_env()


def strip_table_blocks_from_layout_plan(layout_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(layout_plan, dict):
        return None
    copied = deepcopy(layout_plan)
    for section in copied.get("sections") or []:
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks")
        if isinstance(blocks, list):
            section["blocks"] = [block for block in blocks if not (isinstance(block, dict) and block.get("type") == "table")]
    return copied

IMAGE_OVERRIDE_SIZE_POLICIES = {
    "program",
    "wiring",
    "phenomenon",
    "other",
    "default",
    "default_small",
    "program_small",
    "device_small",
    "small",
    "narrow",
    "skip",
}


def build_revised_docx(record: TaskRecord) -> Path:
    if record.report_file is None:
        raise ValueError("缺少原始实验报告 DOCX")
    if record.report_file.suffix.lower() != ".docx":
        raise ValueError("原始实验报告必须是 DOCX 文件")

    run_pre_generation_shadow_gate(record)
    output = record.output_dir / f"{record.report_file.stem}_revised.docx"
    shutil.copy2(record.report_file, output)
    effective_layout_plan = get_effective_preview_layout_plan(record)

    doc = Document(output)
    draft = build_report_draft(record)
    template = resolve_report_template(doc)
    logger.info(
        "report template resolved task_id=%s template=%s confidence=%.2f body=%s",
        record.task_id,
        template.template_id,
        template.confidence,
        template.body_location,
    )
    template.adapter.update_header(doc, _header_values(record, draft.experiment_name))
    body_cell = template.adapter.get_body_container(doc)
    try:
        if body_cell is not None:
            clear_container_content(body_cell)
            _write_report_content(body_cell, record, draft, effective_layout_plan)
        else:
            clear_container_content(doc)
            _write_report_content(doc, record, draft, effective_layout_plan)
        record.table_audit_report = build_table_audit_report(
            record,
            effective_layout_plan=effective_layout_plan,
            executor_report=record.layout_executor_report,
        )
    except Exception:
        record.table_audit_report = build_table_audit_report(
            record,
            effective_layout_plan=effective_layout_plan,
            executor_report=record.layout_executor_report,
        )
        raise
    doc.save(output)
    return output


def run_pre_generation_shadow_gate(record: TaskRecord) -> dict[str, Any]:
    preview_data = record.preview_data if isinstance(record.preview_data, dict) else None
    layout_plan = get_effective_preview_layout_plan(record)
    if layout_plan is None and preview_data is not None:
        layout_plan = build_validated_layout_plan(preview_data)

    if preview_data is None or layout_plan is None:
        result = {
            "passed": True,
            "warnings": ["Shadow gate skipped: preview data or validated layout plan unavailable."],
            "errors": [],
            "summary": {},
            "sections": [],
            "checks": {},
            "skipped": True,
        }
        record.shadow_gate_report = result
        logger.info("shadow gate skipped task_id=%s", record.task_id)
        return result

    result = run_layout_shadow_check(preview_data, layout_plan, record.image_files)
    result["skipped"] = False
    record.shadow_gate_report = result
    if result.get("errors"):
        detail = "; ".join(str(item).strip() for item in result["errors"] if str(item).strip()) or "unknown shadow gate error"
        raise ValueError(f"Layout shadow check failed: {detail}")
    if result.get("warnings"):
        logger.info("shadow gate warnings task_id=%s warnings=%s", record.task_id, result["warnings"])
    else:
        logger.info("shadow gate passed task_id=%s", record.task_id)
    return result


def _write_report_content(
    container,
    record: TaskRecord,
    draft: ReportDraft,
    effective_layout_plan: dict[str, Any] | None = None,
) -> None:
    layout_plan = effective_layout_plan
    if layout_plan is None:
        append_legacy_fallback_content(container, draft.sections, record.image_files, record.metadata)
        record.layout_executor_report = _legacy_layout_executor_report("preview_layout_plan missing")
        return

    execution_plan = _build_execution_layout_plan(layout_plan, draft.sections)
    try:
        executor_result = append_layout_plan_content(container, execution_plan, record.image_files)
    except Exception as exc:
        record.layout_executor_report = _failed_layout_executor_report(str(exc))
        raise
    record.layout_executor_report = _normalize_layout_executor_report(executor_result)
    if record.layout_executor_report["errors"]:
        raise ValueError("; ".join(record.layout_executor_report["errors"]))


def _legacy_layout_executor_report(reason: str) -> dict[str, Any]:
    return {
        "used": False,
        "fallbackUsed": True,
        "fallbackReason": reason,
        "writtenBlocks": None,
        "writtenImages": None,
        "degradedImages": None,
        "imageRows": None,
        "pairedImages": None,
        "writtenTables": None,
        "tableRows": None,
        "warnings": [f"legacy fallback used: {reason}"],
        "errors": [],
    }


def append_legacy_fallback_content(
    container,
    sections: SectionList,
    image_files: list[Path],
    metadata: dict | None = None,
) -> None:
    """
    Legacy fallback only.

    Normal generation must use preview_layout_plan + layout_executor.
    This path is reserved for compatibility when preview_layout_plan is missing.
    """
    append_report_content(container, sections, image_files, metadata)


def _failed_layout_executor_report(error: str) -> dict[str, Any]:
    return {
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
        "errors": [error],
    }


def _normalize_layout_executor_report(result: dict[str, Any] | None) -> dict[str, Any]:
    body = dict(result or {})
    return {
        "used": bool(body.get("used")),
        "fallbackUsed": bool(body.get("fallbackUsed")),
        "fallbackReason": body.get("fallbackReason"),
        "writtenBlocks": body.get("writtenBlocks"),
        "writtenImages": body.get("writtenImages"),
        "degradedImages": body.get("degradedImages"),
        "imageRows": body.get("imageRows"),
        "pairedImages": body.get("pairedImages"),
        "writtenTables": body.get("writtenTables"),
        "tableRows": body.get("tableRows"),
        "warnings": list(body.get("warnings") or []),
        "errors": list(body.get("errors") or []),
    }


def get_selected_preview_layout_plan(record: TaskRecord) -> dict[str, Any] | None:
    if record.layout_plan_source == "ai" and isinstance(record.adopted_ai_layout_plan, dict):
        layout_plan = record.adopted_ai_layout_plan
    else:
        layout_plan = record.preview_layout_plan if isinstance(record.preview_layout_plan, dict) else None
    if not table_feature_enabled():
        return strip_table_blocks_from_layout_plan(layout_plan)
    return _merge_manual_tables_into_layout_plan(layout_plan, record.manual_tables)


def get_effective_preview_layout_plan(record: TaskRecord) -> dict[str, Any] | None:
    layout_plan = get_selected_preview_layout_plan(record)
    if layout_plan is None:
        return None
    if not table_feature_enabled():
        return strip_table_blocks_from_layout_plan(layout_plan)
    return _apply_table_controls_to_layout_plan(
        layout_plan,
        record.table_edits,
        record.table_selection,
        strict=False,
    )


def _apply_table_controls_to_layout_plan(
    layout_plan: dict[str, Any],
    table_edits: dict[str, list[list[str]]] | None,
    table_selection: dict[str, bool] | None,
    strict: bool = True,
) -> dict[str, Any]:
    return apply_table_selection_to_layout_plan(
        apply_table_edits_to_layout_plan(layout_plan, table_edits, strict=strict),
        table_selection,
        strict=strict,
    )


def _merge_manual_tables_into_layout_plan(
    layout_plan: dict[str, Any] | None,
    manual_tables: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not isinstance(layout_plan, dict):
        return None
    copied = deepcopy(layout_plan)
    if not manual_tables:
        _assign_table_ids(copied)
        return copied

    normalized_manual_tables = [
        _normalize_manual_table(table)
        for table in manual_tables
        if isinstance(table, dict)
    ]
    selected_manual_tables = normalized_manual_tables
    if not normalized_manual_tables:
        _assign_table_ids(copied)
        return copied

    sections = copied.get("sections")
    if not isinstance(sections, list) or not sections:
        copied["sections"] = [{"key": "manual_section", "title": "实验结果", "blocks": selected_manual_tables}]
        _assign_table_ids(copied)
        return copied

    target_section = None
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        if "实验结果" in title:
            target_section = section
            break
    if target_section is None:
        target_section = sections[-1] if isinstance(sections[-1], dict) else None
    if target_section is None:
        copied["sections"] = [{"key": "manual_section", "title": "实验结果", "blocks": selected_manual_tables}]
    else:
        blocks = target_section.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
        target_section["blocks"] = list(blocks) + selected_manual_tables
    _assign_table_ids(copied)
    return copied


def build_table_audit_report(
    record: TaskRecord,
    effective_layout_plan: dict[str, Any] | None = None,
    executor_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not table_feature_enabled():
        executor = _normalize_layout_executor_report(executor_report)
        return {
            "plannedTables": [],
            "layoutPlanSource": str(record.layout_plan_source or "rule"),
            "summary": {
                "plannedCount": 0,
                "selectedCount": 0,
                "unselectedCount": 0,
                "editedCount": 0,
                "manualCount": 0,
                "writtenTables": int(executor.get("writtenTables") or 0),
                "tableRows": int(executor.get("tableRows") or 0),
                "legacyFallback": bool(executor.get("fallbackUsed")),
                "layoutPlanSource": str(record.layout_plan_source or "rule"),
                "disabled": True,
            },
            "warnings": list(executor.get("warnings") or []),
            "errors": list(executor.get("errors") or []),
        }
    original_layout_plan = get_selected_preview_layout_plan(record) or (
        record.preview_layout_plan if isinstance(record.preview_layout_plan, dict) else None
    )
    planned_tables = extract_table_preview_summary(original_layout_plan, record.table_selection, record.table_edits)
    effective_table_ids = {
        str(item.get("tableId") or "").strip()
        for item in extract_table_preview_summary(effective_layout_plan)
        if str(item.get("tableId") or "").strip()
    }
    executor = _normalize_layout_executor_report(executor_report)
    legacy_fallback = bool(executor.get("fallbackUsed"))
    executor_errors = list(executor.get("errors") or [])

    audited_tables: list[dict[str, Any]] = []
    for item in planned_tables:
        table_id = str(item.get("tableId") or "").strip()
        selected = bool(item.get("selected"))
        edited = bool(item.get("edited"))
        status = "selected"
        if legacy_fallback:
            status = "legacy_fallback"
        elif not selected:
            status = "user_unselected"
        elif table_id and table_id not in effective_table_ids:
            status = "filtered_by_selection"
        elif executor_errors:
            status = "executor_error"
        audited_item = dict(item)
        audited_item["selected"] = selected
        audited_item["edited"] = edited
        audited_item["status"] = status
        audited_item["source"] = str(item.get("source") or "planned")
        audited_tables.append(audited_item)

    return {
        "plannedTables": audited_tables,
        "layoutPlanSource": str(record.layout_plan_source or "rule"),
        "summary": {
            "plannedCount": len(audited_tables),
            "selectedCount": sum(1 for item in audited_tables if item.get("selected")),
            "unselectedCount": sum(1 for item in audited_tables if not item.get("selected")),
            "editedCount": sum(1 for item in audited_tables if item.get("edited")),
            "manualCount": sum(1 for item in audited_tables if item.get("source") == "manual"),
            "writtenTables": int(executor.get("writtenTables") or 0),
            "tableRows": int(executor.get("tableRows") or 0),
            "legacyFallback": legacy_fallback,
            "layoutPlanSource": str(record.layout_plan_source or "rule"),
        },
        "warnings": list(executor.get("warnings") or []),
        "errors": executor_errors,
    }


def build_report_preview(record: TaskRecord) -> dict:
    experiment_config = load_experiment_config("plc")
    sections = experiment_config.default_sections
    image_plan = build_image_plan(
        record.image_files,
        record.metadata,
        experiment_config,
        image_plan_overrides=record.image_plan_overrides,
    )
    template_info = _preview_template_info(record)
    guide_text = _preview_guide_text(record)
    report_text = _preview_report_text(record)
    preview = {
        "experimentType": experiment_config.experiment_type,
        "experimentTypeName": experiment_config.display_name,
        "experimentName": str(record.metadata.get("experimentNo") or "").strip(),
        "sections": _sections_with_images(sections, image_plan),
        "imagePlan": image_plan,
        "insertedImageCount": sum(1 for image in image_plan if image.get("type") != "skip"),
        "template": template_info,
        "rejectedImages": [dict(image) for image in image_plan if str(image.get("reviewLevel") or "") == "reject"],
        "warnings": _preview_image_warnings(image_plan),
        "layoutPlanSource": str(record.layout_plan_source or "rule"),
    }
    record.preview_layout_plan = build_preview_layout_plan(
        preview,
        image_plan=image_plan,
        experiment_config=experiment_config,
        guide_text=guide_text,
        report_text=report_text,
    )
    preview["tablePlan"] = [] if not table_feature_enabled() else extract_table_preview_summary(
        get_selected_preview_layout_plan(record) or record.preview_layout_plan,
        record.table_selection,
        record.table_edits,
    )
    try:
        record.ai_layout_plan_report = generate_ai_layout_plan_candidate(
            metadata=record.metadata,
            experiment_type=str(experiment_config.experiment_type or "plc"),
            guide_text=guide_text,
            report_text=report_text,
            image_plan=image_plan,
            table_plan=preview["tablePlan"],
            current_layout_plan=record.preview_layout_plan,
        )
    except Exception as exc:
        logger.warning("ai planner shadow mode failed task_id=%s", record.task_id, exc_info=True)
        record.ai_layout_plan_report = {
            "enabled": True,
            "ok": False,
            "candidatePlan": None,
            "validation": None,
            "comparison": None,
            "summary": None,
            "error": f"AI planner failed: {exc}",
        }
    record.preview_data = preview
    refresh_preview_runtime_state(record)
    preview = record.preview_data
    return preview


def build_validated_layout_plan(preview: dict[str, Any]) -> dict[str, Any] | None:
    try:
        layout_plan = build_preview_layout_plan(preview)
        logger.debug(
            "preview layout plan validated sections=%s",
            len(layout_plan.get("sections") or []),
        )
        return layout_plan
    except Exception:
        logger.warning("preview layout plan validation failed", exc_info=True)
        return None


def validate_preview_layout_plan(preview: dict[str, Any]) -> None:
    build_validated_layout_plan(preview)


def build_preview_layout_plan(
    preview_data: dict[str, Any],
    image_plan: list[dict[str, Any]] | None = None,
    experiment_config: Any | None = None,
    guide_text: str = "",
    report_text: str = "",
) -> dict[str, Any]:
    preview = dict(preview_data)
    if image_plan is not None:
        preview["imagePlan"] = image_plan
    layout_plan = build_layout_plan_from_preview(preview)
    if table_feature_enabled():
        layout_plan = inject_planned_tables(
            layout_plan,
            experiment_type=str((experiment_config.experiment_type if experiment_config is not None else preview.get("experimentType")) or "plc"),
            guide_text=guide_text,
            report_text=report_text,
            image_plan=preview.get("imagePlan"),
        )
    else:
        layout_plan = strip_table_blocks_from_layout_plan(layout_plan) or layout_plan
    _assign_table_ids(layout_plan)
    validate_layout_plan(layout_plan, _valid_preview_image_indices(preview))
    return layout_plan


def extract_table_preview_summary(
    layout_plan: dict[str, Any] | None,
    table_selection: dict[str, bool] | None = None,
    table_edits: dict[str, list[list[str]]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(layout_plan, dict):
        return []
    _assign_table_ids(layout_plan)
    summaries: list[dict[str, Any]] = []
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_key = str(section.get("key") or "").strip()
        section_title = str(section.get("title") or "").strip()
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            schema_name = str(block.get("schema") or "").strip()
            if not schema_name:
                continue
            try:
                schema = get_table_schema(schema_name)
            except KeyError:
                continue
            rows = (block.get("data") or {}).get("rows") if isinstance(block.get("data"), dict) else []
            row_list = rows if isinstance(rows, list) else []
            table_id = str(block.get("tableId") or "").strip()
            edited_rows = _edited_rows_for_table(table_id, table_edits)
            current_rows = edited_rows if edited_rows is not None else _normalize_table_rows(row_list)
            summaries.append(
                {
                    "tableId": table_id,
                    "sectionKey": section_key,
                    "sectionTitle": section_title,
                    "schema": schema_name,
                    "title": str(block.get("title") or schema.get("title") or "").strip(),
                    "rowCount": len(current_rows),
                    "columnCount": len(_table_headers_for_block(block, schema)),
                    "headers": _table_headers_for_block(block, schema),
                    "rows": current_rows,
                    "edited": edited_rows is not None,
                    "autoPlanned": str(block.get("source") or "").strip() == "table_planner" or "source" not in block,
                    "selected": _table_selected(table_id, table_selection),
                    "source": str(block.get("source") or "planned").strip() or "planned",
                }
            )
    return summaries


def refresh_preview_runtime_state(record: TaskRecord) -> None:
    if not isinstance(record.preview_data, dict):
        return
    selected_plan = get_selected_preview_layout_plan(record) or record.preview_layout_plan
    record.preview_data["layoutPlanSource"] = str(record.layout_plan_source or "rule")
    record.preview_data["sections"] = build_preview_sections_from_layout_plan(
        selected_plan,
        record.preview_data.get("imagePlan") if isinstance(record.preview_data.get("imagePlan"), list) else [],
    )
    record.preview_data["tablePlan"] = extract_table_preview_summary(
        selected_plan,
        record.table_selection,
        record.table_edits,
    )
    record.preview_data["aiPlannerPreview"] = build_ai_planner_preview_summary(record.ai_layout_plan_report)


def adopt_ai_preview_layout_plan(record: TaskRecord) -> dict[str, Any]:
    report = record.ai_layout_plan_report if isinstance(record.ai_layout_plan_report, dict) else None
    if not report:
        raise ValueError("AI layout plan is unavailable")
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    if validation and not bool(validation.get("passed")):
        errors = list(validation.get("errors") or [])
        detail = "; ".join(str(item).strip() for item in errors if str(item).strip()) or str(report.get("error") or "AI layout plan failed validation")
        raise ValueError(detail)
    candidate = report.get("candidatePlan")
    if not isinstance(candidate, dict):
        raise ValueError("AI layout plan candidate is unavailable")

    normalized = deepcopy(candidate)
    _normalize_ai_candidate_layout_plan(normalized, record)
    valid_image_indices = _valid_preview_image_indices(record.preview_data or {})
    validate_layout_plan(normalized, valid_image_indices)
    _validate_ai_candidate_references(normalized, record)
    _assign_table_ids(normalized)

    record.adopted_ai_layout_plan = normalized
    record.layout_plan_source = "ai"
    refresh_preview_runtime_state(record)
    return normalized


def restore_rule_preview_layout_plan(record: TaskRecord) -> None:
    record.layout_plan_source = "rule"
    record.adopted_ai_layout_plan = None
    refresh_preview_runtime_state(record)


def apply_table_edits_to_layout_plan(
    layout_plan: dict[str, Any],
    table_edits: dict[str, list[list[str]]] | None,
    strict: bool = True,
) -> dict[str, Any]:
    if not isinstance(layout_plan, dict):
        raise ValueError("layout plan is required")
    copied = deepcopy(layout_plan)
    _assign_table_ids(copied)
    if not table_edits:
        return copied

    valid_table_ids = {
        str(item.get("tableId") or "").strip()
        for item in extract_table_preview_summary(copied)
        if str(item.get("tableId") or "").strip()
    }
    unknown_table_ids = sorted(table_id for table_id in table_edits.keys() if table_id not in valid_table_ids)
    if unknown_table_ids and not strict:
        table_edits = {
            table_id: rows
            for table_id, rows in table_edits.items()
            if table_id in valid_table_ids
        }
        unknown_table_ids = []
    if unknown_table_ids:
        raise ValueError(f"Unknown tableId: {', '.join(unknown_table_ids)}")

    for section in copied.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            table_id = str(block.get("tableId") or "").strip()
            if table_id not in table_edits:
                continue
            rows = _validate_and_normalize_table_edit_rows(block, table_edits[table_id])
            data = dict(block.get("data") or {})
            data["rows"] = rows
            block["data"] = data
    return copied


def apply_table_selection_to_layout_plan(
    layout_plan: dict[str, Any],
    table_selection: dict[str, bool] | None,
    strict: bool = True,
) -> dict[str, Any]:
    if not isinstance(layout_plan, dict):
        raise ValueError("layout plan is required")
    if not table_selection:
        copied = deepcopy(layout_plan)
        _assign_table_ids(copied)
        return copied

    _assign_table_ids(layout_plan)
    valid_table_ids = {
        str(item.get("tableId") or "").strip()
        for item in extract_table_preview_summary(layout_plan)
        if str(item.get("tableId") or "").strip()
    }
    unknown_table_ids = sorted(table_id for table_id in table_selection.keys() if table_id not in valid_table_ids)
    if unknown_table_ids and not strict:
        table_selection = {
            table_id: selected
            for table_id, selected in table_selection.items()
            if table_id in valid_table_ids
        }
        unknown_table_ids = []
    if unknown_table_ids:
        raise ValueError(f"Unknown tableId: {', '.join(unknown_table_ids)}")

    effective_plan = deepcopy(layout_plan)
    _assign_table_ids(effective_plan)
    for section in effective_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        section["blocks"] = [
            block
            for block in blocks
            if not (
                isinstance(block, dict)
                and block.get("type") == "table"
                and not _table_selected(str(block.get("tableId") or "").strip(), table_selection)
            )
        ]
    return effective_plan


def _preview_guide_text(record: TaskRecord) -> str:
    if record.guide_file is None:
        return ""
    try:
        return extract_guide_text(record.guide_file, max_chars=MAX_TEXT_CHARS)
    except Exception:
        logger.warning("preview guide extraction failed task_id=%s", record.task_id, exc_info=True)
        return ""


def _preview_report_text(record: TaskRecord) -> str:
    if record.report_file is None or record.report_file.suffix.lower() != ".docx":
        return ""
    try:
        return extract_report_text(record.report_file)
    except Exception:
        logger.warning("preview report extraction failed task_id=%s", record.task_id, exc_info=True)
        return ""


def _build_execution_layout_plan(layout_plan: dict[str, Any], sections: SectionList) -> dict[str, Any]:
    execution_plan = deepcopy(layout_plan)
    existing_sections = execution_plan.get("sections")
    if not isinstance(existing_sections, list):
        existing_sections = []
        execution_plan["sections"] = existing_sections

    by_title = {
        str(section.get("title") or "").strip(): section
        for section in existing_sections
        if isinstance(section, dict) and str(section.get("title") or "").strip()
    }
    ordered_sections: list[dict[str, Any]] = []
    for section_index, (title, lines) in enumerate(sections, start=1):
        normalized_title = str(title or "").strip()
        if not normalized_title:
            continue
        section = by_title.get(normalized_title)
        if section is None:
            section = {"key": f"section_{section_index}", "title": normalized_title, "blocks": []}
        existing_blocks = section.get("blocks")
        if not isinstance(existing_blocks, list):
            existing_blocks = []
        retained_blocks = [block for block in existing_blocks if isinstance(block, dict) and block.get("type") != "paragraph"]
        paragraph_blocks = [
            {"type": "paragraph", "content": str(line).strip()}
            for line in lines
            if str(line).strip()
        ]
        section["blocks"] = paragraph_blocks + retained_blocks
        ordered_sections.append(section)

    known_titles = {str(title or "").strip() for title, _ in sections if str(title or "").strip()}
    for section in existing_sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        if title and title not in known_titles:
            ordered_sections.append(section)

    execution_plan["sections"] = ordered_sections
    _assign_table_ids(execution_plan)
    return execution_plan


def _assign_table_ids(layout_plan: dict[str, Any]) -> None:
    table_index = 0
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            table_id = str(block.get("tableId") or "").strip()
            if table_id:
                continue
            block["tableId"] = f"table_{table_index}"
            table_index += 1


def _table_selected(table_id: str, table_selection: dict[str, bool] | None) -> bool:
    if not table_id or not isinstance(table_selection, dict):
        return True
    return bool(table_selection.get(table_id, True))


def _edited_rows_for_table(
    table_id: str,
    table_edits: dict[str, list[list[str]]] | None,
) -> list[list[str]] | None:
    if not table_id or not isinstance(table_edits, dict) or table_id not in table_edits:
        return None
    return _normalize_table_rows(table_edits.get(table_id) or [])


def _normalize_table_rows(rows: list[Any]) -> list[list[str]]:
    normalized: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        normalized.append([str(cell) for cell in row])
    return normalized


def _table_headers_for_block(block: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if str(block.get("schema") or "").strip() == "custom_table":
        headers = block.get("headers")
        if isinstance(headers, list):
            return [str(header or "").strip() for header in headers]
    return list(schema.get("headers") or [])


def _normalize_manual_table(table: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(table)
    normalized["type"] = "table"
    normalized["schema"] = "custom_table"
    normalized["source"] = "manual"
    normalized["tableId"] = str(normalized.get("tableId") or "").strip()
    normalized["headers"] = [str(header or "").strip() for header in list(normalized.get("headers") or [])]
    data = dict(normalized.get("data") or {})
    data["rows"] = _normalize_table_rows(list(data.get("rows") or []))
    normalized["data"] = data
    normalized["selected"] = bool(normalized.get("selected", True))
    normalized["title"] = str(normalized.get("title") or "自定义表格").strip() or "自定义表格"
    normalized["sectionKey"] = str(normalized.get("sectionKey") or "").strip()
    normalized["sectionTitle"] = str(normalized.get("sectionTitle") or "").strip()
    return normalized


def validate_and_normalize_manual_tables(
    manual_tables: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_tables: list[dict[str, Any]] = []
    for index, table in enumerate(manual_tables or []):
        if not isinstance(table, dict):
            raise ValueError("manualTables entries must be objects")
        normalized = _normalize_manual_table(table)
        if not normalized["tableId"]:
            normalized["tableId"] = f"manual_table_{index}"
        block = {
            "type": "table",
            "schema": "custom_table",
            "headers": list(normalized.get("headers") or []),
            "data": {"rows": _normalize_table_rows((normalized.get("data") or {}).get("rows") or [])},
        }
        errors = validate_table_block(block)
        if errors:
            raise ValueError("; ".join(errors))
        normalized["headers"] = block["headers"]
        normalized["data"] = block["data"]
        normalized_tables.append(normalized)
    return normalized_tables


def _validate_and_normalize_table_edit_rows(block: dict[str, Any], rows: Any) -> list[list[str]]:
    schema_name = str(block.get("schema") or "").strip()
    schema = get_table_schema(schema_name)
    if not isinstance(rows, list):
        raise ValueError(f"Invalid rows for {schema_name}: rows must be a list")
    normalized = _normalize_table_rows(rows)
    headers = _table_headers_for_block(block, schema)
    edit_block = {
        "type": "table",
        "schema": schema_name,
        "data": {"rows": normalized},
    }
    if schema_name == "custom_table":
        edit_block["headers"] = headers
    errors = []
    expected_columns = len(headers)
    if len(normalized) != len(rows):
        errors.append("table rows must be a two-dimensional list")
    for row_index, row in enumerate(normalized):
        if len(row) != expected_columns:
            errors.append(
                f"table row {row_index} column count mismatch: expected {expected_columns}, got {len(row)}"
            )
    if len(normalized) > int(schema.get("max_rows") or 0):
        errors.append(f"table block rows exceed max_rows: {len(normalized)} > {schema.get('max_rows')}")
    errors.extend(validate_table_block(edit_block))
    deduped_errors: list[str] = []
    for error in errors:
        if error not in deduped_errors:
            deduped_errors.append(error)
    if deduped_errors:
        raise ValueError("; ".join(deduped_errors))
    return normalized


def _valid_preview_image_indices(preview: dict[str, Any]) -> set[int]:
    indices: set[int] = set()
    for image in preview.get("imagePlan") or []:
        if not isinstance(image, dict) or image.get("type") == "skip":
            continue
        image_index = _coerce_int(image.get("imageIndex"), -1)
        if image_index >= 0:
            indices.add(image_index)
    return indices


def _valid_preview_image_refs(preview: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for image in preview.get("imagePlan") or []:
        if not isinstance(image, dict) or image.get("type") == "skip":
            continue
        image_index = _coerce_int(image.get("imageIndex"), -1)
        if image_index >= 0:
            refs.add(f"image_{image_index}")
        image_ref = str(image.get("image_ref") or image.get("imageRef") or "").strip()
        if image_ref:
            refs.add(image_ref)
    return refs


def _preview_image_plan_by_index(preview: dict[str, Any]) -> dict[int, dict[str, Any]]:
    items: dict[int, dict[str, Any]] = {}
    for image in preview.get("imagePlan") or []:
        if not isinstance(image, dict):
            continue
        image_index = _coerce_int(image.get("imageIndex"), -1)
        if image_index >= 0:
            items[image_index] = image
    return items


def _normalize_ai_candidate_layout_plan(layout_plan: dict[str, Any], record: TaskRecord) -> None:
    preview = record.preview_data if isinstance(record.preview_data, dict) else {}
    image_plan_by_index = _preview_image_plan_by_index(preview)
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "image":
                continue
            image_index = _coerce_int(block.get("imageIndex"), -1)
            image_info = image_plan_by_index.get(image_index)
            if image_index >= 0 and not str(block.get("image_ref") or "").strip():
                block["image_ref"] = f"image_{image_index}"
            if not str(block.get("caption") or "").strip():
                block["caption"] = _default_image_caption(image_info, image_index)


def _default_image_caption(image_info: dict[str, Any] | None, image_index: int) -> str:
    if isinstance(image_info, dict):
        return get_safe_image_caption(image_info, image_info)
    return f"实验图片 {image_index + 1}"


def _validate_ai_candidate_references(layout_plan: dict[str, Any], record: TaskRecord) -> None:
    preview = record.preview_data if isinstance(record.preview_data, dict) else {}
    valid_image_indices = _valid_preview_image_indices(preview)
    valid_image_refs = _valid_preview_image_refs(preview)
    image_plan_by_index = _preview_image_plan_by_index(preview)
    for section_index, section in enumerate(layout_plan.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for block_index, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            image_index = _coerce_int(block.get("imageIndex"), -1)
            image_ref = str(block.get("image_ref") or "").strip()
            if image_index < 0 or image_index not in valid_image_indices:
                raise ValueError(f"AI layout plan references unknown imageIndex: {image_index}")
            if image_ref and image_ref not in valid_image_refs:
                raise ValueError(f"AI layout plan references unknown image_ref: {image_ref}")
            image_info = image_plan_by_index.get(image_index) or {}
            review_level = str(image_info.get("reviewLevel") or image_info.get("review_level") or "").strip()
            if review_level == "reject" or image_info.get("type") == "skip":
                raise ValueError(f"AI layout plan references rejected image: image_{image_index}")


def _preview_template_info(record: TaskRecord) -> dict:
    if record.report_file is None or record.report_file.suffix.lower() != ".docx":
        return {
            "templateId": "unknown",
            "displayName": "未识别模板",
            "confidence": 0,
            "bodyLocation": "未识别正文区域",
        }
    template = resolve_report_template(Document(record.report_file))
    return {
        "templateId": template.template_id,
        "displayName": template.display_name,
        "confidence": template.confidence,
        "bodyLocation": template.body_location,
    }


def build_image_plan(
    image_files: list[Path],
    metadata: dict | None = None,
    experiment_config: Any | None = None,
    image_plan_overrides: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    metas = image_metas_by_filename((metadata or {}).get("imageMetas"))
    config = experiment_config or load_experiment_config("plc")
    experiment_type = str((metadata or {}).get("experimentType") or config.experiment_type or "plc")
    for image_index, image_file in enumerate(image_files):
        meta = metas.get(image_file.name, {})
        try:
            recognition = _recognize_image_for_plan(
                image_file,
                meta,
                experiment_type=experiment_type,
                image_ref=f"image_{image_index}",
                image_index=image_index,
            )
        except Exception as exc:
            logger.warning("image recognition failed image=%s", image_file, exc_info=True)
            recognition = {
                "schema_version": "image-plan.v1",
                "experiment_type": "generic",
                "image_ref": f"image_{image_index}",
                "imageIndex": image_index,
                "filename": image_file.name,
                "category": "unknown",
                "category_cn": "待确认",
                "confidence": 0.0,
                "review_level": "reject",
                "review_reasons": ["IMAGE_RECOGNITION_FAILED"],
                "quality": {"readable": False, "needs_review": True},
                "suggested": {"insert_section": "实验结果", "caption": "待确认图片", "size_policy": "other"},
                "features": {},
                "score_detail": {},
                "error": {"code": "IMAGE_RECOGNITION_FAILED", "message": str(exc)},
            }
        plan.append(
            adapt_recognition_to_image_plan(
                image_index=image_index,
                filename=image_file.name,
                recognition=recognition,
                meta=meta,
                experiment_config=config,
            )
        )
    plan = _apply_image_plan_overrides(plan, image_plan_overrides, config.default_sections)
    return sorted(plan, key=lambda item: (str(item.get("section") or ""), int(item.get("sortOrder") or 0)))


def _apply_image_plan_overrides(
    image_plan: list[dict[str, Any]],
    image_plan_overrides: dict[str, dict[str, Any]] | None,
    valid_sections: list[str],
) -> list[dict[str, Any]]:
    if not image_plan_overrides:
        return image_plan

    normalized_sections = {str(section).strip(): str(section).strip() for section in valid_sections if str(section).strip()}
    next_plan: list[dict[str, Any]] = []
    for image in image_plan:
        if not isinstance(image, dict):
            continue
        image_ref = str(image.get("image_ref") or image.get("imageRef") or f"image_{image.get('imageIndex')}").strip()
        override = image_plan_overrides.get(image_ref) if isinstance(image_plan_overrides, dict) else None
        if not isinstance(override, dict):
            next_plan.append(image)
            continue
        updated = dict(image)
        if str(updated.get("reviewLevel") or updated.get("review_level") or "").strip() == "reject" or updated.get("type") == "skip":
            next_plan.append(updated)
            continue
        category = str(override.get("category") or updated.get("category") or "").strip()
        if category:
            updated["category"] = category
            updated["categoryCn"] = _category_display_name(category)
            updated["category_cn"] = _category_display_name(category)
        caption = normalize_caption_text(override.get("caption"))
        if caption:
            updated["caption"] = caption
            updated["suggestedCaption"] = caption
            suggested = dict(updated.get("suggested") or {})
            suggested["caption"] = caption
            updated["suggested"] = suggested
        insert_section = str(override.get("insertSection") or "").strip()
        if insert_section:
            resolved_section = normalized_sections.get(insert_section, insert_section)
            updated["section"] = resolved_section
            updated["insertSection"] = resolved_section
            suggested = dict(updated.get("suggested") or {})
            suggested["insert_section"] = resolved_section
            updated["suggested"] = suggested
        size_policy = str(override.get("sizePolicy") or "").strip()
        if size_policy:
            updated["sizePolicy"] = size_policy
            suggested = dict(updated.get("suggested") or {})
            suggested["size_policy"] = size_policy
            updated["suggested"] = suggested
        updated["needsReview"] = False
        updated["reviewLevel"] = "ok"
        updated["review_level"] = "ok"
        review_reasons = list(updated.get("reviewReasons") or updated.get("review_reasons") or [])
        if "user_override" not in review_reasons:
            review_reasons.append("user_override")
        updated["reviewReasons"] = review_reasons
        updated["review_reasons"] = review_reasons
        quality = dict(updated.get("quality") or {})
        quality["needs_review"] = False
        updated["quality"] = quality
        updated["overridden"] = True
        next_plan.append(updated)
    return next_plan


def validate_and_normalize_image_plan_overrides(
    overrides: dict[str, Any] | None,
    preview_data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    preview = preview_data if isinstance(preview_data, dict) else {}
    image_plan = preview.get("imagePlan") if isinstance(preview.get("imagePlan"), list) else []
    valid_by_ref: dict[str, dict[str, Any]] = {}
    for image in image_plan:
        if not isinstance(image, dict):
            continue
        image_ref = str(image.get("image_ref") or image.get("imageRef") or f"image_{image.get('imageIndex')}").strip()
        if image_ref:
            valid_by_ref[image_ref] = image
    valid_sections = {
        str(section.get("title") or "").strip()
        for section in (preview.get("sections") or [])
        if isinstance(section, dict) and str(section.get("title") or "").strip()
    }
    normalized: dict[str, dict[str, Any]] = {}
    for raw_ref, raw_override in overrides.items():
        image_ref = str(raw_ref or "").strip()
        if not image_ref or image_ref not in valid_by_ref:
            raise ValueError(f"Unknown image_ref: {image_ref}")
        if not isinstance(raw_override, dict):
            raise ValueError(f"Override for {image_ref} must be an object")
        item: dict[str, Any] = {}
        if "category" in raw_override:
            category = str(raw_override.get("category") or "").strip()
            if category not in IMAGE_OVERRIDE_CATEGORIES:
                raise ValueError(f"Invalid image category: {category}")
            item["category"] = category
        if "caption" in raw_override:
            item["caption"] = normalize_caption_text(raw_override.get("caption"))
        if "insertSection" in raw_override:
            insert_section = str(raw_override.get("insertSection") or "").strip()
            if insert_section not in valid_sections:
                raise ValueError(f"Invalid insertSection: {insert_section}")
            item["insertSection"] = insert_section
        if "sizePolicy" in raw_override:
            size_policy = str(raw_override.get("sizePolicy") or "").strip()
            if size_policy not in IMAGE_OVERRIDE_SIZE_POLICIES:
                raise ValueError(f"Invalid sizePolicy: {size_policy}")
            item["sizePolicy"] = size_policy
        normalized[image_ref] = item
    return normalized


def _category_display_name(category: str) -> str:
    normalized = str(category or "").strip()
    if not normalized:
        return "待确认"
    return str(CATEGORY_DISPLAY.get(normalized) or CATEGORY_DISPLAY.get("unknown") or "待确认")


def _sections_with_images(section_titles: list[str], image_plan: list[dict[str, str | bool | int]]) -> list[dict]:
    return [
        {
            "title": title,
            "paragraphs": [],
            "images": [
                image
                for image in image_plan
                if image.get("section") == title and image.get("type") != "skip"
            ],
        }
        for title in section_titles
    ]


def build_preview_sections_from_layout_plan(
    layout_plan: dict[str, Any] | None,
    image_plan: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(layout_plan, dict):
        return []

    image_by_index: dict[int, dict[str, Any]] = {}
    for image in image_plan or []:
        if not isinstance(image, dict):
            continue
        image_index = _coerce_int(image.get("imageIndex"), -1)
        if image_index >= 0:
            image_by_index[image_index] = image

    sections: list[dict[str, Any]] = []
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        paragraphs: list[str] = []
        images: list[dict[str, Any]] = []
        block_count = 0
        image_count = 0
        table_count = 0
        warning_count = 0
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            block_count += 1
            block_type = str(block.get("type") or "").strip()
            if block_type == "paragraph":
                content = str(block.get("content") or "").strip()
                if content:
                    paragraphs.append(content)
            elif block_type == "image":
                image_index = _coerce_int(block.get("imageIndex"), -1)
                image_info = image_by_index.get(image_index, {})
                image_entry = dict(image_info)
                image_entry["imageIndex"] = image_index
                image_entry["section"] = title
                image_entry["caption"] = get_safe_image_caption(block, image_info)
                image_entry["type"] = str(image_info.get("type") or block.get("imageType") or "").strip()
                image_entry["recognized"] = bool(image_info.get("recognized", True))
                images.append(image_entry)
                image_count += 1
            elif block_type == "table":
                table_count += 1
            elif block_type == "warning":
                warning_count += 1
        sections.append(
            {
                "key": str(section.get("key") or "").strip(),
                "title": title,
                "paragraphs": paragraphs,
                "images": images,
                "blockCount": block_count,
                "imageCount": image_count,
                "tableCount": table_count,
                "warningCount": warning_count,
            }
        )
    return sections


def _recognize_image_for_plan(
    path: Path,
    meta: dict[str, Any],
    *,
    experiment_type: str,
    image_ref: str,
    image_index: int,
) -> dict[str, Any]:
    result = image_recognizer.recognize_image_file(
        path,
        experiment_type=experiment_type,
        image_ref=image_ref,
        image_index=image_index,
    )
    return result if isinstance(result, dict) else {}


def _preview_image_warnings(image_plan: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for image in image_plan:
        if not isinstance(image, dict):
            continue
        filename = str(image.get("filename") or f"image_{image.get('imageIndex')}").strip()
        review_level = str(image.get("reviewLevel") or image.get("review_level") or "").strip()
        reasons = list(image.get("reviewReasons") or image.get("review_reasons") or [])
        if review_level == "review":
            reason_text = ", ".join(str(item).strip() for item in reasons if str(item).strip()) or "manual review required"
            warnings.append(f"Image needs review: {filename} ({reason_text})")
        elif review_level == "reject":
            reason_text = ", ".join(str(item).strip() for item in reasons if str(item).strip()) or "rejected by recognizer"
            warnings.append(f"Image rejected: {filename} ({reason_text})")
    return warnings


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _header_values(record: TaskRecord, experiment_name: str) -> dict[str, str]:
    metadata = record.metadata
    return {
        "experimentName": experiment_name,
        "studentName": str(metadata.get("studentName") or ""),
        "studentId": str(metadata.get("studentId") or ""),
        "className": str(metadata.get("className") or ""),
        "teacherName": str(metadata.get("teacherName") or metadata.get("instructorName") or ""),
        "courseName": str(metadata.get("courseName") or ""),
        "studentCollege": str(metadata.get("studentCollege") or metadata.get("college") or ""),
        "offeringCollegeLab": _offering_college_lab(metadata),
        "date": _current_date_string(),
    }


def _offering_college_lab(metadata: dict) -> str:
    direct_value = str(metadata.get("offeringCollegeLab") or "").strip()
    if direct_value:
        return direct_value
    parts = [
        str(metadata.get("offeringCollege") or "").strip(),
        str(metadata.get("labName") or metadata.get("laboratory") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _current_date_string() -> str:
    return datetime.now().strftime("%Y年%m月%d日")


def build_report_draft(record: TaskRecord) -> ReportDraft:
    config = LLMConfig.from_env()
    if config is not None:
        experiment_label = infer_experiment_label(
            record.report_file.name if record.report_file else "",
            str(record.metadata.get("experimentNo") or ""),
        )
        full_guide_text = extract_guide_text(record.guide_file, max_chars=None)
        selected_guide_text = select_experiment_section(full_guide_text, experiment_label)
        guide_text = selected_guide_text.strip()[:MAX_TEXT_CHARS]
        report_text = extract_report_text(record.report_file)
        metadata = dict(record.metadata)
        metadata["resolvedExperimentNo"] = experiment_label
        logger.info(
            "experiment context task_id=%s user_experiment=%s resolved=%s guide_chars=%s selected_guide_chars=%s selected_preview=%r",
            record.task_id,
            record.metadata.get("experimentNo"),
            experiment_label,
            len(full_guide_text),
            len(selected_guide_text),
            selected_guide_text[:180],
        )
        return generate_report_sections(
            config=config,
            metadata=metadata,
            guide_text=guide_text,
            report_text=report_text,
            image_names=[path.name for path in record.image_files],
        )
    experiment_name = str(record.metadata.get("experimentNo") or "本次实验").strip()
    return ReportDraft(experiment_name=experiment_name, sections=build_fallback_sections(record))


def build_fallback_sections(record: TaskRecord) -> SectionList:
    config = load_experiment_config("plc")
    metadata = record.metadata
    experiment_no = metadata.get("experimentNo") or "本次实验"
    student_name = metadata.get("studentName") or "未填写"
    student_id = metadata.get("studentId") or "未填写"
    class_name = metadata.get("className") or "未填写"
    guide_name = record.guide_file.name if record.guide_file else "未上传"
    image_groups = classify_images([path.name for path in record.image_files])

    image_lines = _fallback_image_summary_lines(image_groups, config)
    context = {
        "experimentNo": str(experiment_no),
        "studentName": str(student_name),
        "studentId": str(student_id),
        "className": str(class_name),
        "guideName": str(guide_name),
    }
    sections: SectionList = []
    for section in config.fallback_sections:
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        if section.get("content") == "image_summary":
            sections.append((title, image_lines))
            continue
        paragraphs = [
            _format_fallback_template(str(template), context)
            for template in section.get("paragraphTemplates", [])
            if str(template).strip()
        ]
        sections.append((title, paragraphs))
    return sections


def _fallback_image_summary_lines(image_groups: dict[str, list[str]], config) -> list[str]:
    image_lines = []
    labels = config.fallback_image_labels
    for key, label in labels.items():
        files = image_groups.get(key, [])
        if files:
            image_lines.append(f"{label}：{'、'.join(files)}")
    if not image_lines:
        image_lines.append(config.fallback_no_images_text)
    return image_lines


def _format_fallback_template(template: str, context: dict[str, str]) -> str:
    try:
        return template.format(**context)
    except (KeyError, ValueError):
        return template


def append_report_content(container, sections: SectionList, image_files: list[Path], metadata: dict | None = None) -> None:
    image_groups = group_images_by_section(image_files, (metadata or {}).get("imageMetas"))
    container.add_paragraph("")
    for title, lines in sections:
        heading = container.add_paragraph()
        heading.paragraph_format.line_spacing = 1.15
        heading.paragraph_format.space_after = Pt(3)
        heading_run = heading.add_run(title)
        heading_run.bold = True
        _set_run_font(heading_run)

        for line in lines:
            paragraph = container.add_paragraph(line)
            paragraph.paragraph_format.line_spacing = 1.15
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.first_line_indent = Cm(0.74)
            for run in paragraph.runs:
                _set_run_font(run)

        append_images_to_container(container, _images_for_section_title(image_groups, title))


def _images_for_section_title(image_groups: dict[str, list[ImagePlacement]], title: str) -> list[ImagePlacement]:
    if title.startswith("四、"):
        return image_groups.get(SECTION_OPERATION, [])
    if title.startswith("五、"):
        return image_groups.get(SECTION_PROGRAM, [])
    if title.startswith("六、"):
        return image_groups.get(SECTION_RESULT, [])
    return image_groups.get(title, [])


def append_images_to_container(container, image_files: list[ImagePlacement]) -> None:
    caption_index = 1
    for image_info in image_files:
        try:
            paragraph = container.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run()
            run.add_picture(str(image_info.path), width=Cm(image_width_cm(image_info.type)))

            caption = container.add_paragraph(f"图 {caption_index} {image_info.caption}")
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in caption.runs:
                _set_caption_font(run)
            caption_index += 1
        except Exception:
            paragraph = container.add_paragraph(f"{image_info.caption}：{image_info.path.name}（图片文件已接收，当前无法直接插入）")
            for run in paragraph.runs:
                _set_run_font(run)


def _set_run_font(run) -> None:
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(10.5)


def _set_caption_font(run) -> None:
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(9)
