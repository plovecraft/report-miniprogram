# Agent Handoff

更新时间：2026-05-14

这份文档给后续接手本项目的 agent 使用。目标是减少重复探索，明确边界、测试流程和扩展方式。

## 1. 先读什么

最少先读这些文件：

1. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\project_task_status.md](C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\project_task_status.md)
2. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\api_contract.md](C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\api_contract.md)
3. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\agent_workflow.md](C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\agent_workflow.md)
4. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\main.py](C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\main.py)
5. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\services\docx_builder.py](C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\services\docx_builder.py)
6. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\services\layout_executor.py](C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend\app\services\layout_shadow.py)
7. [C:\Users\wuzitian\WeChatProjects\miniprogram-2\miniprogram\pages\task\task.ts](C:\Users\wuzitian\WeChatProjects\miniprogram-2\miniprogram\pages\task\task.ts)

## 2. 当前主链路，不要改错

正常链路：

```text
build_report_preview(record)
-> preview_data + preview_layout_plan
-> user edits image/table plan
-> confirm
-> apply_table_edits_to_layout_plan
-> apply_table_selection_to_layout_plan
-> shadow gate
-> layout_executor
-> build_quality_report
-> qualityReport / tableAudit
```

fallback 链路：

```text
preview_layout_plan missing
-> legacy append_report_content
```

规则：

- 新功能不要默认走 fallback。
- `preview_layout_plan` 存在时，不能静默回退到 legacy。

## 3. 当前可改和不该改的地方

### 当前建议扩展点

- `preview_layout_plan`
- `table_planner`
- `layout_executor`
- `qualityReport`
- `tableAudit`
- `task` 页面前端交互

### 当前不建议碰的地方

- legacy fallback 主体逻辑
- 表格 schema 白名单边界
- 前后端鉴权语义
- 任务状态枚举
- 已稳定的图片拖拽链路

## 4. 当前后端关键对象

### TaskRecord

重点字段：

- `preview_data`
- `preview_layout_plan`
- `table_selection`
- `table_edits`
- `shadow_gate_report`
- `layout_executor_report`
- `table_audit_report`
- `quality_report`

### 语义

- `table_selection`：是否插入
- `table_edits`：用户保存后的 rows
- `layout_executor_report`：执行摘要
- `table_audit_report`：规划、选择、写入的审计信息

## 5. 当前前端关键状态

`miniprogram/pages/task/task.ts` 中表格本地状态：

- `dirty`
- `saving`
- `saveError`

这三个字段：

- 不属于后端 contract
- 不应写回后端
- 只用于页面保护和交互提示

当前规则：

- `selected=true && dirty=true` 会阻止确认生成
- `selected=false && dirty=true` 不阻止确认生成
- 刷新时 dirty 表优先保留本地 rows

## 6. 接口修改规则

如果要改接口：

1. 先改 `docs/api_contract.md`
2. 再改 `backend/app/main.py`
3. 再改 `miniprogram/services/api.ts`
4. 最后改页面使用方

不要先改页面再猜接口字段。

## 7. 当前测试习惯

### 后端

每次改后端后至少跑：

```powershell
python -m pytest backend\tests -q --tb=short
python -m compileall backend\app backend\tests -q
```

### 前端

每次改小程序后至少跑：

```powershell
Get-ChildItem -Path miniprogram -Recurse -Include *.ts,*.js | Select-String -Pattern '\?\.|\?\?'
```

再做：

- 微信开发者工具编译
- 真机或预览环境走通关键流程

## 8. 当前语法习惯

### 前端

- 不使用 `?.`
- 不使用 `??`
- 不要引入需要额外 Babel/TS 配置的写法
- 小程序页面逻辑优先简单状态合并，不做复杂状态管理框架

### 后端

- 尽量保持纯 Python 标准库 + 已有依赖
- 不引入大型新依赖
- 数据结构改动优先保持向后兼容

## 9. 当前表格能力边界

允许：

- 编辑 `rows`
- 切换 `selected`

不允许：

- 改 `schema`
- 改 `headers`
- 改 `tableId`
- 自定义列数
- 自定义 block 类型
- 自定义任意表格

当前白名单 schema：

- `io_assignment_table`
- `phenomenon_record_table`
- `data_record_table`

## 10. 预留扩展接口

当前已经存在、适合继续扩展的点：

### 后端

- `build_preview_layout_plan(...)`
- `extract_table_preview_summary(...)`
- `apply_table_edits_to_layout_plan(...)`
- `apply_table_selection_to_layout_plan(...)`
- `build_table_audit_report(...)`
- `table_planner.py`
- `layout_executor.py`

### 前端

- `task.preview.tablePlan`
- `updateTablePlan(...)`
- `withPreviewImageUrls(...)` 的 table merge 逻辑

扩展原则：

- 新增能力尽量挂到这些扩展点
- 不要把逻辑横切散落到多个页面和多个 service 里

## 11. 当前容易踩坑的点

1. PowerShell 输出中文可能乱码，不代表文件编码坏了。
2. `preview_data` 是给前端的；`preview_layout_plan` 是后端内部真实执行基线，不要混用。
3. 刷新任务详情时，不能覆盖 `dirty=true` 的本地表格 rows。
4. `table_selection` 和 `table_edits` 都是按 `tableId` 合并，不能按数组下标合并。
5. `qualityReport` 已经承载很多审计字段，新增时尽量增量追加，不要改旧字段语义。
6. legacy fallback 允许存在，但不要继续往它上面叠新功能。

## 12. 后续 agent 开发建议

如果后续继续做增量开发，建议顺序：

1. 先明确任务是前端、后端还是跨端
2. 如果跨端，先写任务卡，再确认接口 contract
3. 先做后端，再做前端
4. 最后跑回归和真机兼容检查

适合继续推进的下一批任务：

- 本地恢复未保存表格编辑
- 历史任务查看 `tableAudit`
- 更细粒度的 executor/table 错误审计

不建议现在立刻做的任务：

- 大范围多实验类型扩展
- LLM 参与 layout/table 规划
- 自定义表格系统
- 复杂表格编辑器

这些会显著提高不稳定性，不适合在当前基础上直接并行推进。
