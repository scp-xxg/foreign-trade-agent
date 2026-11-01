---
name: trade-improvement-planning
description: 将复盘问题转成带负责人、期限、验收和效果检查的行动草案，并检查实验设计缺项。
display_name: 改进行动与实验设计
version: 1.0.0
tags: 外贸, 复盘
---

# 改进行动与实验设计

执行前阅读 [工具契约](references/contract.md)，需要字段详情时查 [JSON Schema](references/schema.json)。用 `trade_buyer_research(action="improvement-planning", data=...)` 真正执行，工具不可用如实报告。

先从有证据问题草拟actions，再调用工具。每项明确problem及evidence、owner/due_at/deliverable/acceptance/metric/baseline/target/check_at；缺负责人期限不得编造。实验补hypothesis/population/comparison/guardrail。区分直接修正和实验验证，用预期影响、证据及投入定性排序，不编造收益。completed_at必须有完成证据且不晚于as_of，check_at不能早于due_at。动作完成不代表验收通过或业务改善。此版本只检查设计与执行证据，没有统计显著性推断；到期取得真实实验结果另行比较，不声称已设置提醒。

复用现有沟通纪要及利润计算，不生成无依据商业承诺。本技能输出内部待审复盘草案，不自动发送、建立提醒、写CRM或更新知识库。保留原文证据、未知项及各阶段跳过原因。

## 验收与效果

可执行率=负责人期限交付验收齐全行动/全部行动；按期完成率=到期前完成/到期行动，需独立真实执行记录；验收通过率=达到标准行动/已验收行动；实验完成率=形成结果实验/到期实验；业务改善需报告基线、样本、周期及保护指标，无结果保持未知。

用独立人工标注材料验收提取与判断，计算用人工核算对照。每项报告样本数、分子分母、周期和适用范围，未测不填写准确率。业务改善使用固定观察期及可比商机验证，不将自然推进全部归因于技能。
