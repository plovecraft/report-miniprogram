from __future__ import annotations

from base64 import b64decode
from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

from backend.app.main import app, generate_task_output, generate_task_preview, task_store
from backend.app.services.docx_builder import build_report_preview


PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def make_docx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buffer)
    return buffer.getvalue()


def create_preview_ready_ai_task(client: TestClient) -> str:
    create_response = client.post("/api/reports/tasks", json={"experimentNo": "Experiment 3", "imageCount": 1})
    task_id = create_response.json()["taskId"]
    record = task_store.get_task(task_id)
    assert record is not None
    report = record.upload_dir / "report.docx"
    guide = record.upload_dir / "guide.docx"
    image = record.upload_dir / "program.png"
    report.write_bytes(make_docx_bytes("source report"))
    guide.write_bytes(make_docx_bytes("guide text"))
    image.write_bytes(PNG_1X1)
    record.report_file = report
    record.guide_file = guide
    record.image_files = [image]
    preview = build_report_preview(record)
    task_store.mark_preview_ready(record, preview, record.preview_layout_plan)
    return task_id


def _candidate_plan(include_table: bool = False) -> dict:
    plan = {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentName": "Experiment 3",
        "sections": [
            {"key": "section_1", "title": "AI 章节", "blocks": [{"type": "paragraph", "content": "AI ONLY TEXT"}]},
            {"key": "section_2", "title": "AI 图片", "blocks": [{"type": "image", "imageIndex": 0, "caption": "AI 图片图注"}]},
        ],
        "warnings": [],
    }
    if include_table:
        plan["sections"][0]["blocks"].append(
            {
                "type": "table",
                "schema": "io_assignment_table",
                "data": {"rows": [["输入", "I0.0", "原按钮", "原说明"]]},
            }
        )
    return plan


def test_adopt_ai_layout_plan_success(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }

    response = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["layoutPlanSource"] == "ai"
    assert body["preview"]["layoutPlanSource"] == "ai"
    assert record.layout_plan_source == "ai"
    assert isinstance(record.adopted_ai_layout_plan, dict)


def test_adopt_ai_layout_plan_rejects_invalid_candidate(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": False,
        "candidatePlan": {"schemaVersion": 1, "sections": [], "warnings": []},
        "validation": {"passed": False, "errors": ["unsupported block type: video"], "warnings": []},
        "summary": {"sectionCount": 0},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 0, "warnings": []},
        "error": "unsupported block type: video",
    }

    response = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    assert response.status_code == 400
    assert "unsupported block type" in response.json()["detail"]
    assert record.layout_plan_source == "rule"
    assert record.adopted_ai_layout_plan is None


def test_restore_rule_layout_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    response = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "rule"})

    assert response.status_code == 200
    assert response.json()["layoutPlanSource"] == "rule"
    assert response.json()["preview"]["layoutPlanSource"] == "rule"
    assert record.layout_plan_source == "rule"
    assert record.adopted_ai_layout_plan is None


def test_build_revised_docx_uses_adopted_ai_plan_after_shadow_gate(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    adopt = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})
    assert adopt.status_code == 200

    client.post(f"/api/reports/tasks/{task_id}/confirm")
    generate_task_output(task_id)

    assert record.shadow_gate_report is not None
    assert record.shadow_gate_report["skipped"] is False
    output = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    output_doc = Document(BytesIO(output.content))
    body_text = "\n".join(p.text for p in output_doc.paragraphs) + "\n" + "\n".join(cell.text for table in output_doc.tables for row in table.rows for cell in row.cells)
    assert "AI ONLY TEXT" in body_text


def test_table_selection_and_edits_still_apply_to_ai_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(include_table=True),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    adopt = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})
    assert adopt.status_code == 200
    preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    table_id = preview["tablePlan"][0]["tableId"]

    edit_response = client.patch(
        f"/api/reports/tasks/{task_id}/table-plan",
        json={"tableSelection": {table_id: True}, "tableEdits": {table_id: [["输入", "I0.0", "改后按钮", "改后说明"]]}},
    )
    assert edit_response.status_code == 200

    client.post(f"/api/reports/tasks/{task_id}/confirm")
    generate_task_output(task_id)
    output = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    output_doc = Document(BytesIO(output.content))
    table_text = "\n".join(cell.text for table in output_doc.tables for row in table.rows for cell in row.cells)
    assert "改后按钮" in table_text

    task_store.mark_preview_ready(record, record.preview_data, record.preview_layout_plan)
    record.output_file = None
    record.quality_report = None
    record.generation_started = False
    hide_response = client.patch(f"/api/reports/tasks/{task_id}/table-plan", json={"tableSelection": {table_id: False}})
    assert hide_response.status_code == 200
    client.post(f"/api/reports/tasks/{task_id}/confirm")
    generate_task_output(task_id)
    output = client.get(f"/api/reports/tasks/{task_id}/download?format=docx")
    output_doc = Document(BytesIO(output.content))
    table_text = "\n".join(cell.text for table in output_doc.tables for row in table.rows for cell in row.cells)
    assert "改后按钮" not in table_text


