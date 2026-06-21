# Developer Handoff

更新时间：2026-05-14

这份文档给后续接手项目的开发者使用，重点是快速进入当前工程，不重复踩坑。

## 1. 当前项目状态

当前项目已经从“固定章节直接写 Word”迁移到“受控 layout_plan + executor”的主链路。

当前正常生成链路：

```text
preview_layout_plan
-> shadow gate
-> layout_executor
-> DOCX
```

当前 legacy fallback：

```text
preview_layout_plan 缺失
-> append_report_content
```

注意：

- fallback 只保留兼容用途。
- 新功能不要继续接到 fallback 上。
- 新功能默认应接在 `preview_layout_plan`、`layout_executor`、`qualityReport` 这条链路上。

## 2. 当前已经实现的核心功能

### 后端

- 任务创建、上传、预览、确认生成、下载
- 微信登录 / 开发态登录
- DOCX 模板保留式写入
- `preview_layout_plan` 缓存
- `shadow gate` 生成前校验
- `layout_executor` 执行：
  - `paragraph`
  - `image`
  - `warning`
  - `table`
- 受控表格 schema：
  - `io_assignment_table`
  - `phenomenon_record_table`
  - `data_record_table`
- 自动推荐表格
- 表格保留 / 不插入
- 表格 rows 最小编辑
- 质量报告：
  - `shadowGate`
  - `layoutExecutor`
  - `tableAudit`

### 前端

- 创建任务页
- 任务预览页
- 图片拖拽调整位置
- 推荐表格只读展示
- 推荐表格保留 / 不插入开关
- 推荐表格 rows 最小编辑
- 单表保存
- 生成前未保存拦截
- 页面内返回 / 创建新任务前未保存提示
- dirty rows 刷新保护

## 3. 当前未完成功能

优先未完成项：

- 表格编辑离开页面后的本地恢复
- 历史任务页展示 `tableAudit`
- PDF 正式导出链路完善
- 多实验类型扩展
- 更复杂的表格编辑能力

当前明确没做：

- 自动保存
- 表格增删行列
- 自定义表格
- 自定义表头
- LLM 自动规划表格

## 4. 关键目录

### 后端

```text
backend/app/main.py
backend/app/services/docx_builder.py
backend/app/services/layout_executor.py
backend/app/services/layout_shadow.py
backend/app/services/layout_validator.py
backend/app/services/table_schema.py
backend/app/services/table_writer.py
backend/app/services/table_planner.py
backend/app/services/task_store.py
backend/app/services/quality_checker.py
backend/tests/
```

### 前端

```text
miniprogram/pages/create/
miniprogram/pages/task/
miniprogram/pages/history/
miniprogram/pages/profile/
miniprogram/services/api.ts
```

### 文档

```text
docs/api_contract.md
docs/agent_workflow.md
docs/layout_plan_internal.md
docs/project_task_status.md
docs/developer_handoff.md
docs/agent_handoff.md
```

## 5. 接口清单

以后改接口，先看：

- [C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\api_contract.md](C:\Users\wuzitian\WeChatProjects\miniprogram-2\docs\api_contract.md)

当前主要接口：

- `GET /health`
- `POST /api/auth/wechat-login`
- `GET /api/users/me`
- `GET /api/users/me/usage`
- `POST /api/reports/tasks`
- `GET /api/reports/tasks`
- `GET /api/reports/tasks/{task_id}`
- `POST /api/reports/tasks/{task_id}/files`
- `PATCH /api/reports/tasks/{task_id}/image-plan`
- `PATCH /api/reports/tasks/{task_id}/table-plan`
- `POST /api/reports/tasks/{task_id}/confirm`
- `GET /api/reports/tasks/{task_id}/download`
- `GET /api/reports/tasks/{task_id}/images/{image_index}`

## 6. 当前数据结构重点

### TaskRecord

当前关键字段：

- `preview_data`
- `preview_layout_plan`
- `table_selection`
- `table_edits`
- `shadow_gate_report`
- `layout_executor_report`
- `table_audit_report`
- `quality_report`

### preview_data.preview.tablePlan

当前每项包含：

- `tableId`
- `sectionKey`
- `sectionTitle`
- `schema`
- `title`
- `headers`
- `rows`
- `rowCount`
- `columnCount`
- `selected`
- `edited`
- `autoPlanned`

前端本地附加状态：

- `dirty`
- `saving`
- `saveError`

注意：

- `dirty/saving/saveError` 是页面本地状态，不入后端。
- 后端只认 `table_selection` 和 `table_edits`。

## 7. 开发注意事项

### 7.1 不要破坏主链路

新功能优先挂在：

```text
preview_layout_plan
-> effective layout_plan
-> shadow gate
-> layout_executor
-> qualityReport
```

不要为了快，把逻辑接回旧 `append_report_content()`。

### 7.2 表格能力是白名单模式

当前只允许：

- `io_assignment_table`
- `phenomenon_record_table`
- `data_record_table`

不要允许前端或外部接口直接传：

- 自定义 schema
- 自定义 headers
- 自定义列数

### 7.3 表格编辑边界

当前只允许编辑：

- `rows[][]`

不允许编辑：

- `tableId`
- `schema`
- `headers`
- 列数
- block type

### 7.4 选择与编辑的应用顺序

正式生成前顺序应保持：

```text
preview_layout_plan
-> apply_table_edits_to_layout_plan()
-> apply_table_selection_to_layout_plan()
-> shadow gate
-> layout_executor
```

不要颠倒。

### 7.5 前端刷新合并规则

当前 `task` 页面刷新时：

- `selected=true && dirty=true` 的表，保留本地 rows
- 已成功保存的表，可用后端 rows 覆盖

后续如果改轮询逻辑，不能把 dirty 表覆盖掉。

### 7.6 真机兼容要求

前端不要引入：

- `?.`
- `??`

提交前检查：

```powershell
Get-ChildItem -Path miniprogram -Recurse -Include *.ts,*.js | Select-String -Pattern '\?\.|\?\?'
```

### 7.7 编码与文本

- 代码文件尽量保持 UTF-8。
- PowerShell 控制台里可能看到中文乱码，不代表文件本身坏了。
- 修改 `.wxml/.ts/.less/.md` 时，优先看文件内容本身，不要只信终端输出。

## 8. 测试流程

### 后端标准回归

在项目根目录执行：

```powershell
python -m pytest backend\tests -q --tb=short
python -m compileall backend\app backend\tests -q
```

### 前端最低检查

```powershell
Get-ChildItem -Path miniprogram -Recurse -Include *.ts,*.js | Select-String -Pattern '\?\.|\?\?'
```

再做：

- 微信开发者工具编译
- 任务创建 -> 上传 -> 预览 -> 确认 -> 下载 走通一次
- 表格编辑 -> 保存 -> 生成 走通一次

## 9. 推荐修改策略

### 适合继续做

- 任务历史页显示 `tableAudit`
- 本地恢复未保存表格编辑
- 更细的 layout / table 执行审计
- PDF 导出补全

### 暂时不要急着做

- 多实验类型全面扩展
- 接 LLM 参与 layout/table 规划
- 放开自定义表格
- 做复杂表格编辑器

这些会明显扩大边界，容易把当前稳定链路打散。

## 10. 接手建议

如果你是新接手开发者，建议顺序：

1. 先读 `docs/project_task_status.md`
2. 再读 `docs/api_contract.md`
3. 再看 `backend/app/services/docx_builder.py`
4. 再看 `backend/app/services/layout_executor.py`
5. 最后看 `miniprogram/pages/task/task.ts`

这样最容易理解当前项目的真实主链路。
