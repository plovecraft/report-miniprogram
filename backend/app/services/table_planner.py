from __future__ import annotations

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
        planned.append(
            _planned_table(
                "io_assignment_table",
                [["输入", "I0.0", "启动按钮", "控制系统启动"], ["输出", "Q0.0", "运行指示灯", "显示运行状态"]],
                preview_sections,
            )
        )

    if _has_phenomenon_image(image_plan) or _contains_any(text, PHENOMENON_KEYWORDS):
        planned.append(
            _planned_table(
                "phenomenon_record_table",
                [["程序运行", "观察输出状态变化", "基本符合实验要求"]],
                preview_sections,
            )
        )

    if _contains_any(text, DATA_KEYWORDS):
        planned.append(
            _planned_table(
                "data_record_table",
                [["1", "实验数据记录", "待填写", "根据实验记录补充"]],
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
