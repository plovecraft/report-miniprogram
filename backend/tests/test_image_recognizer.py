from io import BytesIO

from PIL import Image

from backend.app.services import image_recognizer


def _png_bytes(color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    buf = BytesIO()
    image = Image.new("RGB", (32, 32), color)
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_image_recognizer_returns_image_plan_v1(tmp_path) -> None:
    path = tmp_path / "program.png"
    path.write_bytes(_png_bytes())

    result = image_recognizer.recognize_image_file(path, experiment_type="plc", image_ref="image_0", image_index=0)

    assert result["schema_version"] == "image-plan.v1"
    assert result["image_ref"] == "image_0"
    assert result["imageIndex"] == 0
    assert "category" in result
    assert "confidence" in result
    assert "review_level" in result
    assert "suggested" in result


def test_image_recognizer_fallbacks_to_generic_for_unknown_experiment_type(tmp_path) -> None:
    path = tmp_path / "unknown.png"
    path.write_bytes(_png_bytes((0, 0, 0)))

    result = image_recognizer.recognize_image_file(path, experiment_type="unknown_type")

    assert result["schema_version"] == "image-plan.v1"
    assert result["experiment_type"] == "generic"


def test_non_semantic_filename_still_classified_by_visual_features() -> None:
    image = Image.new("RGB", (600, 400), (255, 255, 255))
    pixels = image.load()
    for y in range(40, 360, 60):
        for x in range(40, 560):
            pixels[x, y] = (0, 0, 0)
    for x in range(80, 520, 120):
        for y in range(40, 340):
            pixels[x, y] = (0, 0, 0)
    buf = BytesIO()
    image.save(buf, format="PNG")

    result = image_recognizer.recognize_image_bytes(
        buf.getvalue(),
        "wxfile_tmp_123.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
    )

    assert result["review_level"] in {"ok", "review"}
    assert result["category"] in {"program", "unknown"}
    assert "visual_score" in result["score_detail"]


def test_unknown_image_defaults_to_review_not_reject(tmp_path) -> None:
    path = tmp_path / "wxfile_tmp_123.png"
    path.write_bytes(_png_bytes((123, 123, 123)))

    result = image_recognizer.recognize_image_file(path, experiment_type="plc")

    assert result["review_level"] == "review"
    assert result["quality"]["needs_review"] is True or result["category"] == "unknown"


def test_unreadable_image_reject(tmp_path) -> None:
    path = tmp_path / "bad.bin"
    path.write_bytes(b"not-an-image")

    result = image_recognizer.recognize_image_file(path, experiment_type="plc")

    assert result["review_level"] == "reject"
    assert result["error"]["code"] in {"INVALID_IMAGE", "UNSUPPORTED_FORMAT", "IMAGE_RECOGNITION_FAILED"}


def test_program_like_image_not_misclassified_as_document() -> None:
    image = Image.new("RGB", (640, 360), (255, 255, 255))
    pixels = image.load()
    for y in range(30, 330, 50):
        for x in range(20, 620):
            pixels[x, y] = (0, 0, 0)
    for x in range(60, 620, 100):
        for y in range(30, 320):
            pixels[x, y] = (0, 0, 0)
    buf = BytesIO()
    image.save(buf, format="PNG")

    result = image_recognizer.recognize_image_bytes(buf.getvalue(), "image_001.png", experiment_type="plc")

    assert result["category"] != "document"


def test_features_include_visual_debug_fields(tmp_path) -> None:
    path = tmp_path / "program.png"
    path.write_bytes(_png_bytes())

    result = image_recognizer.recognize_image_file(path, experiment_type="plc")
    features = result["features"]
    score_detail = result["score_detail"]

    assert "width" in features
    assert "height" in features
    assert "aspect_ratio" in features
    assert "edge_density" in features
    assert "line_count" in features
    assert "horizontal_line_count" in features or "horizontal_lines" in features
    assert "vertical_line_count" in features or "vertical_lines" in features
    assert "brightness" in features
    assert "blur_score" in features
    assert "colorfulness" in features
    assert "filename_score" in score_detail
    assert "visual_score" in score_detail
    assert "final_score" in score_detail


def test_code_like_screenshot_prefers_program_and_not_too_bright() -> None:
    image = Image.new("RGB", (720, 480), (255, 255, 255))
    pixels = image.load()
    for row in range(40, 420, 36):
        for x in range(50, 640):
            if x % 7 in (0, 1, 2, 3):
                pixels[x, row] = (35, 35, 35)
                if row + 1 < 480:
                    pixels[x, row + 1] = (35, 35, 35)
    for x in range(70, 620, 110):
        for y in range(60, 400):
            if y % 29 in (0, 1):
                pixels[x, y] = (60, 60, 60)
    buf = BytesIO()
    image.save(buf, format="PNG")

    result = image_recognizer.recognize_image_bytes(buf.getvalue(), "wxfile_tmp_999.png", experiment_type="plc")

    assert result["category"] == "program"
    assert result["quality"]["too_bright"] is False
