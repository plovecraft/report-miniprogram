from backend.app.services.table_planner import inject_planned_tables, plan_tables_for_preview


def test_table_planner_recommends_io_assignment_table() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        guide_text="本实验需要完成I/O分配，包含输入输出、I0.0、Q0.0、按钮和指示灯。",
    )

    assert any(block["schema"] == "io_assignment_table" for block in tables)


def test_table_planner_recommends_phenomenon_table_from_image_plan() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        image_plan=[{"type": "result", "category": "phenomenon", "caption": "运行现象"}],
    )

    assert any(block["schema"] == "phenomenon_record_table" for block in tables)


def test_table_planner_recommends_data_record_table() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        guide_text="记录测量值并分析误差，包含电压数据。",
    )

    assert any(block["schema"] == "data_record_table" for block in tables)


def test_table_planner_deduplicates_existing_schema() -> None:
    layout_plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "process",
                "title": "四、实验操作过程",
                "blocks": [
                    {
                        "type": "table",
                        "schema": "io_assignment_table",
                        "data": {"rows": [["输入", "I0.0", "启动按钮", "控制系统启动"]]},
                    }
                ],
            }
        ],
        "warnings": [],
    }

    updated = inject_planned_tables(
        layout_plan,
        experiment_type="plc",
        guide_text="I/O分配，I0.0，Q0.0，按钮，指示灯",
    )

    schemas = [
        block["schema"]
        for section in updated["sections"]
        for block in section["blocks"]
        if block["type"] == "table"
    ]
    assert schemas.count("io_assignment_table") == 1


def test_table_planner_limits_auto_tables() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        guide_text="I/O分配、输入输出、测量值、误差、电压、实验现象、运行结果。",
        image_plan=[{"type": "result", "category": "phenomenon", "caption": "运行现象"}],
    )

    assert len(tables) <= 2


def test_table_planner_extracts_io_rows_from_guide_text() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        guide_text="I/O分配：I0.0 启动按钮；Q0.0 运行指示灯。",
    )

    io_table = next(block for block in tables if block["schema"] == "io_assignment_table")

    assert io_table["data"]["rows"] == [
        ["输入", "I0.0", "启动按钮", "控制系统启动"],
        ["输出", "Q0.0", "运行指示灯", "显示运行状态"],
    ]


def test_table_planner_does_not_insert_hardcoded_io_rows_without_addresses() -> None:
    tables = plan_tables_for_preview(
        experiment_type="plc",
        guide_text="本实验需要完成I/O分配，但指导书未列出具体地址。",
    )

    io_table = next(block for block in tables if block["schema"] == "io_assignment_table")

    assert io_table["data"]["rows"] == []
