from __future__ import annotations

from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.table import Table


def append_table_block(container, block: dict[str, Any], schema: dict[str, Any], table_index: int) -> dict[str, Any]:
    title = str(block.get("title") or f"表{table_index} {schema['title']}")
    title_paragraph = container.add_paragraph(title)
    title_paragraph.alignment = 1
    for run in title_paragraph.runs:
        _set_table_font(run, bold=True)

    rows = list((block.get("data") or {}).get("rows") or [])
    headers = list(block.get("headers") or schema["headers"])
    table = container.add_table(rows=len(rows) + 1, cols=len(headers))

    warnings: list[str] = []
    _apply_table_style(table, warnings)
    set_table_borders(table)

    for column_index, header in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        cell.text = str(header)
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                _set_table_font(run, bold=True)

    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row):
            cell = table.rows[row_index].cells[column_index]
            cell.text = str(value)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    _set_table_font(run)

    container.add_paragraph("")
    return {
        "written": True,
        "rows": len(rows),
        "columns": len(headers),
        "warnings": warnings,
        "errors": [],
    }


def set_table_borders(table: Table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_borders = tbl_pr.first_child_found_in("w:tblBorders")
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)

    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = tbl_borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            tbl_borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "6")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")


def _apply_table_style(table: Table, warnings: list[str]) -> None:
    try:
        table.style = "Table Grid"
    except KeyError:
        warnings.append("table style 'Table Grid' is not available in this template, using default table style")


def _set_table_font(run, bold: bool = False) -> None:
    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(10.5)
    run.bold = bold
