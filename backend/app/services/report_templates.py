from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from docx.document import Document as DocumentObject

from .report_inspector import find_body_cell, update_report_header_fields


class ReportTemplateAdapter(Protocol):
    template_id: str
    display_name: str

    def match_score(self, doc: DocumentObject) -> float:
        ...

    def get_body_container(self, doc: DocumentObject):
        ...

    def update_header(self, doc: DocumentObject, values: dict[str, str]) -> None:
        ...

    def body_location(self, doc: DocumentObject) -> str:
        ...


@dataclass(frozen=True)
class ReportTemplateMatch:
    template_id: str
    display_name: str
    confidence: float
    body_location: str
    adapter: ReportTemplateAdapter


class GuangzhouUniversityTableTemplateAdapter:
    template_id = "guangzhou_university_table"
    display_name = "广州大学实验报告表格模板"

    def match_score(self, doc: DocumentObject) -> float:
        text = "\n".join(paragraph.text for paragraph in doc.paragraphs[:5])
        first_table_text = doc.tables[0].cell(0, 0).text if doc.tables and doc.tables[0].rows else ""
        all_table_text = "\n".join(cell.text for table in doc.tables[:1] for row in table.rows[:4] for cell in row.cells)
        score = 0.0
        if "广州大学学生实验报告" in text:
            score += 0.45
        if "实验项目名称" in all_table_text:
            score += 0.3
        if "实验课程名称" in all_table_text or "课程名称" in all_table_text:
            score += 0.15
        if doc.tables and len(doc.tables[0].rows) >= 4:
            score += 0.1
        if "学院" in first_table_text:
            score += 0.05
        return min(score, 1.0)

    def get_body_container(self, doc: DocumentObject):
        return find_body_cell(doc)

    def update_header(self, doc: DocumentObject, values: dict[str, str]) -> None:
        update_report_header_fields(doc, values)

    def body_location(self, doc: DocumentObject) -> str:
        if not doc.tables:
            return "未识别正文区域"
        row_number = 4 if len(doc.tables[0].rows) >= 4 else len(doc.tables[0].rows)
        return f"第 1 个表格第 {row_number} 行第 1 个单元格"


class GenericDocumentTemplateAdapter:
    template_id = "generic_document"
    display_name = "通用文档模板"

    def match_score(self, doc: DocumentObject) -> float:
        return 0.1

    def get_body_container(self, doc: DocumentObject):
        return find_body_cell(doc)

    def update_header(self, doc: DocumentObject, values: dict[str, str]) -> None:
        update_report_header_fields(doc, values)

    def body_location(self, doc: DocumentObject) -> str:
        if not doc.tables:
            return "整篇文档"
        row_number = 4 if len(doc.tables[0].rows) >= 4 else len(doc.tables[0].rows)
        return f"第 1 个表格第 {row_number} 行第 1 个单元格"


TEMPLATE_ADAPTERS: tuple[ReportTemplateAdapter, ...] = (
    GuangzhouUniversityTableTemplateAdapter(),
    GenericDocumentTemplateAdapter(),
)


def resolve_report_template(doc: DocumentObject) -> ReportTemplateMatch:
    scored = [(adapter.match_score(doc), adapter) for adapter in TEMPLATE_ADAPTERS]
    confidence, adapter = max(scored, key=lambda item: item[0])
    return ReportTemplateMatch(
        template_id=adapter.template_id,
        display_name=adapter.display_name,
        confidence=confidence,
        body_location=adapter.body_location(doc),
        adapter=adapter,
    )
