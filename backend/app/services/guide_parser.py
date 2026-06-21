from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
from docx import Document


MAX_TEXT_CHARS = 5000
DEFAULT_DOC_TIMEOUT = 20
logger = logging.getLogger("report-backend.guide")


def extract_guide_text(path: Path | None, max_chars: int | None = MAX_TEXT_CHARS) -> str:
    if path is None or not path.exists():
        return ""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = _extract_docx_text(path)
    elif suffix == ".doc":
        text = _extract_doc_text(path)
    elif suffix == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = path.read_bytes().decode("utf-8", errors="ignore")
    limited = _limit(text, max_chars)
    logger.info("guide extracted file=%s suffix=%s chars=%s limited_chars=%s", path.name, suffix, len(text), len(limited))
    return limited


def _extract_docx_text(path: Path) -> str:
    doc = Document(path)
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def _extract_pdf_text(path: Path) -> str:
    parts: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def _extract_doc_text(path: Path) -> str:
    converted = _convert_doc_to_docx_with_libreoffice(path)
    if converted is not None:
        return _extract_docx_text(converted)
    return _extract_doc_text_with_worker(path)


def _convert_doc_to_docx_with_libreoffice(path: Path) -> Path | None:
    timeout = int(os.getenv("DOC_EXTRACTION_TIMEOUT", str(DEFAULT_DOC_TIMEOUT)))
    for command in _libreoffice_commands():
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            try:
                completed = subprocess.run(
                    [command, "--headless", "--convert-to", "docx", "--outdir", str(output_dir), str(path.resolve())],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                logger.error("libreoffice doc conversion timed out file=%s command=%s timeout=%ss", path.name, command, timeout)
                continue

            converted = output_dir / f"{path.stem}.docx"
            if completed.returncode == 0 and converted.exists():
                stable_path = path.parent / f"{path.stem}_converted.docx"
                stable_path.write_bytes(converted.read_bytes())
                logger.info("libreoffice doc conversion succeeded file=%s output=%s command=%s", path.name, stable_path.name, command)
                return stable_path

            logger.info(
                "libreoffice doc conversion unavailable file=%s command=%s code=%s stderr=%s",
                path.name,
                command,
                completed.returncode,
                completed.stderr.strip()[:400],
            )
    return None


def _libreoffice_commands() -> list[str]:
    configured = os.getenv("LIBREOFFICE_PATH", "").strip()
    commands = [configured] if configured else []
    commands.extend(["libreoffice", "soffice"])
    return commands


def _extract_doc_text_with_worker(path: Path) -> str:
    timeout = int(os.getenv("DOC_EXTRACTION_TIMEOUT", str(DEFAULT_DOC_TIMEOUT)))
    command = [sys.executable, "-m", "backend.app.services.doc_text_worker", str(path.resolve())]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("doc guide extraction timed out file=%s timeout=%ss", path.name, timeout)
        return ""

    if completed.returncode != 0:
        logger.error(
            "doc guide extraction failed file=%s code=%s stderr=%s",
            path.name,
            completed.returncode,
            completed.stderr.strip()[:800],
        )
        return ""
    return completed.stdout


def _limit(text: str, max_chars: int | None = MAX_TEXT_CHARS) -> str:
    stripped = text.strip()
    if max_chars is None:
        return stripped
    return stripped[:max_chars]
