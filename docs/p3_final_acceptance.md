# P3 Final Acceptance

更新时间：2026-05-14

## 验收结论

- 当前状态：未完成
- 原因：自动化验收已通过，但微信开发者工具、真机链路、Word 人工版式验收尚未补齐。

## 验收表

| 项目 | 结果 | 备注 |
|---|---|---|
| 微信开发者工具编译无错误 | not_tested | 本轮未在开发者工具内人工确认 |
| 上传 DOCX 正常 | not_tested | 需人工走上传流程 |
| 上传指导书正常 | not_tested | 需人工走上传流程 |
| 上传图片正常 | not_tested | 需人工走上传流程 |
| 能进入 preview_ready | pass | 后端自动化接口测试已覆盖 |
| 推荐表格显示正常 | not_tested | 需开发者工具或真机确认 |
| 保留 / 不插入开关正常 | pass | 后端接口测试已覆盖 tableSelection 保存 |
| 表格 rows 可编辑 | not_tested | 前端需人工确认输入框交互 |
| 编辑后显示未保存 | not_tested | 前端需人工确认状态提示 |
| 未保存时确认生成被拦截 | not_tested | 前端需人工确认 |
| 保存后可确认生成 | not_tested | 前端需人工确认 |
| 返回按钮未保存提示正常 | not_tested | 前端需人工确认 |
| preview.tablePlan 包含 tableId / selected / rows / edited | pass | 后端接口测试已覆盖 |
| PATCH /table-plan 保存 tableSelection 正常 | pass | 自动化通过 |
| PATCH /table-plan 保存 tableEdits 正常 | pass | 自动化通过 |
| confirm 后任务进入生成流程 | pass | 自动化通过 |
| done 后可下载 DOCX | pass | 自动化通过 |
| qualityReport.tableAudit 存在 | pass | 自动化通过 |
| qualityReport.layoutExecutor 统计正常 | pass | 自动化通过 |
| 模板保留 | pass | 后端质量检查与既有测试已覆盖 |
| 表头信息正常 | not_tested | 需 Word 人工打开确认 |
| 正文写入正常 | pass | 自动化与质量检查已覆盖 |
| 图片插入正常 | pass | 自动化与质量检查已覆盖 |
| 保留表格写入 | pass | 自动化通过 |
| 取消表格不写入 | pass | 自动化通过 |
| 编辑 rows 正确写入 | pass | 自动化通过 |
| 表头没有被前端篡改 | pass | 后端 schema 控制 + 自动化通过 |
| 表格标题正常 | not_tested | 需 Word 人工确认 |
| 表格排版无明显错乱 | not_tested | 需 Word 人工确认 |
| 错误列数 tableEdits 被拒绝 | pass | 自动化通过 |
| 未知 tableId 被拒绝 | pass | 自动化通过 |
| selected=false 的 dirty 表格不阻止生成 | not_tested | 前端需人工确认 |
| selected=false 的 edited 表格不写入 DOCX | pass | 自动化通过 |
| 刷新任务状态不覆盖 dirty rows | not_tested | 前端需人工确认 |

## 发现的问题列表

当前没有新的自动化阻塞问题。未完成项主要是人工验收缺口。

## 阻塞问题

1. 未完成微信开发者工具人工验收。
2. 未完成真机链路验收。
3. 未完成 Word 打开 DOCX 后的人工版式验收。

## 非阻塞问题

1. 当前没有新的自动化功能性失败。
2. 前端离开页面保护和 dirty 状态保护已接入，但未做人工操作确认。

## 是否建议 P3 关闭

- 结论：暂不建议正式关闭。
- 原因：核心自动化通过，但三类人工验收未完成。

## 是否建议进入 P4

- 结论：暂不建议直接进入 P4。
- 原因：如果现在进入 P4，会把人工交互问题和后续扩展问题混在一起，回归成本会明显上升。

## 进入 P4 前必须修复的问题

严格说当前不是“修复”问题，而是必须完成以下人工验收并记录结果：

1. 微信开发者工具完整走通：
   - 上传 -> 预览 -> 表格编辑 -> 保存 -> 确认 -> 下载
2. 真机完整走通至少一轮：
   - 表格编辑未保存提示
   - 返回提示
   - 生成拦截
3. Word 打开最终 DOCX 人工确认：
   - 模板保留
   - 表格标题
   - 表头
   - 表格排版
   - 图片与正文相对位置
