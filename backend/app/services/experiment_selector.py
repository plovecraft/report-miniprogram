from __future__ import annotations

import re


CHINESE_TO_INT = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
INT_TO_CHINESE = {value: key for key, value in CHINESE_TO_INT.items()}
NUMERAL_PATTERN = "一二三四五六七八九十"


def infer_experiment_label(report_name_or_title: str, user_input: str = "") -> str:
    user_label = _label_from_text(user_input)
    if user_label:
        return user_label
    if user_input.strip():
        return user_input.strip()
    return _label_from_text(report_name_or_title)


def select_experiment_section(guide_text: str, experiment_label: str) -> str:
    if not guide_text.strip() or not experiment_label.strip():
        return guide_text

    target_number = _number_from_label(experiment_label)
    if target_number is None:
        return guide_text

    headings = list(_iter_experiment_headings(guide_text))
    for index, heading in enumerate(headings):
        if heading["number"] != target_number:
            continue
        start = heading["start"]
        end = headings[index + 1]["start"] if index + 1 < len(headings) else len(guide_text)
        return guide_text[start:end].strip()
    return guide_text


def _label_from_text(text: str) -> str:
    number = _number_from_label(text)
    if number is None:
        return ""
    return f"实验{INT_TO_CHINESE.get(number, str(number))}"


def _number_from_label(text: str) -> int | None:
    patterns = [
        rf"实验\s*([{NUMERAL_PATTERN}]|\d+)",
        rf"第\s*([{NUMERAL_PATTERN}]|\d+)\s*次\s*实验",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1)
        return int(value) if value.isdigit() else CHINESE_TO_INT.get(value)
    return None


def _iter_experiment_headings(text: str):
    pattern = re.compile(
        rf"(?m)^\s*(实验\s*([{NUMERAL_PATTERN}]|\d+)|第\s*([{NUMERAL_PATTERN}]|\d+)\s*次\s*实验)"
    )
    for match in pattern.finditer(text):
        value = match.group(2) or match.group(3)
        number = int(value) if value.isdigit() else CHINESE_TO_INT.get(value)
        if number is not None:
            yield {"start": match.start(), "number": number, "text": match.group(0)}
