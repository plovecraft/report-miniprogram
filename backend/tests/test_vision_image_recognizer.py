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

    def fake_post(url, headers, json, timeout, allow_redirects):
        assert allow_redirects is False
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
        allow_external=True,
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

    def fake_post(url, headers, json, timeout, allow_redirects):
        assert allow_redirects is False
        return _FakeResponse({"choices": [{"message": {"content": '{"category":"screen","confidence":0.7}'}}]})

    result = vision_image_recognizer.recognize_image_bytes_with_vision(
        _png_bytes(),
        "wxfile_tmp_1.png",
        experiment_type="plc",
        image_ref="image_0",
        image_index=0,
        allow_external=True,
        post=fake_post,
    )

    assert result is not None
    assert result["category"] == "unknown"
    assert result["review_level"] == "review"
    assert result["quality"]["needs_review"] is True


def _enable_vision(monkeypatch):
    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-key")
    monkeypatch.setenv("LLM_MODEL", "synthetic-model")
    return {"visionRecognitionConsent": {
        "accepted": True, "version": "vision-images.v1", "recipient": "example.test"}}


def test_no_consent_or_disabled_never_posts(monkeypatch, tmp_path):
    from backend.app.services import vision_image_recognizer as vision
    _enable_vision(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected external transfer")
    for value in (False, None, "true", 1):
        assert vision.recognize_image_bytes_with_vision(
            _png_bytes(), "private.png", allow_external=value, post=forbidden) is None
    for value in ("0", "false", "", "off"):
        monkeypatch.setenv("VISION_RECOGNITION_ENABLED", value)
        assert vision.recognize_image_bytes_with_vision(
            _png_bytes(), "private.png", allow_external=True, post=forbidden) is None
        assert vision.recognize_image_file_with_vision(
            tmp_path / "missing.png", allow_external=True, post=forbidden) is None


def test_missing_configuration_and_unsafe_endpoint_never_post(monkeypatch):
    from backend.app.services import vision_image_recognizer as vision
    _enable_vision(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected external transfer")
    for name in ("LLM_API_KEY", "LLM_MODEL"):
        with monkeypatch.context() as m:
            m.setenv(name, "")
            assert vision.recognize_image_bytes_with_vision(
                _png_bytes(), "private.png", allow_external=True, post=forbidden) is None
    for url in ("http://example.test", "https://user:secret@example.test"):
        monkeypatch.setenv("LLM_BASE_URL", url)
        assert vision.recognize_image_bytes_with_vision(
            _png_bytes(), "private.png", allow_external=True, post=forbidden) is None


def test_payload_and_failure_logs_do_not_include_filename_or_exception(monkeypatch, caplog):
    import base64
    from requests import RequestException
    from backend.app.services import vision_image_recognizer as vision
    _enable_vision(monkeypatch)
    raw = _png_bytes()
    def fake_post(url, **kwargs):
        payload = kwargs["json"]
        assert "student-secret" not in str(payload)
        assert base64.b64decode(payload["messages"][1]["content"][1]["image_url"]["url"].split(",", 1)[1]) == raw
        assert kwargs["allow_redirects"] is False
        raise RequestException("synthetic-key student-secret response-private " + base64.b64encode(raw).decode())
    assert vision.recognize_image_bytes_with_vision(
        raw, "student-secret.png", allow_external=True, post=fake_post) is None
    assert "RequestException" in caplog.text
    for secret in ("student-secret", "synthetic-key", "response-private", base64.b64encode(raw).decode()):
        assert secret not in caplog.text


def test_stream_and_redirect_failure_fall_back_without_sensitive_logs(monkeypatch, caplog):
    from backend.app.services import vision_image_recognizer as vision
    _enable_vision(monkeypatch)
    monkeypatch.setenv("LLM_STREAM", "1")
    class Response(_FakeResponse):
        def iter_lines(self, **kwargs):
            yield 'data: private-response-not-json'
    def fake_post(url, **kwargs):
        assert kwargs["stream"] is True
        assert kwargs["allow_redirects"] is False
        return Response({})
    assert vision.recognize_image_bytes_with_vision(
        _png_bytes(), "private-name.png", allow_external=True, post=fake_post) is None
    assert "private-response" not in caplog.text and "private-name" not in caplog.text
    assert vision.recognize_image_bytes_with_vision(
        _png_bytes(), "private-name.png", allow_external=True,
        post=lambda *a, **kw: _FakeResponse({}, 307)) is None


def test_real_recognizer_failure_preserves_local_fallback(monkeypatch):
    from requests import RequestException
    from backend.app.services import vision_image_recognizer as vision
    _enable_vision(monkeypatch)
    def failure(*args, **kwargs):
        raise RequestException("synthetic failure")
    monkeypatch.setattr(vision.requests, "post", failure)
    result = image_recognizer.recognize_image_bytes(_png_bytes(), "program.png", allow_external=True)
    assert result["schema_version"] == "image-plan.v1"
    assert result["score_detail"].get("recognizer") != "vision"


def test_task_consent_and_manual_categories_gate_actual_transfers(monkeypatch, tmp_path):
    from backend.app.services.docx_builder import build_image_plan
    from backend.app.services import vision_image_recognizer as vision
    metadata = _enable_vision(monkeypatch)
    path = tmp_path / "program.png"
    path.write_bytes(_png_bytes())
    calls = []
    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return _FakeResponse({"choices": [{"message": {"content": '{"category":"program","confidence":0.9}'}}]})
    monkeypatch.setattr(vision.requests, "post", fake_post)
    for consent in (None, True, {"accepted": "true"}, {"accepted": True, "version": "old", "recipient": "example.test"}):
        build_image_plan([path], {"visionRecognitionConsent": consent})
    assert calls == []
    for category in ("skip", "program", "other", "wiring"):
        build_image_plan([path], {**metadata, "imageMetas": [{"filename": path.name, "category": category}]})
    assert calls == []
    build_image_plan([path], metadata, image_plan_overrides={"image_0": {"category": "program"}})
    assert calls == []
    build_image_plan([path], metadata)
    assert len(calls) == 1
    monkeypatch.setenv("LLM_BASE_URL", "https://changed.test/v1")
    build_image_plan([path], metadata)
    assert len(calls) == 1



def test_image_plan_failure_does_not_return_or_log_exception_content(monkeypatch, tmp_path, caplog):
    from backend.app.services.docx_builder import build_image_plan
    path = tmp_path / "synthetic-private-name.png"
    path.write_bytes(_png_bytes())
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-sensitive-response")
    monkeypatch.setattr(image_recognizer, "recognize_image_file", fail)
    plan = build_image_plan([path])
    assert "synthetic-sensitive-response" not in str(plan)
    assert "synthetic-sensitive-response" not in caplog.text
    assert "synthetic-private-name" not in caplog.text
