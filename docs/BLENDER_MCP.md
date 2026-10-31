# 通用 Blender MCP 中文 3D 建模

外贸产品、服装外观、家具、器皿或其他创意，均使用同一组通用场景工具，不设置物体类别白名单。当前插件0.2.0基于 [MCP for Blender](https://github.com/ahujasid/mcp-for-blender) 和 HugAgentOS CE；模型动态编写 bpy，真实 Blender 执行、检查、渲染、修改和导出。

这不是“输入几个参数调用收纳盒模板”。此前0.1.0的模板限制已移除。可尝试任意类别的概念建模，但生成质量取决于模型、对象复杂度和迭代；不能承诺任何对象一次就准确完成，也不等同于工业生产CAD、服装纸样或布料物理仿真。

## 每名队友部署

先按 [团队部署](TEAM_SETUP.md) 安装此公开项目、创建自己的账号，配置支持工具调用的大模型并指派main_agent。Ubuntu22.04 x86_64，建议8GB可用内存、至少4GB空余磁盘；CPU渲染无需CUDA。

```bash
sudo apt-get update
sudo apt-get install -y bubblewrap xvfb xauth libxi6 libxrender1 libxfixes3 libxkbcommon0 libgl1 libegl1 libsm6
.venv/bin/python extensions/blender/manage.py setup
.venv/bin/python extensions/blender/manage.py install --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME
.venv/bin/python extensions/blender/manage.py status
```

app-home必须与网页后端一致，本机公开测试目录是 ~/.hugagent-hackathon-public-1.0.2，网页3002；3001属于其他项目，不要操作。每人使用自己的数据库、账号和模型，不会从仓库得到此电脑的密钥或会话。

通用场景按调用自动启动隔离Blender，不依赖长期打开Windows窗口。status 的 general_ready 表示运行依赖齐备；首次调用仍会验证实际启动、MCP与渲染。旧0.1管理用的 start/stop 可控制旧固定工具进程，通用版无需常驻该进程。原网页启动方式不变；安装/升级后重启公开后端、刷新页面并新建对话，清掉旧插件缓存。

## 三个通用工具

| 工具 | 职责 |
|---|---|
| blender_scene_info | 读取当前会话保存的版本、实际网格、材质、图片信息；新场景revision0 |
| blender_scene_execute | 动态执行模型编写的bpy，在原场景上局部修改；参数code、expected_revision、user_prompt。执行/检查成功才保存新版本 |
| blender_scene_export | 从指定最新版本导出GLB、1024×768PNG和可编辑Blend，给真实下载链接，同时把渲染缩略图回传模型 |

模型可自由创建网格/曲线/UV/贴图/材质与场景，不为每个商品新增工具或模板。图像花纹应使用GLB支持的UV+Image Texture，并嵌入文件；复杂程序材质不保证可被glTF完整表达，需贴图或另行烘焙。展示布景不想进产品GLB时，标记 obj['hug_display_only']=True。

## 中文示例与多轮改稿

第一轮：

> 请使用“外贸3D打样（Blender）”插件，创建有金色梅花花纹的红色旗袍3D概念模型，包含立领、右斜襟盘扣、短袖和两侧开衩；合理说明概念尺寸。实际动态建模，让花纹嵌入GLB，导出GLB、PNG展示图和Blender源文件。

第二轮，在同一对话：

> 保持旗袍版型、短袖、盘扣和开衩不变，把衣身改成深蓝色，花纹保留金色。实际修改已有模型并重新导出，不要从头新建，也不要只改文字。

同样的工具也可以接收“做一个带把手的陶瓷杯”“设计一把弧形靠背椅”“做低多边形风格展台”等需求。选择合理概念默认值并说明，有关键歧义时澄清；复杂任务先做可检查首版，再逐步修正。结果见PNG和真实文件，不以文字描述替代模型。

旧收纳盒的历史文件仍保留；新通用会话使用独立源场景和版本。模型不会自动关联SKU、认证、价格或现有报价目录；商务报价继续用现有外贸插件。

## 执行、文件和恢复

中文需求 → 当前模型/技能 → 当前账号/会话绑定的stdio工具 → 版本检查 → 全局非阻塞锁 → 独立bubblewrap文件系统中的Blender/Xvfb → 上游MCP执行动态bpy → 实际场景检查 → 打包贴图并保存不可变源场景 → 导出/真实渲染 → 格式/大小/归属检查 → Hug原文件下载 → 浏览器。

- 仅挂载本次工作目录到/workspace，以及只读的Blender、固定addon、启动脚本和系统库；**不挂载宿主/home、Windows盘、私有源码、数据库、密钥或其他会话目录**。环境变量清空，只传运行必需值。
- 新代码基于当前保存的.blend复制件操作，执行失败/超时不会覆盖已接受源场景。成功保存新revision与历史快照，第二轮读取旧场景，保留对象、UV和贴图；后端重启后仍可恢复。
- 状态在app-home/blender/sessions/<账号+会话哈希>/general/scene.json，源场景在versions/，每次运行工作区在operations/。这些都不进Git。
- 上游安全模式阻止os/sys/subprocess/socket、eval/exec/open、驱动/定时器/插件注册等执行逃逸；这是执行边界，不是建模品类限制。禁用自动脚本执行和遥测，MCP只绑定loopback。
- 多请求串行；引擎忙/参数错/旧revision/缺文件/执行失败都明确返回错误，不假称成功。脚本错误保留具体原因供模型修正；无bubblewrap不回退到宿主执行。
- 原图1024×768、GLB和Blend都发布到当前账号原文件接口。匿名401、其他账号403；历史版本不覆盖。下载字节SHA256和回执一致。
- 模型服务或网络不可用会影响中文理解/编写代码；本地引擎可用不代表外部模型永不失败。一次失败应保留版本并重试或更换可用模型。

## 固定依赖与开源来源

Blender5.2.3 LTS Linux压缩包来自官方镜像，先核对 [官方SHA256清单](https://mirror.blender.org/release/Blender5.2/blender-5.2.3.sha256) 再解压。SHA256：78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec。

MCP for Blender2.2.6 / SDK1.30.0在独立 .runtime/blender-mcp-venv 中，不降级HugAgent SDK2。上游addon对应提交992233bb258975a05eec8b5691465c50c2831e34；SHA2566c2917c157c26d7549adcbd480243db2154a9b06bc580664f090530c8ef3801f。Blender GPL-3.0-or-later、上游MCP MIT；依赖包保留各自许可证，二进制不提交。保留 HugAgentOS 与 Blender 署名。

## 验证

```bash
.venv/bin/python -m pytest tests/test_blender_general.py tests/test_blender_integration.py tests/test_blender_file_access.py -q
```

单元/HTTP测试与真实引擎、浏览器验收分别记录，见 [验收记录](BLENDER_ACCEPTANCE_20261031.md)。
