# 八大工作流演示输入材料

这套材料用于逐个测试聊天框中的八个工作流：获客、客户背调、客户沟通、谈单、采购、发品准备、成交、复盘。每次只开启一个工作流，再粘贴对应输入。

## 资料边界

- **真实公开资料**：Giffits GmbH 是德国促销礼品企业；其官网展示带标识的企业礼品和咖啡杯品类。官网 Impressum 列有德国注册地址及商业登记信息，官网联系页公开联系渠道。这些资料只证明公开页面这样记载，不证明其有保温杯采购意向。
- **真实公开产品资料**：Raspberry Pi 5 的规格来自 Raspberry Pi 官方产品页。项目另有公开资料 CSV 和 CC BY 4.0 照片，可用于发品演示。
- **真实公开复盘资料**：TED 编号 690705-2025 是爱尔兰企业宣传品采购中标公告。当前可见的索引记录显示买方、获奖方及公告发布日期，金额未披露。
- **虚构演示资料**：宁波保温杯工厂、其产能/报价/交期、Giffits 询盘、谈判往来、采购报价、PO、发票、收款记录均为演示假设，不是现实交易或真实供货声明。禁止把这些内容当成真实客户往来、合同或付款证明。

## 1. 获客

测试目标：生成画像、预览搜索计划，并尝试真实公开买家搜索。需有可用搜索服务；没有配置时应报告缺口，不能编造搜索结果。

```text
开启获客工作流。我们是用于演示的宁波保温杯供应商，以下能力均为虚构测试数据，不代表真实工厂：500ml 双层真空不锈钢杯，304 不锈钢；现有款 MOQ 500 个，定制颜色 MOQ 1,000 个/色；支持激光 Logo、定制颜色和礼盒；月产能 50,000 个；参考价 FOB Ningbo USD 4.5–6/个；大货交期 30–40 天；食品接触报告覆盖型号和有效期未知。

目标市场德国，买家类型为促销礼品经销商、企业礼品进口商和品牌商。请先生成客户画像与筛选规则，区分事实、测试声明和假设；然后展示搜索计划并执行预算内的真实公开搜索。Giffits GmbH 是我已知的真实候选，请将它作为候选/排重对象处理，不要假设它有采购需求。目标 5 家，最多 4 条查询、8 次网页读取、90 秒。只返回真实工具结果和来源；无搜索服务时停止并说明配置缺口。
```

## 2. 客户背调

测试目标：企业身份、业务适配、联系人来源与交易风险。Giffits 信息来自官网；登记有效性、人员在职和采购意向应继续核验。

```text
开启客户背调工作流，对以下真实公开企业候选执行企业身份 → 业务匹配 → 联系人核验 → 交易风险。只做公开研究，不联系企业。

企业：Giffits GmbH
官网：https://www.giffits.de/
国家：德国
官网法定声明：https://www.giffits.de/impressum.htm
登记信息（官网自述，需独立核验）：Amtsgericht Hamburg，HRB 106954
业务线索：https://www.giffits.de/kaffeebecher
公开联系页：https://www.giffits.de/kontakt.htm
我方产品与限制：使用本演示资料中的 500ml 双层真空不锈钢杯及虚构供货条件；不授权使用第三方品牌 Logo。食品接触报告的产品型号覆盖情况未知。
交易材料：无真实询盘、报价、合同、订单、付款记录或收款主体资料。

请逐条引用来源和原文，区分官网自述、独立核验、用户提供的测试假设及未知信息。通用客服/销售渠道不等于采购负责人；无交易资料不等于无风险。主体冲突时停下等待我人工确认。
```

## 3. 客户沟通

测试目标：使用已审核候选资料练习首次触达、需求澄清、有据答复或回复分流。以下询盘是虚构的，不是 Giffits 发来的。

```text
开启客户沟通工作流。客户候选是 Giffits GmbH；官网 https://www.giffits.de/，其官网公开展示促销礼品和咖啡杯品类。该候选尚无真实采购意向核实。

下面是团队构造的测试询盘 DEMO-INQUIRY-01，不是客户真实来信：
“We are planning a corporate gifting campaign in Germany. Please quote 1,000 black 500 ml stainless steel vacuum tumblers with laser-engraved logo and individual gift boxes. Please advise sample lead time, production lead time, food-contact documentation, shipping terms and payment terms.”

我方供货信息均为虚构测试数据：现有款 MOQ 500；定制颜色 MOQ 1,000/色；样品约 7 天；大货约 30–40 天；参考 FOB Ningbo USD 4.5–6/个；食品接触报告覆盖型号未知。请标记询盘来源为模拟材料，整理需求缺口，并起草内部待审英文回复。不要声称 Giffits 实际询价，不编运费、税费、付款条件、认证覆盖或确定到货时间，不发送邮件。
```

