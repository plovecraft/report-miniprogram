from base64 import b64decode
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

from backend.app.services.docx_builder import build_fallback_sections, build_report_preview, build_revised_docx
from backend.app.services.experiment_config_loader import ExperimentConfig, load_experiment_config
from backend.app.services.image_classifier import classify_image, classify_image_info, group_images_by_section, image_width_cm
from backend.app.services.task_store import TaskRecord


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_loads_plc_experiment_config() -> None:
    config = load_experiment_config("plc")

    assert config.experiment_type == "plc"
    assert config.display_name == "PLC 实验报告"
    assert config.default_sections[:2] == ["一、实验目的", "二、实验设备"]
    assert config.image_types["program"]["section"] == "五、程序设计与梯形图"
    assert config.category_overrides["basic_program"]["caption"] == "基础题梯形图程序"
    assert config.allowed_tables


def test_plc_experiment_config_falls_back_when_config_file_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "backend.app.services.experiment_config_loader.CONFIG_ROOT",
        tmp_path / "missing-configs",
    )

    config = load_experiment_config("plc")

    assert config.experiment_type == "plc"
    assert config.display_name == "PLC 实验报告"
    assert config.default_sections == [
        "一、实验目的",
        "二、实验设备",
        "三、实验要求",
        "四、实验操作过程",
        "五、程序设计与梯形图",
        "六、实验结果",
        "七、实验心得",
    ]


def test_report_preview_uses_plc_config_metadata_and_keeps_image_plan(tmp_path: Path) -> None:
    image = tmp_path / "程序图1.png"
    image.write_bytes(b"image bytes")
    record = TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "实验四",
            "imageMetas": [{"filename": "程序图1.png", "category": "basic_program"}],
        },
        root_dir=tmp_path,
        image_files=[image],
    )

    preview = build_report_preview(record)

    assert preview["experimentType"] == "plc"
    assert preview["experimentTypeName"] == "PLC 实验报告"
    assert preview["experimentName"] == "实验四"
    assert [section["title"] for section in preview["sections"]] == [
        "一、实验目的",
        "二、实验设备",
        "三、实验要求",
        "四、实验操作过程",
        "五、程序设计与梯形图",
        "六、实验结果",
        "七、实验心得",
    ]
    image = preview["imagePlan"][0]
    assert image["imageIndex"] == 0
    assert image["filename"].endswith(".png")
    assert image["type"] == "program"
    assert image["section"] == preview["sections"][4]["title"]
    assert image["caption"] == preview["sections"][4]["images"][0]["caption"]
    assert image["sortOrder"] == 0
    assert image["recognized"] is True
    assert image["schema_version"] == "image-plan.v1"
    assert image["category"] == "basic_program"
    assert image["categoryCn"] == image["category_cn"]
    assert image["needsReview"] is False
    assert preview["insertedImageCount"] == 1


def test_report_preview_builds_and_validates_internal_layout_plan(monkeypatch, tmp_path: Path) -> None:
    called = {}

    def fake_validate(layout_plan, valid_image_indices):
        called["layout_plan"] = layout_plan
        called["valid_image_indices"] = valid_image_indices

    monkeypatch.setattr("backend.app.services.docx_builder.validate_layout_plan", fake_validate)

    image = tmp_path / "程序图1.png"
    image.write_bytes(b"image bytes")
    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "实验四"},
        root_dir=tmp_path,
        image_files=[image],
    )

    preview = build_report_preview(record)

    assert called["layout_plan"]["experimentName"] == "实验四"
    assert called["layout_plan"]["schemaVersion"] == 1
    assert called["layout_plan"]["sections"][4]["blocks"][0]["type"] == "image"
    assert called["valid_image_indices"] == {0}
    assert "layoutPlan" not in preview


def test_classifies_experiment_images_by_filename() -> None:
    assert classify_image("程序图 实验四.png") == "program"
    assert classify_image("接线图.jpg") == "wiring"
    assert classify_image("实物图 运行状态.jpeg") == "physical"
    assert classify_image("现象记录.png") == "result"
    assert classify_image("随手拍.png") == "other"


