from base64 import b64decode

import pytest
from docx import Document

from backend.app.services.layout_executor import append_layout_plan_content
from backend.app.services.layout_validator import LayoutValidationError, validate_layout_plan
from backend.app.services.table_schema import get_table_schema
from backend.app.services.table_writer import append_table_block


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_layout_executor_writes_paragraph_blocks(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Purpose", "blocks": [{"type": "paragraph", "content": "Understand PLC sequencing."}]},
            {"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "Program diagram", "imageType": "program"}]},
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [image])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Purpose" in text
    assert "Understand PLC sequencing." in text
    assert result["writtenBlocks"] == 2
    assert result["warnings"] == []


def test_layout_executor_inserts_image_blocks(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "Program diagram", "imageType": "program"}]}
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [image])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Program diagram" in text
    assert len(doc.inline_shapes) == 1
    assert result["writtenImages"] == 1


def test_layout_executor_records_warning_blocks(tmp_path) -> None:
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Result",
                "blocks": [
                    {"type": "warning", "message": "Needs manual review."},
                    {"type": "paragraph", "content": "Normal body."},
                ],
            }
        ],
        "warnings": ["Needs manual review."],
    }

    result = append_layout_plan_content(doc, layout_plan, [])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Needs manual review." not in text
    assert "Normal body." in text
    assert any("Needs manual review." in warning for warning in result["warnings"])


def test_layout_executor_writes_table_block(tmp_path) -> None:
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "schema": "io_assignment_table",
                        "data": {
                            "rows": [
                                ["输入", "I0.0", "启动按钮", "控制系统启动"],
                                ["输出", "Q0.0", "运行指示灯", "显示运行状态"],
                            ]
                        },
                    },
                    {"type": "paragraph", "content": "Table comes later."},
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Table comes later." in text
    assert result["writtenTables"] == 1
    assert result["tableRows"] == 2
    assert len(doc.tables) == 1
    assert doc.tables[0].rows[0].cells[0].text == "类型"
    assert result["errors"] == []


def test_layout_executor_rejects_invalid_table_block(tmp_path) -> None:
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "schema": "io_assignment_table",
                        "data": {"rows": [["输入", "I0.0", "启动按钮"]]},
                    }
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [])

    assert result["errors"]
    assert any("column count" in error.lower() for error in result["errors"])
    assert len(doc.tables) == 0


def test_layout_executor_rejects_unknown_table_schema(tmp_path) -> None:
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "schema": "unknown_schema",
                        "data": {"rows": [["1", "A", "10", "note"]]},
                    }
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [])

    assert any("unknown table schema" in error.lower() for error in result["errors"])
    assert len(doc.tables) == 0


def test_layout_executor_uses_global_caption_numbers_and_original_image_indices(tmp_path) -> None:
    skipped = tmp_path / "skip.png"
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    for image in [skipped, first, second]:
        image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Process", "blocks": [{"type": "image", "imageIndex": 1, "caption": "Wiring image", "imageType": "wiring"}]},
            {"title": "Result", "blocks": [{"type": "image", "imageIndex": 2, "caption": "Result image", "imageType": "result"}]},
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [skipped, first, second])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "1 Wiring image" in text
    assert "2 Result image" in text
    assert len(doc.inline_shapes) == 2
    assert result["writtenImages"] == 2


def test_layout_executor_can_write_inside_table_cell(tmp_path) -> None:
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    layout_plan = {
        "schemaVersion": 1,
        "sections": [{"title": "Purpose", "blocks": [{"type": "paragraph", "content": "Write inside table cell."}]}],
        "warnings": [],
    }

    result = append_layout_plan_content(cell, layout_plan, [])

    assert "Purpose" in cell.text
    assert "Write inside table cell." in cell.text
    assert result["writtenBlocks"] == 1


def test_layout_executor_degrades_to_text_when_image_insert_fails(tmp_path) -> None:
    bad_image = tmp_path / "bad.png"
    bad_image.write_bytes(b"not a real png")
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [{"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "Broken image", "imageType": "program"}]}],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [bad_image])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Broken image" in text
    assert "bad.png" in text
    assert len(doc.inline_shapes) == 0
    assert result["degradedImages"] == 1


def test_layout_validator_rejects_executor_unknown_image_reference(tmp_path) -> None:
    layout_plan = {
        "schemaVersion": 1,
        "sections": [{"title": "Program", "blocks": [{"type": "image", "imageIndex": 3, "caption": "Missing image"}]}],
        "warnings": [],
    }

    with pytest.raises(LayoutValidationError, match="unknown imageIndex"):
        validate_layout_plan(layout_plan, valid_image_indices={0})


def test_layout_executor_pairs_two_small_images(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "Left program", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "image", "imageIndex": 1, "caption": "Right program", "imageType": "program", "sizePolicy": "program_small"},
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [first, second])

    assert result["writtenImages"] == 2
    assert result["pairedImages"] == 2
    assert result["imageRows"] == 1
    assert len(doc.tables) == 1
    assert len(doc.tables[0].rows) == 1
    assert len(doc.tables[0].rows[0].cells) == 2
    assert "Left program" in doc.tables[0].cell(0, 0).text
    assert "Right program" in doc.tables[0].cell(0, 1).text


def test_layout_executor_does_not_pair_large_images(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Result",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "Large result 1", "imageType": "result", "sizePolicy": "phenomenon"},
                    {"type": "image", "imageIndex": 1, "caption": "Large result 2", "imageType": "result", "sizePolicy": "phenomenon"},
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [first, second])

    assert result["writtenImages"] == 2
    assert result["pairedImages"] == 0
    assert result["imageRows"] == 0
    assert len(doc.tables) == 0
    assert len(doc.inline_shapes) == 2


def test_layout_executor_pairs_only_within_same_section(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "Section one", "imageType": "program", "sizePolicy": "program_small"}]},
            {"title": "Result", "blocks": [{"type": "image", "imageIndex": 1, "caption": "Section two", "imageType": "program", "sizePolicy": "program_small"}]},
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [first, second])

    assert result["pairedImages"] == 0
    assert result["imageRows"] == 0
    assert len(doc.tables) == 0
    assert len(doc.inline_shapes) == 2


