# macOS 部署入口

统一使用 [一键部署说明](docs/ONE_COMMAND_DEPLOY.md)。仓库根目录执行：

~~~bash
./start.sh
~~~

新的部署使用独立镜像和持久卷，覆盖 Windows/WSL、Linux 与 macOS。旧的 mac-dev 睡眠开发容器配置已移除，避免与正式演示入口混淆。

**旧卷不会自动迁移到新卷。** 若曾使用旧配置并已有数据，请保留原来的 foreign_trade_app_home 卷；先停旧实例并备份，再另行迁移完整应用数据。不要删除旧卷，也不要把包含账号、密钥或私有知识的备份提交到 Git。
