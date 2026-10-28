# 外贸业务助手（演示）插件

基于公开 HugAgentOS Community Edition，本目录的外贸业务代码和模拟数据独立编写；上游同步范围见项目变更记录。
**报价目录中的产品、价格、规格和生产周期均为模拟数据。** 买家核验使用真实公开资料，商品资料示例使用可核验规格和独立许可照片；这三类来源分别标注。

版本 **0.3.0**，安装标识保留 `foreign-trade-demo`。提供四个技能、七个当前用户绑定的原生业务工具；原有三个目录 MCP 工具继续独立保留。聊天为业务主入口，询盘、产品内容和协同工作台显示同一账号的记录。[对话指南](../../docs/CHAT_PLUGIN.md) · [团队部署与更新](../../docs/TEAM_SETUP.md) · [场景三完整示例](../../docs/SCENARIO_THREE.md)

## 已实现

- 8 个办公收纳 SKU，支持 SKU、中英文关键词和分类检索。
- `search_products`、`get_product`、`calculate_quote` 三个 MCP 工具。
- 数量阶梯价、MOQ、定制包装门槛与费用、生产周期冲突提示。
- Decimal 确定性计算；金额返回 USD 两位小数字符串。
- 四个技能：`inquiry-quote`、`buyer-inquiry-followup`、`product-content`、`cross-role-collaboration`。
- 当前用户绑定的询盘、报价和产品内容原生工具复用已有工作台服务；不把身份参数交给模型。
- 常见单 SKU 保存、聊天附件导入和候选事实确认使用显式字段工具，复杂编辑保留通用入口；只有成功工具回执才代表操作完成。
- 运费始终待确认；金额小计明确不含运费及未核定费用。
- 通过公开官网/GLEIF核验买家事实；产品内容可导入当前聊天的用户附件，确认后生成。未连接企业私有 ERP。
- 当前账号下的业务、采购、美工、运营、合规协同：六项任务记录负责人标签、必需依赖、状态、结果依据、风险与未确认事项。
- 人工确认事实与逐任务审核分别执行；来源变化使相关任务和下游验收失效，全部有效审核后可下载 Markdown/JSON 内部交接稿。
- 不发邮件，不提交订单，不发布商品，不声称完成平台或目标国合规审查。

## 四个技能与七个原生工具

| 技能 | 业务范围 | 主要工具 |
|---|---|---|
| `inquiry-quote` | 即时模拟目录查询与报价 | 原有 `search_products`、`get_product`、`calculate_quote` MCP |
| `buyer-inquiry-followup` | 保存询盘、公开买家核验、报价、草稿与站内跟进 | `trade_save_inquiry`、`trade_inquiry`、`trade_calculate_quote` |
| `product-content` | 导入附件、确认事实、生成文案/FAQ/图片资料 | `trade_import_product`、`trade_confirm_product_facts`、`trade_product_content` |
| `cross-role-collaboration` | 岗位任务、依赖、人工审核、内部交接 | `trade_collaboration` |

七个原生工具由本公开分支后端按当前认证会话绑定身份，不接受模型指定 owner。它们不由 9120 端口的 MCP 提供，也不意味着产品已发信、上架或通知负责人。负责人姓名是当前账号中的业务标签，不构成多人权限系统。

## 场景三：同一模拟订单协同

以 LYRECO 的公开公司资料作为核验示例，团队构造“DESK-001、500 件、标准包装、交付 Spain”的模拟询盘。保存和报价后，用 `trade_collaboration(action="create")` 关联该询盘，建立五个岗位的六项任务。此案例不代表 LYRECO 的真实订单或合作关系。

当前自动准备仅支持单一 DESK-001 产品行：导入目录模拟规格和程序绘制的几何示意 PNG，保留来源声明与 SHA256；创建时只有候选事实，仍需用户看过摘要后确认，再用产品内容工具生成。几何示意图不是真实产品照片。其他 SKU、多 SKU 可关闭 `prepare_catalog_content`，之后用 `link_content` 关联已有资料包。

`transaction` 只接受同一模拟 SKU 的目录绑定资料。Raspberry Pi 5 等真实外部产品只能设为 `independent_reference`，不能成为 DESK 的规格依据或套用 DESK 价格。来源不匹配时服务端拒绝交易关联。

六项任务依次为需求确认、采购报价、图片素材、商品文案/FAQ、合规表述检查和内部交接。用户先填写负责人、结果与未确认项，提交 `in_review`；在看到当前材料和验收条件后明确确认，助手才调用 `review`。不能直接设置 `done`，不能移除必需依赖。真实未确认项可以保留在经用户审阅的内部交接稿中，不用删空未知项来获得完成状态。