def test_classifies_images_with_section_and_caption_by_filename(tmp_path: Path) -> None:
    assert classify_image_info("天塔之光接线图.png").section == "四、实验操作过程"
    assert classify_image_info("天塔之光接线图.png").caption == "实验接线图"
    assert classify_image_info("程序图1_2.png").caption == "基础题梯形图程序（2）"
    assert classify_image_info("程序图2_1.png").caption == "思考题 1 梯形图程序（1）"
    assert classify_image_info("程序图3_1.png").caption == "思考题 2 梯形图程序（1）"
    assert classify_image_info("基础题现象.jpg").section == "六、实验结果"
    assert classify_image_info("基础题现象.jpg").caption == "基础题运行现象"
    assert classify_image_info("思考题1现象.jpg").caption == "思考题 1 运行现象"
    assert classify_image_info("实物图.jpg").caption == "实验实物图"

    groups = group_images_by_section(
        [
            tmp_path / "天塔之光接线图.png",
            tmp_path / "程序图1_1.png",
            tmp_path / "基础题现象.jpg",
            tmp_path / "随手拍.png",
        ]
    )

    assert [item.caption for item in groups["四、实验操作过程"]] == ["实验接线图"]
    assert [item.caption for item in groups["五、程序设计与梯形图"]] == ["基础题梯形图程序（1）"]
    assert [item.caption for item in groups["六、实验结果"]] == ["基础题运行现象", "随手拍"]


def test_image_classifier_uses_experiment_config_for_category_overrides_and_widths(monkeypatch) -> None:
    config = ExperimentConfig(
        experiment_type="plc",
        display_name="PLC 实验报告",
        default_sections=[],
        fallback_sections=[],
        fallback_image_labels={},
        fallback_no_images_text="",
        image_types={"program": {"section": "配置程序章节", "widthCm": 7.2}},
        category_overrides={
            "basic_program": {
                "type": "program",
                "section": "配置程序章节",
                "caption": "配置图注",
            }
        },
        allowed_tables=[],
        keywords=[],
    )
    monkeypatch.setattr("backend.app.services.image_classifier.load_experiment_config", lambda *_: config)

    placement = classify_image_info("任意文件名.png", "basic_program")

    assert placement is not None
    assert placement.type == "program"
    assert placement.section == "配置程序章节"
    assert placement.caption == "配置图注"
    assert image_width_cm("program") == 7.2


def test_fallback_sections_use_experiment_config_templates_and_image_labels(monkeypatch, tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    guide.write_bytes(b"guide")
    image = tmp_path / "程序图1.png"
    image.write_bytes(b"image")
    record = TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "实验四",
            "studentName": "张三",
            "studentId": "20260001",
            "className": "机器234",
        },
        root_dir=tmp_path,
        guide_file=guide,
        image_files=[image],
    )
    config = SimpleNamespace(
        fallback_sections=[
            {
                "title": "配置章节一",
                "paragraphTemplates": ["指导书={guideName}; 实验={experimentNo}"],
            },
            {
                "title": "配置图片章节",
                "content": "image_summary",
            },
            {
                "title": "配置信息章节",
                "paragraphTemplates": ["{studentName}/{studentId}/{className}"],
            },
        ],
        fallback_image_labels={"program": "配置程序图"},
        fallback_no_images_text="配置无图片",
    )
    monkeypatch.setattr("backend.app.services.docx_builder.load_experiment_config", lambda *_: config)

    sections = build_fallback_sections(record)

    assert sections == [
        ("配置章节一", ["指导书=guide.docx; 实验=实验四"]),
        ("配置图片章节", ["配置程序图：程序图1.png"]),
        ("配置信息章节", ["张三/20260001/机器234"]),
    ]


def test_writes_report_sections_inside_template_body_cell(tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(0, 0).text = "学生信息表头"
    table.cell(1, 0).text = "原正文区域"
    doc.save(source)

    image = upload_dir / "程序图 实验四.png"
    image.write_bytes(b"fake image")
    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")

    record = TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "实验四",
            "studentName": "张三",
            "studentId": "20260001",
            "className": "自动化一班",
        },
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)

    original_doc = Document(source)
    assert "一、实验目的" not in original_doc.tables[0].cell(1, 0).text

    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(1, 0).text
    whole_doc_paragraph_text = "\n".join(p.text for p in output_doc.paragraphs)

    assert "原正文区域" not in body_text
    assert "一、实验目的" in body_text
    assert "实验四" in body_text
    assert "程序图 实验四.png" in body_text
    assert "一、实验目的" not in whole_doc_paragraph_text


def test_rebuilds_template_body_cell_and_removes_stale_report_content(tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(0, 0).text = "学生信息表头"
    stale_cell = table.cell(1, 0)
    stale_cell.text = "实验一 旧交通灯内容"
    stale_cell.add_paragraph("旧心得：本实验与实验三无关")
    doc.save(source)

    image = upload_dir / "程序图 实验三.png"
    image.write_bytes(PNG_1X1)
    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "实验三", "studentName": "张三"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)
    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(1, 0).text

    assert "实验一 旧交通灯内容" not in body_text
    assert "旧心得" not in body_text
    assert "一、实验目的" in body_text
    assert "实验三" in body_text
    assert "程序图 实验三.png" in body_text


