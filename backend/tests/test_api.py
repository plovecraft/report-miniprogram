import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from fastapi.testclient import TestClient

from backend.app.main import app, generate_task_output, generate_task_preview, task_store


def make_docx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buffer)
    return buffer.getvalue()


def make_material_zip(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def create_preview_ready_table_task(client: TestClient) -> tuple[str, dict]:
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    return task_id, preview


def create_preview_ready_ai_task(client: TestClient) -> str:
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 1})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("guide text"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "program.png"},
        files={"file": ("program.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    generate_task_preview(task_id)
    return task_id


def test_health_includes_runtime_summary() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "runtime" in body
    assert "tableFeatureEnabled" in body["runtime"]
    assert "visionRecognitionEnabled" in body["runtime"]


def test_report_task_uploads_previews_confirms_and_downloads_revised_docx(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post(
        "/api/reports/tasks",
        json={
            "experimentNo": "实验四",
            "studentName": "张三",
            "studentId": "20260001",
            "className": "自动化一班",
            "exportPdf": False,
            "imageCount": 1,
        },
    )

    assert create_response.status_code == 200
    task_id = create_response.json()["taskId"]

    report_response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={
            "file": (
                "report.docx",
                make_docx_bytes("原始实验报告正文"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert report_response.status_code == 200

    guide_response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("实验四 交通灯控制"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert guide_response.status_code == 200
    assert guide_response.json()["status"] == "uploading"

    image_response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "程序图1.png"},
        files={"file": ("程序图1.png", b"image bytes", "image/png")},
    )
    assert image_response.status_code == 200
    assert image_response.json()["status"] in {"previewing", "preview_ready"}

    generate_task_preview(task_id)
    preview_response = client.get(f"/api/reports/tasks/{task_id}")
    assert preview_response.status_code == 200
    preview_body = preview_response.json()
    assert preview_body["status"] == "preview_ready"
    assert preview_body["progress"] == 75
    assert preview_body["preview"]["experimentName"] == "实验四"
    assert preview_body["preview"]["sections"][0]["title"] == "一、实验目的"
    assert preview_body["preview"]["sections"][0]["paragraphs"] == []
    assert preview_body["preview"]["imagePlan"][0]["filename"] == "程序图1.png"
    assert preview_body["preview"]["imagePlan"][0]["section"] == "五、程序设计与梯形图"
    assert "layoutPlan" not in preview_body["preview"]
    record = task_store.get_task(task_id)
    assert record is not None
    assert record.preview_layout_plan is not None
    assert record.preview_layout_plan["schemaVersion"] == 1
    assert record.preview_layout_plan["sections"][4]["blocks"][0]["type"] == "image"

    early_download_response = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    assert early_download_response.status_code == 404

    confirm_response = client.post(f"/api/reports/tasks/{task_id}/confirm")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] in {"processing", "done"}

    generate_task_output(task_id)
    status_response = client.get(f"/api/reports/tasks/{task_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "done"
    assert status_body["progress"] == 100
    assert status_body["resultName"].endswith("_revised.docx")
    assert status_body["qualityReport"]["checks"]["body_not_empty"] is True
    assert "warnings" in status_body["qualityReport"]

    download_response = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    output_doc = Document(BytesIO(download_response.content))
    text = "\n".join(p.text for p in output_doc.paragraphs)
    assert "一、实验目的" in text
    assert "实验四" in text
    assert "张三" in text
    assert "程序图1.png" in text


def test_preview_is_lightweight_and_respects_image_category_metadata(monkeypatch, tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    def fail_if_llm_draft_is_built(*args, **kwargs):
        raise AssertionError("preview should not generate report text through LLM")

    monkeypatch.setattr("backend.app.services.docx_builder.build_report_draft", fail_if_llm_draft_is_built)

    create_response = client.post(
        "/api/reports/tasks",
        json={
            "experimentNo": "实验三",
            "imageCount": 1,
            "imageMetas": [
                {
                    "filename": "程序图1.png",
                    "category": "basic_result",
                }
            ],
        },
    )
    assert create_response.status_code == 200
    task_id = create_response.json()["taskId"]

    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("原报告"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("实验三"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "程序图1.png"},
        files={"file": ("程序图1.png", b"image bytes", "image/png")},
    )

    generate_task_preview(task_id)
    body = client.get(f"/api/reports/tasks/{task_id}").json()

    assert body["status"] == "preview_ready"
    assert body["preview"]["sections"][0]["paragraphs"] == []
    image = body["preview"]["imagePlan"][0]
    assert image["imageIndex"] == 0
    assert image["filename"].endswith(".png")
    assert image["type"] == "result"
    assert image["section"] == body["preview"]["sections"][5]["title"]
    assert image["caption"] == body["preview"]["sections"][5]["images"][0]["caption"]
    assert image["sortOrder"] == 0
    assert image["recognized"] is True
    assert image["schema_version"] == "image-plan.v1"
    assert image["category"] == "basic_result"
    assert image["categoryCn"] == image["category_cn"]
    assert image["needsReview"] is False


def test_preview_groups_images_inside_outline_sections_and_serves_image_bytes(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post(
        "/api/reports/tasks",
        json={
            "experimentNo": "实验三",
            "imageCount": 3,
            "imageMetas": [
                {"filename": "接线图.png", "category": "wiring"},
                {"filename": "程序图1.png", "category": "basic_program"},
                {"filename": "基础题现象.jpg", "category": "basic_result"},
            ],
        },
    )
    task_id = create_response.json()["taskId"]

    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("原报告"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("实验三"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    for filename, content_type in [
        ("接线图.png", "image/png"),
        ("程序图1.png", "image/png"),
        ("基础题现象.jpg", "image/jpeg"),
    ]:
        client.post(
            f"/api/reports/tasks/{task_id}/files",
            data={"fieldName": "image", "filename": filename},
            files={"file": (filename, f"bytes-{filename}".encode("utf-8"), content_type)},
        )

    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    sections = {section["title"]: section for section in preview["sections"]}

    assert preview["insertedImageCount"] == 3
    assert preview["template"]["templateId"] == "generic_document"
    assert preview["template"]["displayName"] == "通用文档模板"
    assert preview["template"]["bodyLocation"] == "整篇文档"
    assert [image["caption"] for image in sections["四、实验操作过程"]["images"]] == ["实验接线图"]
    assert [image["caption"] for image in sections["五、程序设计与梯形图"]["images"]] == ["基础题梯形图程序"]
    assert [image["caption"] for image in sections["六、实验结果"]["images"]] == ["基础题运行现象"]
    assert sections["四、实验操作过程"]["images"][0]["imageIndex"] == 0

    image_response = client.get(f"/api/reports/tasks/{task_id}/images/1")
    assert image_response.status_code == 200
    assert image_response.content == b"bytes-\xe7\xa8\x8b\xe5\xba\x8f\xe5\x9b\xbe1.png"


def test_updates_preview_image_plan_and_generation_uses_new_section(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post(
        "/api/reports/tasks",
        json={
            "experimentNo": "实验三",
            "imageCount": 1,
            "imageMetas": [{"filename": "程序图1.png", "category": "basic_program"}],
        },
    )
    task_id = create_response.json()["taskId"]

    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("原报告"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("实验三"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "程序图1.png"},
        files={"file": ("程序图1.png", b"image bytes", "image/png")},
    )

    generate_task_preview(task_id)
    update_response = client.patch(
        f"/api/reports/tasks/{task_id}/image-plan",
        json={
            "images": [
                {
                    "filename": "程序图1.png",
                    "category": "basic_program",
                    "section": "六、实验结果",
                    "sortOrder": 0,
                }
            ]
        },
    )

    assert update_response.status_code == 200
    preview = update_response.json()["preview"]
    sections = {section["title"]: section for section in preview["sections"]}
    assert sections["五、程序设计与梯形图"]["images"] == []
    assert sections["六、实验结果"]["images"][0]["caption"] == "基础题梯形图程序"
    assert "layoutPlan" not in preview

    record = task_store.get_task(task_id)
    assert record is not None
    assert record.preview_layout_plan is not None
    assert record.preview_layout_plan["schemaVersion"] == 1
    layout_sections = {section["title"]: section for section in record.preview_layout_plan["sections"]}
    assert layout_sections["五、程序设计与梯形图"]["blocks"] == []
    assert layout_sections["六、实验结果"]["blocks"][0]["imageIndex"] == 0

    task_store.mark_processing(record)
    generate_task_output(task_id)
    result = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    output_doc = Document(BytesIO(result.content))
    text = "\n".join(p.text for p in output_doc.paragraphs)
    assert "六、实验结果" in text
    assert text.index("六、实验结果") < text.index("基础题梯形图程序")


def test_uploads_material_zip_and_classifies_images_by_folder(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post(
        "/api/reports/tasks",
        json={"experimentNo": "实验四", "imageCount": 0},
    )
    task_id = create_response.json()["taskId"]
    package = make_material_zip(
        {
            "原始报告.docx": make_docx_bytes("原始报告"),
            "实验指导书.docx": make_docx_bytes("实验四"),
            "程序图/1.png": b"program image",
            "现象图/1.jpg": b"result image",
            "接线图/1.png": b"wiring image",
            "实物图/1.jpg": b"physical image",
        }
    )

    response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "materialZip", "filename": "实验4材料.zip"},
        files={"file": ("实验4材料.zip", package, "application/zip")},
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"previewing", "preview_ready"}
    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    sections = {section["title"]: section for section in preview["sections"]}
    assert [image["caption"] for image in sections["四、实验操作过程"]["images"]] == ["实验接线图"]
    assert [image["caption"] for image in sections["五、程序设计与梯形图"]["images"]] == ["梯形图程序"]
    assert [image["caption"] for image in sections["六、实验结果"]["images"]] == ["实验运行现象", "实验实物图"]
    assert preview["insertedImageCount"] == 4


def test_material_zip_rejects_zip_slip_and_unsupported_files(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "实验四", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    bad_package = make_material_zip(
        {
            "../evil.docx": make_docx_bytes("bad"),
            "notes.exe": b"bad",
        }
    )

    response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "materialZip", "filename": "bad.zip"},
        files={"file": ("bad.zip", bad_package, "application/zip")},
    )

    assert response.status_code == 400


def test_material_zip_repairs_windows_gbk_mojibake_names(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "实验三", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    package = make_material_zip(
        {
            "╩╡╤Θ▒¿╕µ3.docx": make_docx_bytes("原始报告"),
            "╩╡╤Θ╓╕╡╝╩Θ.docx": make_docx_bytes("实验三"),
            "╜╙╧▀═╝/1.png": b"wiring image",
            "╧╓╧≤═╝/1.jpg": b"result image",
            "│╠╨≥═╝/1.png": b"program image",
        }
    )

    response = client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "materialZip", "filename": "材料.zip"},
        files={"file": ("材料.zip", package, "application/zip")},
    )

    assert response.status_code == 200
    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    sections = {section["title"]: section for section in preview["sections"]}
    assert [image["caption"] for image in sections["四、实验操作过程"]["images"]] == ["实验接线图"]
    assert [image["caption"] for image in sections["五、程序设计与梯形图"]["images"]] == ["梯形图程序"]
    assert [image["caption"] for image in sections["六、实验结果"]["images"]] == ["实验运行现象"]


def test_quality_report_expected_images_excludes_skipped_images(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post(
        "/api/reports/tasks",
        json={
            "experimentNo": "实验三",
            "imageCount": 1,
            "imageMetas": [{"filename": "随手拍.png", "category": "skip"}],
        },
    )
    task_id = create_response.json()["taskId"]

    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("原报告"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("实验三"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "随手拍.png"},
        files={"file": ("随手拍.png", b"image bytes", "image/png")},
    )

    generate_task_preview(task_id)
    record = task_store.get_task(task_id)
    assert record is not None
    task_store.mark_processing(record)
    generate_task_output(task_id)
    body = client.get(f"/api/reports/tasks/{task_id}").json()

    assert body["qualityReport"]["checks"]["expected_images"] == 0


def test_lists_multiple_tasks_for_history(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    first = client.post("/api/reports/tasks", json={"experimentNo": "实验一", "imageCount": 0}).json()
    second = client.post("/api/reports/tasks", json={"experimentNo": "实验二", "imageCount": 0}).json()

    response = client.get("/api/reports/tasks")

    assert response.status_code == 200
    body = response.json()
    assert [task["taskId"] for task in body["tasks"]] == [second["taskId"], first["taskId"]]
    assert body["tasks"][0]["experimentNo"] == "实验二"
    assert body["tasks"][1]["experimentNo"] == "实验一"
    assert "createdAt" in body["tasks"][0]
    assert "updatedAt" in body["tasks"][0]


def test_confirming_two_preview_ready_tasks_starts_independent_generation_threads(monkeypatch, tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_ids: list[str] = []
    queued: list[tuple] = []

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            queued.append((target, args, daemon))

        def start(self) -> None:
            return None

    monkeypatch.setattr("backend.app.main.Thread", FakeThread)

    for experiment_no in ["实验一", "实验二"]:
        response = client.post("/api/reports/tasks", json={"experimentNo": experiment_no, "imageCount": 0})
        task_id = response.json()["taskId"]
        record = task_store.get_task(task_id)
        assert record is not None
        task_store.mark_preview_ready(record, {"experimentName": experiment_no, "sections": [], "imagePlan": [], "insertedImageCount": 0})
        task_ids.append(task_id)

    first_confirm = client.post(f"/api/reports/tasks/{task_ids[0]}/confirm")
    second_confirm = client.post(f"/api/reports/tasks/{task_ids[1]}/confirm")

    assert first_confirm.status_code == 200
    assert second_confirm.status_code == 200
    statuses = [client.get(f"/api/reports/tasks/{task_id}").json()["status"] for task_id in task_ids]
    assert statuses == ["processing", "processing"]
    records = [task_store.get_task(task_id) for task_id in task_ids]
    assert all(record is not None and record.generation_started for record in records)
    assert [args[0] for _, args, _ in queued] == task_ids


def test_wechat_login_scopes_task_history_and_records_usage(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    from backend.app.main import user_store

    user_store.reset(tmp_path / "app.sqlite3")
    client = TestClient(app)

    first_login = client.post("/api/auth/wechat-login", json={"code": "first-code"})
    second_login = client.post("/api/auth/wechat-login", json={"code": "second-code"})
    assert first_login.status_code == 200
    assert second_login.status_code == 200
    first_token = first_login.json()["token"]
    second_token = second_login.json()["token"]

    first_task = client.post(
        "/api/reports/tasks",
        headers={"Authorization": f"Bearer {first_token}"},
        json={"experimentNo": "实验一", "imageCount": 0},
    ).json()
    client.post(
        "/api/reports/tasks",
        headers={"Authorization": f"Bearer {second_token}"},
        json={"experimentNo": "实验二", "imageCount": 0},
    )

    first_history = client.get("/api/reports/tasks", headers={"Authorization": f"Bearer {first_token}"}).json()
    second_history = client.get("/api/reports/tasks", headers={"Authorization": f"Bearer {second_token}"}).json()
    anonymous_history = client.get("/api/reports/tasks").json()

    assert [task["taskId"] for task in first_history["tasks"]] == [first_task["taskId"]]
    assert [task["experimentNo"] for task in second_history["tasks"]] == ["实验二"]
    assert len(anonymous_history["tasks"]) == 2

    usage = client.get("/api/users/me/usage", headers={"Authorization": f"Bearer {first_token}"}).json()
    assert usage["records"][0]["event"] == "task_created"
    assert usage["records"][0]["taskId"] == first_task["taskId"]


def test_local_dev_wechat_login_can_use_stable_client_openid(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    from backend.app.main import user_store

    user_store.reset(tmp_path / "app.sqlite3")
    client = TestClient(app)

    first_login = client.post("/api/auth/wechat-login", json={"code": "first-code", "devOpenid": "local-client-1"}).json()
    second_login = client.post("/api/auth/wechat-login", json={"code": "second-code", "devOpenid": "local-client-1"}).json()

    assert first_login["user"]["userId"] == second_login["user"]["userId"]


def test_update_table_plan_selection(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    table_id = preview["tablePlan"][0]["tableId"]

    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableSelection": {table_id: False}},
    )

    assert response.status_code == 200
    updated_preview = response.json()["preview"]
    assert updated_preview["tablePlan"][0]["tableId"] == table_id
    assert updated_preview["tablePlan"][0]["selected"] is False


def test_update_table_plan_rejects_unknown_table_id(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    generate_task_preview(task_id)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableSelection": {"table_999": False}},
    )

    assert response.status_code == 400
    assert "Unknown tableId" in response.json()["detail"]


def test_update_table_plan_edits_rows(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    table_id = preview["tablePlan"][0]["tableId"]

    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "tableEdits": {
                table_id: [
                    ["input", "I0.0", "edited button", "edited control"],
                    ["output", "Q0.0", "edited lamp", "edited state"],
                ]
            }
        },
    )

    assert response.status_code == 200
    updated_preview = response.json()["preview"]
    assert updated_preview["tablePlan"][0]["rows"][0][2] == "edited button"
    assert updated_preview["tablePlan"][0]["edited"] is True


def test_table_edit_allows_add_row_for_schema_table(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id, preview = create_preview_ready_table_task(client)
    table_id = preview["tablePlan"][0]["tableId"]
    rows = preview["tablePlan"][0]["rows"] + [["output", "Q0.1", "new lamp", "new state"]]

    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableEdits": {table_id: rows}},
    )

    assert response.status_code == 200
    assert response.json()["preview"]["tablePlan"][0]["rowCount"] == len(rows)


def test_table_edit_allows_delete_row_for_schema_table(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id, preview = create_preview_ready_table_task(client)
    table_id = preview["tablePlan"][0]["tableId"]
    rows = preview["tablePlan"][0]["rows"][:1]

    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableEdits": {table_id: rows}},
    )

    assert response.status_code == 200
    assert response.json()["preview"]["tablePlan"][0]["rowCount"] == 1


def test_update_table_plan_rejects_wrong_column_count(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    generate_task_preview(task_id)
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    table_id = preview["tablePlan"][0]["tableId"]

    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableEdits": {table_id: [["input", "I0.0", "too few"]]}}
    )

    assert response.status_code == 400
    assert "column count" in response.json()["detail"].lower()


def test_update_table_plan_rejects_unknown_table_edit_id(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 0})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={
            "file": (
                "guide.docx",
                make_docx_bytes("I/O assignment uses I0.0 and Q0.0 with start button and indicator light."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    generate_task_preview(task_id)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableEdits": {"table_999": [["input", "I0.0", "x", "y"]]}}
    )

    assert response.status_code == 400
    assert "Unknown tableId" in response.json()["detail"]


def test_manual_table_can_be_added(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, _preview = create_preview_ready_table_task(client)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "manualTables": [
                {
                    "tableId": "manual_table_0",
                    "title": "自定义记录表",
                    "headers": ["项目", "内容", "备注"],
                    "data": {"rows": [["A", "B", "C"]]},
                    "selected": True,
                }
            ]
        },
    )

    assert response.status_code == 200
    manual_tables = [item for item in response.json()["preview"]["tablePlan"] if item["schema"] == "custom_table"]
    assert len(manual_tables) == 1
    assert manual_tables[0]["headers"] == ["项目", "内容", "备注"]


def test_manual_table_rejects_too_many_columns(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, _preview = create_preview_ready_table_task(client)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "manualTables": [
                {
                    "tableId": "manual_table_0",
                    "title": "bad",
                    "headers": ["1", "2", "3", "4", "5", "6", "7"],
                    "data": {"rows": [["", "", "", "", "", "", ""]]},
                    "selected": True,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert "max_columns" in response.json()["detail"] or "6" in response.json()["detail"]


def test_manual_table_rejects_empty_headers(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, _preview = create_preview_ready_table_task(client)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "manualTables": [
                {
                    "tableId": "manual_table_0",
                    "title": "bad",
                    "headers": ["", "内容"],
                    "data": {"rows": [["", ""]]},
                    "selected": True,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert "header" in response.json()["detail"].lower()


def test_image_plan_override_updates_category(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 1})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("guide"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "program.png"},
        files={"file": ("program.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    generate_task_preview(task_id)

    response = client.patch(
        f"/api/reports/tasks/{task_id}/image-plan",
        json={"overrides": {"image_0": {"category": "wiring"}}},
    )

    assert response.status_code == 200
    assert response.json()["preview"]["imagePlan"][0]["category"] == "wiring"


def test_image_plan_override_rejects_unknown_image_ref(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id, _preview = create_preview_ready_table_task(client)
    response = client.patch(
        f"/api/reports/tasks/{task_id}/image-plan",
        json={"overrides": {"image_99": {"category": "program"}}},
    )

    assert response.status_code == 400
    assert "Unknown image_ref" in response.json()["detail"]


def test_image_plan_override_rejects_invalid_category(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 1})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("source report"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("guide"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "program.png"},
        files={"file": ("program.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    generate_task_preview(task_id)

    response = client.patch(
        f"/api/reports/tasks/{task_id}/image-plan",
        json={"overrides": {"image_0": {"category": "bad_category"}}},
    )

    assert response.status_code == 400
    assert "Invalid image category" in response.json()["detail"]


def test_e2e_table_selected_edited_written_to_docx(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, preview = create_preview_ready_table_task(client)
    table_id = preview["tablePlan"][0]["tableId"]

    edit_response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "tableSelection": {table_id: True},
            "tableEdits": {
                table_id: [
                    ["input", "I0.0", "edited button", "edited control"],
                    ["output", "Q0.0", "edited lamp", "edited state"],
                ]
            },
        },
    )
    assert edit_response.status_code == 200

    confirm_response = client.post(f"/api/reports/tasks/{task_id}/confirm")
    assert confirm_response.status_code == 200
    generate_task_output(task_id)

    task_response = client.get(f"/api/reports/tasks/{task_id}")
    assert task_response.status_code == 200
    body = task_response.json()
    assert body["status"] == "done"
    assert body["qualityReport"]["layoutExecutor"]["writtenTables"] >= 1
    assert body["qualityReport"]["tableAudit"]["summary"]["editedCount"] == 1

    download_response = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    assert download_response.status_code == 200
    output_doc = Document(BytesIO(download_response.content))
    table_text = "\n".join(cell.text for table in output_doc.tables for row in table.rows for cell in row.cells)
    assert "edited button" in table_text
    assert "edited lamp" in table_text


def test_e2e_table_unselected_not_written_to_docx(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, preview = create_preview_ready_table_task(client)
    table_id = preview["tablePlan"][0]["tableId"]

    update_response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "tableSelection": {table_id: False},
            "tableEdits": {
                table_id: [
                    ["input", "I0.0", "hidden button", "hidden control"],
                ]
            },
        },
    )
    assert update_response.status_code == 200

    confirm_response = client.post(f"/api/reports/tasks/{task_id}/confirm")
    assert confirm_response.status_code == 200
    generate_task_output(task_id)

    task_response = client.get(f"/api/reports/tasks/{task_id}")
    body = task_response.json()
    assert body["status"] == "done"
    assert body["qualityReport"]["layoutExecutor"]["writtenTables"] == 0
    assert body["qualityReport"]["tableAudit"]["summary"]["unselectedCount"] == 1
    assert body["qualityReport"]["tableAudit"]["plannedTables"][0]["status"] == "user_unselected"

    download_response = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    assert download_response.status_code == 200
    output_doc = Document(BytesIO(download_response.content))
    table_text = "\n".join(cell.text for table in output_doc.tables for row in table.rows for cell in row.cells)
    assert "hidden button" not in table_text


def test_e2e_table_audit_matches_executor_summary(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    task_id, preview = create_preview_ready_table_task(client)
    table_id = preview["tablePlan"][0]["tableId"]

    update_response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={
            "tableSelection": {table_id: True},
            "tableEdits": {
                table_id: [
                    ["input", "I0.0", "audit button", "audit control"],
                ]
            },
        },
    )
    assert update_response.status_code == 200

    client.post(f"/api/reports/tasks/{task_id}/confirm")
    generate_task_output(task_id)

    task_response = client.get(f"/api/reports/tasks/{task_id}")
    body = task_response.json()
    table_audit = body["qualityReport"]["tableAudit"]
    layout_executor = body["qualityReport"]["layoutExecutor"]

    assert table_audit["summary"]["writtenTables"] == layout_executor["writtenTables"]
    assert table_audit["summary"]["tableRows"] == layout_executor["tableRows"]
    assert table_audit["plannedTables"][0]["tableId"] == table_id


def test_external_image_classifier_hook_is_used_in_preview(monkeypatch, tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    def fake_recognize_image_file(path: Path, **kwargs) -> dict:
        return {
            "schema_version": "image-plan.v1",
            "experiment_type": "plc",
            "image_ref": "image_0",
            "imageIndex": 0,
            "filename": path.name,
            "category": "wiring",
            "category_cn": "接线图",
            "confidence": 0.9,
            "review_level": "ok",
            "review_reasons": [],
            "quality": {"readable": True, "needs_review": False},
            "suggested": {
                "insert_section": "四、实验操作过程",
                "caption": "外部识别接线图",
                "size_policy": "wiring",
            },
            "features": {},
            "score_detail": {},
        }

    monkeypatch.setattr("backend.app.services.image_recognizer.recognize_image_file", fake_recognize_image_file)
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "实验一", "imageCount": 1})
    task_id = create_response.json()["taskId"]
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "report", "filename": "report.docx"},
        files={"file": ("report.docx", make_docx_bytes("原报告"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "guide", "filename": "guide.docx"},
        files={"file": ("guide.docx", make_docx_bytes("实验一"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        f"/api/reports/tasks/{task_id}/files",
        data={"fieldName": "image", "filename": "unknown.png"},
        files={"file": ("unknown.png", b"image bytes", "image/png")},
    )

    generate_task_preview(task_id)
    plan = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]["imagePlan"]

    assert plan[0]["type"] == "wiring"
    assert plan[0]["section"] == "四、实验操作过程"
    assert plan[0]["caption"] == "外部识别接线图"


def test_create_task_returns_readable_time_based_task_id(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)

    first = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 1", "imageCount": 0}).json()["taskId"]
    second = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 2", "imageCount": 0}).json()["taskId"]

    assert re.match(r"^task-\d{8}-\d{6}-[0-9a-f]{4}$", first)
    assert re.match(r"^task-\d{8}-\d{6}-[0-9a-f]{4}$", second)
    assert first != second
    assert task_store.get_task(first) is not None
    assert (tmp_path / "tasks" / first).exists()
