from backend.app.services.experiment_selector import infer_experiment_label, select_experiment_section


def test_infers_experiment_label_from_user_input_before_report_title() -> None:
    assert infer_experiment_label("机器234吴梓添2307700156第三次实验.docx", "实验四") == "实验四"
    assert infer_experiment_label("PLC 实验报告 实验二 定时器.docx", "") == "实验二"
    assert infer_experiment_label("普通报告.docx", "实验三") == "实验三"


def test_selects_matching_experiment_section_from_guide_text() -> None:
    guide_text = "\n".join(
        [
            "实验一 基本指令",
            "这里是实验一内容",
            "实验二 定时器",
            "这里是实验二内容",
            "实验三 计数器控制",
            "这里是实验三目的",
            "这里是实验三要求",
            "实验四 交通灯控制",
            "这里是实验四内容",
        ]
    )

    selected = select_experiment_section(guide_text, "实验三")

    assert "实验三 计数器控制" in selected
    assert "这里是实验三要求" in selected
    assert "实验二 定时器" not in selected
    assert "实验四 交通灯控制" not in selected