def test_inserts_valid_images_with_captions_inside_template_body_cell(tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(0, 0).text = "学生信息表头"
    table.cell(1, 0).text = "原正文区域"
    doc.save(source)

    image = upload_dir / "程序图 实验四.png"
    image.write_bytes(PNG_1X1)
    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "实验四"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)

    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(1, 0).text
    assert len(output_doc.inline_shapes) == 1
    assert "图 1 梯形图程序" in body_text


def test_inserts_images_into_matching_report_sections(tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=4, cols=1)
    table.cell(0, 0).text = "学生信息表头"
    table.cell(3, 0).text = "旧正文区域"
    doc.save(source)

    image_names = [
        "天塔之光接线图.png",
        "程序图1_1.png",
        "程序图2_1.png",
        "基础题现象.jpg",
        "思考题1现象.jpg",
        "实物图.jpg",
    ]
    image_files = []
    for name in image_names:
        image = upload_dir / name
        image.write_bytes(PNG_1X1)
        image_files.append(image)

    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "实验三"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=image_files,
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)

    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(3, 0).text
    assert len(output_doc.inline_shapes) == len(image_names)
    assert "实验接线图" in body_text
    assert "基础题梯形图程序（1）" in body_text
    assert "思考题 1 梯形图程序（1）" in body_text
    assert "基础题运行现象" in body_text
    assert "思考题 1 运行现象" in body_text
    assert "实验实物图" in body_text


def test_user_image_category_overrides_filename_and_can_skip_images(tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=4, cols=1)
    table.cell(3, 0).text = "旧正文区域"
    doc.save(source)

    result_image = upload_dir / "程序图1_1.png"
    result_image.write_bytes(PNG_1X1)
    skipped_image = upload_dir / "实物图.jpg"
    skipped_image.write_bytes(PNG_1X1)
    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")

    record = TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "实验三",
            "imageMetas": [
                {"filename": "程序图1_1.png", "category": "basic_result"},
                {"filename": "实物图.jpg", "category": "skip"},
            ],
        },
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[result_image, skipped_image],
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)

    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(3, 0).text
    assert len(output_doc.inline_shapes) == 1
    assert "基础题运行现象" in body_text
    assert "基础题梯形图程序" not in body_text
    assert "实验实物图" not in body_text


def test_preserves_guangzhou_table_and_updates_only_project_and_body_cell(tmp_path: Path) -> None:
    source = tmp_path / "guangzhou-template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    doc.add_paragraph("广州大学学生实验报告")
    table = doc.add_table(rows=4, cols=7)
    table.rows[0].cells[0].text = "学院"
    table.rows[0].cells[1].text = "机械与电气工程学院"
    table.rows[1].cells[0].text = "课程名称"
    table.rows[1].cells[1].text = "可编程控制器"
    table.rows[2].cells[0].text = "实验项目名称"
    table.rows[2].cells[1].text = "旧实验项目"
    table.rows[2].cells[2].text = "指导老师"
    table.rows[2].cells[3].text = "李老师"
    for index in range(4, 7):
        table.rows[2].cells[index].text = ""
    body_cell = table.rows[3].cells[0]
    for index in range(1, 7):
        body_cell = body_cell.merge(table.rows[3].cells[index])
    body_cell.text = "实验一 旧正文"
    body_cell.add_paragraph("旧图片说明：图 1")
    doc.save(source)

    guide = upload_dir / "guide.docx"
    guide_doc = Document()
    guide_doc.add_paragraph("实验三 天塔之光模拟控制")
    guide_doc.add_paragraph("掌握移位寄存器指令。")
    guide_doc.save(guide)

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "实验三", "studentName": "张三"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[],
    )
    record.output_dir.mkdir(parents=True)

    output = build_revised_docx(record)

    original_doc = Document(source)
    original_table = original_doc.tables[0]
    assert original_table.rows[2].cells[1].text == "旧实验项目"
    assert original_table.rows[2].cells[3].text == "李老师"
    assert "实验一 旧正文" in original_table.rows[3].cells[0].text

    output_doc = Document(output)
    output_table = output_doc.tables[0]
    assert len(output_table.rows) == 4
    assert output_table.rows[0].cells[1].text == "机械与电气工程学院"
    assert output_table.rows[1].cells[1].text == "可编程控制器"
    assert output_table.rows[2].cells[0].text == "实验项目名称"
    assert output_table.rows[2].cells[1].text == "实验三"
    assert output_table.rows[2].cells[2].text == "指导老师"
    assert output_table.rows[2].cells[3].text == "李老师"
    revised_body = output_table.rows[3].cells[0]
    assert revised_body.vertical_alignment == WD_CELL_VERTICAL_ALIGNMENT.TOP
    assert "实验一 旧正文" not in revised_body.text
    assert "旧图片说明" not in revised_body.text
    assert "一、实验目的" in revised_body.text
    assert "实验三" in revised_body.text


