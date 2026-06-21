import json
import logging

from backend.app.services.llm_writer import LLMConfig, generate_report_sections


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def test_openai_compatible_writer_posts_chat_completion_and_parses_sections() -> None:
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_dumps(
                                {
                                    "experiment_purpose": ["掌握 PLC 定时控制方法。"],
                                    "experiment_requirements": ["完成实验四交通灯控制。"],
                                    "operation_process": ["上传程序并观察运行状态。"],
                                    "program_design": ["使用定时器控制红绿灯切换。"],
                                    "experiment_result": ["交通灯按要求循环运行。"],
                                    "reflection": ["加深了对时序控制的理解。"],
                                }
                            )
                        }
                    }
                ]
            }
        )

    config = LLMConfig(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="demo-model",
        timeout=15,
    )

    draft = generate_report_sections(
        config=config,
        metadata={"experimentNo": "实验四"},
        guide_text="实验四：交通灯控制",
        report_text="原报告正文",
        image_names=["程序图1.png"],
        post=fake_post,
    )

    assert calls[0]["url"] == "https://example.test/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"]["model"] == "demo-model"
    assert calls[0]["timeout"] == 15
    assert "用户输入的实验序号优先级最高" in calls[0]["json"]["messages"][1]["content"]
    assert "每个章节的文本量要求" in calls[0]["json"]["messages"][1]["content"]
    assert "实验结果：3-5 段" in calls[0]["json"]["messages"][1]["content"]
    assert draft.sections[0] == ("一、实验目的", ["掌握 PLC 定时控制方法。"])
    assert ("六、实验结果", ["交通灯按要求循环运行。"]) in draft.sections


def test_parses_structured_report_draft_with_experiment_name() -> None:
    def fake_post(url, headers, json, timeout):
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_dumps(
                                {
                                    "experiment_name": "实验三  天塔之光模拟控制",
                                    "sections": [
                                        {
                                            "title": "一、实验目的",
                                            "paragraphs": ["掌握 SHRB 指令的基本应用。"],
                                        },
                                        {
                                            "title": "六、实验结果",
                                            "paragraphs": ["程序图1_1.png 对应基础题程序。"],
                                        },
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        )

    draft = generate_report_sections(
        config=LLMConfig(base_url="https://example.test/v1", api_key="test-key", model="demo-model"),
        metadata={"experimentNo": "实验三"},
        guide_text="实验三 天塔之光模拟控制",
        report_text="原报告正文",
        image_names=["程序图1_1.png"],
        post=fake_post,
    )

    assert draft.experiment_name == "实验三  天塔之光模拟控制"
    assert draft.sections == [
        ("一、实验目的", ["掌握 SHRB 指令的基本应用。"]),
        ("六、实验结果", ["基础题梯形图程序（1） 对应基础题程序。"]),
    ]


def test_sanitizes_image_filenames_from_model_paragraphs() -> None:
    def fake_post(url, headers, json, timeout):
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_dumps(
                                {
                                    "experiment_name": "实验三  天塔之光模拟控制",
                                    "sections": [
                                        {
                                            "title": "六、实验结果",
                                            "paragraphs": [
                                                "基础题运行后，与“基础题现象.jpg”记录一致。",
                                                "思考题 1 的效果符合“思考题1现象.jpg”所呈现的结果。",
                                                "程序与程序图1_1.png对应。",
                                            ],
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        )

    draft = generate_report_sections(
        config=LLMConfig(base_url="https://example.test/v1", api_key="test-key", model="demo-model"),
        metadata={"experimentNo": "实验三"},
        guide_text="实验三 天塔之光模拟控制",
        report_text="原报告正文",
        image_names=["基础题现象.jpg", "思考题1现象.jpg", "程序图1_1.png"],
        post=fake_post,
    )

    text = "\n".join(line for _, lines in draft.sections for line in lines)
    assert ".jpg" not in text
    assert ".png" not in text
    assert "基础题运行现象" in text
    assert "思考题 1 运行现象" in text
    assert "基础题梯形图程序" in text


def json_dumps(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


def test_logs_raw_llm_response_for_debugging(caplog) -> None:
    def fake_post(url, headers, json, timeout):
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_dumps(
                                {
                                    "experiment_purpose": ["实验三内容"],
                                    "experiment_result": ["模型回复调试标记"],
                                }
                            )
                        }
                    }
                ]
            }
        )

    config = LLMConfig(base_url="https://example.test/v1", api_key="test-key", model="demo-model")

    with caplog.at_level(logging.INFO, logger="report-backend.llm"):
        generate_report_sections(
            config=config,
            metadata={"experimentNo": "实验三"},
            guide_text="实验三 计数器控制",
            report_text="原报告正文",
            image_names=[],
            post=fake_post,
        )

    assert "llm raw response" in caplog.text
    assert "模型回复调试标记" in caplog.text
