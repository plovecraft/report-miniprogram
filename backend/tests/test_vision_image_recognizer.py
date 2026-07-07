from io import BytesIO

from PIL import Image

from backend.app.services import image_recognizer


def _png_bytes() -> bytes:
    buf = BytesIO()
    image = Image.new("RGB", (32, 32), (255, 255, 255))
    image.save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = "fake response"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self) -> dict:
        return self._payload


def test_vision_recognizer_returns_image_plan_v1(monkeypatch) -> None:
    from backend.app.services import vision_image_recognizer

    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/api")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.4-mini")

    def fake_post(url, headers, json, timeout):
        assert url == "https://example.test/api/chat/completions"
        content = (
            '{"category":"program","category_cn":"程序图","confidence":0.86,'
            '"review_level":"ok","suggested":{"insert_section":"实验过程",'
            '"caption":"PLC 主程序图","size_policy":"program_small"}}'
        )
        return _FakeResponse({"choices": [{"message": {"content": content}}]})

    result = vision_image_recognizer.recognize_image_bytes_with_vision(
        _png_bytes(),
        "wxfile_tmp_1.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
        post=fake_post,
    )

    assert result is not None
    assert result["schema_version"] == "image-plan.v1"
    assert result["category"] == "program"
    assert result["category_cn"] == "程序图"
    assert result["confidence"] == 0.86
    assert result["review_level"] == "ok"
    assert result["suggested"]["caption"] == "PLC 主程序图"
    assert result["score_detail"]["recognizer"] == "vision"


def test_image_recognizer_uses_vision_when_enabled(monkeypatch) -> None:
    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/api")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.4-mini")

    monkeypatch.setattr(
        "backend.app.services.vision_image_recognizer.recognize_image_bytes_with_vision",
        lambda *args, **kwargs: {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": "wxfile_tmp_1.png",
            "category": "wiring",
            "category_cn": "接线图",
            "confidence": 0.91,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {"insert_section": "实验过程", "caption": "PLC 接线图", "size_policy": "wiring"},
            "features": {},
            "score_detail": {"recognizer": "vision"},
        },
    )

    result = image_recognizer.recognize_image_bytes(
        _png_bytes(),
        "wxfile_tmp_1.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
    )

    assert result["category"] == "wiring"
    assert result["confidence"] == 0.91
    assert result["score_detail"]["recognizer"] == "vision"


def test_image_recognizer_falls_back_when_vision_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/api")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setattr(
        "backend.app.services.vision_image_recognizer.recognize_image_bytes_with_vision",
        lambda *args, **kwargs: None,
    )

    result = image_recognizer.recognize_image_bytes(
        _png_bytes(),
        "wxfile_tmp_1.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
    )

    assert result["schema_version"] == "image-plan.v1"
    assert result["score_detail"].get("recognizer") != "vision"


def test_vision_unknown_category_becomes_review(monkeypatch) -> None:
    from backend.app.services import vision_image_recognizer

    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/api")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.4-mini")

    def fake_post(url, headers, json, timeout):
        return _FakeResponse({"choices": [{"message": {"content": '{"category":"screen","confidence":0.7}'}}]})

    result = vision_image_recognizer.recognize_image_bytes_with_vision(
        _png_bytes(),
        "wxfile_tmp_1.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
        post=fake_post,
    )

    assert result is not None
    assert result["category"] == "unknown"
    assert result["review_level"] == "review"
    assert result["quality"]["needs_review"] is True
