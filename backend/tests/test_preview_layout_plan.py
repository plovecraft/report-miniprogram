from base64 import b64decode
from pathlib import Path

from backend.app.services.docx_builder import (
    apply_table_edits_to_layout_plan,
    apply_table_selection_to_layout_plan,
    build_table_audit_report,
    build_preview_layout_plan,
    build_report_preview,
    extract_table_preview_summary,
    get_effective_preview_layout_plan,
    run_pre_generation_shadow_gate,
)
from backend.app.services.layout_validator import validate_layout_plan
from backend.app.services.task_store import TaskRecord


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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


def test_build_preview_creates_preview_layout_plan(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    preview = build_report_preview(record)

    assert preview["sections"]
    assert record.preview_layout_plan is not None
    assert record.preview_layout_plan["sections"]


def test_preview_layout_plan_contains_image_blocks(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)

    layout_plan = build_preview_layout_plan(preview)
    image_blocks = [
        block
        for section in layout_plan["sections"]
        for block in section["blocks"]
        if block["type"] == "image"
    ]

    assert len(image_blocks) == 1
    assert image_blocks[0]["imageIndex"] == 0


def test_preview_layout_plan_validates_successfully(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)

    layout_plan = build_preview_layout_plan(preview)

    validate_layout_plan(layout_plan, {0})


def test_build_preview_layout_plan_injects_table_blocks(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)

    layout_plan = build_preview_layout_plan(
        preview,
        guide_text="I/O assignment uses I0.0 and Q0.0 with start button and indicator light.",
    )

    table_blocks = [
        block
        for section in layout_plan["sections"]
        for block in section["blocks"]
        if block["type"] == "table"
    ]
    assert table_blocks


def test_table_feature_disabled_hides_table_plan_and_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TABLE_FEATURE_ENABLED", "0")
    record = _build_record(tmp_path)

    preview = build_report_preview(record)

    blocks = [
        block
        for section in record.preview_layout_plan["sections"]
        for block in section.get("blocks", [])
    ]
    assert preview["tablePlan"] == []
    assert not [block for block in blocks if block.get("type") == "table"]


def test_table_feature_disabled_strips_effective_layout_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TABLE_FEATURE_ENABLED", "0")
    record = _build_record(tmp_path)
    record.preview_layout_plan = {
        "schemaVersion": "layout-plan.v1",
        "sections": [
            {
                "key": "result",
                "title": "实验结果",
                "blocks": [
                    {"type": "paragraph", "text": "keep"},
                    {
                        "type": "table",
                        "tableId": "table_0",
                        "schema": "io_assignment_table",
                        "title": "I/O 分配表",
                        "data": {"rows": [["输入", "I0.0", "启动按钮", "启动"]]},
                    },
                ],
            }
        ],
    }

    effective = get_effective_preview_layout_plan(record)

    blocks = effective["sections"][0]["blocks"]
    assert [block["type"] for block in blocks] == ["paragraph"]


def test_table_feature_disabled_audit_marks_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TABLE_FEATURE_ENABLED", "0")
    record = _build_record(tmp_path)

    audit = build_table_audit_report(
        record,
        effective_layout_plan={
            "schemaVersion": "layout-plan.v1",
            "sections": [{"key": "result", "title": "实验结果", "blocks": []}],
        },
        executor_report={"writtenTables": 0, "tableRows": 0, "fallbackUsed": False},
    )

    assert audit["plannedTables"] == []
    assert audit["summary"]["disabled"] is True
    assert audit["summary"]["plannedCount"] == 0


def test_preview_layout_plan_with_auto_table_validates(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    preview = build_report_preview(record)

    layout_plan = build_preview_layout_plan(
        preview,
        guide_text="Record measured values and error data while observing experiment phenomenon.",
        image_plan=[{"imageIndex": 0, "type": "result", "category": "phenomenon", "caption": "Observed phenomenon"}],
    )

    validate_layout_plan(layout_plan, {0})


def test_shadow_gate_uses_cached_preview_layout_plan(monkeypatch, tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    record.preview_data = build_report_preview(record)
    assert record.preview_layout_plan is not None

    def fail_if_rebuilt(*args, **kwargs):
        raise AssertionError("cached preview layout plan should be used before rebuilding")

    monkeypatch.setattr("backend.app.services.docx_builder.build_validated_layout_plan", fail_if_rebuilt)

    result = run_pre_generation_shadow_gate(record)

    assert result["passed"] is True
    assert result["skipped"] is False


def test_preview_layout_plan_does_not_change_frontend_preview_shape(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    preview = build_report_preview(record)

    assert "experimentType" in preview
    assert "experimentTypeName" in preview
    assert "experimentName" in preview
    assert "sections" in preview
    assert "imagePlan" in preview
    assert "insertedImageCount" in preview
    assert "template" in preview
    assert "tablePlan" in preview
    assert "layoutPlan" not in preview


def test_preview_data_contains_table_plan_summary(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide

    preview = build_report_preview(record)

    assert preview["tablePlan"]
    first_table = preview["tablePlan"][0]
    assert first_table["schema"] == "io_assignment_table"
    assert first_table["title"]
    assert first_table["rowCount"] >= 1
    assert first_table["headers"]


def test_table_plan_summary_contains_table_id_and_selected(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide

    preview = build_report_preview(record)

    assert preview["tablePlan"]
    first_table = preview["tablePlan"][0]
    assert first_table["tableId"].startswith("table_")
    assert first_table["selected"] is True


def test_table_plan_summary_contains_rows_and_edited(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide

    preview = build_report_preview(record)

    assert preview["tablePlan"]
    first_table = preview["tablePlan"][0]
    assert isinstance(first_table["rows"], list)
    assert first_table["edited"] is False


def test_table_plan_summary_does_not_break_existing_preview_shape(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    preview = build_report_preview(record)

    assert "experimentType" in preview
    assert "sections" in preview
    assert "imagePlan" in preview
    assert isinstance(preview.get("tablePlan"), list)


def test_extract_table_preview_summary_handles_no_tables() -> None:
    summary = extract_table_preview_summary(
        {
            "schemaVersion": 1,
            "sections": [{"key": "purpose", "title": "Purpose", "blocks": [{"type": "paragraph", "content": "test"}]}],
            "warnings": [],
        }
    )

    assert summary == []


def test_apply_table_selection_removes_unselected_table_blocks(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.add_paragraph("Record measured values, error data, and observed phenomenon.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide

    preview = build_report_preview(record)
    summary = preview["tablePlan"]
    assert len(summary) >= 1

    effective = apply_table_selection_to_layout_plan(
        record.preview_layout_plan,
        {summary[0]["tableId"]: False},
    )

    effective_summary = extract_table_preview_summary(effective)
    assert all(item["tableId"] != summary[0]["tableId"] for item in effective_summary)


def test_apply_table_edits_replaces_rows(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide
    preview = build_report_preview(record)
    summary = preview["tablePlan"]

    edited = apply_table_edits_to_layout_plan(
        record.preview_layout_plan,
        {
            summary[0]["tableId"]: [
                ["input", "I0.0", "edited button", "edited control"],
                ["output", "Q0.0", "edited lamp", "edited state"],
            ]
        },
    )

    table_summary = extract_table_preview_summary(edited)
    assert table_summary[0]["rows"][0][2] == "edited button"


def test_task_response_includes_table_plan_if_preview_ready(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    from docx import Document

    guide_doc = Document()
    guide_doc.add_paragraph("I/O assignment uses I0.0 and Q0.0 with start button and indicator light.")
    guide_doc.save(guide)
    record = _build_record(tmp_path)
    record.guide_file = guide
    preview = build_report_preview(record)
    record.preview_data = preview

    response = record.to_response()

    assert "preview" in response
    assert "tablePlan" in response["preview"]


def test_legacy_without_preview_layout_plan_still_skips(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    result = run_pre_generation_shadow_gate(record)

    assert result["passed"] is True
    assert result["skipped"] is True
    assert any("shadow gate skipped" in warning.lower() for warning in result["warnings"])
