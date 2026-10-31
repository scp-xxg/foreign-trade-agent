# 队友部署、模型配置与代码同步

本指南针对团队公开仓库的 Linux / WSL2 本机部署。团队统一使用本仓库的 `main`，无需切换历史 PR 或功能分支。品牌保留 HugAgentOS；仓库名为 foreign-trade-agent。上游原始说明见 [README_UPSTREAM.md](../README_UPSTREAM.md)，安装外贸功能请使用本指南的团队脚本。

首次部署按第 2—5 节执行 `clone main → setup → init → start → check`；已有账号和数据按第 6—7 节更新，不能靠换目录或重新 `init` 来代替升级。

## 1. 准备环境

推荐 Ubuntu 22.04 / 24.04（Windows 使用 WSL2）、Python 3.11+、Node.js 22 LTS、Git。Python 所链接的 SQLite 还必须达到 3.38。建议至少 8 GB 可用内存和足够的依赖下载空间。

```bash
python3.11 -c 'import sys, sqlite3; print("Python", sys.version.split()[0], "SQLite", sqlite3.sqlite_version); assert sys.version_info >= (3, 11); assert sqlite3.sqlite_version_info >= (3, 38, 0)'
node --version
npm --version
git --version
```

Node 支持 20.19+（20.x）或 22.12+，推荐 22 LTS。Ubuntu 22.04 自带 Python 3.10，不能直接用它执行 setup。下文以 `python3.11` 为例，也可替换成检查合格的 `python3.12`；Conda 激活后可用 `python`。如果已有 Conda，可以单独准备环境：

```bash
conda create -n foreign-trade python=3.12 -y
conda activate foreign-trade
python -c 'import sys, sqlite3; print("Python", sys.version.split()[0], "SQLite", sqlite3.sqlite_version); assert sys.version_info >= (3, 11); assert sqlite3.sqlite_version_info >= (3, 38, 0)'
```

如果已有 nvm，可以安装 Node 22：

```bash
nvm install 22
nvm use 22
```

