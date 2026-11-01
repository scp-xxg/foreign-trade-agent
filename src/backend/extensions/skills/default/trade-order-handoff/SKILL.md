---
name: trade-order-handoff
description: 将已确认订单整理成采购生产质检物流交接草案，检查企业执行前置条件，不直接启动履约。
display_name: 订单交接与履约启动
version: 1.0.0
tags: 外贸, 成交
---

# 订单交接与履约启动

执行前阅读[工具契约](references/contract.md)，字段详情见[输入Schema](references/schema.json)。调用`trade_buyer_research(action="order-handoff", data=...)`，工具不可用时如实说明。

将产品规格版本、数量单位、包装标签、质检依据、交期和文件要求提取为terms，handoff_required_fields按企业流程扩充。requirements覆盖readiness/signature/payment/handoff四类规则；不适用也须提供批准依据及证据，缺规则不默认放行。记录部门owner、due_at及depends_on作为里程碑；后续版本变化重新跑条款和条件检查。工具汇总交接字段、缺项及阻塞，recipient_acceptance仍未记录，execution_started=false。不能将到账或合同签署等单个条件等同可启动；未查询库存产能物流要明确未知。

只返回内部待审材料，不自动发信、签署、认领收款、写CRM或启动履约。复用背调核验主体、谈单确认条件、沟通生成消息，不重复执行无关触达。来源引用仅说明原文关联，不能独立证明真实性。

## 验收与效果

交接完整率=内容及来源有效的适用必填项/全部适用必填项；首次交接接收率、遗漏导致返工率、满足成交条件到交接耗时。条件未满足却启动次数验收为0，实际执行指标由真实业务记录核验。

用独立人工标注材料验证提取与状态，金额以人工核算对照；覆盖缺项、版本冲突、错误账户、未来记录、混合币种及不同付款方式。每项指标报告样本数、分子分母和观察周期，未测保持未知；业务改善需在可比客户和订单上观察，不把全部成交归因于技能。
