# 高校实验报告智能生成系统任务文档

更新时间：2026-05-14

## 1. 当前任务进度

### 已完成阶段

- `P0` 文档治理
- `P1` PLC 配置化基础
- `P2` layout_plan / shadow gate / layout_executor 主链路收敛
- `P3-01` 受控表格 schema + writer
- `P3-02` 确定性 table planner 自动插表
- `P3-03` 预览响应暴露 `tablePlan`
- `P3-04` 推荐表格保留 / 不插入控制
- `P3-05` `tableAudit` 质量审计
- `P3-06` 推荐表格最小 rows 编辑
- `P3-07` 表格编辑未保存状态与生成前拦截

### 当前进行中

- `P3-08` 表格编辑离开页面保护与刷新保护
  - 已完成代码接入：
    - 页面内返回前确认
    - “创建新任务”前确认
    - 刷新时 dirty rows 本地保护
    - 推荐表格区域未保存总提示
  - 仍建议补一次微信开发者工具人工回归确认

### 当前测试状态

- 后端测试：`136 passed`
- 后端 `compileall`：通过
- 前端真机风险语法扫描：无 `?.` / `??`

## 2. 当前已实现功能

### 2.1 用户与任务

- 微信登录 / 开发态登录
- 当前用户信息查询
- 使用记录查询
- 创建任务
- 按用户列出历史任务
- 查看任务详情

### 2.2 材料上传

- 上传原始实验报告
- 上传实验指导书
- 上传实验图片
- 上传材料压缩包 `zip`
- 后端自动拆包并识别：
  - 原报告
  - 指导书
  - 图片

### 2.3 预览生成

- 解析原报告模板
- 构建 `preview_data`
- 构建并缓存 `preview_layout_plan`
- 章节 / 图片预览
- 图片分类结果预览
- 图片拖拽调整章节与顺序

### 2.4 正式生成链路

当前正常路径：

`preview_layout_plan -> shadow gate -> layout_executor -> DOCX`

当前兼容 fallback：

`preview_layout_plan` 缺失时，才允许走 legacy `append_report_content`

### 2.5 表格能力

当前白名单表格：

- `io_assignment_table`
- `phenomenon_record_table`
- `data_record_table`

当前已支持：

- 后端自动推荐表格
- 预览接口返回 `tablePlan`
- 前端展示推荐表格
- 用户可控制：
  - 保留
  - 不插入
- 用户可编辑 `rows`
- 用户可单表保存 rows
- 生成前按用户选择与编辑结果写入 DOCX

### 2.6 质量与审计

- `shadowGate` 报告
- `layoutExecutor` 报告
- `tableAudit` 报告

当前 `qualityReport` 已可反映：

- 模板是否保留
- 正文是否替换
- 图片插入数量
- 是否走 layout executor / fallback
- 推荐表格数量
- 用户取消的表格
- 实际写入表格数量
- 编辑过的表格数量

## 3. 当前未实现功能

### 3.1 表格相关

- 前端表格内容批量保存
- 自动保存
- 表格增删行
- 表格增删列
- 自定义表格
- 表头编辑
- 表格拖拽排序
- 表格预览与 DOCX 最终渲染对照 UI

### 3.2 智能规划相关

- LLM 参与表格规划
- LLM 参与 layout_plan 规划
- 多实验类型自动识别与切换
- 通用 generic / circuit / hydraulics 扩展

### 3.3 产品能力

- 表格编辑离开页面后的本地恢复
- 历史任务的详细审计页
- 多人协作 / 权限控制
- 云端长期持久化恢复
- PDF 正式导出链路完善

## 4. 当前核心接口

### 健康与用户

- `GET /health`
- `POST /api/auth/wechat-login`
- `GET /api/users/me`
- `GET /api/users/me/usage`

### 任务

- `POST /api/reports/tasks`
- `GET /api/reports/tasks`
- `GET /api/reports/tasks/{task_id}`
- `POST /api/reports/tasks/{task_id}/confirm`

### 上传

- `POST /api/reports/tasks/{task_id}/files`

支持字段：

- `report`
- `guide`
- `image`
- `materialZip`

### 预览编辑

- `PATCH /api/reports/tasks/{task_id}/image-plan`
- `PATCH /api/reports/tasks/{task_id}/table-plan`

`table-plan` 当前支持：

```json
{
  "tableSelection": {
    "table_0": true,
    "table_1": false
  },
  "tableEdits": {
    "table_0": [
      ["输入", "I0.0", "启动按钮", "控制系统启动"],
      ["输出", "Q0.0", "运行指示灯", "显示运行状态"]
    ]
  }
}
```

### 下载与图片

- `GET /api/reports/tasks/{task_id}/download`
- `GET /api/reports/tasks/{task_id}/images/{image_index}`

## 5. 当前关键内部结构

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

### preview_data

当前预览主要包含：

- `sections`
- `imagePlan`
- `tablePlan`
- `template`
- `experimentName`
- `experimentType`

### tablePlan

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

## 6. 当前注意事项

### 6.1 不要破坏正式生成主链路

正常链路必须优先走：

`preview_layout_plan -> shadow gate -> layout_executor -> DOCX`

不要把新功能直接接回 legacy `append_report_content`。

### 6.2 legacy fallback 仍然存在，但只能兼容使用

只有缺失 `preview_layout_plan` 时才允许 fallback。

不能把 fallback 当正常路径继续扩展。

### 6.3 表格能力必须受白名单约束

当前只允许：

- `io_assignment_table`
- `phenomenon_record_table`
- `data_record_table`

禁止前端或外部请求直接提交自定义：

- schema
- headers
- 列数
- block type

### 6.4 表格编辑只允许修改 rows

当前允许编辑：

- `rows[][]` 的单元格文本

当前不允许编辑：

- `headers`
- `schema`
- `tableId`
- 列数
- block 类型

### 6.5 前端 dirty 状态是本地状态

当前前端 `dirty / saving / saveError` 只存在于页面本地，不进入后端。

含义：

- `dirty=true`：本地已改、未保存
- `saving=true`：正在请求 `PATCH /table-plan`
- `saveError`：最近一次保存失败信息

### 6.6 已保存与未保存的边界

当前只有点击“保存表格内容”后，编辑内容才会进入后端 `table_edits`。

如果用户只编辑不保存：

- 不会进入后端
- 不会写入最终 DOCX

### 6.7 当前前端防丢失保护范围

当前已保护：

- 确认生成前拦截
- 页面内自定义返回前提示
- “创建新任务”前提示
- 刷新时不覆盖 `dirty=true` 的本地 rows

当前未完全保护：

- 系统级关闭小程序
- 微信原生手势返回
- 进程被系统回收后的本地恢复

## 7. 下一步建议

### 优先建议

1. 完成 `P3-08` 真机回归确认
2. 补任务历史中的 `tableAudit` 展示
3. 增加未保存表格的本地恢复能力

### 暂不建议立即做

- 接 LLM 做表格规划
- 开放自定义表格
- 做复杂表格编辑器
- 同时扩到多实验类型

这些都会显著扩大边界，当前阶段先稳住 PLC 场景更合理。
