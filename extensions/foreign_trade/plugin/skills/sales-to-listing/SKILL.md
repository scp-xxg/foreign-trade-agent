---
name: sales-to-listing
description: 以同一商品和同一询盘贯穿报价、跟进、商品资料、本地化审核与岗位交接，支持中文两轮改稿及文件下载。
---
# SailAgent 询盘到上品

目标用户是中小外贸团队。主入口为中文对话；工作台用于核对证据和下载。不要一次堆出所有功能，按当前业务阶段执行。用户未给产品、数量、包装和市场时先补齐，不补造事实。

## A 销售阶段
1. 读取 buyer-inquiry-followup 和 inquiry-quote 技能。核对用户给出的公司官网/登记国；买家事实逐项保留来源与未知项，官网与登记不证明来信人或信用。
2. 询盘标题使用稳定的客户与SKU标识，避免把数量/包装写死在标题，改量后标题与正文互相矛盾。查询目录产品，明确数量、包装、目的地、模拟声明；用 trade_save_inquiry 保存，再用 trade_calculate_quote 真实计算，勿心算报价。
3. 生成 Alibaba RFQ 英文回复，货值、包装费和不含运税口径须与报价快照一致。给出未发送草稿和中英PDF/Excel下载卡；未指定付款/运费/有效期不能暗定。
4. 用户改量或包装时，读取同一个 inquiry_id 最新 revision，更新、重算、刷新回复；不要另建“第二轮”订单。跟进待办只有用户明确时间且含时区才创建。
5. 读取 localization-review，用 trade_review 查询规则并校验 alibaba_rfq；展示文字批注和风险标记。用户改稿后创建第二份审核，previous_review_id 指向原审核，保留前后比较。高风险不得描述为已通过。

## 同商品接力与 B 运营阶段
6. 读取 cross-role-collaboration；用 trade_collaboration create 关联已保存的 inquiry_id。演示单一 DESK-001 可 prepare_catalog_content=true，得到同款模拟规格与示意图及 content_pack_id。其他产品必须上传自己的授权资料并关联，不能拿 Raspberry Pi 资料充当DESK商品。
7. 读取 product-content，获取该 content_pack_id 的候选事实与图片来源，展示给用户后等待明确确认。用 trade_confirm_product_facts 确认原候选索引，再 generate；中文资料用AI模式，模板模式只处理已有英语事实，不能冒充翻译。
8. 返回英文资料、FAQ、方/横/竖三图与ZIP素材包。图片为原图/示意图排版，不称AI生成写实商品照片。
9. 根据确认事实形成 Amazon US Listing 草稿，区分标题、Item Highlights、bullets；用 trade_review 对同一个 pack_id 进行 amazon_listing 校验，用户改稿后第二次校验并关联前轮。规则知识有版本与来源，不称平台批准。
10. 岗位协作沿用同一 inquiry_id、pack_id 和资料版本。业务/采购/美工/运营/合规是岗位任务，不是五个已自治工作的智能体。展示负责人、依赖、待确认项；只在用户明确审阅确认后验收，不为演示自动“全部完成”。来源变化须重新审阅。

## 企业知识与异常
用户询问企业规则时，先检索其可访问知识库并取原文证据；未找到来源不要编造政策。例：样品退款须分别判断数量与期限，不把其他SKU的规则套入本单。
409需读回最新版本；422修正缺项并等确认；模型/网络失败保留已存记录，清楚说明本次未完成；不把模板结果、缓存资料说成实时AI/外网成功。任何文件下载均使用真实工具回执；不编造链接、不发送客户消息、不发布商品。

## 文件交付约定
trade_calculate_quote成功回执自动形成PDF/Excel报价卡，trade_product_content生成结果自动形成文案、FAQ、三图和ZIP卡。指引用户点击这些原生卡即可，不要用通用文件工具重新制作或寻找同名PDF/Excel；原始上传文件在资料工作台通过已返回的认证URL读取。重复取历史记录不等于必须重新计算或重新生成；只有业务条件变化才重算，避免无意义增加版本。
