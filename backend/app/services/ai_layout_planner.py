from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from requests import HTTPError, RequestException

from .layout_validator import LayoutValidationError, validate_layout_plan
from .llm_writer import LLMConfig


logger = logging.getLogger("report-backend.ai-layout-planner")


def generate_ai_layout_plan_candidate(
    *,
    metadata: dict,
    experiment_type: str,
    guide_text: str,
    report_text: str,
    image_plan: list,
    table_plan: list,
    current_layout_plan: dict,
) -> dict:
    config = LLMConfig.from_env()
    if config is None:
        return {
            "enabled": False,
            "ok": False,
            "candidatePlan": None,
            "validation": None,
            "comparison": None,
            "summary": None,
            "error": "LLM planner disabled or not configured",
        }

    try:
        payload = {
            "model": config.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {
                    "role": "user",
                    "content": _user_prompt(
                        metadata=metadata,
                        experiment_type=experiment_type,
                        guide_text=guide_text,
                        report_text=report_text,
                        image_plan=image_plan,
                        table_plan=table_plan,
                        current_layout_plan=current_layout_plan,
                    ),
                },
            ],
        }
        response = requests.post(
            f"{config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=config.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        candidate = normalize_ai_layout_plan_candidate(_parse_json_content(content))
        validation = _validate_candidate(candidate, image_plan)
        comparison = compare_layout_plans(current_layout_plan, candidate) if validation["passed"] else None
        summary = summarize_ai_layout_plan(candidate) if validation["passed"] else None
        return {
            "enabled": True,
            "ok": bool(validation["passed"]),
            "candidatePlan": candidate,
            "validation": validation,
            "comparison": comparison,
            "summary": summary,
            "error": None if validation["passed"] else "; ".join(validation["errors"]),
        }
    except (RequestException, HTTPError) as exc:
        logger.warning("ai layout planner request failed", exc_info=True)
        return {
            "enabled": True,
            "ok": False,
            "candidatePlan": None,
            "validation": None,
            "comparison": None,
            "summary": None,
            "error": f"AI planner request failed: {exc}",
        }
    except Exception as exc:
        logger.warning("ai layout planner failed", exc_info=True)
        return {
            "enabled": True,
            "ok": False,
            "candidatePlan": None,
            "validation": None,
            "comparison": None,
            "summary": None,
            "error": f"AI planner failed: {exc}",
        }


def compare_layout_plans(rule_plan: dict, ai_plan: dict) -> dict[str, Any]:
    rule_sections = _sections(rule_plan)
    ai_sections = _sections(ai_plan)
    rule_section_count = len(rule_sections)
    ai_section_count = len(ai_sections)
    rule_image_blocks = _count_blocks(rule_plan, "image")
    ai_image_blocks = _count_blocks(ai_plan, "image")
    rule_table_blocks = _count_blocks(rule_plan, "table")
    ai_table_blocks = _count_blocks(ai_plan, "table")
    rule_warning_blocks = _count_blocks(rule_plan, "warning")
    ai_warning_blocks = _count_blocks(ai_plan, "warning")
    rule_section_titles = _section_titles(rule_sections)
    ai_section_titles = _section_titles(ai_sections)
    rule_table_schemas = _table_schemas(rule_plan)
    ai_table_schemas = _table_schemas(ai_plan)
    rule_image_refs = _image_refs(rule_plan)
    ai_image_refs = _image_refs(ai_plan)
    warnings: list[str] = []
    if rule_section_count != ai_section_count:
        warnings.append("section count differs between rule plan and ai candidate")
    if rule_image_blocks != ai_image_blocks:
        warnings.append("image block count differs between rule plan and ai candidate")
    if rule_table_blocks != ai_table_blocks:
        warnings.append("table block count differs between rule plan and ai candidate")
    if rule_warning_blocks != ai_warning_blocks:
        warnings.append("warning block count differs between rule plan and ai candidate")
    missing_in_ai = [title for title in rule_section_titles if title not in ai_section_titles]
    extra_in_ai = [title for title in ai_section_titles if title not in rule_section_titles]
    if missing_in_ai:
        warnings.append("ai candidate is missing rule-plan sections")
    if extra_in_ai:
        warnings.append("ai candidate adds extra sections")
    return {
        "ruleSectionCount": rule_section_count,
        "aiSectionCount": ai_section_count,
        "ruleImageBlocks": rule_image_blocks,
        "aiImageBlocks": ai_image_blocks,
        "ruleTableBlocks": rule_table_blocks,
        "aiTableBlocks": ai_table_blocks,
        "ruleWarningBlocks": rule_warning_blocks,
        "aiWarningBlocks": ai_warning_blocks,
        "sectionCountDelta": ai_section_count - rule_section_count,
        "imageBlockDelta": ai_image_blocks - rule_image_blocks,
        "tableBlockDelta": ai_table_blocks - rule_table_blocks,
        "warningBlockDelta": ai_warning_blocks - rule_warning_blocks,
        "ruleSectionTitles": rule_section_titles,
        "aiSectionTitles": ai_section_titles,
        "missingInAi": missing_in_ai,
        "extraInAi": extra_in_ai,
        "tableSchemasInRule": rule_table_schemas,
        "tableSchemasInAi": ai_table_schemas,
        "imageRefsInRule": rule_image_refs,
        "imageRefsInAi": ai_image_refs,
        "warnings": warnings,
    }


def summarize_ai_layout_plan(ai_plan: dict) -> dict[str, Any]:
    sections = _sections(ai_plan)
    return {
        "sectionCount": len(sections),
        "blockCount": _count_all_blocks(ai_plan),
        "paragraphBlocks": _count_blocks(ai_plan, "paragraph"),
        "imageBlocks": _count_blocks(ai_plan, "image"),
        "tableBlocks": _count_blocks(ai_plan, "table"),
        "warningBlocks": _count_blocks(ai_plan, "warning"),
        "sectionTitles": _section_titles(sections),
        "tableSchemas": _table_schemas(ai_plan),
        "imageRefs": _image_refs(ai_plan),
    }


def build_ai_planner_preview_summary(ai_layout_plan_report: dict[str, Any] | None) -> dict[str, Any]:
    report = dict(ai_layout_plan_report or {})
    validation = dict(report.get("validation") or {})
    comparison = dict(report.get("comparison") or {})
    enabled = bool(report.get("enabled"))
    ok = bool(report.get("ok"))
    validation_passed = bool(validation.get("passed"))
    error = report.get("error")
    if not enabled:
        status = "disabled"
    elif ok and validation_passed:
        status = "valid"
    elif validation and not validation_passed:
        status = "invalid"
    else:
        status = "failed"
    if not validation_passed:
        comparison = {}
    warnings = list(comparison.get("warnings") or [])
    warnings.extend(str(item).strip() for item in validation.get("warnings") or [] if str(item).strip())
    adoptable = bool(enabled and ok and validation_passed)
    adoption_blocked_reason = None
    if not adoptable:
        if status == "disabled":
            adoption_blocked_reason = "LLM planner disabled or not configured"
        elif status == "failed":
            adoption_blocked_reason = str(error or "AI planner failed")
        elif status == "invalid":
            adoption_blocked_reason = "; ".join(str(item).strip() for item in validation.get("errors") or [] if str(item).strip()) or str(error or "AI layout plan failed validation")
    return {
        "enabled": enabled,
        "ok": ok,
        "validationPassed": validation_passed,
        "status": status,
        "adoptable": adoptable,
        "adoptionBlockedReason": adoption_blocked_reason,
        "summary": dict(report.get("summary") or {}) or None,
        "comparison": comparison or None,
        "warnings": warnings,
        "error": error,
    }


def normalize_ai_layout_plan_candidate(raw_candidate: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(raw_candidate or {})
    for wrapper_key in ("layout_plan", "candidatePlan"):
        wrapped = candidate.get(wrapper_key)
        if isinstance(wrapped, dict):
            candidate = dict(wrapped)
            break
    if "schemaVersion" not in candidate:
        version = candidate.pop("version", None)
        if version is not None:
            candidate["schemaVersion"] = version
    if "schemaVersion" not in candidate and isinstance(candidate.get("sections"), list):
        candidate["schemaVersion"] = 1
    sections = candidate.get("sections")
    if isinstance(sections, list):
        normalized_sections: list[Any] = []
        for section in sections:
            if not isinstance(section, dict):
                normalized_sections.append(section)
                continue
            normalized_section = dict(section)
            blocks = normalized_section.get("blocks")
            if isinstance(blocks, list):
                normalized_blocks: list[Any] = []
                for block in blocks:
                    if not isinstance(block, dict):
                        normalized_blocks.append(block)
                        continue
                    normalized_block = dict(block)
                    if str(normalized_block.get("type") or "").strip() == "table":
                        normalized_block.pop("headers", None)
                    normalized_blocks.append(normalized_block)
                normalized_section["blocks"] = normalized_blocks
            normalized_sections.append(normalized_section)
        candidate["sections"] = normalized_sections
    return candidate


def _validate_candidate(candidate: dict[str, Any], image_plan: list) -> dict[str, Any]:
    valid_indices = {
        int(item.get("imageIndex"))
        for item in image_plan or []
        if isinstance(item, dict)
        and item.get("type") != "skip"
        and item.get("imageIndex") is not None
    }
    try:
        validate_layout_plan(candidate, valid_indices)
        return {"passed": True, "errors": [], "warnings": []}
    except LayoutValidationError as exc:
        return {"passed": False, "errors": [str(exc)], "warnings": []}


def _sections(plan: dict[str, Any]) -> list[dict[str, Any]]:
    sections = plan.get("sections")
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def _section_titles(sections: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for section in sections:
        title = str(section.get("title") or section.get("key") or "").strip()
        if title:
            titles.append(title)
    return titles


def _count_blocks(plan: dict[str, Any], block_type: str) -> int:
    count = 0
    for section in _sections(plan):
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        count += sum(1 for block in blocks if isinstance(block, dict) and block.get("type") == block_type)
    return count


def _count_all_blocks(plan: dict[str, Any]) -> int:
    count = 0
    for section in _sections(plan):
        blocks = section.get("blocks")
        if isinstance(blocks, list):
            count += sum(1 for block in blocks if isinstance(block, dict))
    return count


def _table_schemas(plan: dict[str, Any]) -> list[str]:
    schemas: list[str] = []
    for section in _sections(plan):
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            schema = str(block.get("schema") or "").strip()
            if schema and schema not in schemas:
                schemas.append(schema)
    return schemas


def _image_refs(plan: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for section in _sections(plan):
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            image_ref = str(block.get("image_ref") or "").strip()
            if image_ref:
                ref_value = image_ref
            elif block.get("imageIndex") is not None:
                ref_value = f"image_{int(block.get('imageIndex'))}"
            else:
                continue
            if ref_value not in refs:
                refs.append(ref_value)
    return refs


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("AI planner response must be a JSON object")
    return parsed


def _system_prompt() -> str:
    return (
        "You are an AI layout planner working in shadow mode. "
        "Output JSON only. You are not a Word generator. "
        "You may only generate a layout_plan candidate. "
        "The root object must include schemaVersion and sections. "
        "schemaVersion must be the integer 1. "
        "sections must be an array. "
        "Allowed block types: paragraph, image, table, warning. "
        "Allowed table schemas: io_assignment_table, phenomenon_record_table, data_record_table. "
        "Image blocks may only reference existing imageIndex/image_ref from image_plan. "
        "Do not invent images. Do not define custom headers. "
        "Do not output unknown block types. Do not invent experiment data. "
        "Do not generate DOCX. Output must be validatable by the existing layout validator."
    )


def _user_prompt(
    *,
    metadata: dict,
    experiment_type: str,
    guide_text: str,
    report_text: str,
    image_plan: list,
    table_plan: list,
    current_layout_plan: dict,
) -> str:
    payload = {
        "experiment_type": experiment_type,
        "metadata": metadata,
        "guide_text": guide_text,
        "report_text": report_text,
        "image_plan": image_plan,
        "table_plan": table_plan,
        "current_layout_plan": current_layout_plan,
        "required_output_shape": {
            "schemaVersion": 1,
            "experimentType": experiment_type,
            "experimentName": str(metadata.get("experimentNo") or ""),
            "sections": [
                {
                    "key": "section_1",
                    "title": "一、实验目的",
                    "blocks": [
                        {"type": "paragraph", "content": "..."},
                        {"type": "image", "imageIndex": 0, "caption": "..."},
                        {"type": "table", "schema": "io_assignment_table", "data": {"rows": [["..."]]}},
                        {"type": "warning", "message": "..."},
                    ],
                }
            ],
            "warnings": [],
        },
    }
    return json.dumps(payload, ensure_ascii=False)
