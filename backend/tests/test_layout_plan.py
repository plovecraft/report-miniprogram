import pytest

from backend.app.services.layout_schema import build_layout_plan_from_preview
from backend.app.services.layout_validator import LayoutValidationError, validate_layout_plan


def test_builds_layout_plan_from_existing_preview_sections_and_images() -> None:
    preview = {
        "experimentType": "plc",
        "experimentTypeName": "PLC 实验报告",
        "experimentName": "实验三",
        "sections": [
            {
                "title": "一、实验目的",
                "paragraphs": ["掌握 PLC 基本控制方法。"],
                "images": [],
            },
            {
                "title": "五、程序设计与梯形图",
                "paragraphs": [],
                "images": [
                    {
                        "imageIndex": 2,
                        "filename": "程序图1.png",
                        "type": "program",
                        "section": "五、程序设计与梯形图",
                        "caption": "基础题梯形图程序",
                        "sortOrder": 0,
                        "recognized": True,
                    }
                ],
            },
        ],
        "imagePlan": [
            {
                "imageIndex": 2,
                "filename": "程序图1.png",
                "type": "program",
                "section": "五、程序设计与梯形图",
                "caption": "基础题梯形图程序",
                "sortOrder": 0,
                "recognized": True,
            }
        ],
        "insertedImageCount": 1,
    }

    layout_plan = build_layout_plan_from_preview(preview)

    assert layout_plan == {
        "schemaVersion": 1,
        "experimentType": "plc",
        "experimentTypeName": "PLC 实验报告",
        "experimentName": "实验三",
        "sections": [
            {
                "key": "section_1",
                "title": "一、实验目的",
                "blocks": [{"type": "paragraph", "content": "掌握 PLC 基本控制方法。"}],
            },
            {
                "key": "section_2",
                "title": "五、程序设计与梯形图",
                "blocks": [
                    {
                        "type": "image",
                        "imageIndex": 2,
                        "caption": "基础题梯形图程序",
                        "imageType": "program",
                    }
                ],
            },
        ],
        "warnings": [],
    }
    validate_layout_plan(layout_plan, valid_image_indices={2})


def test_layout_validator_rejects_unknown_blocks_and_unknown_images() -> None:
    invalid_block_plan = {
        "schemaVersion": 1,
        "sections": [{"title": "一、实验目的", "blocks": [{"type": "video", "content": "x"}]}],
        "warnings": [],
    }
    with pytest.raises(LayoutValidationError, match="unsupported block type"):
        validate_layout_plan(invalid_block_plan, valid_image_indices=set())

    invalid_image_plan = {
        "schemaVersion": 1,
        "sections": [{"title": "五、程序设计与梯形图", "blocks": [{"type": "image", "imageIndex": 99}]}],
        "warnings": [],
    }
    with pytest.raises(LayoutValidationError, match="unknown imageIndex"):
        validate_layout_plan(invalid_image_plan, valid_image_indices={1})


def test_layout_validator_accepts_warning_blocks_without_writing_them_to_sections() -> None:
    plan = {
        "schemaVersion": 1,
        "sections": [
            {
                "title": "一、实验目的",
                "blocks": [
                    {"type": "warning", "message": "图片置信度较低，需要用户确认。"},
                    {"type": "paragraph", "content": "本节内容。"},
                ],
            }
        ],
        "warnings": ["存在未识别图片"],
    }

    validate_layout_plan(plan, valid_image_indices=set())


def test_layout_validator_rejects_missing_or_unsupported_schema_version() -> None:
    plan_without_version = {
        "sections": [{"title": "一、实验目的", "blocks": [{"type": "paragraph", "content": "正文"}]}],
        "warnings": [],
    }
    with pytest.raises(LayoutValidationError, match="schemaVersion"):
        validate_layout_plan(plan_without_version, valid_image_indices=set())

    plan_with_bad_version = dict(plan_without_version, schemaVersion=999)
    with pytest.raises(LayoutValidationError, match="unsupported schemaVersion"):
        validate_layout_plan(plan_with_bad_version, valid_image_indices=set())


def test_layout_validator_rejects_non_integer_schema_version() -> None:
    base_plan = {
        "sections": [{"title": "一、实验目的", "blocks": [{"type": "paragraph", "content": "正文"}]}],
        "warnings": [],
    }

    for bad_version in ["1", 1.0, True]:
        with pytest.raises(LayoutValidationError, match="schemaVersion"):
            validate_layout_plan(dict(base_plan, schemaVersion=bad_version), valid_image_indices=set())
