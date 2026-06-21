from copy import deepcopy

from backend.app.services.ai_planner_evaluator import (
    evaluate_ai_planner_sample,
    evaluate_ai_planner_samples,
)


def _rule_plan() -> dict:
    return {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "实验目的",
                "blocks": [{"type": "paragraph", "content": "test"}],
            },
            {
                "key": "section_2",
                "title": "实验过程",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "程序图"},
                    {"type": "table", "schema": "io_assignment_table", "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]}},
                ],
            },
        ],
        "warnings": [],
    }


def _sample(**overrides) -> dict:
    data = {
        "sample_name": "plc_sample",
        "metadata": {"experimentNo": "Experiment 3"},
        "experiment_type": "plc",
        "guide_text": "guide",
        "report_text": "report",
        "image_plan": [{"imageIndex": 0, "image_ref": "image_0", "type": "program"}],
        "table_plan": [{"schema": "io_assignment_table"}],
        "rule_layout_plan": _rule_plan(),
    }
    data.update(overrides)
    return data


def test_evaluate_ai_planner_sample_valid_candidate(monkeypatch) -> None:
    candidate = {
        "enabled": True,
        "ok": True,
        "candidatePlan": deepcopy(_rule_plan()),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "comparison": {
            "ruleSectionCount": 2,
            "aiSectionCount": 2,
            "ruleImageBlocks": 1,
            "aiImageBlocks": 1,
            "ruleTableBlocks": 1,
            "aiTableBlocks": 1,
            "sectionCountDelta": 0,
            "imageBlockDelta": 0,
            "tableBlockDelta": 0,
            "warnings": [],
        },
        "summary": {
            "sectionCount": 2,
            "blockCount": 3,
            "paragraphBlocks": 1,
            "imageBlocks": 1,
            "tableBlocks": 1,
            "warningBlocks": 0,
            "sectionTitles": ["实验目的", "实验过程"],
            "tableSchemas": ["io_assignment_table"],
            "imageRefs": ["image_0"],
        },
        "error": None,
    }
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: candidate,
    )

    result = evaluate_ai_planner_sample(**_sample())

    assert result["validationPassed"] is True
    assert result["scores"]["validPlan"] is True


def test_evaluate_ai_planner_sample_invalid_candidate(monkeypatch) -> None:
    candidate = {
        "enabled": True,
        "ok": False,
        "candidatePlan": {
            "schemaVersion": 1,
            "experimentType": "plc",
            "experimentName": "Experiment 3",
            "sections": [{"key": "section_1", "title": "实验目的", "blocks": [{"type": "video"}]}],
            "warnings": [],
        },
        "validation": {"passed": False, "errors": ["unsupported block type: video"], "warnings": []},
        "comparison": {},
        "summary": {"sectionCount": 1},
        "error": "unsupported block type: video",
    }
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: candidate,
    )

    result = evaluate_ai_planner_sample(**_sample())

    assert result["validationPassed"] is False
    assert result["errors"]


def test_evaluate_ai_planner_detects_missing_image_refs(monkeypatch) -> None:
    plan = deepcopy(_rule_plan())
    plan["sections"][1]["blocks"][0]["imageIndex"] = 99
    candidate = {
        "enabled": True,
        "ok": False,
        "candidatePlan": plan,
        "validation": {"passed": False, "errors": ["unknown imageIndex: 99"], "warnings": []},
        "comparison": {},
        "summary": {"sectionCount": 2},
        "error": "unknown imageIndex: 99",
    }
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: candidate,
    )

    result = evaluate_ai_planner_sample(**_sample())

    assert result["scores"]["imageRefsValid"] is False


def test_evaluate_ai_planner_detects_unknown_table_schema(monkeypatch) -> None:
    plan = deepcopy(_rule_plan())
    plan["sections"][1]["blocks"][1]["schema"] = "custom_table"
    candidate = {
        "enabled": True,
        "ok": False,
        "candidatePlan": plan,
        "validation": {"passed": False, "errors": ["unknown table schema"], "warnings": []},
        "comparison": {},
        "summary": {"sectionCount": 2},
        "error": "unknown table schema",
    }
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: candidate,
    )

    result = evaluate_ai_planner_sample(**_sample())

    assert result["scores"]["tableSchemasValid"] is False


def test_evaluate_ai_planner_samples_summary(monkeypatch) -> None:
    valid = {
        "enabled": True,
        "ok": True,
        "candidatePlan": deepcopy(_rule_plan()),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "comparison": {
            "ruleSectionCount": 2,
            "aiSectionCount": 2,
            "ruleImageBlocks": 1,
            "aiImageBlocks": 1,
            "ruleTableBlocks": 1,
            "aiTableBlocks": 1,
            "sectionCountDelta": 0,
            "imageBlockDelta": 0,
            "tableBlockDelta": 0,
            "warnings": [],
        },
        "summary": {"sectionCount": 2},
        "error": None,
    }
    invalid = {
        "enabled": True,
        "ok": False,
        "candidatePlan": {
            "schemaVersion": 1,
            "experimentType": "plc",
            "experimentName": "Experiment 3",
            "sections": [{"key": "section_1", "title": "实验目的", "blocks": [{"type": "video"}]}],
            "warnings": [],
        },
        "validation": {"passed": False, "errors": ["unsupported block type: video"], "warnings": []},
        "comparison": {
            "ruleSectionCount": 2,
            "aiSectionCount": 1,
            "ruleImageBlocks": 1,
            "aiImageBlocks": 0,
            "ruleTableBlocks": 1,
            "aiTableBlocks": 0,
            "sectionCountDelta": -1,
            "imageBlockDelta": -1,
            "tableBlockDelta": -1,
            "warnings": [],
        },
        "summary": {"sectionCount": 1},
        "error": "unsupported block type: video",
    }
    queue = [valid, invalid]
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: queue.pop(0),
    )

    result = evaluate_ai_planner_samples([_sample(sample_name="a"), _sample(sample_name="b")])

    assert result["total"] == 2
    assert result["validationPassedCount"] == 1
    assert result["failedCount"] == 1
    assert "summary" in result


def test_ai_planner_evaluation_does_not_modify_rule_plan(monkeypatch) -> None:
    original = _rule_plan()
    snapshot = deepcopy(original)
    monkeypatch.setattr(
        "backend.app.services.ai_planner_evaluator.generate_ai_layout_plan_candidate",
        lambda **kwargs: {
            "enabled": False,
            "ok": False,
            "candidatePlan": None,
            "validation": None,
            "comparison": None,
            "summary": None,
            "error": "disabled",
        },
    )

    evaluate_ai_planner_sample(**_sample(rule_layout_plan=original))

    assert original == snapshot
