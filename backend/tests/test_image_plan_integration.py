from io import BytesIO
from pathlib import Path

from docx import Document
from PIL import Image

from backend.app.services import image_recognizer
from backend.app.services.docx_builder import build_report_preview, build_revised_docx
from backend.app.services.task_store import TaskRecord


def _png_bytes(color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    buf = BytesIO()
    image = Image.new("RGB", (64, 64), color)
    image.save(buf, format="PNG")
    return buf.getvalue()


def _docx(path: Path, text: str) -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def _record(tmp_path: Path, *, image_name: str = "program.png", image_bytes: bytes | None = None) -> TaskRecord:
    root_dir = tmp_path / "task"
    upload_dir = root_dir / "uploads"
    output_dir = root_dir / "outputs"
    upload_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    report = _docx(upload_dir / "report.docx", "source report")
    guide = _docx(upload_dir / "guide.docx", "guide text")
    image = upload_dir / image_name
    image.write_bytes(image_bytes if image_bytes is not None else _png_bytes())
    return TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "Experiment 3", "imageCount": 1},
        root_dir=root_dir,
        report_file=report,
        guide_file=guide,
        image_files=[image],
    )


def test_image_plan_keeps_legacy_fields(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.91,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {"insert_section": "五、程序设计与梯形图", "caption": "PLC 控制程序图", "size_policy": "program"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert image["imageIndex"] == 0
    assert image["category"] == "program"
    assert image["categoryCn"] == "程序图"
    assert image["caption"] == "PLC 控制程序图"
    assert image["suggestedCaption"] == "PLC 控制程序图"
    assert image["insertSection"] == "五、程序设计与梯形图"
    assert image["sizePolicy"] == "program"
    assert image["needsReview"] is False


def test_review_image_marked_needs_review(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "unknown",
            "category_cn": "待确认",
            "confidence": 0.31,
            "review_level": "review",
            "review_reasons": ["low confidence"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "六、实验结果", "caption": "待确认图片", "size_policy": "other"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert image["reviewLevel"] == "review"
    assert image["needsReview"] is True
    assert preview["warnings"]


def test_reject_image_not_inserted_into_layout_plan(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "unknown",
            "category_cn": "待确认",
            "confidence": 0.0,
            "review_level": "reject",
            "review_reasons": ["INVALID_IMAGE"],
            "quality": {"readable": False, "needs_review": True},
            "suggested": {"insert_section": "六、实验结果", "caption": "待确认图片", "size_policy": "other"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    image_blocks = [
        block
        for section in record.preview_layout_plan["sections"]
        for block in section["blocks"]
        if block["type"] == "image"
    ]

    assert preview["imagePlan"][0]["type"] == "skip"
    assert image_blocks == []
    assert preview["rejectedImages"]


def test_suggested_caption_used_in_image_block(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.9,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {"insert_section": "五、程序设计与梯形图", "caption": "自定义程序图注", "size_policy": "program"},
            "features": {},
            "score_detail": {},
        },
    )

    build_report_preview(record)
    image_blocks = [
        block
        for section in record.preview_layout_plan["sections"]
        for block in section["blocks"]
        if block["type"] == "image"
    ]

    assert image_blocks[0]["caption"] == "自定义程序图注"


def test_suggested_insert_section_affects_image_placement(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "phenomenon",
            "category_cn": "实验现象图",
            "confidence": 0.88,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {"insert_section": "六、实验结果", "caption": "实验现象图", "size_policy": "phenomenon"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    sections = {section["title"]: section for section in preview["sections"]}

    assert sections["六、实验结果"]["images"][0]["caption"] == "实验现象图"


def test_preview_response_contains_review_fields(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.67,
            "review_level": "review",
            "review_reasons": ["small margin"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "五、程序设计与梯形图", "caption": "程序图", "size_policy": "program"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert "confidence" in image
    assert image["reviewLevel"] == "review"
    assert image["reviewReasons"] == ["small margin"]
    assert image["suggestedCaption"] == "程序图"


def test_bad_image_does_not_fail_preview(tmp_path: Path) -> None:
    record = _record(tmp_path, image_name="bad.png", image_bytes=b"not-an-image")

    preview = build_report_preview(record)

    assert preview["imagePlan"][0]["reviewLevel"] == "reject"
    assert preview["rejectedImages"]
    assert preview["sections"]


def test_build_revised_docx_skips_rejected_images(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "unknown",
            "category_cn": "待确认",
            "confidence": 0.0,
            "review_level": "reject",
            "review_reasons": ["INVALID_IMAGE"],
            "quality": {"readable": False, "needs_review": True},
            "suggested": {"insert_section": "六、实验结果", "caption": "待确认图片", "size_policy": "other"},
            "features": {},
            "score_detail": {},
        },
    )

    preview = build_report_preview(record)
    record.preview_data = preview
    output = build_revised_docx(record)
    doc = Document(output)

    assert len(doc.inline_shapes) == 0


def test_preview_includes_review_image(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "wxfile_tmp_123.png",
            "category": "unknown",
            "category_cn": "待确认",
            "confidence": 0.22,
            "review_level": "review",
            "review_reasons": ["unknown category requires manual review"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "四、实验操作过程", "caption": "实验图片", "size_policy": "default"},
            "features": {"width": 320, "height": 240},
            "score_detail": {"filename_score": 0.0, "visual_score": 0.2, "final_score": 0.22},
        },
    )

    preview = build_report_preview(record)

    assert preview["imagePlan"][0]["reviewLevel"] == "review"
    assert preview["imagePlan"][0]["needsReview"] is True
    image_blocks = [
        block
        for section in record.preview_layout_plan["sections"]
        for block in section["blocks"]
        if block["type"] == "image"
    ]
    assert image_blocks


def test_preview_runs_recognizer_even_with_meta_category(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path, image_name="random_upload.png")
    record.metadata["imageMetas"] = [{"filename": "random_upload.png", "category": "basic_program"}]

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "random_upload.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.83,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {"insert_section": "五、程序设计与梯形图", "caption": "PLC 程序图", "size_policy": "program"},
            "features": {"line_count": 12},
            "score_detail": {"visual_score": 0.83},
        },
    )

    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert image["confidence"] == 0.83
    assert image["score_detail"]["visual_score"] == 0.83
    assert image["features"]["line_count"] == 12


def test_preview_auto_category_does_not_override_recognition(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path, image_name="wxfile_tmp_123.png")
    record.metadata["imageMetas"] = [{"filename": "wxfile_tmp_123.png", "category": "auto"}]

    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "wxfile_tmp_123.png",
            "category": "program",
            "category_cn": "绋嬪簭鍥?",
            "confidence": 0.78,
            "review_level": "review",
            "review_reasons": ["small margin"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "浜斻€佺▼搴忚璁′笌姊舰鍥?", "caption": "PLC 绋嬪簭鍥?", "size_policy": "program"},
            "features": {"line_count": 10},
            "score_detail": {"visual_score": 0.78},
        },
    )

    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert image["category"] == "program"
    assert image["categoryCn"] == "绋嬪簭鍥?"
    assert image["reviewLevel"] == "review"
    assert image["confidence"] == 0.78


def test_image_plan_override_updates_caption(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)
    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.91,
            "review_level": "review",
            "review_reasons": ["low confidence"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "实验过程", "caption": "原始图注", "size_policy": "program"},
            "features": {},
            "score_detail": {},
        },
    )

    record.image_plan_overrides = {"image_0": {"caption": "PLC 主程序图"}}
    preview = build_report_preview(record)

    assert preview["imagePlan"][0]["caption"] == "PLC 主程序图"


def test_image_plan_override_updates_insert_section(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)
    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "program",
            "category_cn": "程序图",
            "confidence": 0.91,
            "review_level": "review",
            "review_reasons": ["low confidence"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "实验过程", "caption": "原始图注", "size_policy": "program"},
            "features": {},
            "score_detail": {},
        },
    )

    record.image_plan_overrides = {"image_0": {"insertSection": "实验结果"}}
    preview = build_report_preview(record)

    assert preview["imagePlan"][0]["section"] == "实验结果"


def test_review_image_override_marks_ok(monkeypatch, tmp_path: Path) -> None:
    record = _record(tmp_path)
    monkeypatch.setattr(
        image_recognizer,
        "recognize_image_file",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "program.png",
            "category": "unknown",
            "category_cn": "待确认",
            "confidence": 0.32,
            "review_level": "review",
            "review_reasons": ["low confidence"],
            "quality": {"readable": True, "needs_review": True},
            "suggested": {"insert_section": "实验过程", "caption": "实验图片", "size_policy": "default"},
            "features": {},
            "score_detail": {},
        },
    )

    record.image_plan_overrides = {"image_0": {"category": "program", "caption": "PLC 主程序图", "insertSection": "实验过程"}}
    preview = build_report_preview(record)
    image = preview["imagePlan"][0]

    assert image["reviewLevel"] == "ok"
    assert image["needsReview"] is False
    assert "user_override" in image["reviewReasons"]
