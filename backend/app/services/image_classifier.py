from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import image_recognizer
from .experiment_config_loader import load_experiment_config


SECTION_OPERATION = "四、实验操作过程"
SECTION_PROGRAM = "五、程序设计与梯形图"
SECTION_RESULT = "六、实验结果"
_NO_CATEGORY_OVERRIDE = object()


@dataclass(frozen=True)
class ImagePlacement:
    path: Path
    type: str
    section: str
    caption: str
    sort_order: int = 0


def classify_image(filename: str) -> str:
    info = classify_image_info(filename)
    return info.type if info is not None else "other"


def classify_image_info(filename: str, category: str | None = None) -> ImagePlacement | None:
    path = Path(filename)
    placement = _placement_from_category(path, category)
    if placement is not _NO_CATEGORY_OVERRIDE:
        return placement

    name = path.stem.lower()
    if _contains_any(name, ["接线", "面板", "实验面板", "wiring", "wire", "circuit"]):
        return _placement_for_type(path, "wiring", "实验接线图")
    if _contains_any(name, ["实物", "现场", "运行器件", "device", "physical", "hardware"]):
        return _placement_for_type(path, "physical", "实验实物图")
    if _contains_any(name, ["现象", "结果", "运行现象", "phenomenon", "result"]):
        return _placement_for_type(path, "result", _result_caption(name))

    match = re.search(r"程序图[_\- ]?(\d+)[_\- ]?(\d+)?", name)
    if match:
        caption = _program_caption(match.group(1))
        if match.group(2):
            caption += f"（{match.group(2)}）"
        return _placement_for_type(path, "program", caption)
    if _contains_any(name, ["程序", "梯形", "ladder", "program", "awl"]):
        return _placement_for_type(path, "program", "梯形图程序")
    return _placement_for_type(path, "other", path.stem)


def classify_images(filenames: list[str]) -> dict[str, list[str]]:
    result = {"program": [], "wiring": [], "physical": [], "result": [], "other": []}
    for filename in filenames:
        result[classify_image(filename)].append(filename)
    return result


def group_images_by_section(
    image_paths: list[Path],
    image_metas: list[dict[str, Any]] | None = None,
) -> dict[str, list[ImagePlacement]]:
    metas = image_metas_by_filename(image_metas)
    groups: dict[str, list[ImagePlacement]] = {}
    for index, path in enumerate(image_paths):
        meta = metas.get(path.name, {})
        recognition = _recognize_image(path, meta)
        manual_category = str(meta.get("category") or "").strip()
        info = classify_image_info(path.name, manual_category or None)
        if info is None and not manual_category:
            recognition_category = str(recognition.get("category") or "").strip()
            category_hint = recognition_category if recognition_category not in {"", "unknown"} else None
            info = classify_image_info(path.name, category_hint)
        if info is None:
            continue
        recognition_section = ""
        recognition_caption = ""
        if info.type == "other":
            recognition_section = str(recognition.get("section") or "").strip()
            recognition_caption = str(recognition.get("caption") or "").strip()
        section = str(meta.get("section") or recognition_section).strip() or info.section
        caption = str(meta.get("caption") or recognition_caption).strip() or info.caption
        sort_order = _coerce_int(meta.get("sortOrder"), index)
        groups.setdefault(section, []).append(
            ImagePlacement(path=path, type=info.type, section=section, caption=caption, sort_order=sort_order)
        )
    for section in list(groups):
        groups[section] = sorted(groups[section], key=lambda item: item.sort_order)
    return groups


def image_categories_by_filename(image_metas: list[dict[str, Any]] | None) -> dict[str, str]:
    return {
        filename: str(meta.get("category") or "")
        for filename, meta in image_metas_by_filename(image_metas).items()
        if str(meta.get("category") or "").strip()
    }


