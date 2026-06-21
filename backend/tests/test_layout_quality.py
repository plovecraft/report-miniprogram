from base64 import b64decode
from pathlib import Path

import pytest
from docx import Document

from backend.app.main import generate_task_output, task_store
from backend.app.services.docx_builder import (
    build_report_preview,
    build_revised_docx,
    build_table_audit_report,
    run_pre_generation_shadow_gate,
)
from backend.app.services.table_schema import get_table_schema
from backend.app.services.task_store import TaskRecord


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _make_docx(path: Path, text: str = "body") -> Path:
    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = text
    doc.save(path)
    return path


def _build_record(tmp_path: Path, *, image_bytes: bytes = PNG_1X1) -> TaskRecord:
    root_dir = tmp_path / "task"
    upload_dir = root_dir / "uploads"
    output_dir = root_dir / "outputs"
    upload_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    report = _make_docx(upload_dir / "report.docx", "old body")
    guide = _make_docx(upload_dir / "guide.docx", "guide body")
    image = upload_dir / "program.png"
    image.write_bytes(image_bytes)
    return TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        },
        root_dir=root_dir,
        report_file=report,
        guide_file=guide,
        image_files=[image],
    )


def _attach_preview(record: TaskRecord) -> None:
    preview = build_report_preview(record)
    record.preview_data = preview
    assert record.preview_layout_plan is not None


def _first_image_block(layout_plan: dict) -> dict:
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                return block
    raise AssertionError("expected image block")


def test_layout_executor_report_marks_used_for_preview_layout_plan(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report is not None
    assert record.layout_executor_report["used"] is True
    assert record.layout_executor_report["fallbackUsed"] is False
    assert record.layout_executor_report["fallbackReason"] is None


def test_layout_executor_report_marks_fallback_without_preview_layout_plan(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report is not None
    assert record.layout_executor_report["used"] is False
    assert record.layout_executor_report["fallbackUsed"] is True
    assert "preview_layout_plan missing" in str(record.layout_executor_report["fallbackReason"])
    assert any("legacy fallback" in warning.lower() for warning in record.layout_executor_report["warnings"])


def test_layout_executor_errors_do_not_silent_fallback(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)

    def fail_executor(*args, **kwargs):
        raise ValueError("executor boom")

    from backend.app.services import docx_builder as docx_builder_module

    original_executor = docx_builder_module.append_layout_plan_content
    docx_builder_module.append_layout_plan_content = fail_executor
    try:
        with pytest.raises(Exception, match="executor boom"):
            build_revised_docx(record)
    finally:
        docx_builder_module.append_layout_plan_content = original_executor

    assert record.layout_executor_report is not None
    assert record.layout_executor_report["used"] is True
    assert record.layout_executor_report["fallbackUsed"] is False
    assert record.layout_executor_report["errors"]


def test_shadow_gate_still_blocks_unknown_image_before_generation(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    _first_image_block(record.preview_layout_plan)["imageIndex"] = 99

    with pytest.raises(Exception, match="unknown imageIndex"):
        build_revised_docx(record)


def test_quality_report_contains_layout_executor_summary(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.image_files = [image]
    _attach_preview(record)
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    report = record.quality_report["layoutExecutor"]
    assert report["used"] is True
    assert report["fallbackUsed"] is False
    assert "fallbackReason" in report
    assert "warnings" in report
    assert "errors" in report
    assert "writtenTables" in report
    assert "tableRows" in report
    assert "imageRows" in report
    assert "pairedImages" in report


def test_quality_report_marks_legacy_fallback_explicitly(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.image_files = [image]
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    report = record.quality_report["layoutExecutor"]
    assert report["used"] is False
    assert report["fallbackUsed"] is True
    assert "preview_layout_plan missing" in str(report["fallbackReason"])


def test_quality_report_contains_table_summary(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
        },
    )

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report["writtenTables"] == 1
    assert record.layout_executor_report["tableRows"] == 1


def test_generate_task_output_keeps_table_summary_in_quality_report(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.image_files = [image]
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "data_record_table",
            "data": {"rows": [["1", "voltage", "24V", "ok"]]},
        },
    )
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    layout_report = record.quality_report["layoutExecutor"]
    assert layout_report["writtenTables"] == 1
    assert layout_report["tableRows"] == 1


def test_build_revised_docx_respects_table_selection(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
            "source": "table_planner",
        },
    )
    record.table_selection = {"table_0": False}

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report["writtenTables"] == 0


def test_shadow_gate_uses_effective_layout_plan_after_table_selection(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
            "source": "table_planner",
        },
    )
    record.table_selection = {"table_0": False}

    result = run_pre_generation_shadow_gate(record)

    assert result["passed"] is True
    assert result["summary"]["table_count"] == 0


def test_build_revised_docx_writes_auto_planned_table(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "title": "Table 1 I/O Assignment",
            "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
            "source": "table_planner",
        },
    )

    output = build_revised_docx(record)
    doc = Document(output)
    body_cell = doc.tables[0].cell(1, 0)

    assert output.exists()
    assert len(body_cell.tables) >= 1
    assert record.layout_executor_report["writtenTables"] >= 1


