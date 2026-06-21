from __future__ import annotations

from typing import Any


TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "io_assignment_table": {
        "title": "I/O 分配表",
        "headers": ["类型", "地址", "元件名称", "功能说明"],
        "max_rows": 20,
    },
    "phenomenon_record_table": {
        "title": "实验现象记录表",
        "headers": ["测试项目", "观察现象", "结果判断"],
        "max_rows": 20,
    },
    "data_record_table": {
        "title": "数据记录表",
        "headers": ["序号", "测量项目", "测量值", "备注"],
        "max_rows": 30,
    },
    "custom_table": {
        "title": "自定义表格",
        "headers": [],
        "max_rows": 30,
        "max_columns": 6,
        "custom_headers": True,
    },
}


def get_table_schema(schema_name: str) -> dict[str, Any]:
    return dict(TABLE_SCHEMAS[schema_name])


def list_table_schemas() -> dict[str, dict[str, Any]]:
    return {name: dict(schema) for name, schema in TABLE_SCHEMAS.items()}


def validate_table_block(block: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_name = str(block.get("schema") or "").strip()
    if schema_name not in TABLE_SCHEMAS:
        return [f"unknown table schema: {schema_name or '<empty>'}"]

    schema = TABLE_SCHEMAS[schema_name]
    uses_custom_headers = bool(schema.get("custom_headers"))
    headers = _normalize_headers(block.get("headers")) if uses_custom_headers else list(schema.get("headers") or [])

    if not uses_custom_headers and "headers" in block:
        errors.append("table block cannot override schema headers")

    if uses_custom_headers:
        if not headers:
            errors.append("custom table headers must not be empty")
        if len(headers) > int(schema.get("max_columns") or 0):
            errors.append(
                f"custom table headers exceed max_columns: {len(headers)} > {schema.get('max_columns')}"
            )

    expected_columns = len(headers)
    data = block.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return errors + ["table block data.rows must be a list"]

    if len(rows) > int(schema["max_rows"]):
        errors.append(f"table block rows exceed max_rows: {len(rows)} > {schema['max_rows']}")

    for row_index, row in enumerate(rows):
        if not isinstance(row, list):
            errors.append(f"table row {row_index} must be a list")
            continue
        if expected_columns and len(row) != expected_columns:
            errors.append(
                f"table row {row_index} column count mismatch: expected {expected_columns}, got {len(row)}"
            )
        for column_index, cell in enumerate(row):
            if isinstance(cell, (list, dict, tuple, set)):
                errors.append(f"table row {row_index} cell {column_index} must be a scalar value")
    return errors


def _normalize_headers(headers: Any) -> list[str]:
    if not isinstance(headers, list):
        return []
    normalized: list[str] = []
    for value in headers:
        text = str(value or "").strip()
        if not text:
            return []
        normalized.append(text)
    return normalized
