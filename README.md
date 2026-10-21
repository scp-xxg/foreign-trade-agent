<!-- Modified by foreign-trade-agent contributors, 2026-10-21: public team distribution. -->
# foreign-trade-agent

面向外贸产品查询与询盘报价的黑客松演示 Agent，基于公开 **HugAgentOS Community Edition desktop-v1.0.2**。仓库名称暂用 `foreign-trade-agent`，页面名称和 Logo 暂保留 HugAgentOS。

**报价目录中的产品、价格和参考生产周期均为虚构演示数据，非真实商业报价。** 场景二另附可核验的真实产品资料和有署名的公开授权照片，两者独立，不混用价格。

## 已实现

- 8 个办公收纳 SKU：中英文检索、产品规格、MOQ 和数量阶梯价。
- “询盘转报价（演示）”插件：产品检索、产品详情、Decimal 报价计算三个 MCP 工具及对应技能。
- 定制包装门槛与费用、交期冲突说明；改量或改包装后重新计算。
- 中英对照 PDF、中文/英文双工作表 Excel 下载；直接使用工具回执，保留来源和稳定报价编号。
- 外贸首页、6 条推荐问题、默认助手提示词、团队部署脚本和自动检查。
- 场景一询盘工作台：买家官网/GLEIF 事实卡、AI 需求建议人工确认、中英回复草稿和跟进待办；内置真实 LYRECO 公开资料配明确标注的演示询盘。[使用与数据边界](docs/SCENARIO_ONE.md)
- 场景二产品内容工作台：上传资料与原图、人工确认事实、生成英文上品资料和客服 FAQ、三种原图排版素材及 ZIP 下载；使用 Raspberry Pi 5 官方规格及 CC BY 4.0 照片演示。[完整流程](docs/SCENARIO_TWO.md) · [公开来源与图片许可](docs/SCENARIO_TWO_SOURCES.md)

## 队友快速部署（Linux / WSL2）

先准备 **Python 3.11+、Node.js 22（至少 22.12）、Git**；推荐 Python 3.11。Node 20.19+ 也满足当前前端要求。Windows 队员请进入 WSL2 Linux 终端执行。

```bash
git clone https://github.com/scp-xxg/foreign-trade-agent.git
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

首次登录进入 **系统设置 → 模型服务 → 添加模型**，填写自己的模型服务地址、API Key、模型名及上下文长度，保存并测试。将对话模型指派给 **主智能体推理 main_agent**，其他使用的对话角色也按页面提示指派。模型须支持工具调用；仓库不附带开发者的模型密钥。

团队入口使用本机 SQLite，报价场景无需 Docker、PostgreSQL、Redis 或外部向量库。首次安装需要网络；老版本 Linux 可能需要 Rust/Cargo 编译依赖，setup 会提前检查。

## 部署后与当前演示一致吗？

| 项目 | 新部署结果 |
|---|---|
| 首页、外贸文案、6 条推荐问题、当前 Logo | 同一版本及初始化配置，保持一致 |
| 模拟目录、报价规则、PDF / Excel 下载卡 | 同一版本保持一致 |
| 询盘工作台、产品内容工作台、公开演示素材 | 同一版本保持一致；每人自行上传和创建演示记录 |
| 询盘转报价（演示）插件 | init 自动安装到你的账号，技能和代码随仓库保留 |
| 账号密码、模型 Key、聊天历史、上传文件 | 每台机器独立，不通过 Git 同步 |
| 模型措辞、速度与推理质量 | 取决于所配模型，金额以计算工具为准 |

**只执行 git clone 不会复制数据库中的安装状态，首次部署必须完成 init。**

## 日常更新

停止自己运行的服务，保存本地改动后执行：

```bash
git pull --ff-only
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python extensions/foreign_trade/team.py install --username YOUR_USERNAME
.venv/bin/python extensions/foreign_trade/team.py start
```

install 更新外贸插件、首页和默认提示词，保留原账号密码与业务库；如果自行改过这些场景配置，更新前先保留自己的版本。完整停止、更新和自检步骤见 [部署指南](docs/TEAM_SETUP.md)。

## 验证

```bash
.venv/bin/python extensions/foreign_trade/team.py check
```

网页验收：先查询 DESK-001，再报价“1000 件、定制包装、目的国西班牙”。预期货值 **USD 4800.00**、包装费 **USD 300.00**、不含运费及税费小计 **USD 5100.00**，并能下载两种报价单。

## 四人协作

main 保持可运行；每项功能独立分支、提交 PR，通过 CI 和队友复核后合并。公开仓库任何人都可拉取；直接推送需所有者添加协作者，也可 Fork 后提交 PR。建议按产品/报价规则、插件与工作流、前端与导出、测试与演示分工。

不要提交模型密钥、数据库、上传文件、日志、.runtime、.venv 或 node_modules。模拟产品可以提交，真实客户询盘和业务资料不进入公开仓库。

## 来源与许可

上游：[ZJU-REAL/HugAgentOS](https://github.com/ZJU-REAL/HugAgentOS)，基线 desktop-v1.0.2，提交 d16a09be1e408c1acf3ef6ff89523cda1341ef41。保留上游 Git 历史、版权和第三方归属。

许可证为 **Apache License 2.0 加补充条款**，完整条件见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。界面保留 Powered by HugAgentOS 署名；白标及受限多租户 SaaS 场景遵循原许可。所有实现基于公开社区版，未使用私有商业版代码。

团队改动见 [CHANGES_FOREIGN_TRADE.md](CHANGES_FOREIGN_TRADE.md)，业务细节见 [外贸插件说明](extensions/foreign_trade/README.md)。上游原始说明保存在 [README_UPSTREAM.md](README_UPSTREAM.md) 和 [README_CN_UPSTREAM.md](README_CN_UPSTREAM.md)；其中的上游安装地址不会安装本项目，请以本页步骤为准。