def image_metas_by_filename(image_metas: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(image_metas, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in image_metas:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename:
            result[Path(filename).name] = dict(item)
    return result


def image_width_cm(image_type: str) -> float:
    config = load_experiment_config("plc")
    configured = config.image_types.get(image_type, {}).get("widthCm")
    try:
        if configured is not None:
            return float(configured)
    except (TypeError, ValueError):
        pass
    if image_type in {"program", "wiring"}:
        return 8.0
    if image_type in {"physical", "result", "phenomenon", "device"}:
        return 11.5
    if image_type in {"instrument", "meter", "chart", "document", "other", "unknown"}:
        return 9.0
    return 9.0


def _placement_from_category(path: Path, category: str | None) -> ImagePlacement | None | object:
    normalized = (category or "").strip()
    if not normalized or normalized in {"auto", "unknown"}:
        return _NO_CATEGORY_OVERRIDE
    if normalized == "skip":
        return None
    configured = _placement_from_config(path, normalized)
    if configured is not None:
        return configured
    if normalized in {"program", "basic_program", "thought1_program", "thought2_program"}:
        return _placement_for_type(path, "program", _caption_from_category(normalized, path.stem))
    if normalized == "wiring":
        return _placement_for_type(path, "wiring", "实验接线图")
    if normalized in {"physical", "device"}:
        return _placement_for_type(path, "physical", "实验实物图")
    if normalized in {"phenomenon", "result", "basic_result", "thought1_result", "thought2_result", "meter", "instrument", "chart"}:
        return _placement_for_type(path, "result", _caption_from_category(normalized, path.stem))
    if normalized in {"document", "other"}:
        return _placement_for_type(path, "other", path.stem)
    return _NO_CATEGORY_OVERRIDE


def _placement_from_config(path: Path, category: str) -> ImagePlacement | None:
    override = load_experiment_config("plc").category_overrides.get(category)
    if not override:
        return None
    image_type = str(override.get("type") or category).strip() or "other"
    caption = str(override.get("caption") or "").strip() or path.stem
    section = str(override.get("section") or "").strip() or _section_for_type(image_type)
    return ImagePlacement(path=path, type=image_type, section=section, caption=caption)


def _placement_for_type(path: Path, image_type: str, caption: str) -> ImagePlacement:
    return ImagePlacement(path=path, type=image_type, section=_section_for_type(image_type), caption=caption)


def _section_for_type(image_type: str) -> str:
    configured = str(load_experiment_config("plc").image_types.get(image_type, {}).get("section") or "").strip()
    if configured:
        return configured
    if image_type == "program":
        return SECTION_PROGRAM
    if image_type == "wiring":
        return SECTION_OPERATION
    return SECTION_RESULT


def _caption_from_category(category: str, fallback: str) -> str:
    if category == "basic_program":
        return "基础题梯形图程序"
    if category == "thought1_program":
        return "思考题 1 梯形图程序"
    if category == "thought2_program":
        return "思考题 2 梯形图程序"
    if category == "basic_result":
        return "基础题运行现象"
    if category == "thought1_result":
        return "思考题 1 运行现象"
    if category == "thought2_result":
        return "思考题 2 运行现象"
    if category in {"result", "phenomenon"}:
        return "实验运行现象"
    if category in {"physical", "device"}:
        return "实验实物图"
    if category == "wiring":
        return "实验接线图"
    if category in {"instrument", "meter"}:
        return "仪表读数图"
    if category == "chart":
        return "曲线/图表"
    if category == "document":
        return "文档/截图"
    if category == "program":
        return "梯形图程序"
    return fallback


def _result_caption(name: str) -> str:
    if "基础" in name:
        return "基础题运行现象"
    if "思考题1" in name or "思考1" in name:
        return "思考题 1 运行现象"
    if "思考题2" in name or "思考2" in name:
        return "思考题 2 运行现象"
    return "实验运行现象"


def _program_caption(group: str) -> str:
    if group == "1":
        return "基础题梯形图程序"
    if group == "2":
        return "思考题 1 梯形图程序"
    if group == "3":
        return "思考题 2 梯形图程序"
    return f"程序图 {group}"


def _contains_any(value: str, keywords: list[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _recognize_image(path: Path, meta: dict[str, Any]) -> dict[str, Any]:
    try:
        result = image_recognizer.classify_image(path)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}
