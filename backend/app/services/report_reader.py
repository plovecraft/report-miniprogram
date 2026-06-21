from __future__ import annotations

from pathlib import Path

from docx import Document


MAX_REPORT_CHARS = 4000


def extract_report_text(path: Path | None) -> str:
    if path is None or not path.exists() or path.suffix.lower() != ".docx":
        return ""
    doc = Document(path)
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts).strip()[:MAX_REPORT_CHARS]