## 4. 谈单

测试目标：诊断异议、谈判策略、条件交换和试单建议。不得计算真实毛利，因为演示材料没有真实成本和授权底线。

```text
开启谈单工作流。基于 DEMO-INQUIRY-01（团队虚构询盘，非 Giffits 真实来信）和以下模拟回复做诊断：

“Your indicative price is above our target. Could you offer USD 4.00 per unit including the gift box and delivery to Hamburg? We would also need delivery within 20 days.”

我方仍只有虚构测试条件：参考 FOB Ningbo USD 4.5–6/个；定制颜色每色 MOQ 1,000；大货生产约 30–40 天；样品约 7 天。真实单位成本、运费、可让步范围、利润底线和授权人均未知。

请区分客户陈述与待验证推断，指出 USD 4.00 到 Hamburg 和 20 天到货分别缺少哪些成本/运输条件。给出不降价的可交换条件、需向客户澄清的问题和内部待审英文回复草稿。不要伪造毛利或批准权限，不承诺交期，不寄样、不发送。
```

## 5. 采购

测试目标：需求净量、供应商寻源/能力、可比成本、质量计划。两份报价是人为构造的测试报价，只验证计算和缺项处理，不代表真实供应商。

```text
开启采购工作流，为团队模拟的 1,000 个 500ml 双层真空不锈钢杯（304 材质、黑色、激光 Logo、独立礼盒）建立采购准备案。所有下列报价都是虚构测试数据，不可视为真实报价或真实供应商。

需求交付地点：德国 Hamburg；期望日期：2026-12-20。库存、确认在途量和安全库存均未知，请先列缺项，不要把毛需求称为净采购量。

测试报价 A（虚构，source_id=DEMO-QUOTE-A）：1,000 个；杯体 USD 3.10/个；激光加工 USD 0.35/个；礼盒 USD 0.40/个；一次性制版费 USD 80；FOB Ningbo。另有买方安排的海运估算 USD 180；生产期 35 天；报价有效期至 2026-11-15。
测试报价 B（虚构，source_id=DEMO-QUOTE-B）：1,000 个；杯体含激光加工 USD 3.35/个；礼盒 USD 0.25/个；一次性费用 USD 0；FOB Ningbo。另有买方安排的海运估算 USD 120；生产期 40 天；报价有效期至 2026-11-15。

请先完成需求缺口和报价口径比较，明确 A/B 都是模拟报价。未提供供应商身份、能力证据、汇率/税费、样品标准、实际库存和 PO 前，不要判定供应商合格、发布采购订单、启动交期跟踪或结算。质量阶段列出应补的检验指标，不捏造实测值。
```

## 6. 发品准备

测试目标：导入真实产品资料、确认事实、生成平台适配草稿并检查规则。先把项目中的 CSV 和照片实际上传到聊天；仅粘贴文件路径不算上传。

真实资料：Raspberry Pi 官方产品页 <https://www.raspberrypi.com/products/raspberry-pi-5/>；项目资料 [product_facts.csv](../extensions/foreign_trade/demo_product/product_facts.csv)、[product_facts_en.csv](../extensions/foreign_trade/demo_product/product_facts_en.csv)、[raspberry-pi-5-original.jpg](../extensions/foreign_trade/demo_product/raspberry-pi-5-original.jpg)。图片作者 SimonWaldherr，CC BY 4.0，须保留署名。

```text
开启发品准备工作流。我已在当前聊天实际附上 Raspberry Pi 5 的 product_facts.csv 和 raspberry-pi-5-original.jpg。请为 Amazon US 准备内部待审 Listing，先标准化并展示事实、来源和缺失项，等待我确认后再继续生成。

规格来源：https://www.raspberrypi.com/products/raspberry-pi-5/
照片署名：Photo: SimonWaldherr, Raspberry Pi 5.jpg (CC BY 4.0). Layout and text added; original photo retained. Source: https://commons.wikimedia.org/wiki/File:Raspberry_Pi_5.jpg License: https://creativecommons.org/licenses/by/4.0/

不得从照片推断 RAM 容量、价格、库存、保修、销售授权或认证。平台规则若无当前可核验版本，标为待确认，不要声称已通过 Amazon 审核；不要发布商品。
```

