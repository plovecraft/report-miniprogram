from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

from backend.app.services.report_templates import (
    GenericDocumentTemplateAdapter,
    GuangzhouUniversityTableTemplateAdapter,
    resolve_report_template,
)


def test_resolves_guangzhou_table_template_and_body_cell() -> None:
    doc = Document()
    doc.add_paragraph("广州大学学生实验报告")
    table = doc.add_table(rows=4, cols=4)
    table.rows[2].cells[0].text = "实验项目名称"
    table.rows[2].cells[1].text = "旧项目"
    table.rows[3].cells[0].text = "旧正文"

    match = resolve_report_template(doc)

    assert isinstance(match.adapter, GuangzhouUniversityTableTemplateAdapter)
    assert match.template_id == "guangzhou_university_table"
    assert match.display_name == "广州大学实验报告表格模板"
    assert match.body_location == "第 1 个表格第 4 行第 1 个单元格"
    assert match.confidence >= 0.8
    body = match.adapter.get_body_container(doc)
    assert body is not None
    assert body.text == "旧正文"
    assert body.vertical_alignment == WD_CELL_VERTICAL_ALIGNMENT.TOP


def test_template_adapter_updates_header_fields() -> None:
    doc = Document()
    doc.add_paragraph("广州大学学生实验报告")
    table = doc.add_table(rows=4, cols=4)
    table.rows[2].cells[0].text = "实验项目名称"
    table.rows[2].cells[1].text = "旧项目"
    table.rows[2].cells[2].text = "指导老师"
    table.rows[2].cells[3].text = "原老师"

    match = resolve_report_template(doc)
    match.adapter.update_header(
        doc,
        {
            "experimentName": "实验三  天塔之光模拟控制",
            "teacherName": "",
        },
    )

    assert table.rows[2].cells[1].text == "实验三  天塔之光模拟控制"
    assert table.rows[2].cells[3].text == "原老师"


def test_falls_back_to_generic_document_template() -> None:
    doc = Document()
    doc.add_paragraph("普通实验报告")

    match = resolve_report_template(doc)

    assert isinstance(match.adapter, GenericDocumentTemplateAdapter)
    assert match.template_id == "generic_document"
    assert match.body_location == "整篇文档"
    assert match.adapter.get_body_container(doc) is None


def test_generic_template_uses_existing_table_body_cell_when_present() -> None:
    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(1, 0).text = "普通表格正文"

    match = resolve_report_template(doc)

    assert isinstance(match.adapter, GenericDocumentTemplateAdapter)
    assert match.body_location == "第 1 个表格第 2 行第 1 个单元格"
    assert match.adapter.get_body_container(doc).text == "普通表格正文"
