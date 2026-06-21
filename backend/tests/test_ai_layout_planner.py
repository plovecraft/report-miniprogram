from base64 import b64decode
from pathlib import Path

from backend.app.services.ai_layout_planner import (
    build_ai_planner_preview_summary,
    compare_layout_plans,
    generate_ai_layout_plan_candidate,
    normalize_ai_layout_plan_candidate,
    summarize_ai_layout_plan,
)
from backend.app.main import generate_task_output, task_store
from backend.app.services.docx_builder import (
    adopt_ai_preview_layout_plan,
    build_report_preview,
    build_revised_docx,
    get_effective_preview_layout_plan,
    restore_rule_preview_layout_plan,
)
from backend.app.services.llm_writer import LLMConfig
from backend.app.services.task_store import TaskRecord


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class _FakeResponse:
    def __init__(self, content: str, status_code: int = 200) -> None:
        self._content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"bad status {self.status_code}")

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                    }
                }
            ]
        }


def _build_record(tmp_path: Path) -> TaskRecord:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    return TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        },
        root_dir=tmp_path,
        image_files=[image],
    )


def _base_rule_plan() -> dict:
    return {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentTypeName": "PLC",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [{"type": "paragraph", "content": "test"}],
            },
            {
                "key": "section_2",
                "title": "五、程序设计与梯形图",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "程序图", "imageType": "program"}],
            },
        ],
        "warnings": [],
    }


def _valid_ai_candidate_plan() -> dict:
    return {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "AI 章节",
                "blocks": [{"type": "paragraph", "content": "AI ONLY TEXT"}],
            },
            {
                "key": "section_2",
                "title": "AI 程序图",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "AI 图片图注"}],
            },
        ],
        "warnings": [],
    }


def test_ai_planner_disabled_without_config(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.ai_layout_planner.LLMConfig.from_env", lambda: None)

    result = generate_ai_layout_plan_candidate(
        metadata={"experimentNo": "Experiment 3"},
        experiment_type="plc",
        guide_text="guide",
        report_text="report",
        image_plan=[],
        table_plan=[],
        current_layout_plan=_base_rule_plan(),
    )

    assert result["enabled"] is False
    assert result["ok"] is False
    assert result["candidatePlan"] is None


def test_compare_layout_plans_counts_blocks() -> None:
    rule_plan = _base_rule_plan()
    ai_plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [
                    {"type": "paragraph", "content": "text"},
                    {"type": "table", "schema": "io_assignment_table", "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]}}
                ],
            }
        ],
        "warnings": [],
    }

    comparison = compare_layout_plans(rule_plan, ai_plan)

    assert comparison["ruleSectionCount"] == 2
    assert comparison["aiSectionCount"] == 1
    assert comparison["ruleImageBlocks"] == 1
    assert comparison["aiImageBlocks"] == 0
    assert comparison["ruleTableBlocks"] == 0
    assert comparison["aiTableBlocks"] == 1
    assert comparison["ruleWarningBlocks"] == 0
    assert comparison["aiWarningBlocks"] == 0


def test_compare_layout_plans_reports_section_titles() -> None:
    rule_plan = _base_rule_plan()
    ai_plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [{"type": "paragraph", "content": "text"}],
            },
            {
                "key": "section_9",
                "title": "实验原理",
                "blocks": [{"type": "paragraph", "content": "text"}],
            },
        ],
        "warnings": [],
    }

    comparison = compare_layout_plans(rule_plan, ai_plan)

    assert "一、实验目的" in comparison["ruleSectionTitles"]
    assert "实验原理" in comparison["aiSectionTitles"]
    assert "五、程序设计与梯形图" in comparison["missingInAi"]
    assert "实验原理" in comparison["extraInAi"]


def test_compare_layout_plans_reports_table_schemas() -> None:
    rule_plan = _base_rule_plan()
    rule_plan["sections"][0]["blocks"].append(
        {"type": "table", "schema": "io_assignment_table", "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]}}
    )
    ai_plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [
                    {"type": "table", "schema": "phenomenon_record_table", "data": {"rows": [["运行", "观察", "正常"]]}}
                ],
            }
        ],
        "warnings": [],
    }

    comparison = compare_layout_plans(rule_plan, ai_plan)

    assert comparison["tableSchemasInRule"] == ["io_assignment_table"]
    assert comparison["tableSchemasInAi"] == ["phenomenon_record_table"]