修改询盘条件、报价、确认事实或图片输出后，相关任务及下游显示失效；`refresh_sources` 接受新版依据但不会重新完成审核。`link_content` 也会清掉受影响的旧验收。下载先核对当前版本，旧修订或并发更新返回 409，不替换成新版本的审核稿。逐步操作、参数和 HTTP 契约见 [SCENARIO_THREE.md](../../docs/SCENARIO_THREE.md)。

## 文件

- `catalog.json`：唯一模拟事实来源、目录版本和每个 SKU 的记录引用。
- `engine.py`：标准库业务引擎，无网络、数据库或持久化写入。
- `mcp_server.py`：只监听 `127.0.0.1:9120` 的本机 HTTP MCP。
- `plugin/`：插件清单、技能和工具连接配置。
- `demo_product/`：Raspberry Pi 独立公开示例，以及 DESK-001 模拟规格、几何示意图和来源校验清单。
- `manage.py`：启动、状态、停止及 ZIP 打包。
- `smoke_test.py`：真实 MCP 协议验证。
- `../../tests/test_foreign_trade_engine.py`：离线计算和边界测试。

## 启动与打包

在公开项目根目录执行：

~~~bash
source .venv/bin/activate
python extensions/foreign_trade/manage.py start
python extensions/foreign_trade/smoke_test.py
python extensions/foreign_trade/manage.py build
~~~

启动和打包可重复运行。修改数据或服务代码后，先执行 `manage.py stop`，再执行 `manage.py start`。
PID 和日志位于 `.runtime/`，生成包位于 `dist/`，均已加入本目录 `.gitignore`。

## 接入 HugAgentOS

1. 保持 HugAgentOS 后端运行，并完成模型配置。
2. 当前账号打开 **能力中心 → 插件 → 添加插件 → 导入插件包（zip）**。
3. 选择 `extensions/foreign_trade/dist/foreign-trade-demo.zip`。
4. 确认技能与“外贸产品与报价（演示）”连接器已启用。
5. 新建聊天，输入 / 选择 **外贸业务助手（演示）**，或直接描述外贸业务请求。
6. 核对真实工具调用记录：search_products、get_product、calculate_quote。
7. 结果应标注 DEMO，列出资料版本、运费待确认及英语回复草稿。

MCP 使用本机回环地址，无 API Key。适用于同机 CLI/Web 环境；若改用 Docker，须配置容器到服务的网络，容器 localhost 不是宿主机。
ZIP 同时包含 runtime/ 下的原报价服务、引擎和目录源码，以及四个技能、宿主依赖说明和对话指南。独立运行 runtime/mcp_server.py 仍只提供原三个模拟报价工具；七个原生业务工具依赖本公开项目的配套后端、认证和前端，ZIP 不能单独给未修改的上游实例安装完整能力。宿主端的 `foreign_trade` 包还须包含 `demo_product/` 资源。
部署前确认 9120 端口未被其他服务占用；管理脚本不会停止不属于本项目的进程。

## 验收案例

| 输入 | 预期 |
|---|---|
| DESK-001，500 件，标准包装，西班牙 | 货值 USD 2400.00，包装费 0.00，运费待确认 |
| 改为 2000 件 | 重新计算，货值 USD 8400.00 |
| DESK-001，1000 件，定制包装 | 货值 4800.00，包装费 300.00，小计 USD 5100.00 |
| DESK-001，99 件 | MOQ 校验失败，data=null，不输出部分报价 |
| 未提供数量 | 技能先询问数量，不用 MOQ 代替数量 |

每次修改数量、包装或交期，技能须重新调用计算工具。requested_lead_days 指期望生产天数，不是到货日期。
金额、数量、错误和来源以工具 JSON 为准，模型说明只是草稿。

## 测试

~~~bash
python -m unittest discover -s tests -p "test_foreign_trade*.py" -v
HUGAGENT_SKIP_ENV_FILES=1 python -m pytest tests/test_foreign_trade_collaboration.py tests/test_trade_plugin_tools.py tests/test_trade_plugin_end_to_end.py -q
python extensions/foreign_trade/smoke_test.py
git diff --check
~~~

框架原有许可证及 Powered by 声明保持原样。

## 网页未提供导入入口时的本地安装

使用公开版自身的安装服务，只给指定现有账号添加插件，不创建账号、不改变权限：

~~~bash
python extensions/foreign_trade/install.py --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME
~~~

安装或更新后刷新网页并新建对话。该命令会写入所指定公开实例的插件、技能与连接器记录。

CE 原版隐藏插件贡献的首页快捷卡。本地安装脚本会在现有“首页建议问题”最前面追加一条外贸询盘示例，保留其他建议和设置；插件本身的快捷声明也保留，供支持该入口的宿主使用。

