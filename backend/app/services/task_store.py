from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any


TaskStatus = str


@dataclass
class TaskRecord:
    task_id: str
    metadata: dict[str, Any]
    root_dir: Path
    user_id: str | None = None
    status: TaskStatus = "queued"
    message: str = "Task created, waiting for uploads"
    progress: int = 5
    report_file: Path | None = None
    guide_file: Path | None = None
    image_files: list[Path] = field(default_factory=list)
    output_file: Path | None = None
    preview_data: dict[str, Any] | None = None
    preview_layout_plan: dict[str, Any] | None = None
    ai_layout_plan_report: dict[str, Any] | None = None
    layout_plan_source: str = "rule"
    adopted_ai_layout_plan: dict[str, Any] | None = None
    table_selection: dict[str, bool] | None = None
    table_edits: dict[str, list[list[str]]] | None = None
    manual_tables: list[dict[str, Any]] | None = None
    image_plan_overrides: dict[str, dict[str, Any]] | None = None
    shadow_gate_report: dict[str, Any] | None = None
    layout_executor_report: dict[str, Any] | None = None
    table_audit_report: dict[str, Any] | None = None
    quality_report: dict[str, Any] | None = None
    error: str = ""
    preview_started: bool = False
    generation_started: bool = False
    preview_running: bool = False
    generation_running: bool = False
    preview_lock: RLock = field(default_factory=RLock, repr=False)
    generation_lock: RLock = field(default_factory=RLock, repr=False)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def upload_dir(self) -> Path:
        return self.root_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "outputs"

    def to_response(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "taskId": self.task_id,
            "status": self.status,
            "message": self.error or self.message,
            "progress": self.progress,
            "experimentNo": str(self.metadata.get("experimentNo") or ""),
            "userId": self.user_id or "",
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.output_file:
            body["resultName"] = self.output_file.name
        if self.preview_data:
            body["preview"] = self.preview_data
        if self.quality_report:
            body["qualityReport"] = self.quality_report
        return body

    def to_summary_response(self) -> dict[str, Any]:
        body = {
            "taskId": self.task_id,
            "status": self.status,
            "message": self.error or self.message,
            "progress": self.progress,
            "experimentNo": str(self.metadata.get("experimentNo") or ""),
            "userId": self.user_id or "",
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.output_file:
            body["resultName"] = self.output_file.name
        return body


class TaskStore:
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.tasks: dict[str, TaskRecord] = {}
        self._lock = RLock()
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def reset(self, storage_root: Path | None = None) -> None:
        if storage_root is not None:
            self.storage_root = storage_root
        if self.storage_root.exists():
            shutil.rmtree(self.storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.tasks = {}

    def create_task(self, metadata: dict[str, Any], user_id: str | None = None) -> TaskRecord:
        task_id = uuid.uuid4().hex
        record = TaskRecord(task_id=task_id, metadata=metadata, root_dir=self.storage_root / task_id, user_id=user_id)
        record.upload_dir.mkdir(parents=True, exist_ok=True)
        record.output_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.tasks[task_id] = record
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self.tasks.get(task_id)

    def list_tasks(self, user_id: str | None = None) -> list[TaskRecord]:
        with self._lock:
            records = list(self.tasks.values())
            if user_id:
                records = [record for record in records if record.user_id == user_id]
            return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def save_upload_bytes(self, record: TaskRecord, field_name: str, filename: str, content: bytes) -> Path:
        safe_name = Path(filename or "upload.bin").name or "upload.bin"
        target_dir = record.upload_dir / field_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._dedupe_path(target_dir / safe_name)
        target.write_bytes(content)

        if field_name == "report":
            record.report_file = target
        elif field_name == "guide":
            record.guide_file = target
        elif field_name == "image":
            record.image_files.append(target)

        if record.status not in {"previewing", "preview_ready", "processing", "done", "failed"}:
            record.status = "uploading"
            record.progress = 35
            record.message = "Files uploaded, waiting for generation"
        self.touch(record)
        return target

    def mark_previewing(self, record: TaskRecord) -> None:
        record.status = "previewing"
        record.progress = 60
        record.message = "Generating report outline preview"
        record.preview_started = True
        self.touch(record)

    def mark_preview_ready(
        self,
        record: TaskRecord,
        preview_data: dict[str, Any],
        preview_layout_plan: dict[str, Any] | None = None,
    ) -> None:
        record.preview_data = preview_data
        record.preview_layout_plan = preview_layout_plan
        record.status = "preview_ready"
        record.progress = 75
        record.message = "Preview is ready, please confirm before generating DOCX"
        self.touch(record)

    def mark_processing(self, record: TaskRecord) -> None:
        record.status = "processing"
        record.progress = 70
        record.message = "Generating revised DOCX"
        record.generation_started = True
        self.touch(record)

    def mark_done(self, record: TaskRecord, output_file: Path, quality_report: dict[str, Any] | None = None) -> None:
        record.output_file = output_file
        record.quality_report = quality_report
        record.status = "done"
        record.progress = 100
        record.message = "Generation complete, DOCX can be downloaded"
        self.touch(record)

    def mark_failed(self, record: TaskRecord, error: str) -> None:
        record.status = "failed"
        record.progress = 100
        record.error = error
        self.touch(record)

    def touch(self, record: TaskRecord) -> None:
        record.updated_at = time.time()

    def _dedupe_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 2
        while True:
            candidate = parent / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1
