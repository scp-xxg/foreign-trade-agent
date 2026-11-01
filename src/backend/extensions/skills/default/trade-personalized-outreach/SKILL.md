---
name: trade-personalized-outreach
description: 为已审核的优先跟进买家使用已确认英文事实生成有来源的开发信及中文审核对照，保留供货声明与联系渠道证据，仅生成待审草稿。
display_name: 个性化开发信生成
version: 1.0.0
tags: [外贸, 获客]
---

# 个性化开发信生成

先使用线索评分技能完成判断。调用 `trade_buyer_research(action="outreach",data=...)`；同源认证 API 为 POST `/v1/foreign-trade/buyer-search/outreach`。参数 lead 为完整评分输入，另需 channel、channel_type=email|contact_page、channel_source_url、channel_retrieved_at、company_name、sender_company、product_en、supplier_claim_en、supplier_claim_reference、goal=find_contact|share_catalog|confirm_interest、facts_confirmed。

可选 buyer_fact_en（人工审核过的英文事实）、buyer_fact_dimension=product|buyer_type|market|supply。事实须关联lead中match或partial的同维证据；资料不足留空，使用需求确认信。供应商声明必须来自商家资料并附资料编号或来源，禁止编造认证、价格、MOQ、采购意向与负责人。公司名称及供货资料采用已核对单行文本，不允许占位符。英文资料缺失时先准备并请商家核对译文，不能声称当前模板引擎自动翻译或核实了事实。

仅follow_up且facts_confirmed=true可生成。当前使用确定性双语模板：英文正文采用用户已核对英文事实；中文对照保留英文事实原文，不是完整自动译文。未独立验证语义与事实，不把用户确认当成独立核验。通用邮箱及联系页均称呼公司团队，不按邮箱前缀推断岗位。一个草稿只保留一个行动请求。

输出两个主题行、英文正文、中文审核对照、事实证据、商家承诺、渠道证据、检查结果、输入快照、draft状态及not_sent。人工审阅并批准后仍不发送。修改资料、重新背调、改评分或审核应使旧草稿批准失效。无发送工具，无CRM写入，不将批准解释为发送授权。

评估草稿可用率=无需实质修改的批准数/审核草稿数；无依据断言率=含无依据断言草稿数/抽检数，目标0；记录审核耗时。正向回复率、有效商机率与拒绝投诉率需要真实投递记录，当前不计算。用相似线索随机对照评估文案，不以打开率代表获客效果。