收到事实卡后，先人工检查 CSV 中的 8 条规格与图片署名，再在第二轮明确告诉助手确认哪些事实。不要把未确认字段一并确认。

## 7. 成交

测试目标：成交准备度、条款核对、PI 草拟、签署/付款和交接前置条件。为验证安全边界，使用虚构订单，但不伪造签字、批准模板或到账凭证。

```text
开启成交工作流。以下是 DEMO-PO-2026-001 的虚构测试资料，不是真实订单或承诺：

买方：Giffits GmbH（仅为官网公开企业候选，未建立真实交易关系）
卖方：Ningbo Demo Drinkware Co., Ltd.（虚构测试公司）
产品：500ml 双层真空不锈钢杯，304 材质，黑色，激光 Logo，独立礼盒
数量：1,000 件
单价：USD 5.10/件；货值小计 USD 5,100
贸易术语：FOB Ningbo；运费、保险、税费未包含/未知
付款条件：测试草案 30% 定金、70% 装运前支付；尚未双方确认
交期：生产约 30–40 天（虚构供货假设）；运输时间未知
PO、报价、规格版本、批准合同模板、签署记录、受控收款账户、银行到账凭证、质检和交接文件：均未提供。

请按六阶段做成交准备度检查，引用实际材料；列出阻塞项。可给 PI/合同字段清单或未批准模板下的补件清单，但不要声称订单已确认、合同已批准或款项已到账。不要把水单/口头承诺当银行入账，不签署、不发信、不下单、不启动生产。
```

## 8. 复盘

测试目标：真实公开记录的单商机时间线、赢单证据、原因未知、改进行动和案例边界。此例不是我方出口订单；只有一笔记录，整体漏斗应跳过。

公开记录：TED `690705-2025`，<https://ted.europa.eu/en/notice/-/detail/690705-2025>；索引页 <https://tenderscout.ie/award/690705-2025>。索引记录显示项目为爱尔兰企业宣传品采购，买方 The Irish Air Navigation Service，中标方 ASA Marketing Limited，公告发布日期 2025-10-21，金额未披露。实际授标日期、投标报价、竞标者、评审分数和赢单原因未知。官方 TED 正文应在实际演示中再次核验。

```text
开启复盘工作流，对 TED 公开采购记录做单商机复盘（scope=deal），不是我方出口成交：

项目：Ireland – Information and promotion products – Corporate Merchandise Tender No 7 2025
商机 ID：IE-TED-690705-2025
买方：The Irish Air Navigation Service
中标方：ASA Marketing Limited
结果：仅从中标供应商视角记录 won
公告发布日期：2025-10-21（不是已确认的实际授标日期）
公告金额：未披露
TED 编号：690705-2025
复盘截至：2026-11-01T12:00:00+08:00

来源 S1：https://tenderscout.ie/award/690705-2025
可见原文：“Contract awarded by The Irish Air Navigation Service”; “VALUE Not disclosed”; “PUBLISHED 2025-10-21”; “TED REFERENCE 690705-2025”; “WINNER(S) ASA Marketing Limited”。
来源 S2：https://ted.europa.eu/en/notice/-/detail/690705-2025

请尝试核验 TED 官方公告。时间线只能把 2025-10-21 记为公告发布日期；若没有授标生效日，保持未知。无投标过程和赢单原因证据时返回 needs_evidence，不推断价格、关系或客户满意度。单商机不计算周期漏斗；改进建议限于补充招标文件、报价、评审和合同证据；经验只能是单案例，不能升级成已验证打法。
```

## 建议演示顺序

获客 → 人工审核候选 → 背调 → 人工审核 → 沟通 → 谈单 → 采购 → 发品准备 → 成交 → 复盘。每个入口单独开启；工作流切换互斥。Giffits 仅作为真实公开候选示例，Raspberry Pi 5 仅作为真实产品资料示例，TED 采购公告仅作为公开复盘案例；它们彼此没有已知交易关系。演示中的虚构工厂和单据必须一直保留“DEMO/模拟”标记。
