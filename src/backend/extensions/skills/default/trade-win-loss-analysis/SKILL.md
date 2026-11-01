---
name: trade-win-loss-analysis
description: 对赢单、丢单及停滞商机分析客户陈述、观察因素、可控因素和原因假设，保留反证及未知。
display_name: 赢单与丢单原因分析
version: 1.0.0
tags: 外贸, 复盘
---

# 赢单与丢单原因分析

执行前阅读 [工具契约](references/contract.md)，需要字段详情时查 [JSON Schema](references/schema.json)。用 `trade_buyer_research(action="win-loss-analysis", data=...)` 真正执行，工具不可用如实报告。

先核对deals.outcome，won/lost须有outcome_evidence；open/paused不归为丢单。reasons每项关联deal_id，kind=customer_statement/observed_factor/hypothesis，已述及已观察因素必须附证据，假设明确待验证。输出反证、可控程度和验证问题。客户陈述仅证明其表达，不能证明唯一或真实原因。价格需核对规格、贸易术语和比较对象；沉默不得直接归因。无原因材料输出needs_evidence，不编结论和成交概率。

复用现有沟通纪要及利润计算，不生成无依据商业承诺。本技能输出内部待审复盘草案，不自动发送、建立提醒、写CRM或更新知识库。保留原文证据、未知项及各阶段跳过原因。

## 验收与效果

原因证据覆盖率=有证据原因项/原因项；人工认可率=复核认可判断/抽查判断；无依据确定归因次数验收为0；新发现有效问题率=复核确认新问题/新提出问题；原因确认率=后续证据确认假设/已开展验证假设。

用独立人工标注材料验收提取与判断，计算用人工核算对照。每项报告样本数、分子分母、周期和适用范围，未测不填写准确率。业务改善使用固定观察期及可比商机验证，不将自然推进全部归因于技能。
