# 外贸询盘转报价演示插件

基于公开 HugAgentOS Community Edition `desktop-v1.0.2`，本目录代码和模拟数据独立编写。
**全部产品、价格、规格和生产周期均为虚构演示数据，非真实商业报价。**

## 已实现

- 8 个办公收纳 SKU，支持 SKU、中英文关键词和分类检索。
- `search_products`、`get_product`、`calculate_quote` 三个 MCP 工具。
- 数量阶梯价、MOQ、定制包装门槛与费用、生产周期冲突提示。
- Decimal 确定性计算；金额返回 USD 两位小数字符串。
- 首页“询盘转报价”技能：先查产品事实，再调用计算工具，输出英语回复草稿。
- 运费始终待确认；金额小计明确不含运费及未核定费用。
- 不连接真实商家数据库，不发邮件，不提交订单，不声称完成平台或目标国合规审查。

## 文件

- `catalog.json`：唯一模拟事实来源、目录版本和每个 SKU 的记录引用。
- `engine.py`：标准库业务引擎，无网络、数据库或持久化写入。
- `mcp_server.py`：只监听 `127.0.0.1:9120` 的本机 HTTP MCP。
- `plugin/`：插件清单、技能和工具连接配置。
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
5. 回到首页，点击 **询盘转报价**。
6. 核对真实工具调用记录：search_products、get_product、calculate_quote。
7. 结果应标注 DEMO，列出资料版本、运费待确认及英语回复草稿。

MCP 使用本机回环地址，无 API Key。适用于同机 CLI/Web 环境；若改用 Docker，须配置容器到服务的网络，容器 localhost 不是宿主机。
ZIP 同时包含 runtime/ 下的服务、引擎和目录源码；其他开发者可在相同依赖环境下启动 runtime/mcp_server.py，再导入插件。
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
python extensions/foreign_trade/smoke_test.py
git diff --check
~~~

框架原有许可证及 Powered by 声明保持原样。

## 网页未提供导入入口时的本地安装

使用公开版自身的安装服务，只给指定现有账号添加插件，不创建账号、不改变权限：

~~~bash
python extensions/foreign_trade/install.py --app-home "$HOME/.hugagent-hackathon-public-1.0.2" --username hks
~~~

安装或更新后刷新网页并新建对话。该命令会写入所指定公开实例的插件、技能与连接器记录。

CE 原版隐藏插件贡献的首页快捷卡。本地安装脚本会在现有“首页建议问题”最前面追加一条外贸询盘示例，保留其他建议和设置；插件本身的快捷声明也保留，供支持该入口的宿主使用。

运行中的实例通过 CLI 安装后，可在插件页将本插件关闭再开启以刷新进程内缓存，随后新建对话。输入 `/` 选择“询盘转报价（演示）”可显式携带插件；正式验收须看到技能激活和真实 calculate_quote 回执，不能只以最终文本数字判断成功。

报价工具额外返回 quotation_markdown，表格中的货品单价与每件定制包装费分别列示；effective_unit_price 仅表示两者之和，不能再次叠加包装费。

本公开项目同时修复了上游工具调用 ID 跨轮重复，以及 plugin:local 标识无法恢复下一轮插件组件的问题。多轮演示应使用当前项目源码启动后端，保留对应回归测试。


## 外贸首页与默认助手

本公开分支的首页标题为“外贸询盘，从产品查询到报价”，推荐问题覆盖产品检索、规格与 MOQ、基础报价、阶梯价对比、定制包装和询盘澄清。保留 HugAgentOS 产品名称、图标、Powered by 及原开源许可证。

- 后端默认文案：`src/backend/core/content/content_blocks.py`。
- 前端兜底文案：`src/frontend/src/utils/pageConfigDefaults.ts`，页面组件兜底保持一致。
- 默认助手身份与报价边界：`src/backend/prompts/prompt_text/default/system/00_role.system.md`。
- 当前公开实例的页面配置存于数据库；仅更新默认源码不会覆盖已有配置。首次部署或明确要恢复外贸首页时，可执行：

~~~bash
python extensions/foreign_trade/install.py --app-home "$HOME/.hugagent-hackathon-public-1.0.2" --username hks --apply-homepage-copy
~~~

该选项只替换首页介绍、输入提示与推荐问题；不修改账号权限、导航或开源署名。常规插件更新不带此选项，保留已有首页编辑。前端源码改动后须执行 `VITE_EDITION=ce VITE_DEFAULT_LANGUAGE=zh-CN npm --prefix src/frontend run build` 并刷新网页。

已有实例的默认系统提示词还可能由 `prompt_versions` 的活跃版本或提示词片段覆盖；更新时须通过公开版提示词管理服务同步相应版本，并触发提示词缓存失效。可在上述安装命令追加 `--apply-assistant-prompt`：它会保留原活跃版本，复制其其他片段，仅更新身份、业务事实约束与插件加载步骤，激活 `foreign-trade-demo-v1`。运行中可将“询盘转报价（演示）”插件关闭再开启以热刷新提示词缓存，无需重启或重新登录。旧会话可能保留历史助手介绍，使用新建对话验收。


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

2026-10-21 已在公开实例网页完成：查询 DESK-001 → 同会话报价 1000 件定制包装/西班牙 → 刷新恢复报价卡 → 点击 PDF 与 Excel 下载 → 读取下载文件并渲染核对。对应报价 `DEMO-C5FE4698703080E2`，货值 USD 4800.00、包装费 USD 300.00、不含运费及税费小计 USD 5100.00。PDF 为 1 页中英对照；Excel 两个工作表的数量、单价与总额一致，金额为数字单元格。验证样例与渲染预览保存在忽略的 `.runtime/download-verification/`。

报价计算测试共 35 项、前端导出回归 15 组通过，真实 MCP 同时验证三个报价档位及五类非法输入拒绝。PDF 使用项目现有 html2pdf 浏览器渲染，Excel 使用项目现有 xlsx 库；运行功能不依赖开发机上的文档校验工具。
