# 采购功能真实资料与独立模拟测试

日期：2026-11-01。最新执行时间约12:50 Asia/Shanghai。

## 真实客户候选资料

实时读取LYRECO集团官网及联系页：

- https://www.lyreco.com/group/
- https://www.lyreco.com/group/contacts

官网自述涉及办公用品、家具、IT设备、打印解决方案、个人防护、卫生用品、咖啡及餐饮。联系页提供公开联系表单。它是一个真实企业候选，不是用户已确认客户；没有提交联系表单或发送消息。没有获得其真实采购需求、库存、采购订单、供应商报价、验收或付款资料。

采购系统不能由企业公开介绍推定真实采购量、供应商产能或审批。这次将两份真实网页作为来源输入，未编造需求行，七阶段均返回needs_input；这验证了公开资料不足时没有声称采购完成。

首次尝试还读取Raspberry Pi 5产品页，收到HTTP403，没有获得可用原文。失败检查保存在first-attempt-summary.json。随后使用LYRECO联系页补充资料；不将前次失败隐藏为首次全部成功。

## 独立模拟记录测试

与真实公司完全分离的case_id：SYNTHETIC-ONLY-NOT-LYRECO-NOT-RASPBERRYPI。

使用项目既有测试fixture创建合成采购单，所有供应商名称、数量、价格、审批标志均为测试输入，不是LYRECO或Raspberry Pi的业务事实，也不是用户提供或真实人员批准的记录。调用生产服务函数ProcurementInput与prepare，无模拟函数返回。

|阶段|实际结果|含义|
|---|---|---|
|需求|review_required；净量75|100需求＋5安全库存－20可用库存－10在途|
|寻源|review_required|根据模拟准入证据进入待审核；不证明已真实搜集和认证供应商|
|能力|review_required；可用产能75|模拟产能100－已承诺25|
|比价|review_required；CNY770|75件×10元＋20元运费，仅同数量同费用口径|
|质量|review_required|模拟实测10，范围9至11；另测实测12能检出越界|
|交期|needs_completion|旧进度、已逾期及剩余时间不足被提示；没有创建后台监控|
|结算|review_required；核对余额CNY650|模拟发票货值750－确认付款100；不包含另行报价的20元运费，二者不是同一总应收口径；不授权付款|

13项测试断言全部通过：实时读取两来源、公开资料缺项、净量、产能、成本、余额、无外部动作、未知运费不排名、质量越界、验收差异不输出核对余额、未确认库存不算净量、重复发票拒绝、改价后指纹变化。

## 已复现的功能缺口

**交期阶段未强制核验批准PO。** 删除模拟订单及其单据后，delivery仍返回进度分析，没有missing_purchase_order或order_review_required提示。工作流文档要求取得真实批准PO后进入该阶段，但后端prepare目前未实施对应门禁。诊断性分析可以保留，建议明确区分“无PO的计划分析”与“批准订单的履约跟进”，并在缺PO或PO未批准时输出阻塞项。

因此13项选定断言通过不等于采购功能完整验收通过。缺口单独保存在summary.json的known_gap字段和boundary-results.json中的missing-po-delivery。

另需注意：采购工具只核对传入证据，不会自动将客户官网转成需求，不会自动联网搜集供应商，也不独立鉴定审核标志真实性。真实使用需要补充实际需求、受权审核、供应商报价及履约资料。

## 测试范围与产物

本次完成真实公开资料采集及七阶段生产服务函数测试；没有执行登录HTTP接口、前端聊天或真实模型编排验收。没有下单、付款、写CRM、发消息或修改采购功能代码。

- customer-source.json、customer-contact-source.json：真实网页文本、URL及获取时间。
- public-only-input.json、public-only-results.json：仅真实资料时的缺项响应。
- synthetic-input.json、synthetic-results.json：独立合成采购数据及七阶段回执。
- boundary-results.json：未知运费、质量超限、验收差异、未确认库存及无PO交期探针。
- summary.json：最终13项检查及已知缺口。
- first-attempt-summary.json：403失败的首次结果。
- test_live.py：复跑脚本，会重新联网并覆盖本目录结果；保留证据后再运行。

在项目根目录的开发环境执行：

```bash
.venv/bin/python outputs/procurement-live/test_live.py
```

本次不提供采购节省、准交率或业务准确率结论；没有相应真实业务样本及基线。
