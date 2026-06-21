from __future__ import annotations

from copy import deepcopy
from typing import Any

from .ai_layout_planner import (
    compare_layout_plans,
    generate_ai_layout_plan_candidate,
    summarize_ai_layout_plan,
)


def evaluate_ai_planner_sample(
    *,
    sample_name: str,
    metadata: dict,
    experiment_type: str,
    guide_text: str,
    report_text: str,
    image_plan: list,
    table_plan: list,
    rule_layout_plan: dict,
    llm_config=None,
) -> dict[str, Any]:
    rule_plan_snapshot = deepcopy(rule_layout_plan)
    ai_result = generate_ai_layout_plan_candidate(
        metadata=metadata,
        experiment_type=experiment_type,
        guide_text=guide_text,
        report_text=report_text,
        image_plan=image_plan,
        table_plan=table_plan,
        current_layout_plan=deepcopy(rule_layout_plan),
    )
    candidate = ai_result.get("candidatePlan")
    validation = ai_result.get("validation") or {}
    comparison = ai_result.get("comparison") or {}
    rule_summary = summarize_ai_layout_plan(rule_plan_snapshot)
    ai_summary = dict(ai_result.get("summary") or {})
    errors = _collect_errors(ai_result, validation)
    scores = _build_scores(
        candidate=candidate,
        image_plan=image_plan,
        validation_passed=bool(validation.get("passed")),
        comparison=comparison,
    )

    warnings = list(comparison.get("warnings") or [])
    if ai_result.get("error"):
        warnings.append(str(ai_result["error"]))

    return {
        "sampleName": sample_name,
        "aiEnabled": bool(ai_result.get("enabled")),
        "aiOk": bool(ai_result.get("ok")),
        "validationPassed": bool(validation.get("passed")),
        "ruleSummary": rule_summary,
        "aiSummary": ai_summary,
        "comparison": comparison,
        "scores": scores,
        "warnings": warnings,
        "errors": errors,
    }


def evaluate_ai_planner_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_ai_planner_sample(**sample) for sample in samples]
    total = len(results)
    ai_enabled_count = sum(1 for item in results if item["aiEnabled"])
    ai_ok_count = sum(1 for item in results if item["aiOk"])
    validation_passed_count = sum(1 for item in results if item["validationPassed"])
    invalid_candidate_count = sum(1 for item in results if not item["scores"]["validPlan"])
    unknown_block_count = sum(1 for item in results if not item["scores"]["noUnknownBlocks"])
    failed_count = sum(1 for item in results if item["errors"])
    comparisons = [item["comparison"] for item in results if item["comparison"]]

    return {
        "total": total,
        "aiEnabledCount": ai_enabled_count,
        "aiOkCount": ai_ok_count,
        "validationPassedCount": validation_passed_count,
        "failedCount": failed_count,
        "samples": results,
        "summary": {
            "avgSectionCountDelta": _avg(comparisons, "sectionCountDelta"),
            "avgImageBlockDelta": _avg(comparisons, "imageBlockDelta"),
            "avgTableBlockDelta": _avg(comparisons, "tableBlockDelta"),
            "invalidCandidateCount": invalid_candidate_count,
            "unknownBlockCount": unknown_block_count,
        },
    }


def _collect_errors(ai_result: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    errors = list(validation.get("errors") or [])
    if ai_result.get("error"):
        error_text = str(ai_result["error"]).strip()
        if error_text and error_text not in errors:
            errors.append(error_text)
    return errors


def _build_scores(
    *,
    candidate: dict[str, Any] | None,
    image_plan: list,
    validation_passed: bool,
    comparison: dict[str, Any],
) -> dict[str, bool]:
    return {
        "validPlan": validation_passed,
        "reasonableSectionCount": _reasonable_section_count(candidate, comparison),
        "imageRefsValid": _image_refs_valid(candidate, image_plan),
        "tableSchemasValid": _table_schemas_valid(candidate),
        "noUnknownBlocks": _no_unknown_blocks(candidate),
    }


def _reasonable_section_count(candidate: dict[str, Any] | None, comparison: dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    ai_section_count = int(comparison.get("aiSectionCount") or 0)
    rule_section_count = int(comparison.get("ruleSectionCount") or 0)
    if ai_section_count <= 0:
        return False
    return abs(ai_section_count - rule_section_count) <= max(2, rule_section_count)


def _image_refs_valid(candidate: dict[str, Any] | None, image_plan: list) -> bool:
    if not isinstance(candidate, dict):
        return False
    valid_refs = {
        str(item.get("image_ref") or "").strip()
        for item in image_plan or []
        if isinstance(item, dict) and str(item.get("image_ref") or "").strip()
    }
    valid_refs.update(
        f"image_{int(item.get('imageIndex'))}"
        for item in image_plan or []
        if isinstance(item, dict) and item.get("imageIndex") is not None
    )
    for section in candidate.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            if block.get("image_ref") is not None:
                ref = str(block.get("image_ref") or "").strip()
            elif block.get("imageIndex") is not None:
                ref = f"image_{int(block.get('imageIndex'))}"
            else:
                return False
            if ref not in valid_refs:
                return False
    return True


def _table_schemas_valid(candidate: dict[str, Any] | None) -> bool:
    if not isinstance(candidate, dict):
        return False
    allowed = {"io_assignment_table", "phenomenon_record_table", "data_record_table"}
    for section in candidate.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            schema = str(block.get("schema") or "").strip()
            if schema not in allowed:
                return False
    return True


def _no_unknown_blocks(candidate: dict[str, Any] | None) -> bool:
    if not isinstance(candidate, dict):
        return False
    allowed = {"paragraph", "image", "table", "warning"}
    for section in candidate.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                return False
            if str(block.get("type") or "").strip() not in allowed:
                return False
    return True


def _avg(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0
    values = [float(item.get(key) or 0) for item in items]
    return sum(values) / len(values)
