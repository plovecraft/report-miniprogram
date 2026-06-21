from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger("report-backend.experiment-config")

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs" / "experiment_types"


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_type: str
    display_name: str
    default_sections: list[str]
    fallback_sections: list[dict[str, Any]]
    fallback_image_labels: dict[str, str]
    fallback_no_images_text: str
    image_types: dict[str, dict[str, Any]]
    category_overrides: dict[str, dict[str, Any]]
    allowed_tables: list[str]
    keywords: list[str]


PLC_FALLBACK_CONFIG = ExperimentConfig(
    experiment_type="plc",
    display_name="PLC \u5b9e\u9a8c\u62a5\u544a",
    default_sections=[
        "\u4e00\u3001\u5b9e\u9a8c\u76ee\u7684",
        "\u4e8c\u3001\u5b9e\u9a8c\u8bbe\u5907",
        "\u4e09\u3001\u5b9e\u9a8c\u8981\u6c42",
        "\u56db\u3001\u5b9e\u9a8c\u64cd\u4f5c\u8fc7\u7a0b",
        "\u4e94\u3001\u7a0b\u5e8f\u8bbe\u8ba1\u4e0e\u68af\u5f62\u56fe",
        "\u516d\u3001\u5b9e\u9a8c\u7ed3\u679c",
        "\u4e03\u3001\u5b9e\u9a8c\u5fc3\u5f97",
    ],
    fallback_sections=[
        {
            "title": "\u4e00\u3001\u5b9e\u9a8c\u76ee\u7684",
            "paragraphTemplates": ["\u6839\u636e\u5b9e\u9a8c\u6307\u5bfc\u4e66\u300a{guideName}\u300b\u6574\u7406{experimentNo}\u7684\u5b9e\u9a8c\u76ee\u6807\u3002"],
        },
        {
            "title": "\u4e8c\u3001\u5b9e\u9a8c\u8981\u6c42",
            "paragraphTemplates": ["\u5b8c\u6210{experimentNo}\u76f8\u5173\u63a7\u5236\u8981\u6c42\uff0c\u4fdd\u6301\u539f\u62a5\u544a\u6a21\u677f\u548c\u5b66\u751f\u4fe1\u606f\u4e0d\u53d8\u3002"],
        },
        {
            "title": "\u4e09\u3001\u5b9e\u9a8c\u4fe1\u606f",
            "paragraphTemplates": ["\u59d3\u540d\uff1a{studentName}", "\u5b66\u53f7\uff1a{studentId}", "\u73ed\u7ea7\uff1a{className}"],
        },
        {
            "title": "\u56db\u3001\u5b9e\u9a8c\u64cd\u4f5c\u8fc7\u7a0b",
            "paragraphTemplates": ["\u6839\u636e\u6307\u5bfc\u4e66\u6b65\u9aa4\u548c\u4e0a\u4f20\u56fe\u7247\u6574\u7406\u64cd\u4f5c\u8fc7\u7a0b\u3002\u5f53\u524d\u672a\u914d\u7f6e\u5927\u6a21\u578b\u65f6\uff0c\u4ec5\u5199\u5165\u7ed3\u6784\u5316\u9aa8\u67b6\u3002"],
        },
        {"title": "\u4e94\u3001\u7a0b\u5e8f\u8bbe\u8ba1\u4e0e\u56fe\u7247\u6750\u6599", "content": "image_summary"},
        {
            "title": "\u516d\u3001\u5b9e\u9a8c\u7ed3\u679c",
            "paragraphTemplates": ["\u6839\u636e\u73b0\u8c61\u56fe\u3001\u5b9e\u7269\u56fe\u548c\u8fd0\u884c\u8bb0\u5f55\u6574\u7406\u5b9e\u9a8c\u7ed3\u679c\u3002\u914d\u7f6e\u5927\u6a21\u578b\u540e\u5c06\u81ea\u52a8\u751f\u6210\u6b63\u5f0f\u5185\u5bb9\u3002"],
        },
        {
            "title": "\u4e03\u3001\u5b9e\u9a8c\u5fc3\u5f97",
            "paragraphTemplates": ["\u914d\u7f6e\u5927\u6a21\u578b\u540e\u5c06\u81ea\u52a8\u8865\u5168\u5b9e\u9a8c\u5fc3\u5f97\uff0c\u5e76\u4fdd\u6301\u5b66\u751f\u5b9e\u9a8c\u62a5\u544a\u8bed\u6c14\u3002"],
        },
    ],
    fallback_image_labels={
        "program": "\u7a0b\u5e8f\u56fe",
        "wiring": "\u63a5\u7ebf\u56fe",
        "physical": "\u5b9e\u7269\u56fe",
        "result": "\u73b0\u8c61/\u7ed3\u679c\u56fe",
        "other": "\u5176\u4ed6\u56fe\u7247",
    },
    fallback_no_images_text="\u6682\u672a\u4e0a\u4f20\u5b9e\u9a8c\u56fe\u7247\u3002",
    image_types={
        "program": {
            "displayName": "\u7a0b\u5e8f\u56fe",
            "section": "\u4e94\u3001\u7a0b\u5e8f\u8bbe\u8ba1\u4e0e\u68af\u5f62\u56fe",
            "widthCm": 8.0,
        },
        "wiring": {
            "displayName": "\u63a5\u7ebf\u56fe",
            "section": "\u56db\u3001\u5b9e\u9a8c\u64cd\u4f5c\u8fc7\u7a0b",
            "widthCm": 8.0,
        },
        "physical": {
            "displayName": "\u5b9e\u7269\u56fe",
            "section": "\u516d\u3001\u5b9e\u9a8c\u7ed3\u679c",
            "widthCm": 11.5,
        },
        "result": {
            "displayName": "\u73b0\u8c61/\u7ed3\u679c\u56fe",
            "section": "\u516d\u3001\u5b9e\u9a8c\u7ed3\u679c",
            "widthCm": 11.5,
        },
        "other": {
            "displayName": "\u5176\u4ed6\u56fe\u7247",
            "section": "\u516d\u3001\u5b9e\u9a8c\u7ed3\u679c",
            "widthCm": 9.0,
        },
    },
    category_overrides={},
    allowed_tables=["io_assignment_table", "phenomenon_record_table", "truth_table"],
    keywords=[
        "PLC",
        "\u68af\u5f62\u56fe",
        "I/O \u5206\u914d",
        "\u8f93\u5165\u8f93\u51fa",
        "\u7ee7\u7535\u5668",
        "\u6307\u793a\u706f",
    ],
)


