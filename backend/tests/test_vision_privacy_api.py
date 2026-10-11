from io import BytesIO
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import main
from backend.app.services.llm_writer import LLMConfig
from backend.app.services import vision_image_recognizer as vision


def _docx(text):
    buf = BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buf)
    return buf.getvalue()


def _png():
    buf = BytesIO()
    Image.new("RGB", (32, 32), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("zip_mode", [False, True])
@pytest.mark.parametrize("consented", [False, True])
def test_upload_preview_and_confirm_respect_task_consent(monkeypatch, tmp_path, zip_mode, consented):
    main.task_store.reset(tmp_path / "tasks")
    monkeypatch.delenv("LLM_DISABLE_FOR_TESTS", raising=False)
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-key")
    monkeypatch.setenv("LLM_MODEL", "synthetic-model")
    # Keep the independent text generator local; exercise the actual vision gate.
    monkeypatch.setattr(LLMConfig, "from_env", classmethod(lambda cls: None))
    monkeypatch.setattr(main, "start_preview_if_ready", lambda record: None)
    monkeypatch.setattr(main, "start_generation_if_confirmed", lambda record: None)
    calls = []
    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": '{"category":"program","confidence":0.9}'}}]}
    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return Response()
    monkeypatch.setattr(vision.requests, "post", fake_post)
    client = TestClient(main.app)
    info = client.get("/api/privacy/vision").json()
    assert info == {"enabled": True, "version": "vision-images.v1", "recipient": "example.test"}
    metadata = {"experimentNo": "实验一", "imageCount": 1}
    if consented:
        metadata["visionRecognitionConsent"] = {"accepted": True, "version": info["version"], "recipient": info["recipient"]}
    task_id = client.post("/api/reports/tasks", json=metadata).json()["taskId"]
    def upload(field, name, data):
        response = client.post(f"/api/reports/tasks/{task_id}/files",
                               data={"fieldName": field, "filename": name},
                               files={"file": (name, data, "application/octet-stream")})
        assert response.status_code == 200
    if zip_mode:
        buf = BytesIO()
        with ZipFile(buf, "w") as archive:
            archive.writestr("report.docx", _docx("原报告"))
            archive.writestr("guide.docx", _docx("实验一 指导书"))
            archive.writestr("images/photo.png", _png())
        upload("materialZip", "materials.zip", buf.getvalue())
    else:
        upload("report", "report.docx", _docx("原报告"))
        upload("guide", "guide.docx", _docx("实验一 指导书"))
        upload("image", "photo.png", _png())
    assert calls == []  # Upload alone stores files; recognition starts with preview.
    main.generate_task_preview(task_id)
    record = main.task_store.get_task(task_id)
    assert record.preview_data is not None
    assert len(calls) == int(consented)
    assert client.post(f"/api/reports/tasks/{task_id}/confirm").status_code == 200
    main.generate_task_output(task_id)
    assert record.output_file is not None and record.output_file.exists()
    assert len(calls) == int(consented)  # Generation uses the prepared plan.
    monkeypatch.setenv("VISION_RECOGNITION_ENABLED", "0")
    assert client.get("/api/privacy/vision").json()["enabled"] is False
