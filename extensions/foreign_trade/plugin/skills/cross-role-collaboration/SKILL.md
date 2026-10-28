---
name: cross-role-collaboration
description: 用户要求外贸跨岗位协作、订单交接、分配采购美工运营合规任务、查看阻塞和验收时使用。复用当前账号的询盘、报价与资料包，保留来源版本、依赖、负责人标签和待确认事项；不发送消息或发布商品。
version: 0.3.0
---

# 跨岗位协同

使用前完整读取本技能。入口是 `trade_collaboration`，其身份由当前认证会话绑定；不传 user_id、账号权限、密码、Token 或服务器路径。

## 边界

- 这是当前账号下的岗位协同单。岗位和负责人姓名是业务标签，不代表其他账号获得访问权，也不代表真正通知了该岗位。
- 公开公司事实、团队构造的询盘、模拟价格和产品素材分别注明来源。不能把 Raspberry Pi 等真实品牌的规格或照片当作 DESK-001 的产品依据。
- 审核仅为内部资料检查，不是法律合规认证；未知供货、运费、税费、库存、授权等事项保留待确认。
- 不发送邮件、不向队友发消息、不发布商品、不下单或付款。

## 创建和推进

1. 用现有询盘工具读取用户指定的询盘，确定真实记录 ID 和当前报价；缺少产品条件时先澄清，不自行补造。
2. `trade_collaboration(action="create", data={"title":"...","inquiry_id":"...","prepare_catalog_content":true})` 建立协同单。可传 assignees 岗位到姓名标签的映射。未指定负责人保留待指定。
3. 未指定资料包且 prepare_catalog_content=true 时，目前仅支持询盘中单一 DESK-001 产品行，保存候选事实和明确标注模拟的几何示意图。首次创建回执的 content_preparation.created=true、facts_confirmed=false、generated=false，不表示确认或生成完成；后续以最新回执为准。其他 SKU 或多 SKU 设置 prepare_catalog_content=false，保留资料待办，之后关联已有包。若传外部产品包，content_relationship 必须为 independent_reference，不能替代本订单商品材料。
4. 对话展示六项任务、负责人、依赖、验收条件、阻塞及待确认项。资料确认和生成仍通过产品内容技能完成；报价仍通过原计算工具完成。
5. `action="get"` 取得最新 revision。用 `action="update_task"`、collaboration_id、revision、task_id 和 data 更新负责人、结果说明、待确认项或状态；状态仅 todo、in_progress、in_review、cancelled。data 可含 assignee_label、status、result_note、unresolved_items、risks、depends_on；不能移除模板必需依赖。不要凭口头总结写成已完成。
6. 用户看到本任务的实际产物、检查项和未决事项后明确确认，才可 `action="review"`，同时提供 collaboration_id、最新 revision、task_id，data={"confirmed":true,"review_note":"用户确认的审核意见"}。任务必须为 in_review，负责人、结果依据及依赖须满足服务端检查。revision 和 task_id 只放在工具顶层，不放进 data。不得替用户自动确认。
7. 服务端决定任务完成和整个协同单的可交接状态。所有写操作都使用上一成功回执的最新 revision；409 时重读，不循环重放写操作。

## 变更和交接

- 每次展示或下载先读取当前记录。询盘商品、报价、确认事实、原图或输出发生变化后，相关任务和下游验收会失效。
- `action="refresh_sources"` 接受最新来源快照，但不表示重新审核完成。说明哪些任务需复核，再逐项推进。
- 未关联商品资料时，可用 `action="link_content"`、collaboration_id、当前 revision 和 data 中的 content_pack_id、content_relationship 关联当前账号资料包。content_relationship 为 transaction 或 independent_reference；transaction 仅接受同一模拟 SKU 的目录绑定资料。关联会重新检查产品关系并使相关验收失效；真实外部品牌包只能作为独立参考。
- 跟进待办等无关变化不应被解释成产品内容已变化；以服务端 stale/blocked 和检查结果为准。
- 成功回执会显示协同状态卡。Markdown/JSON 下载来自已验证的当前协同单，不由模型编造链接。内部交接可以保留已明确记录并接受的待确认事项，不得把“可内部交接”写成“可直接发货/已合规”。
- 失败或未执行应如实报告，保留记录 ID 和未完成步骤，不能把调用 JSON 示例当作实际执行。