def test_compare_layout_plans_reports_image_refs() -> None:
    rule_plan = _base_rule_plan()
    ai_plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_2",
                "title": "五、程序设计与梯形图",
                "blocks": [{"type": "image", "imageIndex": 1, "caption": "程序图"}],
            }
        ],
        "warnings": [],
    }

    comparison = compare_layout_plans(rule_plan, ai_plan)

    assert comparison["imageRefsInRule"] == ["image_0"]
    assert comparison["imageRefsInAi"] == ["image_1"]


def test_summarize_ai_layout_plan_counts_blocks() -> None:
    ai_plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [
                    {"type": "paragraph", "content": "text"},
                    {"type": "warning", "message": "warn"},
                ],
            },
            {
                "key": "section_2",
                "title": "五、程序设计与梯形图",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "程序图"},
                    {"type": "table", "schema": "io_assignment_table", "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]}}
                ],
            },
        ],
        "warnings": [],
    }

    summary = summarize_ai_layout_plan(ai_plan)

    assert summary["sectionCount"] == 2
    assert summary["blockCount"] == 4
    assert summary["paragraphBlocks"] == 1
    assert summary["imageBlocks"] == 1
    assert summary["tableBlocks"] == 1
    assert summary["warningBlocks"] == 1
    assert summary["tableSchemas"] == ["io_assignment_table"]
    assert summary["imageRefs"] == ["image_0"]


def test_ai_planner_candidate_validated_with_mock_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.ai_layout_planner.LLMConfig.from_env",
        lambda: LLMConfig(base_url="http://mock", api_key="key", model="model"),
    )
    candidate = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [{"type": "paragraph", "content": "test"}],
            },
            {
                "key": "section_2",
                "title": "五、程序设计与梯形图",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "程序图"}],
            },
        ],
        "warnings": [],
    }
    monkeypatch.setattr(
        "backend.app.services.ai_layout_planner.requests.post",
        lambda *args, **kwargs: _FakeResponse(__import__("json").dumps(candidate, ensure_ascii=False)),
    )

    result = generate_ai_layout_plan_candidate(
        metadata={"experimentNo": "Experiment 3"},
        experiment_type="plc",
        guide_text="guide",
        report_text="report",
        image_plan=[{"imageIndex": 0, "type": "program"}],
        table_plan=[],
        current_layout_plan=_base_rule_plan(),
    )

    assert result["enabled"] is True
    assert result["ok"] is True
    assert result["validation"]["passed"] is True
    assert result["summary"]["imageBlocks"] == 1


def test_ai_planner_rejects_invalid_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.ai_layout_planner.LLMConfig.from_env",
        lambda: LLMConfig(base_url="http://mock", api_key="key", model="model"),
    )
    candidate = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [{"type": "video", "content": "bad"}],
            }
        ],
        "warnings": [],
    }
    monkeypatch.setattr(
        "backend.app.services.ai_layout_planner.requests.post",
        lambda *args, **kwargs: _FakeResponse(__import__("json").dumps(candidate, ensure_ascii=False)),
    )

    result = generate_ai_layout_plan_candidate(
        metadata={"experimentNo": "Experiment 3"},
        experiment_type="plc",
        guide_text="guide",
        report_text="report",
        image_plan=[],
        table_plan=[],
        current_layout_plan=_base_rule_plan(),
    )

    assert result["enabled"] is True
    assert result["ok"] is False
    assert result["validation"]["passed"] is False
    assert result["validation"]["errors"]
    assert result["error"]


