# 一键部署与参赛复现

适用 Windows（WSL 终端）、Linux、macOS。先安装并启动 Docker Desktop，或 Docker Engine + Compose v2；建议预留 8 GB 内存、15 GB 磁盘。首次构建需要联网下载公开依赖。运行环境、前端、字体、插件都在镜像中，无需在宿主机安装 Python 或 Node。容器基础镜像已固定摘要，Python依赖采用 requirements-sailagent.lock 约束，前端采用 npm ci 锁文件。容器固定 linux/amd64；Apple Silicon Mac 使用 Docker 的 amd64 仿真，首次构建较慢。

## 启动

在完整仓库根目录运行：

~~~bash
./start.sh
~~~

Windows PowerShell 可直接运行同一条 Compose 命令：

~~~powershell
docker compose -f compose.sailagent.yml run --build --rm --service-ports sailagent
~~~

首次按终端提示创建**自己的用户名和密码**。不提供默认账号、不导入维护者数据库或密钥。启动完成打开 <http://127.0.0.1:3002>。已有本机数据会保留账号、模型、业务记录和知识库；重复启动不会重置密码。登录会话使用当前公开版本的内存存储，重启后需重新登录，已保存业务数据不受影响。

首次登录后在 **设置 → 模型服务** 添加支持工具调用的模型，测试成功并指定 **main_agent**。密钥只填本机网页，不提交 Git。没有可用模型时，仍可通过工作台执行产品查询、确定性报价、本地模板资料和规则审核；自然语言多轮及子智能体需要模型服务正常。

首次初始化会安装外贸技能插件和三个核心岗位，并导入随仓库提供的官方合规案例。维护者的私人敏感词文档不会随镜像分发；自己的词库按 [敏感词说明](SENSITIVE_TERMS.md) 导入。

## 日常运行与更新

前台运行按 Ctrl-C 停止；之后可在后台启动：

~~~bash
./start.sh --background
./start.sh --logs
./start.sh --stop
~~~

后台首次启动前应先完成交互初始化。停止不删除数据。更新前先停止当前实例，再拉取 main 并重新构建：

~~~bash
./start.sh --stop
git pull --ff-only origin main
./start.sh --background
~~~

默认只监听本机回环地址，不向局域网公开管理页面。MCP、沙箱内部端口不映射到宿主机。3002 已占用时指定其他端口，后续命令继续使用同一设置：

~~~bash
SAILAGENT_PORT=3012 ./start.sh
~~~

不要同时启动两个实例操作同一数据卷。启动器会锁住数据目录，防止并发升级。需要独立演示环境可设置不同 Compose 项目名：

~~~bash
COMPOSE_PROJECT_NAME=sailagent-demo SAILAGENT_PORT=3012 ./start.sh
~~~

## 数据、备份与离线现场

数据保存在 Docker 命名卷（默认 sailagent_sailagent_data），与代码和镜像分离。不要使用 docker compose down -v，它会删除卷。备份先停止实例，再导出自己的卷；备份中含私有业务数据和本机配置，不上传公开仓库。

比赛前完成一次联网构建、模型配置、两条流程及下载验收，再保留镜像和数据。已有镜像的离线启动：

~~~bash
docker compose -f compose.sailagent.yml run --rm --service-ports sailagent
~~~

该命令不触发构建；模型生成和实时买家官网核验仍需要对应网络连接。离线规则与模板能力不会冒充实时联网查询或模型生成。

## 提交前检查

1. 登录后看到 SailAgent，保留 Powered by HugAgentOS 开源署名。
2. 三个岗位和外贸插件可用，官方多国合规案例在知识库可检索。
3. 销售登记同一询盘、计算报价、修改数量重算，下载中英 PDF 和双语 Excel。
4. 将同款商品关联资料包及运营任务，确认事实后生成英文 Listing、FAQ、三种比例图片和 ZIP。
5. 在审核卡展示规则来源、风险标记、文字批注及修改后的复审结果。
6. 停止再启动，原询盘、资料包、知识库仍在，下载链接仍受本机账号权限保护。
7. 上传可运行作品及 1 页方案说明；提交前给安装、模型连通和文件下载留出实测时间。

宿主机源码部署的高级操作仍可参考 [团队安装](TEAM_SETUP.md)。不要混用两个部署方式的数据目录。


## 已验证范围

2026-11-01 在 WSL Ubuntu / Docker linux-amd64 上，使用全新独立数据卷完成实际构建和启动：创建自己的账号、三角色安装、8 个公开合规案例及 Wiki 原文读取，500 件报价 USD 2400 → 1000 件定制包装 USD 5100、跟进待办、同 SKU 接力资料包、三种比例 PNG、ZIP 与审核报告下载，并停止重启后读回同一记录和文件。另验证原生 update_drafts 保存修订中英回复且报价编号/金额不变，三个角色的本地登记与数据库知识库绑定一致。新卷验证采用明确标注的本地模板模式，未配置模型；真实模型对话仍须使用队友自己的服务验收。
