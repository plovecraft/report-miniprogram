from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Thread
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .services.docx_builder import (
    adopt_ai_preview_layout_plan,
    apply_table_edits_to_layout_plan,
    build_image_plan,
    build_report_preview,
    build_revised_docx,
    build_validated_layout_plan,
    extract_table_preview_summary,
    get_selected_preview_layout_plan,
    refresh_preview_runtime_state,
    restore_rule_preview_layout_plan,
    validate_and_normalize_image_plan_overrides,
    validate_and_normalize_manual_tables,
)
from .services.ai_layout_planner import build_ai_planner_preview_summary
from .services.image_classifier import classify_image_info, image_categories_by_filename
from .services.llm_writer import LLMConfig
from .services.material_package import extract_material_package
from .services.quality_checker import build_quality_report
from .services.runtime_config import runtime_summary
from .services.task_store import TaskRecord, TaskStore
from .services.user_store import UserStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("report-backend")


def _resolve_storage_root(backend_root: Path) -> Path:
    configured = str(os.getenv("STORAGE_DIR") or "").strip()
    if not configured:
        return backend_root / "storage"
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = (backend_root / candidate).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _cors_origins() -> list[str]:
    raw = str(os.getenv("CORS_ORIGINS") or "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _max_upload_bytes() -> int:
    raw = str(os.getenv("MAX_UPLOAD_MB") or "100").strip()
    try:
        mb = max(1, int(raw))
    except ValueError:
        mb = 100
    return mb * 1024 * 1024


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")
STORAGE_ROOT = _resolve_storage_root(BACKEND_ROOT)
task_store = TaskStore(STORAGE_ROOT / "tasks")
user_store = UserStore(STORAGE_ROOT / "app.sqlite3")
MAX_UPLOAD_BYTES = _max_upload_bytes()

app = FastAPI(title="Experiment Report Backend MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    llm_config = LLMConfig.from_env()
    body: dict[str, Any] = {"status": "ok", "llmConfigured": llm_config is not None, "runtime": runtime_summary()}
    if llm_config is not None:
        body["llmBaseUrl"] = llm_config.base_url
        body["llmModel"] = llm_config.model
    return body


@app.post("/api/auth/wechat-login")
def wechat_login(payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing WeChat login code")
    dev_openid = str(payload.get("devOpenid") or "").strip()
    try:
        return user_store.login_with_wechat_code(code, dev_openid=dev_openid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/users/me")
def get_current_user(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"user": user}


@app.get("/api/users/me/usage")
def get_current_user_usage(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"records": user_store.list_usage(user["userId"])}


@app.post("/api/reports/tasks")
def create_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    user = _current_user(request)
    record = task_store.create_task(payload, user_id=user["userId"] if user else None)
    user_store.record_usage(record.user_id, "task_created", record.task_id, {"experimentNo": payload.get("experimentNo")})
    logger.info(
        "task created task_id=%s experiment=%s expected_images=%s",
        record.task_id,
        payload.get("experimentNo"),
        expected_image_count(record),
    )
    return record.to_response()


@app.get("/api/reports/tasks")
def list_tasks(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    records = task_store.list_tasks(user_id=user["userId"] if user else None)
    return {"tasks": [record.to_summary_response() for record in records]}


@app.post("/api/reports/tasks/{task_id}/files")
async def upload_task_file(task_id: str, request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)

    content_length = request.headers.get("content-length", "")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds MAX_UPLOAD_MB={MAX_UPLOAD_BYTES // (1024 * 1024)}",
                )
        except ValueError:
            pass
    form = _parse_multipart(await request.body(), request.headers.get("content-type", ""))
    field_name = form["fields"].get("fieldName", "")
    filename = form["fields"].get("filename") or form["file_name"]
    file_content = form["file_content"]
    if field_name not in {"report", "guide", "image", "materialZip"}:
        raise HTTPException(status_code=400, detail="Unknown file field")

    if field_name == "materialZip":
        try:
            package = extract_material_package(file_content, record.upload_dir / "material_package")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _apply_material_package(record, package)
        logger.info(
            "material package saved task_id=%s filename=%s report=%s guide=%s images=%s",
            task_id,
            filename,
            record.report_file.name if record.report_file else None,
            record.guide_file.name if record.guide_file else None,
            len(record.image_files),
        )
        start_preview_if_ready(record)
        return record.to_response()

    saved_path = task_store.save_upload_bytes(record, field_name, filename, file_content)
    logger.info(
        "file saved task_id=%s field=%s filename=%s bytes=%s uploaded_images=%s/%s path=%s",
        task_id,
        field_name,
        filename,
        len(file_content),
        len(record.image_files),
        expected_image_count(record),
        saved_path,
    )
    start_preview_if_ready(record)
    return record.to_response()


def _apply_material_package(record: TaskRecord, package) -> None:
    if package.report_file is not None:
        record.report_file = package.report_file
    if package.guide_file is not None:
        record.guide_file = package.guide_file
    record.image_files.extend(package.image_files)
    existing_metas = record.metadata.get("imageMetas")
    if not isinstance(existing_metas, list):
        existing_metas = []
    record.metadata["imageMetas"] = existing_metas + package.image_metas
    record.metadata["imageCount"] = len(record.image_files)
    if record.status not in {"previewing", "preview_ready", "processing", "done", "failed"}:
        record.status = "uploading"
        record.progress = 35
        record.message = "Material package uploaded, waiting for generation"
    task_store.touch(record)


def start_preview_if_ready(record: TaskRecord) -> None:
    if record.preview_started or record.preview_data or record.generation_started:
        return
    if not record.report_file or not record.guide_file:
        logger.info(
            "preview waiting task_id=%s report=%s guide=%s",
            record.task_id,
            bool(record.report_file),
            bool(record.guide_file),
        )
        return

    expected_images = expected_image_count(record)
    if len(record.image_files) < expected_images:
        logger.info("preview waiting task_id=%s images=%s/%s", record.task_id, len(record.image_files), expected_images)
        return

    task_store.mark_previewing(record)
    logger.info("preview queued task_id=%s", record.task_id)
    Thread(target=generate_task_preview, args=(record.task_id,), daemon=True).start()


def start_generation_if_confirmed(record: TaskRecord) -> None:
    if record.generation_started:
        return
    if not record.preview_data:
        raise HTTPException(status_code=409, detail="Preview is not ready")

    task_store.mark_processing(record)
    logger.info("generation queued task_id=%s", record.task_id)
    Thread(target=generate_task_output, args=(record.task_id,), daemon=True).start()


def expected_image_count(record: TaskRecord) -> int:
    raw_value = record.metadata.get("imageCount", 0)
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 0


def generate_task_preview(task_id: str) -> None:
    record = task_store.get_task(task_id)
    if record is None:
        logger.warning("preview skipped missing task task_id=%s", task_id)
        return
    with record.preview_lock:
        if record.preview_data:
            logger.info("preview skipped existing preview task_id=%s", task_id)
            return

        try:
            logger.info(
                "preview started task_id=%s report=%s guide=%s images=%s llm_configured=%s",
                task_id,
                record.report_file.name if record.report_file else None,
                record.guide_file.name if record.guide_file else None,
                [path.name for path in record.image_files],
                LLMConfig.from_env() is not None,
            )
            preview_data = build_report_preview(record)
            task_store.mark_preview_ready(record, preview_data, record.preview_layout_plan)
            logger.info(
                "preview ready task_id=%s sections=%s images=%s",
                task_id,
                len(preview_data.get("sections") or []),
                len(preview_data.get("imagePlan") or []),
            )
        except Exception as exc:
            task_store.mark_failed(record, str(exc))
            logger.exception("preview failed task_id=%s", task_id)


def generate_task_output(task_id: str) -> None:
    record = task_store.get_task(task_id)
    if record is None:
        logger.warning("generation skipped missing task task_id=%s", task_id)
        return
    with record.generation_lock:
        if record.output_file and record.output_file.exists():
            logger.info("generation skipped existing output task_id=%s output=%s", task_id, record.output_file)
            return

        try:
            logger.info(
                "generation started task_id=%s report=%s guide=%s images=%s llm_configured=%s",
                task_id,
                record.report_file.name if record.report_file else None,
                record.guide_file.name if record.guide_file else None,
                [path.name for path in record.image_files],
                LLMConfig.from_env() is not None,
            )
            output_file = build_revised_docx(record)
            quality_report = build_quality_report(
                source_file=record.report_file,
                output_file=output_file,
                expected_image_count=expected_inserted_image_count(record),
                target_experiment=str(record.metadata.get("experimentNo") or ""),
            )
            if record.shadow_gate_report:
                quality_report["shadowGate"] = {
                    "passed": bool(record.shadow_gate_report.get("passed")),
                    "warnings": list(record.shadow_gate_report.get("warnings") or []),
                    "errors": list(record.shadow_gate_report.get("errors") or []),
                    "summary": dict(record.shadow_gate_report.get("summary") or {}),
                    "skipped": bool(record.shadow_gate_report.get("skipped")),
                }
            if record.layout_executor_report:
                quality_report["layoutExecutor"] = {
                    "used": bool(record.layout_executor_report.get("used")),
                    "fallbackUsed": bool(record.layout_executor_report.get("fallbackUsed")),
                    "fallbackReason": record.layout_executor_report.get("fallbackReason"),
                    "writtenBlocks": record.layout_executor_report.get("writtenBlocks"),
                    "writtenImages": record.layout_executor_report.get("writtenImages"),
                    "degradedImages": record.layout_executor_report.get("degradedImages"),
                    "imageRows": record.layout_executor_report.get("imageRows"),
                    "pairedImages": record.layout_executor_report.get("pairedImages"),
                    "writtenTables": record.layout_executor_report.get("writtenTables"),
                    "tableRows": record.layout_executor_report.get("tableRows"),
                    "warnings": list(record.layout_executor_report.get("warnings") or []),
                    "errors": list(record.layout_executor_report.get("errors") or []),
                }
            if record.ai_layout_plan_report:
                quality_report["aiPlanner"] = build_ai_planner_preview_summary(record.ai_layout_plan_report)
            quality_report["tableAudit"] = record.table_audit_report
            task_store.mark_done(record, output_file, quality_report)
            user_store.record_usage(record.user_id, "task_done", task_id, {"resultName": output_file.name})
            logger.info("generation done task_id=%s output=%s quality_passed=%s", task_id, output_file, quality_report["passed"])
        except Exception as exc:
            task_store.mark_failed(record, str(exc))
            user_store.record_usage(record.user_id, "task_failed", task_id, {"error": str(exc)})
            logger.exception("generation failed task_id=%s", task_id)


@app.get("/api/reports/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    return record.to_response()


@app.post("/api/reports/tasks/{task_id}/confirm")
def confirm_task_preview(task_id: str, request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if record.output_file and record.output_file.exists():
        return record.to_response()
    start_generation_if_confirmed(record)
    return record.to_response()


@app.patch("/api/reports/tasks/{task_id}/image-plan")
def update_task_image_plan(task_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if record.generation_started or record.output_file:
        raise HTTPException(status_code=409, detail="Cannot update image plan after generation has started")
    images = payload.get("images")
    overrides = payload.get("overrides")
    if images is not None and not isinstance(images, list):
        raise HTTPException(status_code=400, detail="images must be a list")
    if overrides is not None and not isinstance(overrides, dict):
        raise HTTPException(status_code=400, detail="overrides must be an object")
    if images is None and overrides is None:
        raise HTTPException(status_code=400, detail="Missing images or overrides")

    if isinstance(images, list):
        _merge_image_plan_metadata(record, images)
    if isinstance(overrides, dict):
        try:
            validated_overrides = validate_and_normalize_image_plan_overrides(overrides, record.preview_data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        next_overrides = dict(record.image_plan_overrides or {})
        next_overrides.update(validated_overrides)
        record.image_plan_overrides = next_overrides
    record.preview_data = build_report_preview(record)
    task_store.mark_preview_ready(record, record.preview_data, record.preview_layout_plan)
    logger.info(
        "image plan updated task_id=%s images=%s overrides=%s",
        task_id,
        len(images or []),
        len(record.image_plan_overrides or {}),
    )
    return record.to_response()


@app.patch("/api/reports/tasks/{task_id}/table-plan")
def update_task_table_plan(task_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if record.generation_started or record.output_file:
        raise HTTPException(status_code=409, detail="Cannot update table plan after generation has started")
    if not isinstance(record.preview_layout_plan, dict) or not isinstance(record.preview_data, dict):
        raise HTTPException(status_code=409, detail="Preview is not ready")

    selection = payload.get("tableSelection")
    edits = payload.get("tableEdits")
    manual_tables = payload.get("manualTables")
    if selection is not None and not isinstance(selection, dict):
        raise HTTPException(status_code=400, detail="tableSelection must be an object")
    if edits is not None and not isinstance(edits, dict):
        raise HTTPException(status_code=400, detail="tableEdits must be an object")
    if manual_tables is not None and not isinstance(manual_tables, list):
        raise HTTPException(status_code=400, detail="manualTables must be a list")
    if selection is None and edits is None and manual_tables is None:
        raise HTTPException(status_code=400, detail="Missing tableSelection, tableEdits, or manualTables object")

    if isinstance(manual_tables, list):
        try:
            record.manual_tables = validate_and_normalize_manual_tables(manual_tables)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        manual_selection = dict(record.table_selection or {})
        manual_ids = {str(table.get("tableId") or "").strip() for table in record.manual_tables if str(table.get("tableId") or "").strip()}
        for table in record.manual_tables:
            table_id = str(table.get("tableId") or "").strip()
            if table_id:
                manual_selection[table_id] = bool(table.get("selected", True))
        record.table_selection = {
            table_id: selected
            for table_id, selected in manual_selection.items()
            if table_id not in manual_ids or any(str(table.get("tableId") or "").strip() == table_id for table in record.manual_tables)
        }
        if isinstance(record.table_edits, dict):
            record.table_edits = {
                table_id: rows
                for table_id, rows in record.table_edits.items()
                if not table_id.startswith("manual_table_") or table_id in manual_ids
            }

    active_layout_plan = get_selected_preview_layout_plan(record)
    if not isinstance(active_layout_plan, dict):
        raise HTTPException(status_code=409, detail="Preview layout plan is unavailable")
    table_summary = extract_table_preview_summary(active_layout_plan)
    valid_table_ids = {
        str(item.get("tableId") or "").strip()
        for item in table_summary
        if str(item.get("tableId") or "").strip()
    }
    provided_ids = set()
    if isinstance(selection, dict):
        provided_ids.update(str(table_id).strip() for table_id in selection.keys())
    if isinstance(edits, dict):
        provided_ids.update(str(table_id).strip() for table_id in edits.keys())
    unknown_table_ids = sorted(table_id for table_id in provided_ids if table_id and table_id not in valid_table_ids)
    if unknown_table_ids:
        raise HTTPException(status_code=400, detail=f"Unknown tableId: {', '.join(unknown_table_ids)}")

    if isinstance(selection, dict):
        next_selection = dict(record.table_selection or {})
        for table_id, selected in selection.items():
            normalized_id = str(table_id).strip()
            if normalized_id:
                next_selection[normalized_id] = bool(selected)
        record.table_selection = next_selection
    if isinstance(edits, dict):
        normalized_edits = {
            str(table_id).strip(): rows
            for table_id, rows in edits.items()
            if str(table_id).strip()
        }
        try:
            apply_table_edits_to_layout_plan(active_layout_plan, normalized_edits)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        next_edits = dict(record.table_edits or {})
        next_edits.update(normalized_edits)
        record.table_edits = next_edits
    refresh_preview_runtime_state(record)
    task_store.touch(record)
    logger.info(
        "table plan updated task_id=%s selection=%s edits=%s manualTables=%s",
        task_id,
        len(record.table_selection or {}),
        len(record.table_edits or {}),
        len(record.manual_tables or []),
    )
    return record.to_response()


@app.patch("/api/reports/tasks/{task_id}/layout-plan-source")
def update_task_layout_plan_source(task_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if record.generation_started or record.output_file:
        raise HTTPException(status_code=409, detail="Cannot update layout plan source after generation has started")
    if not isinstance(record.preview_layout_plan, dict) or not isinstance(record.preview_data, dict):
        raise HTTPException(status_code=409, detail="Preview is not ready")

    source = str(payload.get("source") or "").strip().lower()
    if source not in {"rule", "ai"}:
        raise HTTPException(status_code=400, detail="source must be 'rule' or 'ai'")

    try:
        if source == "ai":
            adopt_ai_preview_layout_plan(record)
        else:
            restore_rule_preview_layout_plan(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_store.touch(record)
    logger.info("layout plan source updated task_id=%s source=%s", task_id, record.layout_plan_source)
    return {
        "ok": True,
        "layoutPlanSource": record.layout_plan_source,
        "preview": record.preview_data,
        "task": record.to_response(),
    }


def expected_inserted_image_count(record: TaskRecord) -> int:
    try:
        image_plan = build_image_plan(record.image_files, record.metadata)
    except Exception:
        categories = image_categories_by_filename(record.metadata.get("imageMetas"))
        return sum(1 for path in record.image_files if classify_image_info(path.name, categories.get(path.name)) is not None)
    return sum(1 for item in image_plan if str(item.get("type") or "") != "skip")


def _merge_image_plan_metadata(record: TaskRecord, updates: list[dict[str, Any]]) -> None:
    current = record.metadata.get("imageMetas")
    if not isinstance(current, list):
        current = []
    by_filename = {
        Path(str(item.get("filename") or "")).name: dict(item)
        for item in current
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    }
    valid_filenames = {path.name for path in record.image_files}
    for update in updates:
        if not isinstance(update, dict):
            continue
        filename = Path(str(update.get("filename") or "")).name
        if filename not in valid_filenames:
            continue
        merged = by_filename.get(filename, {"filename": filename})
        for key in ["category", "section", "caption", "sortOrder"]:
            if key in update:
                merged[key] = update[key]
        by_filename[filename] = merged
    record.metadata["imageMetas"] = list(by_filename.values())
    task_store.touch(record)


@app.get("/api/reports/tasks/{task_id}/download")
def download_task_result(task_id: str, request: Request, format: str = "docx") -> FileResponse:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if format != "docx":
        raise HTTPException(status_code=400, detail="Current MVP only supports DOCX download")
    if record.output_file is None or not record.output_file.exists():
        raise HTTPException(status_code=404, detail="Result file is not ready")

    logger.info("download result task_id=%s output=%s", task_id, record.output_file)
    return FileResponse(
        record.output_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=record.output_file.name,
    )


@app.get("/api/reports/tasks/{task_id}/images/{image_index}")
def get_task_image(task_id: str, image_index: int, request: Request) -> FileResponse:
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(record, request)
    if image_index < 0 or image_index >= len(record.image_files):
        raise HTTPException(status_code=404, detail="Image not found")
    image_file = record.image_files[image_index]
    if not image_file.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_file, media_type=_image_media_type(image_file), filename=image_file.name)


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".bmp":
        return "image/bmp"
    return "application/octet-stream"


def _current_user(request: Request) -> dict[str, Any] | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        return user_store.get_user_by_token(token)
    token = str(request.query_params.get("access_token") or "").strip()
    if token:
        return user_store.get_user_by_token(token)
    return None


def _ensure_task_access(record: TaskRecord, request: Request) -> None:
    if not record.user_id:
        return
    user = _current_user(request)
    if user is None or user["userId"] != record.user_id:
        raise HTTPException(status_code=403, detail="No access to this task")


def _parse_multipart(body: bytes, content_type: str) -> dict[str, Any]:
    boundary_marker = "boundary="
    if boundary_marker not in content_type:
        raise HTTPException(status_code=400, detail="Request is not multipart/form-data")
    boundary = content_type.split(boundary_marker, 1)[1].strip().strip('"')
    boundary_bytes = ("--" + boundary).encode()

    fields: dict[str, str] = {}
    file_name = ""
    file_content = b""

    for raw_part in body.split(boundary_bytes):
        part = raw_part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue

        raw_headers, content = part.split(b"\r\n\r\n", 1)
        content = content.removesuffix(b"\r\n")
        headers = raw_headers.decode("utf-8", errors="replace")
        disposition = next((line for line in headers.split("\r\n") if line.lower().startswith("content-disposition:")), "")
        name = _extract_disposition_value(disposition, "name")
        filename = _extract_disposition_value(disposition, "filename")

        if filename:
            file_name = filename
            file_content = content
        elif name:
            fields[name] = content.decode("utf-8", errors="replace")

    if not file_content:
        raise HTTPException(status_code=400, detail="Missing upload file")
    return {"fields": fields, "file_name": file_name or "upload.bin", "file_content": file_content}


def _extract_disposition_value(disposition: str, key: str) -> str:
    token = f'{key}="'
    if token not in disposition:
        return ""
    return disposition.split(token, 1)[1].split('"', 1)[0]
