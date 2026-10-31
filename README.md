<!-- Modified by foreign-trade-agent contributors, 2026-10-21: public team distribution. -->
# foreign-trade-agent

面向外贸询盘、商品资料和跨岗位协同的演示 Agent，最初基于公开 HugAgentOS Community Edition desktop-v1.0.2，现同步上游 **2026-10-27 main（d969492f）**。仓库名称暂用 `foreign-trade-agent`，页面名称和 Logo 暂保留 HugAgentOS。

**报价目录中的产品、价格和参考生产周期均为虚构演示数据，非真实商业报价。** 场景二另附可核验的真实产品资料和有署名的公开授权照片，两者独立，不混用价格。

参赛演示与六项要求的对应关系见 [赛题完整演示手册](docs/HACKATHON_DEMO.md)；包含两平台/角色、规则知识、两种反馈及两轮修改脚本。

## 已实现

- 8 个办公收纳 SKU：中英文检索、产品规格、MOQ 和数量阶梯价。
- “外贸业务助手（演示）”插件 0.4.0：五个技能覆盖即时查询报价、买家询盘跟进、产品内容、跨岗位协同、本地化与规则校验；包含八个会话绑定业务工具，另保留三个目录/报价 MCP 工具。以对话为主入口，复用工作台。[对话使用与升级](docs/CHAT_PLUGIN.md)
- 定制包装门槛与费用、交期冲突说明；改量或改包装后重新计算。
- 中英对照 PDF、中文/英文双工作表 Excel 下载；直接使用工具回执，保留来源和稳定报价编号。
- 外贸首页、6 条推荐问题、默认助手提示词、团队部署脚本和自动检查。
- 场景一询盘工作台：买家官网/GLEIF 事实卡、AI 需求建议人工确认、中英回复草稿和跟进待办；内置真实 LYRECO 公开资料配明确标注的演示询盘。[使用与数据边界](docs/SCENARIO_ONE.md)
- 场景二产品内容工作台：上传资料与原图、人工确认事实、生成英文上品资料和客服 FAQ、三种原图排版素材及 ZIP 下载；使用 Raspberry Pi 5 官方规格及 CC BY 4.0 照片演示。[完整流程](docs/SCENARIO_TWO.md) · [公开来源与图片许可](docs/SCENARIO_TWO_SOURCES.md)

- 场景三：同一模拟订单下的业务、采购、美工、运营和合规协同任务；来源版本变化会使相关验收失效，人工审核后下载内部交接稿。[流程与边界](docs/SCENARIO_THREE.md)

- 本地化与规则审核：基于真实保存的询盘或确认产品资料，生成阿里RFQ销售回复/Amazon US Listing草稿，检索带官方来源与版本的知识规则，检查平台要求及报价条款，保存文字批注、风险标记、两轮差异和MD/JSON审阅报告。未发现问题不代表全量合规或平台批准。

[2026-10-31 实际验收记录](docs/ACCEPTANCE_20261031.md) 区分真实模型、浏览器下载、API与单元测试；[2026-10-28 验收记录](docs/ACCEPTANCE_20261028.md) 保留为历史证据。[完整问答脚本](docs/HACKATHON_DEMO.md) 是预期行为，不是已通过记录。模型服务不可用时，产品工作台可明确选择“本地原文模板（不调用模型）”，整理已经确认的英文事实；对话编排仍需可用模型。

## 队友快速部署（Linux / WSL2）

团队统一从 `main` 获取公开版本，无需切换历史功能分支。首次部署见 [队友部署指南](docs/TEAM_SETUP.md)，现场操作见 [三个场景逐步演示](docs/DEMO_WALKTHROUGH.md)。

先准备 **Python 3.11+（内置 SQLite ≥ 3.38）、Node.js 22（至少 22.12）、Git**；推荐 Python 3.11。Node 20.19+ 也满足当前前端要求。Windows 队员请进入 WSL2 Linux 终端执行。

```bash
git clone --branch main https://github.com/scp-xxg/foreign-trade-agent.git
cd foreign-trade-agent
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python extensions/foreign_trade/team.py init
.venv/bin/python extensions/foreign_trade/team.py start
```

如果本机 `python3` 已是 3.11+，可替换上面的 `python3.11`。Ubuntu 22.04 默认 Python 3.10 不满足要求，准备方法见 [队友部署指南](docs/TEAM_SETUP.md)。

- `setup`：检查依赖、创建虚拟环境、安装后端、锁定前端依赖并构建中文 CE 页面。
- `init`：设置自己的登录账号和密码，安装外贸插件并应用首页和提示词。
- `start`：启动本机外贸 MCP 和网页服务，保持终端打开。

默认地址 **http://127.0.0.1:3001**；个人数据位于 `~/.foreign-trade-agent`。

本机演示若用 **3002** 避开其他服务，新的默认目录实例在启动时加 `--port 3002`；已有实例必须保留原数据目录：

```bash
TRADE_APP_HOME="/absolute/path/to/your/existing-app-home"
test -f "$TRADE_APP_HOME/data.db" && \
  .venv/bin/python extensions/foreign_trade/team.py start --app-home "$TRADE_APP_HOME" --port 3002
```

打开 <http://127.0.0.1:3002>，在另一个终端设置同一 `TRADE_APP_HOME` 后执行 `.venv/bin/python extensions/foreign_trade/team.py check --app-home "$TRADE_APP_HOME" --port 3002 --running`。也可选择其他空闲网页端口；沙箱 8900 和报价 MCP 9120 保持不变。不要停止占用 3001 的其他容器，不要用重新 init 解决端口冲突。