运行中的实例通过 CLI 安装后，可在插件页将本插件关闭再开启以刷新进程内缓存，随后新建对话。输入 `/` 选择“外贸业务助手（演示）”可显式携带插件；正式验收须看到技能激活和真实 calculate_quote 回执，不能只以最终文本数字判断成功。

报价工具额外返回 quotation_markdown，表格中的货品单价与每件定制包装费分别列示；effective_unit_price 仅表示两者之和，不能再次叠加包装费。

当前分支按上游工具装配与插件身份接口接入原生业务工具，并保留多轮身份恢复和工具调用回归。多轮演示应使用当前项目源码及其匹配的依赖启动后端。


## 外贸首页与默认助手

本公开分支的首页与默认助手以外贸业务为定位，支持产品查询、询盘报价、买家核验与跟进、商品资料制作，以及岗位协同与内部交接。保留 HugAgentOS 产品名称、图标、Powered by 及原开源许可证。

- 后端默认文案：`src/backend/core/files/content/content_blocks_constants.py`。
- 前端兜底文案：`src/frontend/src/utils/pageConfigDefaults.ts`，页面组件兜底保持一致。
- 默认助手身份与报价边界：`src/backend/prompts/prompt_text/default/system/00_role.system.md`。
- 当前公开实例的页面配置存于数据库；仅更新默认源码不会覆盖已有配置。首次部署或明确要恢复外贸首页时，可执行：

~~~bash
python extensions/foreign_trade/install.py --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME --apply-homepage-copy
~~~

该选项只替换首页介绍、输入提示与推荐问题；不修改账号权限、导航或开源署名。常规插件更新不带此选项，保留已有首页编辑。前端源码改动后须执行 `VITE_EDITION=ce VITE_DEFAULT_LANGUAGE=zh-CN npm --prefix src/frontend run build` 并刷新网页。

已有实例的默认系统提示词还可能由 `prompt_versions` 的活跃版本或提示词片段覆盖；更新时须通过公开版提示词管理服务同步相应版本，并触发提示词缓存失效。可在上述安装命令追加 `--apply-assistant-prompt`：它会保留原活跃版本，复制其其他片段，仅更新身份、业务事实约束与插件加载步骤，激活带内容摘要的 `foreign-trade-demo-v3-*` 版本。若既有同名版本后来被人工编辑，安装器另建版本保留该编辑。仅更新插件说明/提示词时可关闭再开启“外贸业务助手（演示）”刷新缓存；新增后端原生工具代码后需重启本公开实例。旧会话可能保留历史助手介绍，使用新建对话验收。


## 中英文报价单下载

成功报价下方提供独立下载卡，可下载中英对照 PDF 和含“中文报价单 / English Quotation”两个工作表的 Excel。导出基于实际 `calculate_quote` 回执，不提取模型的 Markdown 表格；同一报价编号对应同一份计算快照。原对话记录的 PDF 按钮继续用于整段聊天记录，与报价单下载分开。

1. 从首页查询产品规格与 MOQ。
2. 明确 SKU、件数、包装和目的国，要求报价。
3. 在该轮回复下方核对 DEMO 编号和小计，分别点击两个下载按钮。
4. 打开 PDF 检查中英文金额和条件；打开 Excel 检查两个语言工作表。
5. 修改数量或包装后必须重新计算，并使用新一轮编号下载。Excel 中金额是固定快照，不是可编辑询价计算器。

只有带 `document_type=foreign_trade_quote`、`document_version=1` 的成功回执可导出；错误/截断/金额不一致的结果不会生成下载卡。旧历史没有此契约时，重新报价即可。刷新后被裁剪的工具结果通过“加载报价单下载选项”按需读取，沿用现有会话访问校验。文件在浏览器本地生成，无新增公开下载服务或外部上传。

修改引擎后须重启本目录 MCP 服务；修改前端后须构建并刷新网页。默认保留原开源署名及许可证。


### 导出回归与网页验收

~~~bash
python -m unittest discover -s tests -p "test_foreign_trade*.py" -v
python extensions/foreign_trade/smoke_test.py
npm --prefix src/frontend run test:foreign-trade-quote
VITE_EDITION=ce VITE_DEFAULT_LANGUAGE=zh-CN npm --prefix src/frontend run build
~~~

网页验收应实际完成查询、同会话报价、刷新恢复、下载和文件内容核对；场景三还需验证人工审核、内部交接下载与改单失效。CI 和现场验收结果以相应验收记录为准，此说明不证明当前部署已经通过验收。PDF 使用项目现有 html2pdf 浏览器渲染，Excel 使用项目现有 xlsx 库；运行功能不依赖开发机上的文档校验工具。