没有这些工具时，先按 [Python](https://www.python.org/downloads/)、[Node.js](https://nodejs.org/en/download) 官方说明准备。老版本 Linux 的 ripgrep 依赖可能需要编译；setup 检查到缺少 Cargo 时，按 [Rust 官方安装说明](https://rustup.rs/) 安装后重新打开终端。受限 bash 沙箱可选依赖：`sudo apt install bubblewrap`。产品检索和确定性报价本身不使用 bash 工具。

## 2. 拉取和安装

```bash
git clone --branch main https://github.com/scp-xxg/foreign-trade-agent.git
cd foreign-trade-agent
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python -c 'import sys, sqlite3; print("Python", sys.version.split()[0], "SQLite", sqlite3.sqlite_version); assert sys.version_info >= (3, 11); assert sqlite3.sqlite_version_info >= (3, 38, 0)'
```

Conda 环境中的 Python/SQLite 已满足要求时，也可用 `python extensions/foreign_trade/team.py setup`。

setup 会创建或更新本仓库 `.venv`、安装 requirements.txt 和 editable 项目，用 package-lock.json 执行 npm ci，并构建中文 CE 前端。它不创建账号，也不完成首页和插件初始化；仅拉取源码、构建前端还不能得到完整外贸首页。不要另外执行上游 curl 安装器，否则会安装原始 HugAgentOS 而非本仓库。

## 3. 创建自己的实例和安装插件

```bash
.venv/bin/python extensions/foreign_trade/team.py init
```

首次部署默认使用 **`~/.foreign-trade-agent`**。若你已在维护一个实例，请跳到第 6 节，不要用新目录代替已有目录。在终端输入自己的用户名和密码；密码仅在终端隐藏输入，不作为命令参数、环境变量或文件保存，也不提交 Git。初始化会：

1. 在 `~/.foreign-trade-agent` 创建独立 SQLite 和本机文件目录。
2. 创建本机账号，应用外贸首页、推荐问题和外贸助手提示词。
3. 将“外贸业务助手（演示）”0.4.0 安装到该账号，包含五个技能、八个会话绑定业务工具，另保留三个目录/报价 MCP 工具。

五个技能为 `inquiry-quote`、`buyer-inquiry-followup`、`product-content`、`cross-role-collaboration`、`localization-review`。八个业务工具为 `trade_save_inquiry`、`trade_import_product`、`trade_confirm_product_facts`、`trade_inquiry`、`trade_calculate_quote`、`trade_product_content`、`trade_collaboration`、`trade_review`。三个 MCP 工具为 `search_products`、`get_product`、`calculate_quote`。原生业务工具需要本公开宿主的注册和当前用户身份，单独导入 ZIP 不会给未适配的上游安装这些能力。

同名账号已存在时，init 保留密码和权限。数据目录已有其他账号时，不会额外创建管理员；已有实例更新应使用正确目录和已有用户名执行 `install`。

团队脚本不继承其他项目的 HUGAGENT_HOME，并跳过仓库 `.env`。首次部署若选择自定义目录，从 init 开始，后续每条命令都传同一个 `--app-home`。已有实例则先确认原目录和数据库，只执行 install：

```bash
TRADE_APP_HOME="/absolute/path/to/your/existing-app-home"
test -f "$TRADE_APP_HOME/data.db"
# 路径检查成功，并按第 6—7 节完成停服务、更新和必要升级后：
.venv/bin/python extensions/foreign_trade/team.py install --app-home "$TRADE_APP_HOME" --username YOUR_EXISTING_USERNAME
.venv/bin/python extensions/foreign_trade/team.py start --app-home "$TRADE_APP_HOME"
```

路径检查失败就停止核对；不要用 `init` 或 `upgrade.py --allow-create` 补一个空库。不要把开发者的数据库或模型配置文件复制给队友。

## 4. 启动与配置模型

```bash
.venv/bin/python extensions/foreign_trade/team.py start
```

浏览器打开 http://127.0.0.1:3001，用自己的账号登录。网页/API 默认使用 3001，可用 `--port` 指定；沙箱仍使用 8900，外贸 MCP 仍使用 9120。脚本拒绝占用所选端口的其他服务，不会停止或接管它们。

**3001 已被其他容器或服务占用时，不要停止对方。** 确认 3002 空闲、原公开实例已停止后，使用原数据目录启动：

```bash
TRADE_APP_HOME="/absolute/path/to/your/existing-app-home"
test -f "$TRADE_APP_HOME/data.db" && \
  .venv/bin/python extensions/foreign_trade/team.py start --app-home "$TRADE_APP_HOME" --port 3002
```

此时打开 <http://127.0.0.1:3002>。另一个终端设置同一 `TRADE_APP_HOME` 后，运行：

```bash
.venv/bin/python extensions/foreign_trade/team.py check --app-home "$TRADE_APP_HOME" --port 3002 --running
```

后续 start/check 都带同一 `--port`，另选环境时也继续带原 `--venv`。网页、同源 API、内部回调和检查地址会一起切换；仅换网页端口不需要重建前端，不修改外贸 MCP 的 9120 地址。不要同时在多个端口启动同一 app-home。新端口可能需要重新登录，账号和业务数据仍在原目录，不执行 init。

队友新装可沿用默认 3001；需要自选端口时，建议选一个空闲的非特权端口（1024—65535，避开本实例固定使用的 8900/9120）。CLI 接受 `--port`，实际能否监听由系统权限和占用状态决定。`setup` 仍只装依赖，`init/install` 仍负责配置，端口不是新建数据目录的理由。3002 是本机避开冲突的演示选择，不是全队强制端口。

暂不配置模型，也可登录并使用工作台进行手工事实核对、确定性报价、资料下载、岗位任务和人工验收。产品内容工作台须明确选择 **“本地原文模板（不调用模型）”**：它按已确认原文排版，不翻译；需要英文文案和图片时，先核对产品事实已为英文。现场步骤见 [三个场景逐步演示](DEMO_WALKTHROUGH.md)。模板结果不代表 AI 翻译或聊天编排成功。

**通过聊天驱动技能、AI 翻译与生成需要另行配置并验证可用模型。** 进入 **系统设置 → 模型服务**：

1. 添加一个支持工具调用的对话模型。
2. 在“厂商 / 协议”中选与服务匹配的厂商，填写提供商给出的 Base URL、API Key 和精确模型名。对话模型的“上下文窗口（token，必填）”先尝试自动探测；没有结果时按服务已确认的工作窗口手工填写正整数。
3. 保存并点击测试。适用的 OpenAI 兼容对话模型若没有显式 `api_protocol`，保存时会自动探测 Responses 路由及工具结果往返，决定传输协议；已有显式值会保留，探测不明确不会记为已确定。页面没有单独的 `api_protocol` 输入框，不要按本文去寻找不存在的下拉项或直接修改数据库。
4. 在角色指派中将模型选给 **主智能体推理 main_agent**；对实际使用的其他对话角色按页面提示指派。仅显示模型“正常”但 main_agent 未分配，仍不能对话。

新实例不携带任何原开发者的模型地址或 Key。使用不同模型时，措辞、响应速度和工具调度可能不同；产品事实和金额以工具返回为准。默认关闭非必需的向量长期记忆，产品查询、报价、PDF/Excel 不依赖额外 mem0/Milvus 服务。

维护者提供的这条网关连通性示例（不附地址或 Key）：

| 配置 | 示例与限制 |
|---|---|
| 模型名 | `gpt-6.1-sol`；仅在自己的服务实际提供该模型时使用 |
| 已验证传输 | `Responses`；以保存探测和真实工具结果回传为准，不只看普通文本测试 |
| `context_length` | `128000`；本次采用的保守请求/压缩工作窗口，不是网关最大容量证明，也不是所有同名模型通用值 |
| 角色指派 | `main_agent` 使用这个已配置的对话模型；新建聊天再验证 |

有些网关的模型列表不提供上下文长度，模型可连通却仍缺请求预算配置。不能留空，也不能把官网模型最大窗口直接当第三方线路上限。保存后先发普通问题，再查询 `DESK-001`，确认工具执行后模型能够读回真实结果；两者成功仍不代表两条完整参赛工作流已经通过。旧实例协议迁移按第 7 节处理，不为新示例改写旧供应商的显式协议。

| 操作 | 是否依赖模型 | 是否需要外部网络 |
|---|---|---|
| 聊天理解、调用技能、平台化改稿 | 需要可用聊天模型 | 取决于模型部署；第三方网关需要联网 |
| 产品“AI翻译与生成” | 调用模型并校验数字/单位；失败会如实回退 | 取决于模型服务 |
| 工作台“本地原文模板” | 生成本身不调用模型；不翻译 | 已有上传资料可本地制作 |
| 模拟报价、版本化规则检查、人工任务验收 | 确定性业务逻辑；通过聊天发起仍需模型 | 本地目录/已保存知识无需现场抓取 |
| 买家官网/GLEIF 核验 | 不依赖生成模型 | 需要访问公开来源；失败保留未核实 |

三种图片都用授权原图或明确标注的模拟示意图进行排版，不是 AI 生图。模型失败时可用工作台模板继续独立演示，但只能记录“本地流程完成”，不能记为模型翻译或聊天端到端通过。完整三场景多轮问答与预期输出见 [HACKATHON_DEMO.md](HACKATHON_DEMO.md)。

本地私有知识库操作与旧账号权限处理见 [PRIVATE_KNOWLEDGE.md](PRIVATE_KNOWLEDGE.md)。没有 embedding 时默认采用 Wiki 原文追溯，不代表已配置向量检索。

## 5. 验收相同的外贸功能

```bash
.venv/bin/python extensions/foreign_trade/team.py check
# 主服务运行时，可在另一个终端检查本机服务
.venv/bin/python extensions/foreign_trade/team.py check --running
```

自定义数据目录的实例，所有 check 命令也传相同的 `--app-home`。`check` 是**快速离线自检**：标准 unittest 部署/报价检查加前端报价、资料卡、协同卡及生成模式守卫；它不代替 CI 的完整 pytest 业务与权限回归，也不证明模型成功。`--running` 只额外检查已启动的网页与 MCP，不调用模型。真实聊天、工具调度和文件内容仍须单独验收。

网页检查：

- 首页介绍和推荐问题为外贸场景，支持询盘报价、商品资料制作与跨岗位协同。
- 能力中心 → 插件能看到已启用的“外贸业务助手（演示）”；新聊天可输入 / 显式选择。
- 输入“查询 DESK-001 的规格、起订量和阶梯价”，确认发生产品工具调用。
- 输入“DESK-001，1000 件，定制包装，目的国西班牙，交期未指定，请报价”：货值 USD 4800.00、包装费 USD 300.00、小计 USD 5100.00，不含运费及税费。
- 点击报价下方的“下载中英文 PDF”和“下载中英文 Excel”，核对金额、模拟标识和数据来源。
- 改数量或包装后重新报价，使用新一轮结果的编号下载；Excel 是固定报价快照，不是改数量就自动重算的计算器。

三场景的对话验收、用户确认步骤与工作台联动见 [对话插件指南](CHAT_PLUGIN.md)。新能力来自整个公开分支，单独把 ZIP 导入未修改的上游实例不会安装原生业务工具。

场景三按 [协同说明](SCENARIO_THREE.md) 检查六项岗位任务、人工验收、来源变更失效和 Markdown/JSON 内部交接下载。负责人标签不赋予其他账号访问权限。

布局、样式、功能、模拟目录和初始化提示词随代码复现。账号、模型、历史记录和上传文件每台机器独立；仓库不是运行数据库的备份。

## 6. 停止与更新

在运行 start 的终端按 Ctrl+C 停止网页。MCP 是本机独立进程，需要更新其源码前执行：

```bash
.venv/bin/python extensions/foreign_trade/manage.py stop
```

该命令只停止本 checkout 管理的 MCP；如果本实例的沙箱仍占用 8900，先核对并停止它，不随意结束其他进程。更新、迁移和恢复期间不能有进程继续写同一数据库。

先把源码改动保存在自己的功能分支或另行保存，检查 `git status --short`；不要强制覆盖工作区。根据原启动命令或部署记录填写实际数据目录和已有用户名，只有原实例确实使用默认目录时才填 `$HOME/.foreign-trade-agent`：

```bash
TRADE_APP_HOME="/absolute/path/to/your/existing-app-home"
TRADE_USERNAME="YOUR_EXISTING_USERNAME"
test -f "$TRADE_APP_HOME/data.db"
```

路径检查成功、服务已停止、源码改动已保存后，更新团队仓库的 main：

```bash
git status --short
git switch main
git pull --ff-only origin main
python3.11 extensions/foreign_trade/team.py setup --app-home "$TRADE_APP_HOME"
.venv/bin/python -c 'import sys, sqlite3; print("Python", sys.version.split()[0], "SQLite", sqlite3.sqlite_version); assert sys.version_info >= (3, 11); assert sqlite3.sqlite_version_info >= (3, 38, 0)'
```

`--ff-only` 失败时先处理分支分歧，不强制覆盖。**首次从旧 0.1/0.2 公共版升级时，必须先按第 7 节确认旧库及协议并完成 upgrade，再执行下面的 install。** 旧无版本库若先直接 install，再补 legacy 参数，已经无法利用旧版本状态判定原协议；第 7 节不是事后补救步骤。已完成新版迁移的实例可直接继续：

```bash
.venv/bin/python extensions/foreign_trade/team.py install --app-home "$TRADE_APP_HOME" --username "$TRADE_USERNAME"
.venv/bin/python extensions/foreign_trade/team.py check --app-home "$TRADE_APP_HOME"
.venv/bin/python extensions/foreign_trade/team.py start --app-home "$TRADE_APP_HOME"
```

在另一个终端重新设置相同的 `TRADE_APP_HOME`，可运行 `team.py check --app-home "$TRADE_APP_HOME" --running`。

`install` 先备份并检查/升级 schema，再应用外贸首页、推荐问题、活动提示词与插件新版本。若自行修改过页面文案，请先留存；已有提示词版本会保留。账号密码和业务记录不被安装步骤替换。代码和依赖更新后必须重启本公开实例，刷新浏览器并新建对话。插件安装标识保持 `foreign-trade-demo`；新提示词版本以 `foreign-trade-demo-v4-` 开头。

源码和初始化资料通过 Git 同步；账号、模型配置与密钥、会话、数据库、上传文件、运行状态和备份属于本机，不随 Git 同步。禁止将 app-home 加入仓库。

## 7. 从旧公共版本升级数据库

本次同步点及兼容变化见 [上游同步记录](UPSTREAM_SYNC_20261028.md)。Python 服务命令已改为 `hugagent-server`；`hugagent` 是终端客户端，推荐继续使用 team.py。Python 所链接 SQLite 必须至少 3.38，初始化和迁移入口会拒绝旧 SQLite。

停止服务、完成 setup，并核对上节的 `TRADE_APP_HOME` 后执行升级。旧库有 CE 版本标记时，脚本按旧版本处理已有模型；**无版本标记且明确来自旧版 Chat Completions 公共运行时**时，才添加以下 legacy 参数，未知来源不猜：

```bash
.venv/bin/python extensions/foreign_trade/team.py upgrade --app-home "$TRADE_APP_HOME" --legacy-chat-completions
```

其他实例执行不带该参数的 `team.py upgrade --app-home "$TRADE_APP_HOME"`。协议兼容仅保留升级前已存在、未指定协议且适用两种 OpenAI 传输选择的对话模型；已有显式协议、新版迁移后新增的模型、非对话模型和不适用的厂商不被覆盖，不更改地址、密钥、模型名或采样参数。

升级会先在该 app-home 的 `upgrade-backups/` 建立独立的 **0600 SQLite 快照**，再正常执行 Alembic 和本地初始化。若遇到旧上传文件重名，会停止并报告额外重复行数。核对本机备份及数量后重试，`N` 必须替换为本实例报告的整数；仅已知旧 Chat Completions 实例保留例中的 legacy 参数：

```bash
.venv/bin/python extensions/foreign_trade/team.py upgrade --app-home "$TRADE_APP_HOME" --legacy-chat-completions --repair-legacy-filenames --expected-filename-repairs N
```

修复保留最早记录原名，只给额外重复记录的文件名加唯一后缀，并保留原名审计；自定义标题保留，只有等于旧文件名的标题同步改名。文件 ID、归属、存储引用和字节不变，不移动或删除物理文件；数量不符时停止。不要照抄别人的 N，不用 stamp 越过失败。其他重复身份、非空旧站点数据等阻断需单独处理，不删除数据来强行过关。成功升级后再执行 install，**不要重复传仍期待 N 条修复的参数**。

如现有 `.venv` 的 Python/SQLite 不合格，使用已验证的新 Python 创建另一个环境，保留旧环境。以下示例用于**已知来自旧 Chat Completions 公共运行时**的实例；其他来源须先按本节选择适用参数，再执行 upgrade，不先无旗标升级：

```bash
TRADE_VENV="$(pwd)/.venv-upstream-team"
python3.11 extensions/foreign_trade/team.py setup --venv "$TRADE_VENV" --app-home "$TRADE_APP_HOME"
"$TRADE_VENV/bin/python" extensions/foreign_trade/team.py upgrade --venv "$TRADE_VENV" --app-home "$TRADE_APP_HOME" --legacy-chat-completions
```

需要的 legacy/重名修复参数同上；后续 install、check、start 都继续传同一个 `--venv` 和 `--app-home`。直接调用独立的 install.py / upgrade.py 时使用该环境的 Python，它们没有 `--venv` 参数。

回滚快照不提交仓库、不发送给队友、不加入插件 ZIP。使用同一 app-home 内实际生成的快照路径恢复：

```bash
.venv/bin/python extensions/foreign_trade/team.py upgrade --app-home "$TRADE_APP_HOME" --restore "$TRADE_APP_HOME/upgrade-backups/YOUR_SNAPSHOT.db"
```

恢复前同样必须停止服务；恢复会先另存当前数据库快照。数据库回滚后还需使用对应版本的源码和依赖。SQLite 快照不是上传文件和能力目录的完整备份，须保留原 app-home 中的文件。迁移程序不会改密码、角色授权、模型地址或密钥。

## 8. 团队提交代码

```bash
git switch main
git pull --ff-only origin main
git switch -c codex/your-feature
# 修改和检查后，只提交本次相关文件
git add path/to/changed-file
git commit -m "Describe the feature"
git push -u origin codex/your-feature
```

在 GitHub 提交 PR 至 main，等待 Foreign Trade CI 通过并由队友复核。新增外贸功能建议放在 extensions/foreign_trade；界面导出在前端对应模块中。不要多人同时直接推送 main。

仓库公开不等于所有人都能推送。仓库所有者可以在 Settings → Collaborators 邀请队友；未加入协作者的队友可以 Fork 后提 PR。本次建仓不会自动邀请未知账号。

## 常见问题

| 现象 | 处理 |
|---|---|
| hugagent: command not found | 使用仓库的 .venv/bin/python 执行 team.py，无需依赖 shell 是否激活虚拟环境 |
| 找不到 package.json | 先 cd 到仓库根目录，团队脚本也会自行定位源码位置 |
| 账号已占用 | 使用同一数据目录和现有用户名执行 init/install，不重新创建账号 |
| 有页面但没外贸首页/插件 | 新实例完成 init；已有实例对正确 app-home 和已有用户名执行 install |
| 更新后账号或历史“消失” | 先核对是否连到了原 app-home，不新建账号或空库 |
| Python 版本合格但 SQLite 报错 | 检查该解释器的 SQLite，换合格环境并在所有 team.py 命令中传同一个 --venv |
| 模型测试正常但不能对话 | 检查 main_agent 是否分配，以及模型是否支持工具调用 |
| 报未配置 context_length | 编辑该对话模型，探测或手工填写经当前服务确认的正整数工作窗口；示例128000不是任意线路上限 |
| 普通回复正常，但工具执行后回答为空/失败 | 核对协议探测和工具结果往返能力；保留失败步骤，不用普通HTTP200替代完整工具链验证 |
| 127.0.0.1:3001打不开/连接被重置 | 先核对本项目启动输出和端口归属；其他容器占用时保留对方，按原app-home改用3002，再用同端口check --running |
| 3002页面能开但账号/记录不对 | 核对启动时app-home，换端口可能需重登录；不要init新库或复制他人的认证数据 |
| 新审核工具不出现 | 确认当前公开宿主、0.4.0插件和五技能/八业务工具已安装启用，重开聊天；ZIP不能代替宿主源码升级 |
| 报技能未加载或来源版本冲突 | 完整读取对应技能或get当前来源后核对，不伪造已读、跳过确认或盲重放写入 |
| 模板没有英文图片 | 核对实际事实是否英文及原图/署名是否齐全；中文未翻译不算生成失败被绕过，不称AI已翻译 |
| 产品工具连接失败 | 检查 team.py start 的 MCP 状态和 9120 端口 |
| 更新后仍旧页面 | 确认 setup 前端构建成功，刷新浏览器 |
| 同一金额的文字说法不同 | 模型输出并非固定模板，核对工具回执和下载卡的金额 |

部署前后的开源来源说明始终保留。名称和 Logo 将在团队确定后单独调整。