def test_quality_report_counts_auto_planned_tables(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.image_files = [image]
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
            "source": "table_planner",
        },
    )
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    assert record.quality_report["layoutExecutor"]["writtenTables"] >= 1


def test_quality_report_counts_paired_images(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 2,
            "imageMetas": [
                {"filename": "first.png", "category": "basic_program"},
                {"filename": "second.png", "category": "basic_program"},
            ],
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    first = record.upload_dir / "first.png"
    second = record.upload_dir / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    record.image_files = [first, second]
    _attach_preview(record)
    image_blocks = []
    for section in record.preview_layout_plan["sections"]:
        if section.get("title") == "五、程序设计与梯形图":
            for block in section.get("blocks") or []:
                if isinstance(block, dict) and block.get("type") == "image":
                    block["sizePolicy"] = "program_small"
                    image_blocks.append(block)
    assert len(image_blocks) == 2
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    report = record.quality_report["layoutExecutor"]
    assert report["pairedImages"] == 2
    assert report["imageRows"] == 1


def test_degraded_image_count_in_layout_executor_report(tmp_path: Path) -> None:
    record = _build_record(tmp_path, image_bytes=b"not-a-real-png")
    _attach_preview(record)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report is not None
    assert record.layout_executor_report["degradedImages"] == 1
    assert record.layout_executor_report["writtenImages"] == 0


def test_table_audit_report_records_planned_tables(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "title": "Table 1 I/O Assignment",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )

    audit = build_table_audit_report(record)

    assert audit["plannedTables"]
    first = audit["plannedTables"][0]
    assert first["tableId"].startswith("table_")
    assert first["schema"] == "io_assignment_table"
    assert first["title"] == "Table 1 I/O Assignment"
    assert first["rowCount"] == 1


def test_table_audit_report_marks_user_unselected_tables(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_selection = {"table_0": False}

    audit = build_table_audit_report(record)

    assert audit["plannedTables"][0]["selected"] is False
    assert audit["plannedTables"][0]["status"] == "user_unselected"
    assert audit["summary"]["unselectedCount"] == 1


def test_table_audit_report_counts_selected_tables(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )

    audit = build_table_audit_report(record)

    assert audit["summary"]["plannedCount"] == 1
    assert audit["summary"]["selectedCount"] == 1
    assert audit["summary"]["unselectedCount"] == 0


def test_table_audit_report_merges_executor_written_tables(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    executor_report = {
        "used": True,
        "fallbackUsed": False,
        "warnings": [],
        "errors": [],
        "writtenTables": 1,
        "tableRows": 1,
    }

    audit = build_table_audit_report(record, executor_report=executor_report)

    assert audit["summary"]["writtenTables"] == 1
    assert audit["summary"]["tableRows"] == 1


def test_quality_report_contains_table_audit(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    record.report_file = _make_docx(record.upload_dir / "report.docx", "old body")
    record.guide_file = _make_docx(record.upload_dir / "guide.docx", "guide body")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.image_files = [image]
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    assert "tableAudit" in record.quality_report
    assert "plannedTables" in record.quality_report["tableAudit"]
    assert "summary" in record.quality_report["tableAudit"]


def test_build_revised_docx_table_audit_respects_selection(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_selection = {"table_0": False}

    output = build_revised_docx(record)

    assert output.exists()
    assert record.table_audit_report is not None
    assert record.table_audit_report["summary"]["plannedCount"] == 1
    assert record.table_audit_report["summary"]["writtenTables"] == 0
    assert record.table_audit_report["plannedTables"][0]["status"] == "user_unselected"


def test_legacy_fallback_table_audit_marks_fallback(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.table_audit_report is not None
    assert record.table_audit_report["summary"]["legacyFallback"] is True


def test_build_revised_docx_uses_edited_table_rows(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_edits = {
        "table_0": [["input", "I0.0", "edited button", "edited control"]]
    }

    output = build_revised_docx(record)
    doc = Document(output)
    body_cell = doc.tables[0].cell(1, 0)

    assert output.exists()
    assert body_cell.tables[0].rows[1].cells[2].text == "edited button"


def test_table_edits_do_not_modify_headers_or_schema(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    original_schema = record.preview_layout_plan["sections"][0]["blocks"][0]["schema"]
    record.table_edits = {
        "table_0": [["input", "I0.0", "edited button", "edited control"]]
    }

    output = build_revised_docx(record)
    doc = Document(output)
    body_cell = doc.tables[0].cell(1, 0)

    assert output.exists()
    assert record.preview_layout_plan["sections"][0]["blocks"][0]["schema"] == original_schema
    assert body_cell.tables[0].rows[0].cells[0].text == get_table_schema("io_assignment_table")["headers"][0]


def test_table_selection_false_still_excludes_edited_table(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_edits = {
        "table_0": [["input", "I0.0", "edited button", "edited control"]]
    }
    record.table_selection = {"table_0": False}

    output = build_revised_docx(record)

    assert output.exists()
    assert record.layout_executor_report["writtenTables"] == 0


def test_table_audit_marks_edited_tables(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_edits = {
        "table_0": [["input", "I0.0", "edited button", "edited control"]]
    }

    output = build_revised_docx(record)

    assert output.exists()
    assert record.table_audit_report["plannedTables"][0]["edited"] is True
    assert record.table_audit_report["summary"]["editedCount"] == 1


def test_table_audit_marks_edited_but_unselected_table(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_layout_plan["sections"][0]["blocks"].insert(
        0,
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["input", "I0.0", "start button", "start control"]]},
            "source": "table_planner",
        },
    )
    record.table_edits = {
        "table_0": [["input", "I0.0", "edited button", "edited control"]]
    }
    record.table_selection = {"table_0": False}

    output = build_revised_docx(record)

    assert output.exists()
    planned = record.table_audit_report["plannedTables"][0]
    assert planned["edited"] is True
    assert planned["status"] == "user_unselected"
    assert record.table_audit_report["summary"]["writtenTables"] == 0


def test_manual_table_written_to_docx(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.manual_tables = [
        {
            "tableId": "manual_table_0",
            "title": "自定义记录表",
            "headers": ["项目", "内容", "备注"],
            "data": {"rows": [["A", "B", "C"]]},
            "selected": True,
            "source": "manual",
        }
    ]

    output = build_revised_docx(record)
    doc = Document(output)
    body_cell = doc.tables[0].cell(1, 0)
    table_text = "\n".join(
        cell.text
        for table in body_cell.tables
        for row in table.rows
        for cell in row.cells
    )
    body_text = "\n".join(paragraph.text for paragraph in body_cell.paragraphs)

    assert "自定义记录表" in body_text
    assert "A" in table_text


def test_manual_table_in_table_audit(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.manual_tables = [
        {
            "tableId": "manual_table_0",
            "title": "自定义记录表",
            "headers": ["项目", "内容", "备注"],
            "data": {"rows": [["A", "B", "C"]]},
            "selected": True,
            "source": "manual",
        }
    ]

    build_revised_docx(record)

    assert record.table_audit_report["summary"]["manualCount"] == 1


def test_manual_table_selection_false_not_written(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.manual_tables = [
        {
            "tableId": "manual_table_0",
            "title": "自定义记录表",
            "headers": ["项目", "内容", "备注"],
            "data": {"rows": [["A", "B", "C"]]},
            "selected": False,
            "source": "manual",
        }
    ]
    record.table_selection = {"manual_table_0": False}

    output = build_revised_docx(record)
    doc = Document(output)
    body_cell = doc.tables[0].cell(1, 0)
    table_text = "\n".join(
        cell.text
        for table in body_cell.tables
        for row in table.rows
        for cell in row.cells
    )

    assert "自定义记录表" not in table_text
