from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


MAX_AUTO_TABLES = 2

IO_KEYWORDS = ["i/o", "io", "输入输出", "输入端口", "输出端口", "plc地址", "i0.", "q0.", "x0", "y0", "按钮", "指示灯", "线圈", "触点"]
PHENOMENON_KEYWORDS = ["实验现象", "运行现象", "运行结果", "指示灯", "输出状态", "观察结果"]
DATA_KEYWORDS = ["数据", "测量", "记录", "电压", "电流", "压力", "流量", "误差", "理论值", "测量值"]


def plan_tables_for_preview(
    *,
    experiment_type: str,
    guide_text: str = "",
    report_text: str = "",
    image_plan: list | None = None,
    preview_sections: list | None = None,
) -> list[dict[str, Any]]:
    text = f"{guide_text}\n{report_text}".lower()
    planned: list[dict[str, Any]] = []

    if _contains_any(text, IO_KEYWORDS):
        io_rows = _extract_io_assignment_rows(f"{guide_text}\n{report_text}")
        planned.append(
            _planned_table(
                "io_assignment_table",
                io_rows,
                preview_sections,
            )
        )

    if _has_phenomenon_image(image_plan) or _contains_any(text, PHENOMENON_KEYWORDS):
        planned.append(
            _planned_table(
                "phenomenon_record_table",
                [],
                preview_sections,
            )
        )

    if _contains_any(text, DATA_KEYWORDS):
        planned.append(
            _planned_table(
                "data_record_table",
                [],
                preview_sections,
            )
        )

    return planned[:MAX_AUTO_TABLES]


def inject_planned_tables(
    layout_plan: dict[str, Any],
    *,
    experiment_type: str,
    guide_text: str = "",
    report_text: str = "",
    image_plan: list | None = None,
) -> dict[str, Any]:
    updated = deepcopy(layout_plan)
    sections = updated.get("sections")
    if not isinstance(sections, list):
        return updated

    existing_schemas = {
        str(block.get("schema") or "").strip()
        for section in sections
        if isinstance(section, dict)
        for block in (section.get("blocks") or [])
        if isinstance(block, dict) and block.get("type") == "table"
    }

    planned = plan_tables_for_preview(
        experiment_type=experiment_type,
        guide_text=guide_text,
        report_text=report_text,
        image_plan=image_plan,
        preview_sections=sections,
    )

    inserted = 0
    for block in planned:
        schema_name = str(block.get("schema") or "").strip()
        if not schema_name or schema_name in existing_schemas:
            continue
        section_index = _find_section_index(sections, schema_name)
        if section_index is None:
            continue
        target_blocks = sections[section_index].setdefault("blocks", [])
        if not isinstance(target_blocks, list):
            sections[section_index]["blocks"] = []
            target_blocks = sections[section_index]["blocks"]
        target_blocks.insert(0, block)
        existing_schemas.add(schema_name)
        inserted += 1
        if inserted >= MAX_AUTO_TABLES:
            break

    return updated


def _planned_table(schema_name: str, rows: list[list[str]], preview_sections: list | None) -> dict[str, Any]:
    titles = {
        "io_assignment_table": "表1 I/O 分配表",
        "phenomenon_record_table": "表1 实验现象记录表",
        "data_record_table": "表1 数据记录表",
    }
    return {
        "type": "table",
        "schema": schema_name,
        "title": titles[schema_name],
        "data": {"rows": rows},
        "source": "table_planner",
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _extract_io_assignment_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[str] = set()
    for line in _candidate_lines(text):
        for match in re.finditer(r"\b([IQXYM][0-9]+(?:\.[0-9]+)?)\b", line, flags=re.IGNORECASE):
            address = match.group(1).upper()
            if address in seen:
                continue
            seen.add(address)
            rows.append([
                _io_type_for_address(address),
                address,
                _component_name_from_line(line, address),
                _function_from_line(line),
            ])
    return rows[:20]


def _candidate_lines(text: str) -> list[str]:
    normalized = str(text or "").replace("：", ":")
    lines = re.split(r"[\r\n；;]+", normalized)
    return [line.strip() for line in lines if line.strip()]


def _io_type_for_address(address: str) -> str:
    prefix = address[:1].upper()
    if prefix in {"I", "X"}:
        return "输入"
    if prefix in {"Q", "Y"}:
        return "输出"
    return "内部"


def _component_name_from_line(line: str, address: str) -> str:
    lower = line.lower()
    candidates = [
        ("启动按钮", ["启动按钮", "启动", "start button", "start"]),
        ("停止按钮", ["停止按钮", "停止", "stop button", "stop"]),
        ("复位按钮", ["复位按钮", "复位", "reset button", "reset"]),
        ("按钮", ["按钮", "button"]),
        ("开关", ["开关", "switch"]),
        ("传感器", ["传感器", "sensor"]),
        ("运行指示灯", ["运行指示灯", "指示灯", "indicator light", "lamp"]),
        ("电机", ["电机", "motor"]),
        ("蜂鸣器", ["蜂鸣器", "buzzer"]),
        ("线圈", ["线圈", "coil"]),
    ]
    for label, keywords in candidates:
        if any(keyword.lower() in lower for keyword in keywords):
            return label
    without_address = re.sub(re.escape(address), "", line, flags=re.IGNORECASE).strip(" :-，,")
    return without_address[:24]


def _function_from_line(line: str) -> str:
    lower = line.lower()
    if any(keyword in lower for keyword in ["启动", "start"]):
        return "控制系统启动"
    if any(keyword in lower for keyword in ["停止", "stop"]):
        return "控制系统停止"
    if any(keyword in lower for keyword in ["复位", "reset"]):
        return "复位控制"
    if any(keyword in lower for keyword in ["指示", "显示", "indicator", "lamp"]):
        return "显示运行状态"
    return ""


def _has_phenomenon_image(image_plan: list | None) -> bool:
    if not isinstance(image_plan, list):
        return False
    for image in image_plan:
        if not isinstance(image, dict):
            continue
        type_name = str(image.get("type") or "").strip().lower()
        category_name = str(image.get("category") or "").strip().lower()
        caption = str(image.get("caption") or "").strip()
        if type_name == "result" or category_name == "phenomenon" or "现象" in caption:
            return True
    return False


def _find_section_index(sections: list[dict[str, Any]], schema_name: str) -> int | None:
    titles = [str(section.get("title") or "") for section in sections if isinstance(section, dict)]
    if not titles:
        return None

    preferred_keywords = {
        "io_assignment_table": ["实验过程", "实验原理", "操作过程", "实验要求"],
        "phenomenon_record_table": ["实验结果", "结果", "数据记录"],
        "data_record_table": ["实验结果", "数据记录", "结果"],
    }
    for keyword in preferred_keywords.get(schema_name, []):
        for index, title in enumerate(titles):
            if keyword in title:
                return index
    return 0
