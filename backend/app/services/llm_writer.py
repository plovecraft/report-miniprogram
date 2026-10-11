from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from requests import HTTPError, RequestException

from .image_classifier import classify_image_info


SectionList = list[tuple[str, list[str]]]
PostFn = Callable[..., Any]
logger = logging.getLogger("report-backend.llm")


@dataclass(frozen=True)
class ReportDraft:
    experiment_name: str
    sections: SectionList


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 180
    temperature: float = 0.2
    stream: bool = False
    send_temperature: bool = True

    @classmethod
    def from_env(cls) -> "LLMConfig | None":
        if os.getenv("LLM_DISABLE_FOR_TESTS") == "1":
            return None
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        if not api_key or not model:
            return None
        return cls(
            base_url=_normalize_base_url(os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")),
            api_key=api_key,
            model=model,
            timeout=int(os.getenv("LLM_TIMEOUT", "180")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            stream=_env_bool("LLM_STREAM"),
            send_temperature=_env_bool("LLM_SEND_TEMPERATURE", default=True),
        )


def generate_report_sections(
    *,
    config: LLMConfig,
    metadata: dict[str, Any],
    guide_text: str,
    report_text: str,
    image_names: list[str],
    post: PostFn = requests.post,
) -> ReportDraft:
    user_prompt = _user_prompt(metadata, guide_text, report_text, image_names)
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
    }
    if config.send_temperature:
        payload["temperature"] = config.temperature
    if config.stream:
        payload["stream"] = True
    url = _chat_completions_url(config.base_url)
    logger.info(
        "llm request start model=%s url=%s timeout=%s guide_chars=%s report_chars=%s image_count=%s prompt_chars=%s",
        config.model,
        url,
        config.timeout,
        len(guide_text),
        len(report_text),
        len(image_names),
        len(user_prompt),
    )

    started_at = time.monotonic()
    try:
        if config.stream:
            response = post(
                url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
                stream=True,
            )
        else:
            response = post(
                url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
            )
    except RequestException:
        elapsed = time.monotonic() - started_at
        raise RuntimeError(f"模型 API 连接失败或超时，耗时 {elapsed:.1f}s") from None

    try:
        response.raise_for_status()
    except HTTPError:
        raise RuntimeError("模型 API 请求失败") from None

    content = _response_content(response, stream=config.stream)
    logger.info("llm response received elapsed=%.1fs chars=%s", time.monotonic() - started_at, len(content))
    return normalize_report_draft(_parse_json_content(content), metadata=metadata, image_names=image_names)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _chat_completions_url(base_url: str) -> str:
    normalized = _normalize_base_url(base_url)
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _response_content(response, *, stream: bool) -> str:
    if not stream:
        return response.json()["choices"][0]["message"]["content"]
    chunks: list[str] = []
    pending = ""
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")
        text = str(line).strip()
        if text.startswith("data:"):
            text = text[5:].strip()
        if text == "[DONE]":
            break
        if not text:
            continue
        if pending:
            text = pending + text
            pending = ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            if _looks_like_incomplete_json(exc):
                pending = text
                continue
            logger.warning("llm stream chunk ignored invalid_json")
            continue
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        message = choices[0].get("message") or {}
        piece = delta.get("content") if "content" in delta else message.get("content")
        if piece:
            chunks.append(str(piece))
    if pending:
        logger.warning("llm stream ended with incomplete json")
    return "".join(chunks)


def _looks_like_incomplete_json(exc: json.JSONDecodeError) -> bool:
    message = str(exc)
    return (
        "Unterminated string" in message
        or "Expecting value" in message
        or "Expecting ',' delimiter" in message
        or "Expecting property name enclosed in double quotes" in message
    )


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if base_url == "https://api.deepseek.com":
        return "https://api.deepseek.com/v1"
    if base_url == "https://node-hk.sssaicodeapi.com/api":
        return "https://node-hk.sssaicodeapi.com/api/v1"
    return base_url


def normalize_report_draft(
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    image_names: list[str] | None = None,
) -> ReportDraft:
    experiment_name = str(data.get("experiment_name") or "").strip()
    sections_data = data.get("sections")
    if isinstance(sections_data, list):
        sections = _normalize_section_objects(sections_data)
    else:
        sections = normalize_sections(data)
    sections = _sanitize_section_image_filenames(sections, image_names or [])
    if not experiment_name and metadata is not None:
        experiment_name = str(metadata.get("resolvedExperimentNo") or metadata.get("experimentNo") or "").strip()
    return ReportDraft(experiment_name=experiment_name, sections=sections)


def normalize_sections(data: dict[str, Any]) -> SectionList:
    mapping = [
        ("一、实验目的", "experiment_purpose"),
        ("二、实验要求", "experiment_requirements"),
        ("三、实验信息", "experiment_info"),
        ("四、实验操作过程", "operation_process"),
        ("五、程序设计与图片材料", "program_design"),
        ("六、实验结果", "experiment_result"),
        ("七、实验心得", "reflection"),
    ]
    sections: SectionList = []
    for title, key in mapping:
        lines = _coerce_lines(data.get(key))
        if lines:
            sections.append((title, lines))
    return sections


def _normalize_section_objects(value: list[Any]) -> SectionList:
    sections: SectionList = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        lines = _coerce_lines(item.get("paragraphs"))
        if title and lines:
            sections.append((title, lines))
    return sections


def _coerce_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _sanitize_section_image_filenames(sections: SectionList, image_names: list[str]) -> SectionList:
    replacements = _image_name_replacements(image_names)
    if not replacements:
        return sections
    sanitized: SectionList = []
    for title, lines in sections:
        sanitized.append((title, [_sanitize_image_filenames(line, replacements) for line in lines]))
    return sanitized


def _image_name_replacements(image_names: list[str]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for image_name in image_names:
        info = classify_image_info(image_name)
        replacements[image_name] = info.caption
        replacements[Path(image_name).stem] = info.caption
    return replacements


def _sanitize_image_filenames(text: str, replacements: dict[str, str]) -> str:
    sanitized = text
    for filename, caption in replacements.items():
        sanitized = sanitized.replace(f"“{filename}”", caption)
        sanitized = sanitized.replace(f"\"{filename}\"", caption)
        sanitized = sanitized.replace(f"'{filename}'", caption)
        sanitized = sanitized.replace(filename, caption)
    return sanitized


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("模型返回内容必须是 JSON 对象")
    return parsed


def _system_prompt() -> str:
    return (
        "你是 PLC 实验报告修订助手。根据实验指导书、原报告正文、学生信息和图片文件名，"
        "生成可直接替换原报告正文区域的中文内容。你的任务是修订旧报告，不是追加内容。"
        "必须删除旧实验、跑题、重复、不合理或与目标实验序号不一致的内容，只保留可复用的学生信息。"
        "图片只能根据文件名判断用途，例如程序图、接线图、实物图、现象图；不要声称看到了图片内容。"
        "正文中不要出现任何图片文件名、扩展名或带引号的文件名，例如不要写“基础题现象.jpg”“程序图1_1.png”；"
        "应改写成基础题运行现象、思考题 1 运行现象、基础题梯形图程序等自然描述。"
        "保持学生实验报告语气，不要写成论文。"
        "不要编造无法从材料推断出的具体仪器故障、成绩或教师评价。只输出 JSON，不要输出 Markdown。"
    )


def _user_prompt(metadata: dict[str, Any], guide_text: str, report_text: str, image_names: list[str]) -> str:
    expected = {
        "experiment_name": "实验三  天塔之光模拟控制",
        "sections": [
            {"title": "一、实验目的", "paragraphs": ["..."]},
            {"title": "二、实验设备", "paragraphs": ["..."]},
            {"title": "三、实验要求", "paragraphs": ["..."]},
            {"title": "四、实验操作过程", "paragraphs": ["..."]},
            {"title": "五、程序设计与梯形图", "paragraphs": ["..."]},
            {"title": "六、实验结果", "paragraphs": ["..."]},
            {"title": "七、实验心得", "paragraphs": ["..."]},
        ],
    }
    return "\n".join(
        [
            "请根据目标实验修订原报告正文。旧正文会被整体清空，你输出的 JSON 会作为新的正文写入模板。",
            "用户输入的实验序号优先级最高，如果原报告标题或文件名与用户输入冲突，必须以用户输入为准。",
            "不要保留原报告中与目标实验无关的旧实验内容、旧心得、旧图片说明或错误章节。",
            "图片文件名只用于判断图片类型和实验环节，正文段落禁止直接出现 .jpg、.jpeg、.png、.gif、.bmp、.webp 等文件名。",
            "描述图片时使用自然表达，例如基础题运行现象、思考题 1 运行现象、基础题梯形图程序，不要写带引号的文件名。",
            "每个章节的文本量要求：实验目的 2-3 段，实验设备 2-4 条，实验要求 3-5 段，实验操作过程 4-6 段，程序设计与梯形图 4-7 段，实验结果：3-5 段，实验心得 2-3 段。",
            "每段尽量写成完整句，围绕指导书、原报告可复用信息和图片类型展开；不要为了凑字数编造未提供的设备故障、教师评价或具体成绩。",
            "输出严格 JSON，字段如下：",
            json.dumps(expected, ensure_ascii=False),
            "",
            "学生与任务信息：",
            json.dumps(metadata, ensure_ascii=False),
            "",
            "图片文件名：",
            json.dumps(image_names, ensure_ascii=False),
            "",
            "实验指导书中已选中的目标实验内容：",
            guide_text or "未提取到指导书文本。请只能基于用户实验序号、原报告可复用信息和图片文件名生成保守内容。",
            "",
            "原报告正文：",
            report_text or "未提取到原报告正文。",
        ]
    )
