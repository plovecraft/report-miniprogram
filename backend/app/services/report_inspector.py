from __future__ import annotations

import re

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.table import _Cell


FIELD_LABELS = {
    "experimentName": ("实验项目名称", "实验名称", "项目名称"),
    "studentName": ("姓名",),
    "studentId": ("学号",),
    "className": ("班级", "年级专业班", "年级专业班级"),
    "offeringCollegeLab": ("开课学院及实验室", "开课学院", "实验室"),
    "studentCollege": ("用户学院", "所在学院", "学院"),
    "courseName": ("实验课程名称", "课程名称", "课程"),
    "teacherName": ("指导老师", "指导教师", "老师", "教师"),
    "date": ("日期", "实验日期"),
}


def find_body_cell(doc: DocumentObject) -> _Cell | None:
    if not doc.tables:
        return None
    table = doc.tables[0]
    if not table.rows:
        return None
    row = table.rows[3] if len(table.rows) >= 4 else table.rows[-1]
    if not row.cells:
        return None
    cell = row.cells[0]
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    return cell


def update_experiment_project_name(doc: DocumentObject, experiment_name: str) -> None:
    update_report_header_fields(doc, {"experimentName": experiment_name})


def update_report_header_fields(doc: DocumentObject, values: dict[str, str]) -> None:
    normalized_values = {key: str(value).strip() for key, value in values.items() if str(value).strip()}
    if not normalized_values:
        return

    if doc.tables:
        table = doc.tables[0]
        for row_index, row in enumerate(table.rows):
            if row_index >= 3:
                break
            cells = row.cells
            label_positions = [_field_at_cell(cell.text) for cell in cells]
            for index, field_name in enumerate(label_positions):
                if field_name is None or field_name not in normalized_values:
                    continue
                value_indexes = _value_indexes_for_label(label_positions, index)
                if not value_indexes:
                    continue
                for value_index in value_indexes:
                    cells[value_index].text = normalized_values[field_name]

    _update_standalone_header_paragraphs(doc, normalized_values)


def _value_indexes_for_label(label_positions: list[str | None], label_index: int) -> list[int]:
    indexes: list[int] = []
    for index in range(label_index + 1, len(label_positions)):
        if label_positions[index] is not None:
            break
        indexes.append(index)
    return indexes[:1]


def _field_at_cell(text: str) -> str | None:
    normalized = _normalize_label(text)
    if not normalized:
        return None
    for field_name, labels in FIELD_LABELS.items():
        if any(label == normalized for label in labels):
            return field_name
    return None


def _normalize_label(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace("\u3000", "")
        .replace("：", "")
        .replace(":", "")
        .replace("、", "")
        .replace(",", "")
        .replace("，", "")
        .replace("\n", "")
        .strip()
    )


def _update_standalone_header_paragraphs(doc: DocumentObject, values: dict[str, str]) -> None:
    for paragraph in doc.paragraphs[:5]:
        text = paragraph.text.strip()
        if not text:
            continue
        if "开课学院及实验室" in text:
            _replace_paragraph_text(paragraph, _updated_offering_lab_date_line(text, values))
            continue
        if "date" in values and _looks_like_date_line(text):
            _replace_paragraph_text(paragraph, values["date"])
            return


def _updated_offering_lab_date_line(text: str, values: dict[str, str]) -> str:
    prefix_match = re.match(r"^(.*?开课学院及实验室\s*[：:]\s*)", text)
    prefix = prefix_match.group(1) if prefix_match else "开课学院及实验室：  "
    rest = text[len(prefix) :] if prefix_match else text
    date_match = DATE_OR_PLACEHOLDER_PATTERN.search(rest)
    old_lab = rest[: date_match.start()].strip() if date_match else rest.strip()
    old_date = date_match.group(0).strip() if date_match else ""
    lab = values.get("offeringCollegeLab") or old_lab
    date = values.get("date") or old_date
    return f"{prefix}{lab}                         {date}".rstrip()


def _update_date_paragraphs(doc: DocumentObject, date_value: str) -> None:
    for paragraph in doc.paragraphs[:5]:
        text = paragraph.text.strip()
        if not text:
            continue
        if _looks_like_date_line(text):
            _replace_paragraph_text(paragraph, date_value)
            return


def _looks_like_date_line(text: str) -> bool:
    normalized = _normalize_label(text)
    if normalized in {"日期", "实验日期"}:
        return True
    return bool(DATE_OR_PLACEHOLDER_PATTERN.fullmatch(text.strip()))


def _replace_paragraph_text(paragraph, text: str) -> None:
    paragraph.clear()
    paragraph.add_run(text)


DATE_PATTERN = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
DATE_OR_PLACEHOLDER_PATTERN = re.compile(r"(?:\d{4}\s*)?年\s*(?:\d{1,2}\s*)?月\s*(?:\d{1,2}\s*)?日")
