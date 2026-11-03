# SailAgent

**一条询盘，跑通销售与运营两个业务流程。**

SailAgent 是面向外贸出海团队的开源协作助手：输入客户询盘、商品资料与企业知识，用中文对话完成核验、报价、英文回复、商品资料与平台草稿的生成、审核、修改和文件交付。销售、采购跟单、商品运营三个岗位围绕同一份事实协作，工作台负责查看和编辑记录。

基于 [HugAgentOS](https://github.com/ZJU-REAL/HugAgentOS) 社区版构建，界面保留 Powered by HugAgentOS 开源署名。

## 能力

| 流程 | 输入与操作 | 产出 |
|---|---|---|
| **销售** | 核对买家公开资料 → 查询商品并计算报价 → Alibaba RFQ 英文回复 → 两轮审核修改 → 站内跟进待办 | 中英 PDF、双语 Excel、回复草稿、跟进待办 |
| **同款接力** | 沿用同一条询盘与 SKU → 确认产品事实 → 关联资料包 → 分配运营任务 | 共享的询盘编号、报价编号、资料包编号与版本 |
| **运营** | 英文文案与 FAQ → 原图或示意图排版 → Amazon US Listing 草稿 → 审核修改 | 英文资料、三种比例图片、ZIP 素材包、审核报告 |

- 数量、包装或事实变更后重新计算与生成，旧版本自动失效；复审展示前后差异，下载前校验来源与当前账号权限。
- 价格使用 Decimal 确定性计算；运费、税费、付款条件、贸易术语等未知项保持未知，不自动补全。
- 合规检查同时给出文字批注与颜色风险标记，并保留官方来源、适用范围与核验日期。它是辅助检查，不是认证、平台批准或完整法律审查。
- 结果不会自动发送客户消息、上传平台或发布商品。

## 快速开始

需要 Git、Docker 与 Docker Compose v2，建议 8 GB 内存、15 GB 磁盘，首次构建需要联网。

```bash
git clone https://github.com/scp-xxg/sailagent.git
cd sailagent
./start.sh
```

Windows PowerShell 可直接运行同一条 Compose 命令：

```powershell
docker compose -f compose.sailagent.yml run --build --rm --service-ports sailagent
```

首次启动按终端提示创建**自己的用户名和密码**，完成后打开 <http://127.0.0.1:3002>。再次启动沿用持久卷中的数据；端口被占用时用 `SAILAGENT_PORT=3012 ./start.sh`。账号、模型密钥、上传资料与聊天记录都不随 Git 同步。

首次登录后进入 **设置 → 模型服务**，添加支持工具调用的模型，测试通过后指派 `main_agent`。没有可用模型时，工作台仍可执行商品查询、确定性报价、本地模板资料与规则审核；自然语言多轮对话与子智能体需要模型服务。

后台运行、更新、备份、端口与原生 Python 部署见 [部署指南](docs/ONE_COMMAND_DEPLOY.md)。

## 使用

销售与运营两条流程的完整操作步骤、可复制的对话指令和下载核对点见 [使用指南](docs/USAGE.md)。建议从模拟询盘 `DESK-001`、500 件、标准包装、Spain 开始，第二轮改为 1000 件定制包装，小计应为 **USD 5100.00（不含运费与税费）**。

`DESK-001` 等商品目录、价格与示例询盘均明确标记为模拟；买家公开资料保留来源、获取时间与未知项，不据此推断信用或采购意向。企业私有知识按账号授权读取，敏感词库使用"原文检索 + 生成后匹配"，见 [敏感词说明](docs/SENSITIVE_TERMS.md) 与 [私有知识库](docs/PRIVATE_KNOWLEDGE.md)。

## 项目结构

```
src/backend                后端服务：账号、会话、编排、知识库、插件与原生业务工具
src/frontend               Web 界面（React + Vite），构建产物由后端托管
extensions/foreign_trade   SailAgent 业务层：三个岗位、12 个原生工具、技能插件与模拟目录
extensions/blender         可选：Blender MCP（本地 3D 建模）
extensions/tripo           可选：Tripo 云端 3D 生成
packages/                  前端依赖的本地工作区包（chat-sdk、workbench 等）
docker/                    镜像与本地部署文件
docs/                      部署、使用、岗位、流程与合规说明
document/                  双语产品文档（中/英）
tests/                     业务回归测试
```

## 文档

- 部署：[一键部署](docs/ONE_COMMAND_DEPLOY.md) · [原生 Python 安装与升级](docs/TEAM_SETUP.md)
- 使用：[使用指南](docs/USAGE.md) · [场景一](docs/SCENARIO_ONE.md) · [场景二](docs/SCENARIO_TWO.md) · [场景三](docs/SCENARIO_THREE.md)
- 岗位与技能：[三个核心岗位](docs/CORE_ROLE_AGENTS.md) · [对话插件](docs/CHAT_PLUGIN.md)
- 流程：[获客](docs/ACQUISITION_WORKFLOW.md) · [背调](docs/DILIGENCE_WORKFLOW.md) · [沟通](docs/COMMUNICATION_WORKFLOW.md) · [跟进](docs/FOLLOWUP_WORKFLOW.md) · [采购](docs/PROCUREMENT_WORKFLOW.md) · [谈单](docs/NEGOTIATION_WORKFLOW.md) · [成交](docs/CLOSING_WORKFLOW.md) · [发品](docs/LISTING_PREPARATION.md) · [复盘](docs/RETROSPECTIVE_WORKFLOW.md)
- 品牌与扩展：[品牌与素材](docs/SAILAGENT_BRAND.md) · [Blender MCP](docs/BLENDER_MCP.md) · [Tripo 3D](docs/TRIPO_3D.md) · [智能体上架审核](docs/AGENT_MARKET_REVIEW.md)

## 开发与测试

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install --no-deps -e .
python -m pytest tests -q                     # 业务回归：离线，不需要模型与网络
npm --prefix src/frontend ci && npm --prefix src/frontend run build
```

业务改动放在 `extensions/foreign_trade`，界面导出放在前端对应模块。改动后请确认业务回归与前端构建都通过，详见 [贡献指南](CONTRIBUTING.md)。

## 开源与许可

本项目是 HugAgentOS 社区版的公开衍生项目，保留上游开源署名、Git 历史与版权信息。完整许可见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)（Apache License 2.0 及补充条款）。SailAgent 是此衍生项目的品牌，不代表 HugAgentOS 官方产品。

随仓库提供的商品目录、价格、图片与示例询盘为模拟或已授权素材，不代表实际订单、供货承诺或品牌经销授权。
