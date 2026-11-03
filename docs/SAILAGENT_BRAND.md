# 品牌与素材

产品名称：**SailAgent**（S、A 大写），取自“启航”，面向外贸出海的询盘、商品内容与岗位协同。仓库、目录与命令统一使用 `sailagent`；与上游共用的技术标识（`hugagent`、Python 包 `foreign_trade`、插件 ID `foreign-trade-demo`）保持不变，避免破坏部署、插件与既有数据。

## 标识

Logo 由两片帆、一条弧形航线与目的地点组成：蓝色 `#1264E8`、海青 `#70E5D0`、文字深蓝 `#102A43`。矢量主图适用于 16px 标签页到大尺寸展示，另提供透明 SVG、PNG、ICO 与浅/深底字标。

素材位于 `src/frontend/public/brand/`：

| 文件 | 用途 |
|---|---|
| `sailagent-mark.svg` | 图标矢量主文件 |
| `sailagent-wordmark.svg` / `sailagent-wordmark-light.svg` | 浅底 / 深底字标 |
| `sailagent-icon-192.png` / `sailagent-icon-512.png` | 应用图标 |
| `sailagent-favicon.png` / `sailagent.ico` | 浏览器标签页 |
| `sailagent-wordmark.png` | 透明高分辨率字标 |
| `sailagent-preview.png` | 白底预览 |
| `manifest.webmanifest` | 添加到主屏幕的名称与图标 |

源码、首次部署默认值、登录页、首页、侧栏、标签页、初始化页、默认助手身份与新生成报价单抬头均使用 SailAgent；新导出文件保留 `Powered by HugAgentOS`，既有历史文件与聊天记录不重写。

## 对既有实例应用品牌

网页按正常方式构建后，用明确的公开应用数据目录执行迁移：

```bash
VITE_EDITION=ce VITE_DEFAULT_LANGUAGE=zh-CN npm --prefix src/frontend run build
.venv/bin/python extensions/foreign_trade/brand_identity.py --app-home "$HOME/.sailagent"
```

迁移只改品牌字段，并为默认身份创建新的提示词版本，原提示词保留。备份仅包含原品牌字段、原活动提示词版本 ID 和表行数，不复制模型密钥。业务文案、推荐问题、对话、商品、报价、知识库、账号权限与模型配置都保留。`team.py start` 也会幂等执行同一迁移，避免重启后恢复旧品牌。

## 重新导出素材

仓库中已提交生成好的图标，部署时无需 CairoSVG。仅在需要重绘导出时，在项目环境安装 `cairosvg==2.9.1` 后运行：

```bash
.venv/bin/python extensions/foreign_trade/render_brand.py
```

## 开源来源

界面保留 **Powered by HugAgentOS**，文档继续链接上游项目；`LICENSE` 与上游 `NOTICE` 一并保留。SailAgent 是本公开衍生项目的品牌，不宣称是 HugAgentOS 官方产品。
