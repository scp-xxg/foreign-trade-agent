# Blender MCP：中文产品概念打样

公开项目的附加技能插件，基于 HugAgentOS CE 与 [MCP for Blender](https://github.com/ahujasid/mcp-for-blender)。保留各自开源署名；只使用本地 Blender 和程序化几何，不需要 Style3D 账号，也不调用付费模型/素材生成接口。中文理解仍使用 HugAgent 已配置的支持工具调用的大模型。

## 已支持的业务范围

外贸业务员描述一个“有底、开顶、沿宽度等分”的桌面收纳盒，美工获得可继续编辑的 .blend 源文件、GLB 和实渲染 PNG。支持外尺寸、分格数、壁厚、五种颜色；第二轮只改明确字段，其余保留，旧文件不覆盖。

它是用于询盘沟通的**概念样品**，不是任意物体/服装生成器，不提供纸样、布料仿真、强度、可制造性、认证或生产 CAD 结论。和 DESK-001 没有自动关联；修改模型不会偷偷改变报价目录或询盘。

## 一次性安装（每名队友自己的 WSL/Linux）

先按 [团队部署](TEAM_SETUP.md) 建好此公开项目、账号和模型。Ubuntu 22.04 x86_64，建议 8GB 可用内存、至少 4GB 空余磁盘。CPU 渲染无需 CUDA。

在自己的公开项目目录执行：

```bash
sudo apt-get update
sudo apt-get install -y xvfb xauth libxi6 libxrender1 libxfixes3 libxkbcommon0 libgl1 libegl1 libsm6
.venv/bin/python extensions/blender/manage.py setup
.venv/bin/python extensions/blender/manage.py install --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME
.venv/bin/python extensions/blender/manage.py start
.venv/bin/python extensions/blender/manage.py status
```

这里的 app-home 必须和网页后端使用的目录一致。已有本机公开测试目录使用 ~/.hugagent-hackathon-public-1.0.2；不要使用别的私有项目目录。管理脚本不会复制数据库、账号、模型密钥或会话。每人自己配置模型服务并指派 main_agent。

setup 从 Blender 官方镜像下载 **Blender 5.2.3 LTS Linux**，先核对官方 SHA256，再解压到此 checkout 的 .runtime；用独立 .runtime/blender-mcp-venv 安装 mcp-for-blender==2.2.6 / mcp==1.30.0，不降级 HugAgent 的 MCP SDK2。首次需联网下载，后续建模和渲染均为本地执行。Xvfb 是 GUI 事件循环所需的虚拟显示，不能用 blender -b 替代 MCP 服务。

固定上游 addon.py 对应提交：992233bb258975a05eec8b5691465c50c2831e34。插件 SHA256：6c2917c157c26d7549adcbd480243db2154a9b06bc580664f090530c8ef3801f。

Linux 安装包 SHA256：78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec。来源：[官方校验清单](https://mirror.blender.org/release/Blender5.2/blender-5.2.3.sha256)。Blender 按 GPL-3.0-or-later 分发，上游 MCP 按 MIT 分发；依赖下载包保留原始许可证，第三方引擎及二进制不提交仓库。

## 日常启动与停止

```bash
.venv/bin/python extensions/blender/manage.py start
.venv/bin/python extensions/blender/manage.py status
# 仅停止脚本验证过 PID/cwd/启动参数的 Blender，不停其他项目
.venv/bin/python extensions/blender/manage.py stop
```

原有网页启动方式不变。此电脑公开端口是 http://127.0.0.1:3002；3001 属于其他项目。浏览器刷新后从“能力中心”查看“外贸 3D 打样（Blender）”，新建对话并明确要求使用它，也可从插件入口启动。

## 可复制的两轮问答

第一轮：

> 请使用“外贸 3D 打样（Blender）”插件，创建桌面收纳盒概念样品：外尺寸宽20、深10、高8厘米，3格，壁厚3毫米，蓝色。实际建模并导出 GLB、展示图和 Blender 源文件，给出实际尺寸和下载链接。

预期：插件/技能加载 → blender_product_model(create) → Blender 实际尺寸20×10×8cm、7个产品网格 → v1 → blender_export_product(expected_revision=1) → 三个真实下载链接和PNG展示。

第二轮（在同一对话，不新建）：

> 保持宽深、3格和壁厚不变，高度改为10厘米，颜色改为绿色。重新导出GLB、展示图和Blender源文件，说明与第一版的变化。

预期：get读取v1 → update(expected_revision=1,height_cm=10,color=green) → 实际尺寸20×10×10cm → v2 → export(expected_revision=2)。宽20、深10、3格、3mm均保持；v1文件仍可下载。

下载 GLB 后可在 Blender 的 File → Import → glTF 2.0 导入检查；文件只含产品网格，地面/灯光/相机属于展示布景。PNG1024×768，带“概念样品/版本/参数/非生产文件”和 HugAgentOS 署名。Blend源文件包含可编辑部件和布景。

## 数据与异常链路

用户中文 → 当前模型理解/技能 → Hug 当前账号和会话绑定的 stdio MCP → 参数与版本校验 → 全局非阻塞互斥锁 → 上游 MCP（SDK1、安全模式）→ loopback9876 → Blender/Xvfb → 实际几何回执 → 按会话持久化版本 → 同版本重建/GLB导出/CPU渲染 → 文件结构及大小校验 → Hug 账号归属文件登记 → /files/ 链接 → 浏览器下载。

- 业务状态：app-home/blender/sessions/<账号+会话哈希>/model.json；历史参数保留，后端重启不丢模型。
- 导出：同目录 exports/v<版本>-<随机ID>，每次独立，发布到 Hug 原有 storage/artifacts；不把文件当作模型的文本回答。
- 身份来自 CURRENT_USER_ID/CURRENT_CHAT_ID，工具不接受账号、会话或文件路径参数。每次验证会话归属和插件启用状态；下载复用原有账号鉴权。
- 所有 Blender 操作串行；引擎忙时返回明确错误，不把其他会话的场景作为当前会话导出。导出总是从当前会话保存参数完整重建，不依赖共享场景残留。
- 参数/旧版本错误不写入；Blender断连/执行失败不写入新状态；缺文件/GLB结构错误/外部引用/PNG尺寸错误不提供成功下载。超时不代表成功，重试前先读取版本。
- Blender只绑定127.0.0.1，遥测关闭，外部素材和付费生成入口未暴露。工具仅执行受限的本项目脚本，并开启上游安全模式；不是操作系统沙箱，本机9876仍只应给受信任用户使用。
- 模型服务故障时，直接工具/本地引擎不等于自然语言聊天可用；先在设置→模型服务测试现有模型。

## 验证

```bash
.venv/bin/python -m pytest tests/test_blender_integration.py -q
.venv/bin/python extensions/blender/manage.py status
```

真实两轮对话和浏览器下载的结果见 [Blender 验收记录](BLENDER_ACCEPTANCE_20261031.md)。