def test_build_preview_keeps_rule_layout_plan_when_ai_planner_runs(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    rule_plan_holder = {}

    def fake_ai(**kwargs):
        rule_plan_holder["rule_plan"] = kwargs["current_layout_plan"]
        return {
            "enabled": True,
            "ok": True,
            "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
            "validation": {"passed": True, "errors": [], "warnings": []},
            "comparison": {},
            "summary": {"sectionCount": 0},
            "error": None,
        }

    monkeypatch.setattr("backend.app.services.docx_builder.generate_ai_layout_plan_candidate", fake_ai)

    preview = build_report_preview(record)

    assert record.preview_layout_plan is not None
    assert record.ai_layout_plan_report is not None
    assert record.preview_layout_plan == rule_plan_holder["rule_plan"]
    assert "layoutPlan" not in preview


def test_ai_planner_failure_does_not_fail_preview(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    def fail_ai(**kwargs):
        raise RuntimeError("planner boom")

    monkeypatch.setattr("backend.app.services.docx_builder.generate_ai_layout_plan_candidate", fail_ai)

    preview = build_report_preview(record)

    assert preview["sections"]
    assert record.preview_layout_plan is not None
    assert record.ai_layout_plan_report is not None
    assert record.ai_layout_plan_report["ok"] is False


def test_ai_planner_preview_summary_hides_candidate_plan() -> None:
    summary = build_ai_planner_preview_summary(
        {
            "enabled": True,
            "ok": True,
            "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
            "validation": {"passed": True, "errors": [], "warnings": []},
            "summary": {"sectionCount": 0},
            "comparison": {"ruleSectionCount": 1, "aiSectionCount": 0},
            "error": None,
        }
    )

    assert summary["status"] == "valid"
    assert "candidatePlan" not in summary


def test_task_preview_contains_ai_planner_preview_when_available(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    monkeypatch.setattr(
        "backend.app.services.docx_builder.generate_ai_layout_plan_candidate",
        lambda **kwargs: {
            "enabled": True,
            "ok": True,
            "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
            "validation": {"passed": True, "errors": [], "warnings": []},
            "summary": {"sectionCount": 0, "blockCount": 0},
            "comparison": {"ruleSectionCount": 2, "aiSectionCount": 0},
            "error": None,
        },
    )

    preview = build_report_preview(record)

    assert "aiPlannerPreview" in preview
    assert preview["aiPlannerPreview"]["status"] == "valid"
    assert "summary" in preview["aiPlannerPreview"]
    assert "comparison" in preview["aiPlannerPreview"]


def test_ai_planner_preview_disabled_without_config(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    monkeypatch.setattr("backend.app.services.docx_builder.generate_ai_layout_plan_candidate", lambda **kwargs: {
        "enabled": False,
        "ok": False,
        "candidatePlan": None,
        "validation": None,
        "comparison": None,
        "summary": None,
        "error": "LLM planner disabled or not configured",
    })

    preview = build_report_preview(record)

    assert preview["aiPlannerPreview"]["status"] == "disabled"
    assert record.preview_layout_plan is not None


def test_ai_planner_preview_invalid_candidate_status(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    monkeypatch.setattr(
        "backend.app.services.docx_builder.generate_ai_layout_plan_candidate",
        lambda **kwargs: {
            "enabled": True,
            "ok": False,
            "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
            "validation": {"passed": False, "errors": ["unsupported block type: video"], "warnings": []},
            "comparison": {"ruleSectionCount": 2, "aiSectionCount": 0},
            "summary": {"sectionCount": 0},
            "error": "unsupported block type: video",
        },
    )

    preview = build_report_preview(record)

    assert preview["aiPlannerPreview"]["status"] == "invalid"
    assert preview["aiPlannerPreview"]["validationPassed"] is False


def test_adopt_ai_layout_plan_success(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _valid_ai_candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2},
        "error": None,
    }

    adopt_ai_preview_layout_plan(record)

    assert record.layout_plan_source == "ai"
    assert record.adopted_ai_layout_plan is not None
    assert record.preview_data["layoutPlanSource"] == "ai"


def test_adopt_ai_layout_plan_rejects_invalid_candidate(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": False,
        "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
        "validation": {"passed": False, "errors": ["unsupported block type: video"], "warnings": []},
        "summary": {"sectionCount": 0},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 0},
        "error": "unsupported block type: video",
    }

    try:
        adopt_ai_preview_layout_plan(record)
        assert False, "expected adoption to fail"
    except ValueError as exc:
        assert "unsupported block type" in str(exc)

    assert record.layout_plan_source == "rule"
    assert record.adopted_ai_layout_plan is None


def test_restore_rule_layout_plan(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _valid_ai_candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2},
        "error": None,
    }
    adopt_ai_preview_layout_plan(record)

    restore_rule_preview_layout_plan(record)

    assert record.layout_plan_source == "rule"
    assert record.adopted_ai_layout_plan is None
    assert record.preview_data["layoutPlanSource"] == "rule"


def test_effective_layout_plan_uses_ai_when_adopted(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _valid_ai_candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2},
        "error": None,
    }
    adopt_ai_preview_layout_plan(record)

    effective = get_effective_preview_layout_plan(record)

    assert effective is not None
    assert effective["sections"][0]["title"] == "AI 章节"


def test_adopt_ai_plan_rejects_unknown_image_ref(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    bad_plan = _valid_ai_candidate_plan()
    bad_plan["sections"][1]["blocks"][0]["image_ref"] = "image_999"
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": bad_plan,
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2},
        "error": None,
    }

    try:
        adopt_ai_preview_layout_plan(record)
        assert False, "expected adoption to fail"
    except ValueError as exc:
        assert "unknown image_ref" in str(exc)


