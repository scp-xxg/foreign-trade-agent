# sailagent 品牌

产品名称：**sailagent**（全小写），寓意“启航”。面向外贸出海的询盘、商品内容与岗位协同。技术仓库/目录/命令仍使用foreign-trade-agent、hugagent等既有标识，避免破坏部署、插件与数据。

Logo采用两片帆、一条弧形航线与目的地点：蓝色#1264E8、海青#70E5D0、文字深蓝#102A43。矢量主图适合16px标签页到大尺寸展示；提供透明SVG、PNG、ICO和浅/深底字标。

素材在 src/frontend/public/brand/：

- sailagent-mark.svg：图标矢量主文件。
- sailagent-wordmark.svg / sailagent-wordmark-light.svg：浅底/深底字标。
- sailagent-icon-192.png / sailagent-icon-512.png：应用图标。
- sailagent-favicon.png / sailagent.ico：浏览器标签页。
- sailagent-wordmark.png：透明高分辨率字标；sailagent-preview.png：白底预览。
- manifest.webmanifest：移动端添加到主屏幕的名称与图标。

源码、首次部署默认值、登录页、首页、侧栏、标签页、初始化页、默认助手身份和新生成报价单抬头已采用sailagent。新导出的文件继续保留Powered by HugAgentOS；既有历史文件和聊天记录不重写。

## 已有本地环境升级

网页先按正常方式构建，再使用明确的公开应用数据目录迁移：

```bash
VITE_EDITION=ce VITE_DEFAULT_LANGUAGE=zh-CN npm --prefix src/frontend run build
.venv/bin/python extensions/foreign_trade/brand_identity.py --app-home "$HOME/.foreign-trade-agent"
```

本机现有公开测试数据目录是 ~/.hugagent-hackathon-public-1.0.2，网页端口3002。不要选择其他私有项目的数据目录。

迁移只改品牌字段，并为默认身份创建新的提示词版本；原提示词仍保留。备份仅包含原品牌字段、原活动提示词版本ID和表行数，不复制模型密钥。业务文案、推荐问题、对话、产品、报价、知识库、账号权限及模型配置保留。新版本team.py start也会幂等执行迁移，避免重启后恢复旧品牌。

## 开源来源

界面保留 **Powered by HugAgentOS**，帮助文档继续链接原开源项目；LICENSE及上游NOTICE保留。sailagent是此公开衍生项目的品牌，不宣称是HugAgentOS官方产品。

## 重新导出素材（开发者可选）

已提交生成好的图标，队友部署无需CairoSVG。仅需要重绘导出时，在项目环境安装cairosvg==2.9.1，运行：

```bash
.venv/bin/python extensions/foreign_trade/render_brand.py
```

## 本机验收（2026-10-31）

- 公开扩展测试：617项通过；品牌与CE持久化专项：2项通过。
- CE前端完整构建通过；报价导出15组回归通过。
- Chrome实际登录后，首页、侧栏、标签页显示sailagent，Logo正常加载，底部Powered by HugAgentOS保留；登录页字标已核验。
- 实际新建对话自我介绍：“我叫 sailagent，是基于 HugAgentOS 开源框架的外贸出海助手。”
- 品牌迁移重复执行不再改动，迁移前后各表行数一致。既有业务记录、模型配置及知识库未迁移或清空。
- 另跑旧导航回填测试时有8项失败；使用本次修改前HEAD文件重跑也出现相同8项失败，属于既有外贸导航与上游旧测试夹具不一致，未改动导航业务逻辑。本次不宣称全部上游测试通过。
