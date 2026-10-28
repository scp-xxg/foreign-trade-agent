# 队友部署、模型配置与代码同步

本指南针对团队公开仓库的 Linux / WSL2 本机开发部署。品牌暂保留 HugAgentOS；仓库名为 foreign-trade-agent。原项目部署说明请见根目录 README_UPSTREAM.md，本指南的命令才会安装团队外贸功能。

## 1. 准备环境

推荐 Ubuntu 22.04 / 24.04（Windows 使用 WSL2）、Python 3.11、Node.js 22、Git。建议至少 8 GB 可用内存和足够的依赖下载空间。

```bash
python3 --version
node --version
git --version
```

Python 必须 >= 3.11；Node 至少 20.19 或 22.12。Ubuntu 22.04 自带 Python 3.10，不能直接用它执行 setup。如果已有 Conda，可以单独准备 Python：

```bash
conda create -n foreign-trade python=3.11 -y
conda activate foreign-trade
```

如果已有 nvm，可以安装 Node 22：

```bash
nvm install 22
nvm use 22
```

没有这些工具时，先按 [Python](https://www.python.org/downloads/)、[Node.js](https://nodejs.org/en/download) 官方说明准备。老版本 Linux 的 ripgrep 依赖可能需要编译；setup 检查到缺少 Cargo 时，按 [Rust 官方安装说明](https://rustup.rs/) 安装后重新打开终端。受限 bash 沙箱可选依赖：`sudo apt install bubblewrap`。产品检索和确定性报价本身不使用 bash 工具。

## 2. 拉取和安装

```bash
git clone https://github.com/scp-xxg/foreign-trade-agent.git
cd foreign-trade-agent
python3.11 extensions/foreign_trade/team.py setup
```

Conda 环境中的 Python 已为 3.11 时，也可用 `python extensions/foreign_trade/team.py setup`。

setup 会创建本仓库 `.venv`、安装 requirements.txt 和 editable 项目，用 package-lock.json 执行 npm ci，并构建中文 CE 前端。不要另外执行上游 curl 安装器，否则会安装原始 HugAgentOS 而非本仓库。

## 3. 创建自己的实例和安装插件

```bash
.venv/bin/python extensions/foreign_trade/team.py init
```

在终端输入自己的用户名和密码。密码仅在终端隐藏输入，不作为命令参数，也不提交 Git。初始化会：

1. 在 `~/.foreign-trade-agent` 创建独立 SQLite 和本机文件目录。
2. 创建本机账号，应用外贸首页、6 条推荐问题和外贸助手提示词。
3. 将“外贸业务助手（演示）”0.3.0 安装到该账号，包含四个技能、原报价 MCP 工具和本公开项目提供的会话绑定业务工具。

同名账号已存在时，init 保留密码和权限，仅继续安装/更新场景内容。数据目录已有其他账号时，不会额外创建管理员；请用已有用户名执行 `init --username YOUR_USERNAME` 或 `install --username YOUR_USERNAME`。

默认不继承其他项目的 HUGAGENT_HOME，也不读取仓库 `.env`。如果维护一个已有实例，**每条命令都显式传相同的数据目录**：

```bash
.venv/bin/python extensions/foreign_trade/team.py init --app-home /your/data/directory
.venv/bin/python extensions/foreign_trade/team.py start --app-home /your/data/directory
```

不要把开发者的数据库或模型配置文件复制给队友。

## 4. 启动与配置模型

```bash
.venv/bin/python extensions/foreign_trade/team.py start
```

浏览器打开 http://127.0.0.1:3001，用自己的账号登录。启动命令使用固定本机端口：网页 3001、沙箱 8900、外贸 MCP 9120；冲突时停止自己之前的实例，不要随意结束其他进程。

进入 **系统设置 → 模型服务**：

1. 添加一个支持工具调用的对话模型。
2. 填写提供商给出的 Base URL、API Key 和精确模型名，选择匹配的协议及上下文长度。
3. 保存并点击测试。
4. 在角色指派中将模型选给 **主智能体推理 main_agent**；对实际使用的其他对话角色按页面提示指派。仅显示模型“正常”但 main_agent 未分配，仍不能对话。

新实例不携带任何原开发者的模型地址或 Key。使用不同模型时，措辞、响应速度和工具调度可能不同；产品事实和金额以工具返回为准。默认关闭非必需的向量长期记忆，产品查询、报价、PDF/Excel 不依赖额外 mem0/Milvus 服务。

## 5. 验收相同的外贸功能

```bash
.venv/bin/python extensions/foreign_trade/team.py check
# 主服务运行时，可在另一个终端检查本机服务
.venv/bin/python extensions/foreign_trade/team.py check --running
```

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

该命令只停止本 checkout 管理的 MCP。确定自己的改动已提交或保存后更新：

```bash
git pull --ff-only
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python extensions/foreign_trade/team.py install --username YOUR_USERNAME
.venv/bin/python extensions/foreign_trade/team.py check
.venv/bin/python extensions/foreign_trade/team.py start
```

`install` 应用仓库里的首页、提示词与插件新版本。若自行修改过这些配置，请先保留修改；账号密码和聊天历史不被这个步骤替换。新增后端原生工具或其他代码变更后必须重启本公开实例；只有插件说明内容更新时，可在网页关闭再开启插件刷新缓存，然后新建对话。插件安装标识保持 foreign-trade-demo，原 inquiry-quote 保留；新提示词使用 foreign-trade-demo-v3。

## 7. 从旧公共版本升级数据库

本次同步点及兼容变化见 [上游同步记录](UPSTREAM_SYNC_20261028.md)。Python 服务命令已改为 hugagent-server；推荐继续使用 team.py，不混用上游同名终端客户端。Python 所链接 SQLite 需至少 3.38，团队脚本会提前校验，避免旧 SQLite 错误打开新版库。

停止当前实例后，先在自己的 app-home 上执行升级。来自旧版公共演示、未设模型协议时，保留原 Chat Completions 传输：

```bash
.venv/bin/python extensions/foreign_trade/team.py upgrade --app-home /your/data/directory --legacy-chat-completions
```

升级会先建立本机 0600 SQLite 快照，再正常执行 Alembic 和本地初始化。若遇到旧上传文件重名，会停止并报告需修复的数量；核对本机备份后，用 `--repair-legacy-filenames --expected-filename-repairs N` 明确限定本次修复数量。它只给重复记录的文件名加唯一后缀并保留原名审计，不删除文件、不改文件 ID、归属或字节。不要照抄别人的 N，也不要用 stamp 越过失败。成功升级后再执行 install，不要重复传仍期待 N 条修复的参数。

可以用 `--venv /absolute/path/to/another/venv` 在隔离虚拟环境预演升级；setup、upgrade、install、start 等命令均使用同一个所选 venv 和 app-home。回滚快照位于本机 app-home/upgrade-backups，不提交仓库、不复制给队友。恢复示例：

```bash
.venv/bin/python extensions/foreign_trade/team.py upgrade --app-home /your/data/directory --restore /your/data/directory/upgrade-backups/YOUR_SNAPSHOT.db
```

恢复前同样必须停止服务；恢复会先另存当前数据库快照。数据库回滚后还需使用对应版本的源码和依赖。当前环境的迁移程序不会改密码、角色授权、模型地址或密钥。

## 8. 团队提交代码

```bash
git switch main
git pull --ff-only
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
| 有页面但没插件 | 完成 init，或对当前登录用户名执行 install |
| 模型测试正常但不能对话 | 检查 main_agent 是否分配，以及模型是否支持工具调用 |
| 产品工具连接失败 | 检查 team.py start 的 MCP 状态和 9120 端口 |
| 更新后仍旧页面 | 确认 setup 前端构建成功，刷新浏览器 |
| 同一金额的文字说法不同 | 模型输出并非固定模板，核对工具回执和下载卡的金额 |

部署前后的开源来源说明始终保留。名称和 Logo 将在团队确定后单独调整。
