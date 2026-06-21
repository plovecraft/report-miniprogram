from base64 import b64decode
from pathlib import Path

import pytest
from docx import Document

from backend.app.main import generate_task_output, task_store
from backend.app.services.docx_builder import (
    build_report_preview,
    build_revised_docx,
    build_validated_layout_plan,
    run_pre_generation_shadow_gate,
)
from backend.app.services.task_store import TaskRecord


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _make_docx(path: Path, text: str) -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def _build_record(tmp_path: Path, *, image_bytes: bytes = PNG_1X1) -> TaskRecord:
    root_dir = tmp_path / "task"
    upload_dir = root_dir / "uploads"
    output_dir = root_dir / "outputs"
    upload_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    report = _make_docx(upload_dir / "report.docx", "Original report")
    guide = _make_docx(upload_dir / "guide.docx", "Experiment three guide")
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
    layout_plan = build_validated_layout_plan(preview)
    assert layout_plan is not None
    record.preview_data = preview
    record.preview_layout_plan = layout_plan


def _first_image_block(layout_plan: dict) -> dict:
    for section in layout_plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                return block
    raise AssertionError("expected at least one image block")


def test_generation_shadow_gate_passes_valid_plan(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)

    result = run_pre_generation_shadow_gate(record)

    assert result["passed"] is True
    assert result["errors"] == []
    assert record.shadow_gate_report == result


def test_generation_shadow_gate_blocks_unknown_image(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    _first_image_block(record.preview_layout_plan)["imageIndex"] = 99

    with pytest.raises(ValueError, match="Layout shadow check failed: .*unknown imageIndex"):
        run_pre_generation_shadow_gate(record)


def test_generation_shadow_gate_preserves_warnings(tmp_path: Path) -> None:
    record = _build_record(tmp_path)
    _attach_preview(record)
    record.preview_data["imagePlan"][0]["quality"] = {"needs_review": True}
    record.preview_data["imagePlan"][0]["confidence"] = 0.1

    result = run_pre_generation_shadow_gate(record)

    assert result["errors"] == []
    assert any("needs review" in warning.lower() for warning in result["warnings"])
    assert record.shadow_gate_report == result


def test_generation_shadow_gate_legacy_path_compatible(tmp_path: Path) -> None:
    record = _build_record(tmp_path)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.shadow_gate_report is not None
    assert record.shadow_gate_report["skipped"] is True
    assert any("shadow gate skipped" in warning.lower() for warning in record.shadow_gate_report["warnings"])


def test_generation_shadow_gate_warnings_are_kept_in_quality_report(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    record = task_store.create_task(
        {
            "experimentNo": "Experiment 3",
            "imageCount": 1,
            "imageMetas": [{"filename": "program.png", "category": "basic_program"}],
        }
    )
    report = _make_docx(record.upload_dir / "report.docx", "Original report")
    guide = _make_docx(record.upload_dir / "guide.docx", "Experiment three guide")
    image = record.upload_dir / "program.png"
    image.write_bytes(PNG_1X1)
    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    _attach_preview(record)
    record.preview_data["imagePlan"][0]["quality"] = {"needs_review": True}
    record.preview_data["imagePlan"][0]["confidence"] = 0.1
    task_store.mark_processing(record)

    generate_task_output(record.task_id)

    assert record.status == "done"
    assert record.quality_report is not None
    assert "shadowGate" in record.quality_report
    assert any("needs review" in warning.lower() for warning in record.quality_report["shadowGate"]["warnings"])