def load_experiment_config(experiment_type: str = "plc") -> ExperimentConfig:
    normalized = (experiment_type or "plc").strip().lower() or "plc"
    path = CONFIG_ROOT / f"{normalized}.json"
    if not path.exists():
        logger.warning("experiment config missing type=%s path=%s, using fallback", normalized, path)
        return PLC_FALLBACK_CONFIG
    try:
        return _config_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        logger.exception("experiment config invalid type=%s path=%s, using fallback", normalized, path)
        return PLC_FALLBACK_CONFIG


def _config_from_dict(data: dict[str, Any]) -> ExperimentConfig:
    default_sections = _string_list(data.get("defaultSections")) or PLC_FALLBACK_CONFIG.default_sections
    return ExperimentConfig(
        experiment_type=str(data.get("experimentType") or "plc"),
        display_name=str(data.get("displayName") or PLC_FALLBACK_CONFIG.display_name),
        default_sections=default_sections,
        fallback_sections=_list_of_dicts(data.get("fallbackSections")) or PLC_FALLBACK_CONFIG.fallback_sections,
        fallback_image_labels=_dict_of_strings(data.get("fallbackImageLabels")) or PLC_FALLBACK_CONFIG.fallback_image_labels,
        fallback_no_images_text=str(data.get("fallbackNoImagesText") or PLC_FALLBACK_CONFIG.fallback_no_images_text),
        image_types=_dict_of_dicts(data.get("imageTypes")) or PLC_FALLBACK_CONFIG.image_types,
        category_overrides=_dict_of_dicts(data.get("categoryOverrides")),
        allowed_tables=_string_list(data.get("allowedTables")),
        keywords=_string_list(data.get("keywords")),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_of_dicts(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def _dict_of_strings(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