def test_adopt_ai_plan_rejects_unknown_table_schema(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)
    record.preview_data = preview
    bad_plan = _valid_ai_candidate_plan()
    bad_plan["sections"][0]["blocks"].append(
        {"type": "table", "schema": "bad_schema", "data": {"rows": [["x"]]}}
    )
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": bad_plan,
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2},
        "error": None,
    }

    try:
        adopt_ai_preview_layout_plan(record)
        assert False, "expected adoption to fail"
    except ValueError as exc:
        assert "invalid" in str(exc) or "schema" in str(exc)


def test_preview_shows_layout_plan_source_and_adoptable(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    monkeypatch.setattr(
        "backend.app.services.docx_builder.generate_ai_layout_plan_candidate",
        lambda **kwargs: {
            "enabled": True,
            "ok": True,
            "candidatePlan": _valid_ai_candidate_plan(),
            "validation": {"passed": True, "errors": [], "warnings": []},
            "summary": {"sectionCount": 2, "blockCount": 2},
            "comparison": {"ruleSectionCount": 2, "aiSectionCount": 2, "warnings": []},
            "error": None,
        },
    )

    preview = build_report_preview(record)

    assert preview["layoutPlanSource"] == "rule"
    assert preview["aiPlannerPreview"]["adoptable"] is True


def test_build_revised_docx_still_uses_rule_plan_not_ai_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"

    from docx import Document

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(report)
    doc = Document()
    doc.add_paragraph("guide text")
    doc.save(guide)
    image.write_bytes(PNG_1X1)

    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": {
            "schemaVersion": 1,
            "experimentType": "plc",
            "experimentName": "Experiment 3",
            "sections": [{"key": "section_1", "title": "AI 章节", "blocks": [{"type": "paragraph", "content": "AI ONLY TEXT"}]}],
            "warnings": [],
        },
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 1},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 1},
        "error": None,
    }

    output_doc = Document(build_revised_docx(record))
    body_text = output_doc.tables[0].cell(1, 0).text

    assert "AI ONLY TEXT" not in body_text


def test_build_revised_docx_uses_adopted_ai_plan_after_shadow_gate(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"

    from docx import Document

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(report)
    doc = Document()
    doc.add_paragraph("guide text")
    doc.save(guide)
    image.write_bytes(PNG_1X1)

    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _valid_ai_candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2},
        "error": None,
    }
    adopt_ai_preview_layout_plan(record)

    output_doc = Document(build_revised_docx(record))
    body_text = output_doc.tables[0].cell(1, 0).text

    assert "AI ONLY TEXT" in body_text
    assert record.shadow_gate_report is not None
    assert record.shadow_gate_report["skipped"] is False


