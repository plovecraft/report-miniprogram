from base64 import b64decode

from backend.app.services.layout_shadow import build_layout_shadow_summary, run_layout_shadow_check


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_layout_shadow_summary_renders_text_and_images_in_memory(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"title": "Purpose", "blocks": [{"type": "paragraph", "content": "Understand PLC control flow."}]},
            {
                "title": "Program",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "Program diagram", "imageType": "program"}],
            },
        ],
        "warnings": ["shadow only"],
    }

    summary = build_layout_shadow_summary(layout_plan, [image])

    assert summary["ok"] is True
    assert summary["sectionCount"] == 2
    assert summary["inlineShapeCount"] == 1
    assert summary["warningCount"] == 1
    assert "Understand PLC control flow." in summary["text"]
    assert "Program diagram" in summary["text"]
    assert summary["error"] == ""


def test_layout_shadow_summary_degrades_bad_images_without_failing(tmp_path) -> None:
    bad_image = tmp_path / "bad.png"
    bad_image.write_bytes(b"not an image")
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "Program",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "Broken image", "imageType": "program"}],
            }
        ],
        "warnings": [],
    }

    summary = build_layout_shadow_summary(layout_plan, [bad_image])

    assert summary["ok"] is True
    assert summary["inlineShapeCount"] == 0
    assert "Broken image" in summary["text"]
    assert "bad.png" in summary["text"]


def test_layout_shadow_summary_returns_error_for_invalid_plan() -> None:
    summary = build_layout_shadow_summary(
        {"sections": [{"title": "Purpose", "blocks": [{"type": "paragraph", "content": "Body"}]}]},
        [],
    )

    assert summary["ok"] is False
    assert summary["inlineShapeCount"] == 0
    assert "schemaVersion" in summary["error"]


def test_shadow_check_matches_preview_sections() -> None:
    preview = {
        "sections": [
            {"title": "Purpose", "paragraphs": ["Understand sequencing."], "images": []},
            {"title": "Result", "paragraphs": ["Observed stable outputs."], "images": []},
        ],
        "imagePlan": [],
        "insertedImageCount": 0,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"key": "purpose", "title": "Purpose", "blocks": [{"type": "paragraph", "content": "Understand sequencing."}]},
            {"key": "result", "title": "Result", "blocks": [{"type": "paragraph", "content": "Observed stable outputs."}]},
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [])

    assert result["passed"] is True
    assert result["checks"]["section_titles_match"] is True
    assert result["summary"]["section_count"] == 2
    assert [section["title"] for section in result["sections"]] == ["Purpose", "Result"]


def test_shadow_check_counts_images(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    preview = {
        "sections": [{"title": "Program", "paragraphs": [], "images": [{"imageIndex": 0, "caption": "Program image"}]}],
        "imagePlan": [{"imageIndex": 0, "type": "program", "caption": "Program image"}],
        "insertedImageCount": 1,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "program",
                "title": "Program",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "Program image", "imageType": "program"}],
            }
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [image])

    assert result["passed"] is True
    assert result["summary"]["image_count"] == 1
    assert result["sections"][0]["image_refs"] == ["image_0"]


def test_shadow_check_rejects_unknown_image_ref(tmp_path) -> None:
    image = tmp_path / "program.png"
    image.write_bytes(PNG_1X1)
    preview = {
        "sections": [{"title": "Program", "paragraphs": [], "images": []}],
        "imagePlan": [{"imageIndex": 0, "type": "program", "caption": "Program image"}],
        "insertedImageCount": 1,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "program",
                "title": "Program",
                "blocks": [{"type": "image", "imageIndex": 3, "caption": "Missing image", "imageType": "program"}],
            }
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [image])

    assert result["passed"] is False
    assert result["checks"]["image_references_valid"] is False
    assert any("unknown imageIndex" in error for error in result["errors"])


def test_shadow_check_records_warning_blocks() -> None:
    preview = {
        "sections": [{"title": "Result", "paragraphs": ["Normal result body."], "images": []}],
        "imagePlan": [],
        "insertedImageCount": 0,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "result",
                "title": "Result",
                "blocks": [
                    {"type": "warning", "message": "Needs manual review."},
                    {"type": "paragraph", "content": "Normal result body."},
                ],
            }
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [])

    assert result["passed"] is True
    assert result["summary"]["warning_count"] == 1
    assert "Needs manual review." in result["warnings"]


def test_shadow_check_detects_key_text() -> None:
    preview = {
        "sections": [{"title": "Purpose", "paragraphs": ["Key phrase for shadow check."], "images": []}],
        "imagePlan": [],
        "insertedImageCount": 0,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {"key": "purpose", "title": "Purpose", "blocks": [{"type": "paragraph", "content": "Key phrase for shadow check."}]}
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [])

    assert result["passed"] is True
    assert result["checks"]["key_text_rendered"] is True
    assert "Key phrase for shadow check." in result["sections"][0]["text_preview"]


def test_shadow_check_degrades_low_confidence_image(tmp_path) -> None:
    image = tmp_path / "review.png"
    image.write_bytes(PNG_1X1)
    preview = {
        "sections": [{"title": "Program", "paragraphs": [], "images": [{"imageIndex": 0, "caption": "Review image"}]}],
        "imagePlan": [
            {
                "imageIndex": 0,
                "type": "program",
                "caption": "Review image",
                "quality": {"needs_review": True},
                "confidence": 0.2,
            }
        ],
        "insertedImageCount": 1,
    }
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "program",
                "title": "Program",
                "blocks": [{"type": "image", "imageIndex": 0, "caption": "Review image", "imageType": "program"}],
            }
        ],
        "warnings": [],
    }

    result = run_layout_shadow_check(preview, layout_plan, [image])

    assert result["passed"] is True
    assert result["summary"]["image_count"] == 0
    assert result["summary"]["degraded_image_count"] == 1
    assert result["checks"]["review_images_degraded"] is True
    assert any("needs review" in warning.lower() for warning in result["warnings"])
