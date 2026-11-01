# macOS Docker 环境

这个配置适合 Mac + Docker Desktop，用容器提供项目所需的运行环境：

- Python 3.11
- SQLite 3.40+（满足 3.38+）
- Node.js 22 LTS
- Git

在仓库根目录执行：

```bash
docker compose -f docker-compose.mac-dev.yml build
docker compose -f docker-compose.mac-dev.yml up -d
docker compose -f docker-compose.mac-dev.yml exec foreign-trade-dev bash
```

进入容器后执行项目初始化：

```bash
python3.11 extensions/foreign_trade/team.py setup
.venv/bin/python extensions/foreign_trade/team.py init
.venv/bin/python extensions/foreign_trade/team.py start
```

然后在 Mac 浏览器打开 <http://127.0.0.1:3001>。首次 `init` 会要求在终端输入自己的账号和密码；保持运行 `start` 的终端不要关闭。

停止容器：

```bash
docker compose -f docker-compose.mac-dev.yml down
```

项目源码通过 `/workspace` 挂载，应用数据保存在 Docker volume `foreign_trade_app_home` 中。Mac 需要先安装并启动 Docker Desktop，建议至少预留 8GB 内存和足够的磁盘空间。