def test_table_selection_and_edits_still_apply_to_ai_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"

    from docx import Document

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(report)
    doc = Document()
    doc.add_paragraph("guide text")
    doc.save(guide)
    image.write_bytes(PNG_1X1)

    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    record.preview_data = preview
    ai_plan = _valid_ai_candidate_plan()
    ai_plan["sections"][0]["blocks"].append(
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "原按钮", "原说明"]]},
        }
    )
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": ai_plan,
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2},
        "error": None,
    }
    adopt_ai_preview_layout_plan(record)
    assert record.preview_data["tablePlan"][0]["tableId"] == "table_0"

    record.table_edits = {"table_0": [["输入", "I0.0", "改后按钮", "改后说明"]]}
    record.table_selection = {"table_0": True}
    effective = get_effective_preview_layout_plan(record)
    assert effective is not None
    table_blocks = [
        block
        for section in effective["sections"]
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") == "table"
    ]
    assert table_blocks[0]["data"]["rows"][0][2] == "改后按钮"

    record.table_selection = {"table_0": False}
    effective = get_effective_preview_layout_plan(record)
    assert effective is not None
    table_blocks = [
        block
        for section in effective["sections"]
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") == "table"
    ]
    assert table_blocks == []


def test_generate_task_output_ai_planner_does_not_expose_candidate_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"

    from docx import Document

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(report)
    doc = Document()
    doc.add_paragraph("guide text")
    doc.save(guide)
    image.write_bytes(PNG_1X1)

    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 0, "blockCount": 0},
        "comparison": {"ruleSectionCount": 1, "aiSectionCount": 1},
        "error": None,
    }
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert "candidatePlan" not in record.quality_report["aiPlanner"]


def test_generate_task_output_keeps_ai_planner_summary(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"

    from docx import Document

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(report)
    doc = Document()
    doc.add_paragraph("guide text")
    doc.save(guide)
    image.write_bytes(PNG_1X1)

    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    record.preview_data = preview
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 0, "blockCount": 0},
        "comparison": {"ruleSectionCount": 1, "aiSectionCount": 1},
        "error": None,
    }
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.quality_report["aiPlanner"]["enabled"] is True
    assert record.quality_report["aiPlanner"]["ok"] is True
    assert record.quality_report["aiPlanner"]["validationPassed"] is True
    assert record.quality_report["aiPlanner"]["summary"]["sectionCount"] == 0
    assert "candidatePlan" not in record.quality_report["aiPlanner"]


def test_ai_candidate_normalizes_layout_plan_wrapper() -> None:
    raw = {"layout_plan": {"schemaVersion": 1, "sections": []}}

    normalized = normalize_ai_layout_plan_candidate(raw)

    assert normalized["schemaVersion"] == 1
    assert normalized["sections"] == []


def test_ai_candidate_adds_missing_schema_version_when_safe() -> None:
    raw = {"sections": []}

    normalized = normalize_ai_layout_plan_candidate(raw)

    assert normalized["schemaVersion"] == 1
    assert normalized["sections"] == []


def test_ai_candidate_maps_version_to_schema_version() -> None:
    raw = {"version": 1, "sections": []}

    normalized = normalize_ai_layout_plan_candidate(raw)

    assert normalized["schemaVersion"] == 1
    assert "version" not in normalized


def test_ai_candidate_strips_table_headers_override() -> None:
    raw = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "实验过程",
                "blocks": [
                    {
                        "type": "table",
                        "schema": "io_assignment_table",
                        "headers": ["A", "B"],
                        "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]},
                    }
                ],
            }
        ],
    }

    normalized = normalize_ai_layout_plan_candidate(raw)

    assert "headers" not in normalized["sections"][0]["blocks"][0]


def test_ai_invalid_candidate_hides_comparison() -> None:
    summary = build_ai_planner_preview_summary(
        {
            "enabled": True,
            "ok": False,
            "candidatePlan": {"sections": []},
            "validation": {"passed": False, "errors": ["layout_plan.schemaVersion is required"], "warnings": []},
            "comparison": {
                "sectionCountDelta": -7,
                "imageBlockDelta": -10,
                "tableBlockDelta": -2,
                "warnings": ["bad diff"],
            },
            "summary": None,
            "error": "layout_plan.schemaVersion is required",
        }
    )

    assert summary["status"] == "invalid"
    assert summary["validationPassed"] is False
    assert summary["comparison"] is None
