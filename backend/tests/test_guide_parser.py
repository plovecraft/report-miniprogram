import subprocess
from pathlib import Path

from docx import Document

from backend.app.services import guide_parser


def test_doc_guide_extraction_times_out_without_blocking(monkeypatch, tmp_path: Path) -> None:
    guide = tmp_path / "guide.doc"
    guide.write_bytes(b"legacy word")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setenv("DOC_EXTRACTION_TIMEOUT", "1")
    monkeypatch.setattr(guide_parser, "_convert_doc_to_docx_with_libreoffice", lambda path: None)
    monkeypatch.setattr(guide_parser.subprocess, "run", fake_run)

    assert guide_parser.extract_guide_text(guide) == ""


def test_doc_guide_uses_libreoffice_converted_docx_before_word_worker(monkeypatch, tmp_path: Path) -> None:
    guide = tmp_path / "guide.doc"
    guide.write_bytes(b"legacy word")
    converted = tmp_path / "converted.docx"
    doc = Document()
    doc.add_paragraph("实验三 天塔之光模拟控制")
    doc.save(converted)

    def fail_worker(path: Path) -> str:
        raise AssertionError("Word COM worker should not run when LibreOffice conversion succeeds")

    monkeypatch.setattr(guide_parser, "_convert_doc_to_docx_with_libreoffice", lambda path: converted)
    monkeypatch.setattr(guide_parser, "_extract_doc_text_with_worker", fail_worker)

    assert guide_parser.extract_guide_text(guide) == "实验三 天塔之光模拟控制"


def test_docx_guide_can_be_extracted_without_preselection_truncation(tmp_path: Path) -> None:
    guide = tmp_path / "guide.docx"
    doc = Document()
    doc.add_paragraph("实验一 基本指令")
    doc.add_paragraph("一" * 6000)
    doc.add_paragraph("实验三 计数器控制")
    doc.add_paragraph("这里是实验三的指导内容")
    doc.save(guide)

    text = guide_parser.extract_guide_text(guide, max_chars=None)

    assert "实验三 计数器控制" in text
    assert len(text) > guide_parser.MAX_TEXT_CHARS
