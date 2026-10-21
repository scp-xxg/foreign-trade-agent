---
name: product-content
description: 用户上传产品资料或原图，要求制作英文商品介绍、上品文案、客服 FAQ、产品图片排版和可下载资料包时使用。通过当前用户绑定的 trade_import_product、trade_confirm_product_facts 和 trade_product_content 复用产品内容工作台；可载入 Raspberry Pi 5 真实公开资料。先展示事实摘要和缺失项，等待用户确认后再生成，不擅自发布商品。
version: 0.2.0
tags: 外贸, 商品资料, 英文文案, FAQ, 图片, 来源
---

# 产品资料转商品内容

以用户上传资料或明确选择的公开示例为依据，制作待审阅的英文商品介绍、FAQ 和图片资料包。记录与“产品内容工作台”共用。真实产品资料与模拟报价目录分开，不向报价目录自动添加商品或虚构商业条件。

## 工具和当前用户范围

先完整读取本技能。常见上传与确认优先使用下面的显式字段 helper，不让模型重新编写长 facts 数组：

- trade_import_product(file_ids, title, product_name, brand, model, source_url, image_credit, pack_id="", revision=null)：真实导入当前聊天附件，按明确元数据创建或更新资料包，只返回候选事实，不自动确认。未知元数据留空，不编造来源或图片授权。
- trade_confirm_product_facts(pack_id, revision, confirmed=true, fact_indices=null, product_name=null, brand=null, model=null, source_url=null, image_credit=null)：仅在用户确认候选摘要后调用，由程序采用原 suggested_facts 的精确值。fact_indices 使用回执候选的从 1 开始的索引；null/省略表示采用全部候选，超过 20 条时先让用户选择，不擅自截取。可同时补充用户明确确认的元数据。该工具确认事实但不生成输出，下一步仍要单独 generate。

复杂管理继续使用 trade_product_content(action, pack_id="", revision=null, data={}, file_ids=[], confirmed=false)。action 为 list、get、create、update、import_files、load_demo 或 generate。工具由本公开项目绑定当前登录会话，不能接受模型提供的 owner_user_id。

- create：data 可包含 title；创建后保存回执的 pack_id 与 revision。
- list/get：定位当前用户的既有资料包；同名多个候选先让用户选择，不自行覆盖。
- update：data 可包含 title、product_name、brand、model、source_url、raw_text、facts、image_credit。facts 每项为 label、value、source_url。只有用户确实修订事实、且候选选择 helper 无法表达时才使用该通用入口；不要仅为采用已有候选而让模型重写长数组。
- import_files：保留通用导入入口；常见流程优先 trade_import_product。两个入口的 file_ids 都只能来自当前聊天中实际上传/引用、且工具验证属于当前用户的附件标识。不接收磁盘路径、任意 URL、其他用户文件 ID，也不猜测 ID。
- load_demo：用户明确要求真实公开产品示例时可调用。无 pack_id 时创建新示例资料包；传 pack_id/revision 时只接受空资料包。它载入 Raspberry Pi 5 的固定 CSV 与授权照片，填充来源和署名，只产生 suggested_facts，不把建议当作已确认事实。
- generate：必须已有有效产品名称、确认后的 facts、图片来源说明；传当前 revision 和 confirmed=true。只有符合下一节确认条件时才可将 confirmed 设为 true。

除新建记录外，每次操作使用当前 get 或上一轮成功回执的 revision。冲突先 get 再核对。资料、图片或事实变化后旧输出失效，必须重新确认并生成；不可把历史输出当作当前版本。

## 文件导入和事实确认

1. 识别目标资料包。用户上传文件时优先调用 trade_import_product，以实际 file_ids 和简短元数据导入；已有包先 get 取得当前 revision。用户已上传且可引用的文件不要求再次上传，不通过 bash 读取任意服务器路径。
2. 真实导入后查看 documents、suggested_facts、原文摘要和 warnings。没有导入回执时不能声称文件已导入。文件解析不等于事实已经确认；图片只用于排版，不从外观推断 RAM、容量、认证、配件清单或销售授权。
3. 给用户展示将用于生成的事实摘要、来源、图片署名和缺失项。明确区分“用户资料给出的事实”“公开来源事实”“尚未提供”。保留数字、单位、限定词和配件要求，不加营销承诺。
4. **在这一摘要之后等待用户确认。** 首次“帮我做商品资料”的请求不等于确认尚未展示的抽取结果。用户确认当前候选后，调用 trade_confirm_product_facts 并使用当前 revision、confirmed=true 及用户选择的 1-based fact_indices；程序直接采用候选值，不由模型重写。用户修订候选外内容时先修正摘要，必要时再次确认，再使用通用 update。
5. 确认工具成功后，用它返回的新 revision 单独调用 trade_product_content(action="generate", confirmed=true)。确认事实不等于已生成资料包。不要提前确认或用布尔值跳过人工确认；用户不回应不视为已确认。
6. 呈现真实输出状态与工具返回的资料卡。只在正文中打印 JSON、步骤或链接文本都不等于执行；必须有实际调用成功与对应状态，才可报告导入、确认或生成完成。卡片提供的文案、FAQ、图片和 ZIP 才能作为可下载产物；不能自造 URL、绝对文件路径或声称已经发布/下载到用户设备。

如果当前聊天没有可导入的附件 ID，说明缺少可引用文件，让用户通过聊天上传或在现有产品内容工作台上传。若工具不可用，说明需要更新/启用本公开项目的外贸插件，不绕过用户隔离直接访问数据库或存储目录。

## 输出核对

- AI 只负责有依据的英文翻译，数字和单位须保留；输出仍需人工审阅，不宣称模型保证语义完全正确。
- 工具返回 template 表示翻译未通过或不可用，应明确“基础模板保留原文”，不得称为已完成英文翻译。非英文事实未翻译时，英文图片暂停生成；只展示实际返回的 assets。
- 方图用于产品参考图；横图可能展示精选规格并引导查看完整文案；参数图和 ZIP 按工具实际结果呈现。不能声称每张图片都包含全部事实。
- 当前图片能力是基于授权原图等比缩放、排版和加文字，不是 AI 生成新场景图，也不改变产品结构。
- 图片署名必须保留作者、来源、适用许可及修改说明；使用公开示例时复用 load_demo 返回的署名，不改称团队原创或无版权。
- 价格、MOQ、库存、运费、交期、保修、认证及目标市场合规结论没有资料就写待供应商确认，不用网页宣传语补齐。
- 用户修改事实或重新上传图片后，说明旧输出已失效并重新执行确认与生成。

## 公开示例

Raspberry Pi 5 的规格来自官网，照片由 SimonWaldherr 以 CC BY 4.0 发布。使用 load_demo 的固定来源与署名。它只展示真实资料处理能力，不表示本项目与制造商有经销、采购或合作关系，也不推断照片中的具体 RAM 容量。

用户明确确认之后可以生成英文商品介绍、客服 FAQ、三种实际支持的排版图和 ZIP。整个流程只保存当前账号的数据和产物，不登录电商平台、不上架发布、不向客户发送信息。
