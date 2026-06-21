from docx import Document
from docx.table import Table

from backend.app.services.table_schema import get_table_schema, validate_table_block
from backend.app.services.table_writer import append_table_block


def test_get_table_schema_known_schema() -> None:
    schema = get_table_schema("io_assignment_table")

    assert schema["title"] == "I/O 分配表"
    assert schema["headers"] == ["类型", "地址", "元件名称", "功能说明"]


def test_validate_table_block_rejects_unknown_schema() -> None:
    errors = validate_table_block(
        {
            "type": "table",
            "schema": "missing_schema",
            "data": {"rows": [["输入", "I0.0", "按钮", "启动"]]},
        }
    )

    assert any("unknown table schema" in error.lower() for error in errors)


def test_validate_table_block_rejects_wrong_column_count() -> None:
    errors = validate_table_block(
        {
            "type": "table",
            "schema": "io_assignment_table",
            "data": {"rows": [["输入", "I0.0", "按钮"]]},
        }
    )

    assert any("column count" in error.lower() for error in errors)


def test_append_table_block_writes_docx_table() -> None:
    doc = Document()
    block = {
        "type": "table",
        "schema": "io_assignment_table",
        "title": "表1 I/O 分配表",
        "data": {
            "rows": [
                ["输入", "I0.0", "启动按钮", "控制系统启动"],
                ["输出", "Q0.0", "运行指示灯", "显示运行状态"],
            ]
        },
    }
    schema = get_table_schema("io_assignment_table")

    result = append_table_block(doc, block, schema, table_index=1)

    assert result["written"] is True
    assert len(doc.tables) == 1
    assert doc.tables[0].rows[0].cells[0].text == "类型"
    assert doc.tables[0].rows[1].cells[2].text == "启动按钮"
    assert doc.tables[0].rows[2].cells[3].text == "显示运行状态"


def test_append_table_block_sets_black_borders() -> None:
    doc = Document()
    block = {
        "type": "table",
        "schema": "io_assignment_table",
        "data": {
            "rows": [
                ["输入", "I0.0", "启动按钮", "控制系统启动"],
            ]
        },
    }
    schema = get_table_schema("io_assignment_table")

    append_table_block(doc, block, schema, table_index=1)

    table = doc.tables[0]
    tbl_borders = table._tbl.tblPr.first_child_found_in("w:tblBorders")

    assert tbl_borders is not None
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tbl_borders.find(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{edge}")
        assert border is not None
        assert border.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color") == "000000"
        assert border.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "single"


def test_append_table_block_falls_back_when_table_grid_style_missing(monkeypatch) -> None:
    doc = Document()
    block = {
        "type": "table",
        "schema": "io_assignment_table",
        "data": {
            "rows": [
                ["输入", "I0.0", "启动按钮", "控制系统启动"],
            ]
        },
    }
    schema = get_table_schema("io_assignment_table")

    original_style = Table.style

    def fake_setter(self, value):
        if value == "Table Grid":
            raise KeyError("no style with name 'Table Grid'")
        return original_style.fset(self, value)

    monkeypatch.setattr(Table, "style", property(original_style.fget, fake_setter), raising=True)

    result = append_table_block(doc, block, schema, table_index=1)

    assert result["written"] is True
    assert len(doc.tables) == 1
    assert result["warnings"]
    assert "Table Grid" in result["warnings"][0]