def test_layout_executor_does_not_pair_across_paragraph(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "First image", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "paragraph", "content": "Break the group."},
                    {"type": "image", "imageIndex": 1, "caption": "Second image", "imageType": "program", "sizePolicy": "program_small"},
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [first, second])

    assert result["pairedImages"] == 0
    assert result["imageRows"] == 0
    assert len(doc.tables) == 0
    assert len(doc.inline_shapes) == 2


def test_image_pair_table_has_no_borders(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "Left", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "image", "imageIndex": 1, "caption": "Right", "imageType": "program", "sizePolicy": "program_small"},
                ],
            }
        ],
        "warnings": [],
    }

    append_layout_plan_content(doc, layout_plan, [first, second])

    tbl_borders = doc.tables[0]._tbl.tblPr.first_child_found_in("w:tblBorders")
    assert tbl_borders is not None
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tbl_borders.find(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{edge}")
        assert border is not None
        assert border.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "none"


def test_data_table_still_has_black_borders() -> None:
    doc = Document()
    schema = get_table_schema("io_assignment_table")
    block = {
        "type": "table",
        "schema": "io_assignment_table",
        "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
    }

    append_table_block(doc, block, schema, table_index=1)

    tbl_borders = doc.tables[0]._tbl.tblPr.first_child_found_in("w:tblBorders")
    assert tbl_borders is not None
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tbl_borders.find(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{edge}")
        assert border is not None
        assert border.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "single"
        assert border.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color") == "000000"


def test_layout_executor_single_leftover_image_remains_single(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    third = tmp_path / "third.png"
    for image in (first, second, third):
        image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "First", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "image", "imageIndex": 1, "caption": "Second", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "image", "imageIndex": 2, "caption": "Third", "imageType": "program", "sizePolicy": "program_small"},
                ],
            }
        ],
        "warnings": [],
    }

    result = append_layout_plan_content(doc, layout_plan, [first, second, third])

    assert result["writtenImages"] == 3
    assert result["pairedImages"] == 2
    assert result["imageRows"] == 1
    assert len(doc.tables) == 1
    assert len(doc.inline_shapes) == 3


def test_image_caption_keeps_chinese_text(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "PLC 控制程序图", "imageType": "program"}]}
        ],
        "warnings": [],
    }

    append_layout_plan_content(doc, layout_plan, [image])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "PLC 控制程序图" in text


def test_image_caption_does_not_use_temp_path(tmp_path) -> None:
    image = tmp_path / "wxfile_tmp_123.png"
    image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Result", "blocks": [{"type": "image", "imageIndex": 0, "caption": "wxfile://tmp_xxx.png", "imageType": "other"}]}
        ],
        "warnings": [],
    }

    append_layout_plan_content(doc, layout_plan, [image])

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "wxfile://tmp_xxx.png" not in text
    assert "实验图片" in text


def test_paired_image_caption_uses_safe_caption(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [
                    {"type": "image", "imageIndex": 0, "caption": "PLC 控制程序图", "imageType": "program", "sizePolicy": "program_small"},
                    {"type": "image", "imageIndex": 1, "caption": "wxfile://tmp_2.png", "imageType": "program", "sizePolicy": "program_small"},
                ],
            }
        ],
        "warnings": [],
    }

    append_layout_plan_content(doc, layout_plan, [first, second])

    assert "PLC 控制程序图" in doc.tables[0].cell(0, 0).text
    assert "PLC 控制程序图" in doc.tables[0].cell(0, 1).text


def test_image_caption_font_is_set_for_chinese(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    doc = Document()
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Program", "blocks": [{"type": "image", "imageIndex": 0, "caption": "PLC 控制程序图", "imageType": "program"}]}
        ],
        "warnings": [],
    }

    append_layout_plan_content(doc, layout_plan, [image])

    caption_run = doc.paragraphs[-1].runs[0]
    assert caption_run._element.rPr.rFonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia") == "宋体"
