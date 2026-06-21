from pathlib import Path

from docx import Document

from backend.app.services.quality_checker import build_quality_report


def _make_template(path: Path, body_text: str) -> None:
    doc = Document()
    table = doc.add_table(rows=4, cols=1)
    table.rows[0].cells[0].text = "表头"
    table.rows[3].cells[0].text = body_text
    doc.save(path)


def test_quality_report_passes_when_template_body_and_images_are_ok(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _make_template(source, "实验一 旧正文")

    doc = Document()
    table = doc.add_table(rows=4, cols=1)
    table.rows[0].cells[0].text = "表头"
    table.rows[3].cells[0].text = "一、实验目的\n实验三 天塔之光模拟控制\n六、实验结果"
    doc.add_paragraph().add_run().add_picture(str(_png_1x1(tmp_path)), width=None)
    doc.save(output)

    report = build_quality_report(
        source_file=source,
        output_file=output,
        expected_image_count=1,
        target_experiment="实验三",
    )

    assert report["passed"] is True
    assert report["checks"]["template_preserved"] is True
    assert report["checks"]["body_not_empty"] is True
    assert report["checks"]["images_inserted"] == 1
    assert report["checks"]["filename_reference_found"] is False
    assert report["warnings"] == []


def test_quality_report_warns_about_stale_text_missing_images_and_filenames(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _make_template(source, "实验一 旧正文")
    _make_template(output, "实验一 旧正文\n基础题现象.jpg")

    report = build_quality_report(
        source_file=source,
        output_file=output,
        expected_image_count=2,
        target_experiment="实验三",
    )

    assert report["passed"] is False
    assert report["checks"]["stale_experiment_text_found"] is True
    assert report["checks"]["filename_reference_found"] is True
    assert report["checks"]["images_inserted"] == 0
    assert any("旧实验内容" in warning for warning in report["warnings"])
    assert any("图片文件名" in warning for warning in report["warnings"])


def _png_1x1(tmp_path: Path) -> Path:
    import base64

    path = tmp_path / "pixel.png"
    path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")
    )
    return path
