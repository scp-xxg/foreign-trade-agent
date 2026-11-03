# 部署指南

适用 Windows（WSL 终端）、Linux、macOS。先安装并启动 Docker Desktop，或 Docker Engine + Compose v2；建议预留 8 GB 内存、15 GB 磁盘。首次构建需要联网下载公开依赖。运行环境、前端、字体与插件都在镜像中，无需在宿主机安装 Python 或 Node。容器基础镜像已固定摘要，Python 依赖由 `requirements-sailagent.lock` 约束，前端使用 `npm ci` 锁文件。镜像固定 `linux/amd64`，Apple Silicon Mac 使用 Docker 的 amd64 仿真，首次构建较慢。

## 启动

在仓库根目录运行：

```bash
./start.sh
```

Windows PowerShell 可直接运行同一条 Compose 命令：

```powershell
docker compose -f compose.sailagent.yml run --build --rm --service-ports sailagent
```

首次按终端提示创建**自己的用户名和密码**。仓库不提供默认账号，也不含维护者的数据库或密钥。启动完成后打开 <http://127.0.0.1:3002>。已有数据会保留账号、模型、业务记录与知识库，重复启动不会重置密码；登录会话保存在内存中，重启后需重新登录，已保存的业务数据不受影响。

首次登录后在 **设置 → 模型服务** 添加支持工具调用的模型，测试成功并指定 `main_agent`。密钥只填写在本机网页，不提交 Git。没有可用模型时，工作台仍可执行商品查询、确定性报价、本地模板资料与规则审核；自然语言多轮对话和子智能体需要模型服务正常。

首次初始化会安装外贸技能插件与三个核心岗位，并导入随仓库提供的公开合规案例。自己的敏感词库按 [敏感词说明](SENSITIVE_TERMS.md) 导入，企业资料按 [私有知识库](PRIVATE_KNOWLEDGE.md) 导入。

## 日常运行与更新

前台运行按 Ctrl-C 停止；之后可在后台启动：

```bash
./start.sh --background
./start.sh --logs
./start.sh --stop
```

后台首次启动前应先完成一次交互初始化。停止不会删除数据。更新前先停止当前实例，再拉取 main 并重新构建：

```bash
./start.sh --stop
git pull --ff-only origin main
./start.sh --background
```

默认只监听本机回环地址，不向局域网公开管理页面；MCP 与沙箱内部端口不映射到宿主机。3002 被占用时指定其他端口，后续命令继续使用同一设置：

```bash
SAILAGENT_PORT=3012 ./start.sh
```

不要同时启动两个实例操作同一数据卷，启动器会锁住数据目录以防止并发升级。需要独立环境时使用不同的 Compose 项目名：

```bash
COMPOSE_PROJECT_NAME=sailagent-demo SAILAGENT_PORT=3012 ./start.sh
```

## 数据与备份

数据保存在 Docker 命名卷（默认 `sailagent_sailagent_data`），与代码和镜像分离。不要使用 `docker compose down -v`，它会删除卷。备份前先停止实例，再导出卷；备份中包含私有业务数据与本机配置，不要上传到公开仓库。

```bash
./start.sh --stop
docker run --rm -v sailagent_sailagent_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/sailagent-data.tgz -C /data .
```

恢复时先停止实例，再用同样的挂载方式把归档解回 `/data`。

已有镜像的离线启动（不触发构建）：

```bash
docker compose -f compose.sailagent.yml run --rm --service-ports sailagent
```

模型生成与买家官网实时核验仍需要对应网络连接；离线状态下的规则与模板能力不会冒充实时联网查询或模型生成。

## 自检清单

1. 登录后看到 SailAgent，界面保留 Powered by HugAgentOS 开源署名。
2. 三个岗位与外贸插件可用，公开多国合规案例可在知识库检索。
3. 登记同一条询盘、计算报价、修改数量重算，下载中英 PDF 与双语 Excel。
4. 将同款商品关联资料包与运营任务，确认事实后生成英文 Listing、FAQ、三种比例图片与 ZIP。
5. 审核卡展示规则来源、风险标记、文字批注与修改后的复审结果。
6. 停止再启动，原询盘、资料包与知识库仍在，下载链接仍受本机账号权限保护。

宿主机源码部署见 [原生 Python 安装与升级](TEAM_SETUP.md)。两种部署方式不要混用同一个数据目录。