def test_adopt_ai_plan_rejects_unknown_image_ref(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    candidate = _candidate_plan()
    candidate["sections"][1]["blocks"][0]["image_ref"] = "image_999"
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": candidate,
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }

    response = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    assert response.status_code == 400
    assert "unknown image_ref" in response.json()["detail"]


def test_adopt_ai_plan_rejects_unknown_table_schema(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    candidate = _candidate_plan()
    candidate["sections"][0]["blocks"].append({"type": "table", "schema": "bad_schema", "data": {"rows": [["x"]]}})
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": candidate,
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }

    response = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    assert response.status_code == 400
    assert "schema" in response.json()["detail"] or "invalid" in response.json()["detail"]


def test_preview_shows_layout_plan_source_and_adoptable(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    from backend.app.services.docx_builder import refresh_preview_runtime_state

    refresh_preview_runtime_state(record)
    body = client.get(f"/api/reports/tasks/{task_id}").json()

    assert body["preview"]["layoutPlanSource"] == "rule"
    assert body["preview"]["aiPlannerPreview"]["adoptable"] is True


def test_preview_sections_follow_rule_plan_by_default(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)

    body = client.get(f"/api/reports/tasks/{task_id}").json()

    section_titles = [section["title"] for section in body["preview"]["sections"]]
    assert body["preview"]["layoutPlanSource"] == "rule"
    assert "AI 章节" not in section_titles


def test_preview_sections_follow_ai_plan_when_adopted(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }

    adopt = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    assert adopt.status_code == 200
    preview = adopt.json()["preview"]
    section_titles = [section["title"] for section in preview["sections"]]
    assert preview["layoutPlanSource"] == "ai"
    assert "AI 章节" in section_titles
    assert "一、实验目的" not in section_titles


def test_restore_rule_plan_restores_preview_sections(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    restore = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "rule"})

    assert restore.status_code == 200
    preview = restore.json()["preview"]
    section_titles = [section["title"] for section in preview["sections"]]
    assert preview["layoutPlanSource"] == "rule"
    assert "AI 章节" not in section_titles
    assert "一、实验目的" in section_titles


def test_table_plan_follows_effective_layout_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": {
            "schemaVersion": 1,
            "experimentType": "plc",
            "experimentName": "Experiment 3",
            "sections": [
                {
                    "key": "section_1",
                    "title": "AI 章节",
                    "blocks": [
                        {
                            "type": "table",
                            "schema": "phenomenon_record_table",
                            "data": {"rows": [["运行", "观察变化", "基本正常"]]},
                        }
                    ],
                }
            ],
            "warnings": [],
        },
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 1},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 1, "warnings": []},
        "error": None,
    }
    rule_preview = client.get(f"/api/reports/tasks/{task_id}").json()["preview"]
    rule_schemas = [item["schema"] for item in rule_preview["tablePlan"]]

    adopt = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})
    ai_schemas = [item["schema"] for item in adopt.json()["preview"]["tablePlan"]]
    restore = client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "rule"})
    restored_schemas = [item["schema"] for item in restore.json()["preview"]["tablePlan"]]

    assert rule_schemas != ai_schemas
    assert ai_schemas == ["phenomenon_record_table"]
    assert restored_schemas == rule_schemas


def test_preview_sections_do_not_expose_candidate_plan(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    body = client.get(f"/api/reports/tasks/{task_id}").json()

    assert "candidatePlan" not in body["preview"]


def test_build_revised_docx_unchanged_after_preview_section_alignment(tmp_path: Path) -> None:
    task_store.reset(tmp_path / "tasks")
    client = TestClient(app)
    task_id = create_preview_ready_ai_task(client)
    record = task_store.get_task(task_id)
    assert record is not None
    record.ai_layout_plan_report = {
        "enabled": True,
        "ok": True,
        "candidatePlan": _candidate_plan(),
        "validation": {"passed": True, "errors": [], "warnings": []},
        "summary": {"sectionCount": 2},
        "comparison": {"ruleSectionCount": 7, "aiSectionCount": 2, "warnings": []},
        "error": None,
    }
    client.patch(f"/api/reports/tasks/{task_id}/layout-plan-source", json={"source": "ai"})

    client.post(f"/api/reports/tasks/{task_id}/confirm")
    generate_task_output(task_id)

    assert record.shadow_gate_report is not None
    assert record.layout_executor_report is not None
