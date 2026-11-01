---
name: trade-playbook-learning
description: 从复盘及改进结果生成带适用边界、反例、版本和复查日期的待审案例或经验候选。
display_name: 有效打法与案例沉淀
version: 1.0.0
tags: 外贸, 复盘
---

# 有效打法与案例沉淀

执行前阅读 [工具契约](references/contract.md)，需要字段详情时查 [JSON Schema](references/schema.json)。用 `trade_buyer_research(action="playbook-learning", data=...)` 真正执行，工具不可用如实报告。

先草拟lessons，保留deal_ids/evidence/applicability/exceptions/reviewer/version/review_at。单次结果只能case；多次同名引用不证明有效。requested_tier=validated时工具检查多个独立商机及validation_evidence，但仍保持待审核，不自动升级为验证规则。反例未知应写明待补充，不能编造。工具仅查本次标题重复，knowledge_base_check=not_performed；若有授权可用知识检索工具查重，否则明确尚未检索。saved=false，仅交付候选内容；审核及另行授权后才可调用真实写库工具，不能自行改技能、模板和商业政策。

复用现有沟通纪要及利润计算，不生成无依据商业承诺。本技能输出内部待审复盘草案，不自动发送、建立提醒、写CRM或更新知识库。保留原文证据、未知项及各阶段跳过原因。

## 验收与效果

来源可追溯率=可定位业务证据知识/条目总数；审核通过率=通过候选/已审核候选；检索相关率=认可适用推荐/抽查推荐；采用率=实际使用条目/适用且推荐条目；过期处理及时率=及时修订停用条目/应处理条目。审核通过率不作为单一优化目标。

用独立人工标注材料验收提取与判断，计算用人工核算对照。每项报告样本数、分子分母、周期和适用范围，未测不填写准确率。业务改善使用固定观察期及可比商机验证，不将自然推进全部归因于技能。
