# Layout Plan Internal Contract

This document describes the backend-only `layout_plan` contract. It is not a public API response and must not be exposed in `ReportPreview` without updating `docs/api_contract.md` first.

## Scope

`layout_plan` is an internal bridge between report planning and deterministic DOCX tools.

- LLM or rules may propose layout blocks in the future.
- The backend validates the plan before any execution.
- The executor writes only supported block types.
- Existing public preview and generation APIs remain unchanged.

## Version

Current schema version:

```json
{
  "schemaVersion": 1
}
```

`schemaVersion` is required. Unsupported versions must be rejected by `layout_validator`.

## Shape

```json
{
  "schemaVersion": 1,
  "experimentType": "plc",
  "experimentTypeName": "PLC 实验报告",
  "experimentName": "实验三",
  "sections": [
    {
      "key": "section_1",
      "title": "一、实验目的",
      "blocks": [
        {
          "type": "paragraph",
          "content": "掌握 PLC 基本控制方法。"
        },
        {
          "type": "image",
          "imageIndex": 0,
          "caption": "基础题梯形图程序",
          "imageType": "program"
        },
        {
          "type": "warning",
          "message": "图片置信度较低，需要用户确认。"
        }
      ]
    }
  ],
  "warnings": []
}
```

## Supported Blocks

### paragraph

Writes normal report text.

Required fields:

- `type`: `paragraph`
- `content`: non-empty string

### image

Inserts an uploaded image by original `image_files` index.

Required fields:

- `type`: `image`
- `imageIndex`: integer matching an existing image file

Optional fields:

- `caption`
- `imageType`

`imageIndex` always refers to the original task image list, not a filtered inserted-image list.

### warning

Carries backend/user-review warnings. It is valid in a plan but is not written to DOCX by the current executor.

Required fields:

- `type`: `warning`
- `message`: non-empty string

## Validation Rules

The validator must reject:

- missing or unsupported `schemaVersion`
- missing or invalid `sections`
- section without a non-empty `title`
- section with non-list `blocks`
- unsupported block types
- empty paragraph content
- empty warning message
- image blocks without a valid `imageIndex`
- image blocks referencing an unknown image index

## Execution Rules

The current executor:

- writes headings and paragraph blocks
- inserts image blocks using `imageIndex`
- numbers captions globally across the whole plan
- ignores warning blocks
- degrades failed image insertion to a text note

The current executor is not connected to the production DOCX generation path. Future production rollout should use a feature flag or shadow mode before replacing the existing writer.
