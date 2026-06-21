# AI Planner 真实样本观察记录

## 1. 观察目的

AI Planner 当前仅运行在影子模式，不参与正式生成。本记录用于观察真实实验材料下的 AI 规划状态与差异摘要，判断其是否具备进入下一阶段的条件。

## 2. 当前边界

- 不替换 `preview_layout_plan`
- 不进入 `shadow gate`
- 不进入 `layout_executor`
- 不影响正式 DOCX 生成
- 不暴露完整 `candidatePlan`
- 仅观察 `summary / comparison / status`

## 3. 样本记录

### 样本 1：PLC 基础实验（task_id=12dab6da2c82457c936c24de32b6fd61）

基本信息：
- experimentType：`plc`
- 文件类型：指导书 + 实验报告 + 图片
- 图片数量：18
- 指导书：完整
- tablePlan：有
- imagePlan review/reject：review 15，reject 0

| 项目 | 结果 | 备注 |
|---|---|---|
| status | disabled | LLM 未配置 |
| enabled | false | |
| ok | false | |
| validationPassed | false | |
| error | LLM planner disabled or not configured | |
| warnings | [] | |
| sectionCount | - | 未生成 AI summary |
| imageBlocks | - | 未生成 AI summary |
| tableBlocks | - | 未生成 AI summary |
| tableSchemas | phenomenon_record_table | 来自规则 tablePlan |
| missingInAi | - | 未生成 comparison |
| extraInAi | - | 未生成 comparison |

人工判断：
- 合法性：not_tested
- 章节合理性：not_tested
- 图片使用合理性：not_tested
- 表格建议合理性：not_tested
- 是否出现编造内容：not_tested
- 是否遗漏关键图片：not_tested
- 是否遗漏关键表格：not_tested
- 是否建议进入下一阶段：no

问题：
- 当前环境未启用 LLM，无法观察真实 AI candidate

### 样本 2：PLC 交通灯 / 顺序控制类实验（task_id=03f17f2c60c14468a023a35c89c4c5c9）

基本信息：
- experimentType：`plc`
- 文件类型：实验报告 + 图片
- 图片数量：20
- 指导书：不完整 / 缺失
- tablePlan：有
- imagePlan review/reject：review 18，reject 0

| 项目 | 结果 | 备注 |
|---|---|---|
| status | disabled | LLM 未配置 |
| enabled | false | |
| ok | false | |
| validationPassed | false | |
| error | LLM planner disabled or not configured | |
| warnings | [] | |
| sectionCount | - | 未生成 AI summary |
| imageBlocks | - | 未生成 AI summary |
| tableBlocks | - | 未生成 AI summary |
| tableSchemas | io_assignment_table, phenomenon_record_table | 来自规则 tablePlan |
| missingInAi | - | 未生成 comparison |
| extraInAi | - | 未生成 comparison |

人工判断：
- 合法性：not_tested
- 章节合理性：not_tested
- 图片使用合理性：not_tested
- 表格建议合理性：not_tested
- 是否出现编造内容：not_tested
- 是否遗漏关键图片：not_tested
- 是否遗漏关键表格：not_tested
- 是否建议进入下一阶段：no

问题：
- 当前环境未启用 LLM，无法观察真实 AI candidate
- 该样本指导书缺失，不适合作为 AI 规划能力判断的唯一依据

### 样本 3：非典型文件名样本（task_id=46454b200ed848f6aae1ecf3ac29870e）

基本信息：
- experimentType：`plc`
- 文件类型：指导书 + 实验报告 + 图片
- 图片数量：18
- 指导书：完整
- tablePlan：有
- imagePlan review/reject：review 15，reject 0

| 项目 | 结果 | 备注 |
|---|---|---|
| status | disabled | LLM 未配置 |
| enabled | false | |
| ok | false | |
| validationPassed | false | |
| error | LLM planner disabled or not configured | |
| warnings | [] | |
| sectionCount | - | 未生成 AI summary |
| imageBlocks | - | 未生成 AI summary |
| tableBlocks | - | 未生成 AI summary |
| tableSchemas | phenomenon_record_table | 来自规则 tablePlan |
| missingInAi | - | 未生成 comparison |
| extraInAi | - | 未生成 comparison |

人工判断：
- 合法性：not_tested
- 章节合理性：not_tested
- 图片使用合理性：not_tested
- 表格建议合理性：not_tested
- 是否出现编造内容：not_tested
- 是否遗漏关键图片：not_tested
- 是否遗漏关键表格：not_tested
- 是否建议进入下一阶段：no

问题：
- 当前环境未启用 LLM，无法观察真实 AI candidate
- 样本文件名较非典型，更适合后续在 LLM 已启用后继续观察稳定性

## 4. 汇总判断

| 指标 | 结果 |
|---|---|
| 样本总数 | 3 |
| valid 数量 | 0 |
| invalid 数量 | 0 |
| failed 数量 | 0 |
| disabled 数量 | 3 |
| 平均 sectionCountDelta | 不可评估 |
| 平均 imageBlockDelta | 不可评估 |
| 平均 tableBlockDelta | 不可评估 |
| 是否出现未知 block | 不可评估 |
| 是否出现未知 table schema | 不可评估 |
| 是否出现无效 image_ref | 不可评估 |
| 是否出现明显编造 | 不可评估 |

结论：
- 当前 3 组真实样本都只观察到了 `disabled` 状态。
- 说明影子模式的接线和安全摘要链路存在，但当前环境不具备真实 AI candidate 观察条件。
- 本轮可以确认“影子模式不会影响正式生成”，但不能确认“AI 规划结果是否稳定、是否有参考价值”。

## 5. 是否建议进入 P4-07

结论：
- 暂不建议进入

进入条件：
1. 在真实环境中启用 LLM Planner 配置
2. 至少完成 3 个真实样本的 `valid / invalid / failed` 观察
3. `validationPassed` 应稳定为 `true`，或 invalid case 可被清晰归因
4. 不出现未知 block type
5. 不出现未知 table schema
6. 不引用不存在的 image
7. 不明显遗漏核心图片
8. 不明显乱插表
9. `summary / comparison` 对开发判断具有明确参考价值

## 6. 后续问题清单

1. 问题类型：`weak_value`
   - 表现：当前环境下 3 个真实样本全部为 `disabled`
   - 影响：无法对 AI Planner 真实候选方案进行结构观察
   - 建议修复方向：补齐 LLM 配置后重新跑样本观察

2. 问题类型：`weak_value`
   - 表现：当前无法获得 `comparison` 与 `summary` 的真实样本统计
   - 影响：无法判断 AI 规划相对规则方案的实际参考价值
   - 建议修复方向：启用 LLM 后重新记录 `valid / invalid / failed` 样本

3. 问题类型：`weak_value`
   - 表现：当前样本中大量图片被标记为 `review`
   - 影响：后续 AI 如果依赖图片上下文，可能进一步放大规划不稳定性
   - 建议修复方向：后续样本观察时同步记录 image review 对 AI summary 的影响