def test_build_revised_docx_fills_optional_header_fields_and_current_date(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=4, cols=8)
    table.rows[0].cells[0].text = "用户学院"
    table.rows[0].cells[1].text = "原用户学院"
    table.rows[0].cells[2].text = "班级"
    table.rows[0].cells[3].text = "原班级"
    table.rows[1].cells[0].text = "课程名称"
    table.rows[1].cells[1].text = "原课程"
    table.rows[1].cells[2].text = "开课学院及实验室"
    table.rows[1].cells[3].text = "原实验室"
    table.rows[1].cells[4].text = "日期"
    table.rows[1].cells[5].text = "旧日期"
    table.rows[2].cells[0].text = "指导老师"
    table.rows[2].cells[1].text = "原老师"
    table.rows[3].cells[0].text = "旧正文"
    doc.save(source)

    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"fake guide")
    monkeypatch.setattr("backend.app.services.docx_builder._current_date_string", lambda: "2026年05月07日")

    record = TaskRecord(
        task_id="task-1",
        metadata={
            "experimentNo": "实验三",
            "courseName": "可编程控制器",
            "teacherName": "李老师",
            "offeringCollegeLab": "自动化学院 PLC 实验室",
            "studentCollege": "机械与电气工程学院",
            "className": "机器234",
        },
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[],
    )
    record.output_dir.mkdir(parents=True)

    output_doc = Document(build_revised_docx(record))
    output_table = output_doc.tables[0]

    assert output_table.rows[0].cells[1].text == "机械与电气工程学院"
    assert output_table.rows[0].cells[3].text == "机器234"
    assert output_table.rows[1].cells[1].text == "可编程控制器"
    assert output_table.rows[1].cells[3].text == "自动化学院 PLC 实验室"
    assert output_table.rows[1].cells[5].text == "2026年05月07日"
    assert output_table.rows[2].cells[1].text == "李老师"
def test_build_revised_docx_uses_preview_layout_plan_when_available(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(source)

    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"guide")
    image = upload_dir / "program.png"
    image.write_bytes(PNG_1X1)

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "Experiment 3", "imageMetas": [{"filename": "program.png", "category": "basic_program"}]},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)
    preview = build_report_preview(record)
    record.preview_data = preview

    def fail_if_legacy_used(*args, **kwargs):
        raise AssertionError("legacy append_report_content should not be used when preview_layout_plan exists")

    monkeypatch.setattr("backend.app.services.docx_builder.append_report_content", fail_if_legacy_used)

    output = build_revised_docx(record)

    output_doc = Document(output)
    body_text = output_doc.tables[0].cell(1, 0).text
    assert "Experiment 3" in body_text
    assert record.shadow_gate_report is not None
    assert record.shadow_gate_report["skipped"] is False


def test_build_revised_docx_falls_back_without_preview_layout_plan(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(source)

    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"guide")
    image = upload_dir / "program.png"
    image.write_bytes(PNG_1X1)

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "Experiment 3"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)

    def fail_if_executor_used(*args, **kwargs):
        raise AssertionError("layout executor should not be used without preview_layout_plan")

    monkeypatch.setattr("backend.app.services.docx_builder.append_layout_plan_content", fail_if_executor_used)

    output = build_revised_docx(record)

    assert output.exists()
    assert record.shadow_gate_report is not None
    assert record.shadow_gate_report["skipped"] is True
    assert record.layout_executor_report is not None
    assert record.layout_executor_report["used"] is False
    assert record.layout_executor_report["fallbackUsed"] is True
    assert "preview_layout_plan missing" in str(record.layout_executor_report["fallbackReason"])


def test_append_report_content_is_legacy_only(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "template.docx"
    output_root = tmp_path / "task"
    upload_dir = output_root / "uploads"
    upload_dir.mkdir(parents=True)

    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "old body"
    doc.save(source)

    guide = upload_dir / "guide.docx"
    guide.write_bytes(b"guide")
    image = upload_dir / "program.png"
    image.write_bytes(PNG_1X1)

    record = TaskRecord(
        task_id="task-1",
        metadata={"experimentNo": "Experiment 3"},
        root_dir=output_root,
        report_file=source,
        guide_file=guide,
        image_files=[image],
    )
    record.output_dir.mkdir(parents=True)

    calls = {"legacy": 0}
    from backend.app.services import docx_builder as docx_builder_module

    original_legacy = docx_builder_module.append_report_content

    def track_legacy(*args, **kwargs):
        calls["legacy"] += 1
        return original_legacy(*args, **kwargs)

    monkeypatch.setattr("backend.app.services.docx_builder.append_report_content", track_legacy)

    preview = build_report_preview(record)
    record.preview_data = preview
    build_revised_docx(record)
    assert calls["legacy"] == 0

    record.preview_layout_plan = None
    record.preview_data = None
    record.output_file = None
    build_revised_docx(record)
    assert calls["legacy"] == 1
