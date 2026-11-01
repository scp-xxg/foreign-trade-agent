---
name: trade-payment-verification
description: 依据条款和提供的银行或财务记录核对付款条件、订单匹配及差额，区分付款承诺、水单与到账。
display_name: 收款条件与到账核验
version: 1.0.0
tags: 外贸, 成交
---

# 收款条件与到账核验

执行前阅读[工具契约](references/contract.md)，字段详情见[输入Schema](references/schema.json)。调用`trade_buyer_research(action="payment-verification", data=...)`，工具不可用时如实说明。

先确认payment_method、币种、expected_due及due_evidence，expected_payer和批准account。expected_due是当前节点应收，不是自动取合同总额。payments需transaction_id、订单、金额币种、付款方、账户、时间、类型和原文证据。promise/remittance_slip不得计到账；bank_credit须bank_record来源，finance_verified须finance_confirmation来源。订单、账户、付款方、币种或未来日期异常不计入匹配金额。相同交易ID不重复计；不要给同笔款项伪造不同ID，同一记录跨订单分配必须财务另核。程序只做本次材料匹配，未接银行不声称实时验证。差额以Decimal计算，不擅自豁免手续费汇差；lc/credit用企业付款条件phase=payment审核，不硬套定金。正常金额仍待财务审核，不推定投产。

只返回内部待审材料，不自动发信、签署、认领收款、写CRM或启动履约。复用背调核验主体、谈单确认条件、沟通生成消息，不重复执行无关触达。来源引用仅说明原文关联，不能独立证明真实性。

## 验收与效果

对账准确率=正确匹配记录/抽查记录；异常召回率=检出真实异常/标注异常；误报率=误报/报出异常。误判到账及重复认领次数验收为0；对比财务核对耗时。

用独立人工标注材料验证提取与状态，金额以人工核算对照；覆盖缺项、版本冲突、错误账户、未来记录、混合币种及不同付款方式。每项指标报告样本数、分子分母和观察周期，未测保持未知；业务改善需在可比客户和订单上观察，不把全部成交归因于技能。
