# 外贸业务助手插件

SailAgent 的业务插件，标识 foreign-trade-demo，版本 0.10.0。聊天执行业务，工作台显示相同账号的记录；基于公开 HugAgentOS 社区版，保留开源署名。

## 两条相连的流程

- **销售**：公开买家核验 → 商品查询与报价 → Alibaba RFQ 回复 → 审核修改 → 站内跟进。交付中英 PDF、双语 Excel 与回复草稿。
- **同款接力**：保存的询盘与 SKU → 候选事实 → 用户确认 → 关联资料包及运营任务。
- **运营**：英文资料、FAQ、三种图片排版 → Amazon US Listing → 两轮审核。交付基础 ZIP 与包含最终平台稿的审核 Markdown/JSON。

[九轮演示](../../docs/DEMO_TWO_WORKFLOWS.md) · [一键部署](../../docs/ONE_COMMAND_DEPLOY.md)

## 核心技能与工具

| 技能 | 工具与职责 |
|---|---|
| sales-to-listing | 贯穿同一询盘、资料包和岗位任务 |
| inquiry-quote | search_products、get_product、calculate_quote：模拟目录查询及确定性计算 |
| buyer-inquiry-followup | trade_save_inquiry、trade_inquiry、trade_calculate_quote：当前账号的询盘、报价、草稿和跟进 |
| product-content | trade_import_product、trade_confirm_product_facts、trade_product_content：附件、事实确认及资料生成 |
| cross-role-collaboration | trade_collaboration：同款资料关联、任务、依赖及人工验收 |
| localization-review、trade-compliance-check | trade_review：规则检索、国别/平台/商务审核和修订对比 |

额外的获客、背调、沟通、采购、谈单、成交、复盘技能复用当前用户的业务工具；实际清单以 plugin/plugin.json 与能力中心为准。12 个原生业务工具需本公开项目配套后端及当前会话授权，不能仅靠导入 ZIP 给未适配的上游安装完整能力。三个目录 MCP 工具继续独立提供。

## 数据与业务边界

- 8 个办公收纳 SKU、价格和交期为项目模拟；LYRECO 官网/GLEIF 信息是真实公开证据，不代表交易、来信人身份或信用已核实。
- 同款自动准备目前覆盖单一 DESK-001；其他商品需上传授权资料。Raspberry Pi 公开资料只能作为独立示例，不能套用 DESK 的价格。
- 价格使用 Decimal 计算，改量或包装后重算；运费、税费、付款、贸易术语等未知项不自动补全。
- 所有业务工具绑定当前账号；传入真实记录编号和最新 revision，不接受模型指定 owner。
- 确认事实后才生成资料；图片是授权原图或示意图排版，不等于真实拍摄或 AI 生图。
- 三个核心角色分工协作；任务中的姓名标签不是独立账号权限，也不代表已通知员工。
- 平台审核稿与基础资料包分开保存；复审不会悄悄覆盖原 ZIP。来源改变时需刷新、重算或复审。
- 规则是可追溯的辅助检查，不是认证或平台批准；不自动发信、签约、下单、付款或发布。
- 私有敏感词采用本机版本，不分发用户原文；多国公开案例见 market_compliance.md。

## 打包与检查

在仓库根目录执行：

~~~bash
.venv/bin/python extensions/foreign_trade/manage.py build
.venv/bin/python extensions/foreign_trade/team.py check
~~~

安装会验证实际设备插件、技能与连接器；技能须启用并完整读取，才能调用对应业务工具。版本冲突先读回记录，不重复创建；模型、网络或检查失败必须明确报告。

完整安装/更新见 [TEAM_SETUP.md](../../docs/TEAM_SETUP.md)，同款关联、人工验收和来源失效规则见 [SCENARIO_THREE.md](../../docs/SCENARIO_THREE.md)。