暂不配置模型也可登录并按 [演示手册](docs/DEMO_WALKTHROUGH.md) 完成三条工作台流程。产品资料生成须明确选择“本地原文模板（不调用模型）”，使用已确认的英文事实。

需要聊天编排或 AI 翻译时，再进入 **系统设置 → 模型服务 → 添加模型**，填写自己的模型服务地址、API Key、模型名及上下文长度，保存并测试。兼容模型在未显式指定传输协议时会于保存阶段尝试自动探测协议及工具结果回传；探测不明确不等于成功。将对话模型指派给 **主智能体推理 main_agent**，其他使用的对话角色也按页面提示指派。模型须支持工具调用；仓库不附带开发者的模型密钥。

维护者这条网关的连通性配置示例是 `gpt-6.1-sol`、`Responses`、`context_length=128000`。128000 是本次采用的保守工作窗口，**不是第三方网关的最大容量承诺**，不按模型名字推断其他服务的上限。队友须验证自己服务的协议、窗口及真实工具往返；操作说明和排错见 [部署指南](docs/TEAM_SETUP.md#4-启动与配置模型)。

本地模板生成本身不调用模型，但通过聊天发起它仍需要聊天模型；完全无模型时从工作台操作。公开买家核验需要联网，图片只是授权原图排版，不是 AI 生图。

团队入口使用本机 SQLite，报价场景无需 Docker、PostgreSQL、Redis 或外部向量库。首次安装需要网络；老版本 Linux 可能需要 Rust/Cargo 编译依赖，setup 会提前检查。

## 部署后与当前演示一致吗？

| 项目 | 新部署结果 |
|---|---|
| 首页、外贸文案、6 条推荐问题、当前 Logo | 同一版本及初始化配置，保持一致 |
| 模拟目录、报价规则、PDF / Excel 下载卡 | 同一版本保持一致 |
| 询盘、产品内容、跨岗位协同工作台及公开演示素材 | 同一版本保持一致；每人自行上传和创建演示记录 |
| 外贸业务助手（演示）插件 | init 安装五个技能、八个会话绑定业务工具；另有三个目录/报价 MCP 工具 |
| 账号密码、模型 Key、聊天历史、上传文件 | 每台机器独立，不通过 Git 同步 |
| 模型措辞、速度与推理质量 | 取决于所配模型，金额以计算工具为准 |

**只执行 git clone 不会复制数据库中的安装状态，首次部署必须完成 init。**

## 日常更新

**首次从旧版公共实例升级时，先走 [部署指南](docs/TEAM_SETUP.md) 的旧库升级路径，不能先运行下面的通用 install。** 旧库所需的协议兼容参数必须在第一次迁移前确认；以下简版适用于已完成该迁移的实例。

下面简版仅适用于团队默认数据目录 `~/.foreign-trade-agent`；已有实例使用其他目录时，先按 [部署指南](docs/TEAM_SETUP.md) 核对并给所有数据命令传入同一个 `--app-home`。

停止自己运行的网页及 MCP，提交或另存本地改动后执行。旧数据升级会在自己的 app-home 下建立 SQLite 回滚快照，不复制其他队员的账号与模型配置。升级说明见 [2026-10-28 上游同步](docs/UPSTREAM_SYNC_20261028.md)。

```bash
git fetch origin
git switch main
git pull --ff-only origin main
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python extensions/foreign_trade/team.py install --username YOUR_USERNAME
.venv/bin/python extensions/foreign_trade/team.py start
```

install 更新外贸插件、首页和默认提示词，保留原账号密码与业务库；如果自行改过这些场景配置，更新前先保留自己的版本。完整停止、更新和自检步骤见 [部署指南](docs/TEAM_SETUP.md)。

## 验证

```bash
.venv/bin/python extensions/foreign_trade/team.py check
```

无可用模型时按 [演示手册](docs/DEMO_WALKTHROUGH.md) 从工作台操作；聊天验收需另外配置并验证模型。

报价验收：先查询 DESK-001，再报价“1000 件、定制包装、目的国西班牙”。预期货值 **USD 4800.00**、包装费 **USD 300.00**、不含运费及税费小计 **USD 5100.00**，并能下载两种报价单。

## 四人协作

main 保持可运行；每项功能独立分支、提交 PR，通过 CI 和队友复核后合并。公开仓库任何人都可拉取；直接推送需所有者添加协作者，也可 Fork 后提交 PR。建议按产品/报价规则、插件与工作流、前端与导出、测试与演示分工。

不要提交模型密钥、数据库、上传文件、日志、.runtime、.venv 或 node_modules。模拟产品可以提交，真实客户询盘和业务资料不进入公开仓库。

## 来源与许可

上游：[ZJU-REAL/HugAgentOS](https://github.com/ZJU-REAL/HugAgentOS)，原基线 desktop-v1.0.2（d16a09be），当前上游同步点 d969492ffb77819a48b34d948b1993a4fc99809b。保留上游 Git 历史、版权和第三方归属。

许可证为 **Apache License 2.0 加补充条款**，完整条件见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。界面保留 Powered by HugAgentOS 署名；白标及受限多租户 SaaS 场景遵循原许可。所有实现基于公开社区版，未使用私有商业版代码。

团队改动见 [CHANGES_FOREIGN_TRADE.md](CHANGES_FOREIGN_TRADE.md)，业务细节见 [外贸插件说明](extensions/foreign_trade/README.md)。上游原始说明保存在 [README_UPSTREAM.md](README_UPSTREAM.md) 和 [README_CN_UPSTREAM.md](README_CN_UPSTREAM.md)；其中的上游安装地址不会安装本项目，请以本页步骤为准。
