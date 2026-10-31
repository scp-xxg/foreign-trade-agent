---
name: trade-followup-cadence
description: 为已审核的外贸优先线索，根据公开渠道、真实发送历史和买家时区生成可解释的跟进计划；收到回复、退信或拒绝联系时暂停或停止。
display_name: 跟进节奏规划
version: 1.0.0
tags: 外贸, 跟进, 节奏, 计划
---

# 跟进节奏规划（第七个技能）

调用 `trade_buyer_research(action="cadence", data=...)` 执行计算。需要线索评分与联系人发现的输出，不用文字描述替代工具回执。生成计划不代表发送或建立后台任务。

## 输入与契约

- `lead`: 第五技能完整评分输入：buyer_id、dossier_version、review_version、review_decision（suitable/unsuitable/unknown）、review_reason、hard_excluded、do_not_contact、has_channel、assessments。assessments最多四项，dimension为product/buyer_type/market/supply，result为match/partial/mismatch/unknown；非unknown须提供excerpt、source_url、retrieved_at。
- `contact`: 选择的渠道channel、channel_type（email/contact_page）、公开source_url、带时区ISO retrieved_at、purpose_confirmed。公开邮箱不等于已验证收件人、职位或可投递。
- `timezone`: 买家IANA时区如Europe/Berlin，不能仅从国家猜测；`as_of`为带时区的评估时间，未传用服务器当前时间。
- `initial_sent_at`: 真实首封发送时间或null；`followup_sent_at`: 按先后顺序列出实际发送的0–3次跟进，不能用计划时间替代。全部时间须含时区且不晚于as_of。记录须覆盖此买家全部渠道，不能换邮箱重置次数。
- `max_followups`: 0–3，默认3；`bounced`: 是否退信；`reply`: 有回复时必须传第八技能的完整原始输入，同一buyer_id。不能只传分类摘要绕过暂停。

先核对背调适合审核、渠道归属、用途和四维证据。未审核或覆盖不足75%先补资料，匹配低于75分暂缓；这两个门槛为第五技能的未校准初始值。拒绝联系、硬排除、不适合、退信或回复退订/确认不感兴趣则停止；任何其他回复暂停原计划，按第八技能结果分流。无首封记录返回awaiting_initial_send。

## 输出及节奏

回执含status、reason、score、reply、steps、timezone、rule_version、input_snapshot、metrics与warnings。steps含次序、带时区due_at、目的、proposed/overdue_review和approval_required。

默认首封后3/7/14个日历日的买家当地09:30，周末顺延到周一，已实际发送的步骤不重复；后续建议与最近发送或前一建议至少间隔约3天。当地节假日尚未校验。逾期仅标记待人工审核，不集中补发。次数耗尽返回exhausted。

商家修改买家审核、证据、渠道、拒绝状态、回复或发送历史后必须重新调用，旧计划失效。用户审核每次实际消息和渠道；本工具无发送接口。只有明确要求保存站内待办时才另行使用已有询盘工具并取得最新记录版本，不声称待办等于自动邮件或桌面通知。

## 效果评估

使用有标注的历史发送/回复样本回放，检查停止规则违规数、重复步骤数、时区/时间错误数（验收均为0）；未知历史须报告不能证明去重。规划人工耗时=审核结束减开始，记录中位数及样本数。

业务实验按买家去重随机分组、统一产品和周期，统计每组实际送达买家数、正向回复买家数/实际送达买家数、退订买家数/实际送达买家数、每个正向回复的实际成本。无真实投递/成本记录不可计算；不把计划数量当发送数或将回复增长单独归因于本技能。3/7/14天是待实验的初始节奏，无已验证提升承诺。

当前接口无状态，不保存审核账本、计划或拒绝名单；需在本对话保留来源和实际记录，离开前导出或用户明确保存。
