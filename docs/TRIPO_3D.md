# 高质量云端3D生成接入（Tripo）

公开项目新增 foreign-trade-tripo 插件，使用官方 tripo-cli0.8.0 驱动真实云端生成；保留原有通用Blender插件。工具不按物体类别设白名单，支持服装、产品等单张参考图或文字输入。当前默认H3.1/PBR/详细贴图/12万面/单候选。

## 账号与额度

Tripo网页Studio积分和API积分不共享。必须验证API账号余额及实际可用预算；注册、密钥创建不代表试用积分已到账。新用户赠送策略以实际账号后台为准，不能把宣传文案当作已领取额度。

密钥只交由官方CLI保存在本机公开应用的数据目录，按Hug账号隔离：app-home/tripo/accounts/<账号哈希>。不写源码、插件包、模型参数或Git；环境中已有全局TRIPO_API_KEY等值不会被本插件误用。默认关闭CLI遥测。模型只看到余额/授权预算，不会得到密钥。

## 队友部署

先按 [团队部署](TEAM_SETUP.md) 建好公开应用和账号，按 [Blender部署](BLENDER_MCP.md) 准备本地隔离渲染依赖。Node.js需20+，推荐项目使用的22LTS。

```bash
.venv/bin/python extensions/tripo/manage.py setup --app-home "$HOME/.foreign-trade-agent" --node "$(command -v node)"
.venv/bin/python extensions/tripo/manage.py install --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME
# 在自己的交互终端运行；cn是国内站，ov是国际站，必须与注册站点一致
.venv/bin/python extensions/tripo/manage.py login --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME --region cn
```

setup只在公开checkout的.runtime安装锁定CLI及依赖，不改全局Codex或其他项目配置。登录在官方网页完成，不能把验证码、密钥发送给模型。账号密码、模型配置、3D积分不会随Git同步。

维护者确认免费积分实际到账后，按本次用户明确要求设置有限预算，例如一个40积分任务：

```bash
.venv/bin/python extensions/tripo/manage.py grant-free-budget --app-home "$HOME/.foreign-trade-agent" --username YOUR_USERNAME --credits 40 --jobs 1 --verified-trial
```

只有用户明确同意付费、并自行完成充值后，才可使用同一命令的 --authorized-paid 替代 --verified-trial。两种标志必须二选一，付费预算不会被标成免费额度。预算24小时过期，不能由模型在工具参数里提高；本插件不提供充值或开通自动扣款工具。

## 对话流程

1. 用户上传有权使用的服装/产品参考图，或给文字需求。参考链接用于核对款式，付费原始模型不自动下载或购买。
2. tripo_prepare_asset：读取当前账号拥有的file_id，复制到当前计划目录，调用官方CLI dry-run。返回真实参数、plan_id、估算积分；不上传、不创建云端任务、不扣积分。
3. tripo_account_status：验证当前账号API登录、余额、本次有限预算。额度/权限不足时停在这里。
4. tripo_submit_asset：只提交该plan一次，保存task_id。重复调用复用原任务，不按模型的“重试”指令再次创建。
5. tripo_asset_status(wait=true)：等待/查询同一任务，完成后立即下载GLB；签名下载URL不作为对话结果保存。下载/渲染失败仅重试交付，不重新生成。
6. 真实GLB通过文件结构、网格、内嵌资源校验后，复制到隔离Blender工作区导入、实渲染并保存Blend。发布原始Tripo GLB、匹配的渲染PNG和可编辑Blend；同时插入原有Artifact数据库，保留当前账号与会话归属，供下一轮读取/下载。

产品示例：

> 请使用高质量3D生成插件，把我上传的香槟米金提花旗袍参考图生成一个PBR三维外观模型。先预检积分与账号预算，在本次已授权预算内只生成一次，完成后展示实际网格渲染图与GLB/PNG/Blend下载。不要用参考图冒充生成结果。

第二轮：

> 查询同一个计划的进度。生成完成就交付，超时继续等待原任务，不要重新扣积分创建。

局部几何/颜色改稿可在完成后转给现有Blender通用工具；再次云端生成需新的明确意图与预算，不能把重生成说成精确保留旧网格的局部修改。

## 任务和异常

- 计划按账号+会话隔离，JSON原子写入 app-home/tripo/jobs/<账号会话哈希>/<plan_id>。
- 账号非阻塞锁保护预算/任务，提交前先预留本次预算并记录submitting。网络超时保留submission_unknown，不自动重复创建；可按唯一计划名从官方CLI历史恢复task_id。
- prepared、submitted、processing、rendering、completed分开；提交成功不等于生成完成。
- 服务明确拒绝输入/认证/余额时恢复本地预留预算；不确定结果不恢复并重发。云端失败、交付待重试均如实返回，不能伪造成功或拿已有模板替换。
- 凭据不进入模型参数。工具身份来自Hug CURRENT_USER_ID/CURRENT_CHAT_ID，每次验证会话归属及正式安装实例启用状态。
- 每个输出都具有Artifact数据库行与原文件接口归属，使用原有下载鉴权；用户生成结果、密钥、额度、日志及参考图不随源码提交。
- 图片转3D会推测不可见表面；服装输出是视觉网格，不是生产纸样、合体结果或布料物理仿真。应查看真实模型后评价画质。

## 本轮参考与验证边界

用户指定的参考商品：[Qipao-Cheongsam](https://connect.clo-set.com/detail/75d34f3dcfaa40dc91d297eaa08555f0)。公开预览为米金色修身提花旗袍；本轮重新制作原创2D概念参考图，没有购买、下载或导入其付费原始3D文件。2D参考图不是已生成的3D结果。

已完成：官方CLI安装与身份验证、真实参考图读取与dry-run（40积分）、正式Hug插件安装、真实对话调用账号/计划查询并正确停在0余额状态、任务预算/去重/未知提交不重发/文件边界的离线测试。API初次验证余额为0，尚未提交扣额任务；后续是否生成须以实际额度与用户决定为准，不能把离线测试写成云端生成成功。

```bash
.venv/bin/python -m pytest tests/test_tripo_generation.py -q
```

官方来源：[CLI文档](https://developers.tripo3d.com/zh/docs/cli)、[计费](https://developers.tripo3d.com/zh/docs/billing)、[官方CLI仓库](https://github.com/vast-enterprise/Tripo-API-CLI)。
