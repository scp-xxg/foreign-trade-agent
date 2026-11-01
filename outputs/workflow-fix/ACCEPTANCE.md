# 八个工作流共性故障修复与验收

日期：2026-11-01。真实聊天： http://localhost:3001/c/chat_20261101_125502_vqsd0s

## 修复

- 默认技能选择纳入当前用户拥有、就绪且启用的本地插件实际技能 ID，修复导入名称后缀造成的 skill_not_loaded；保留权限、禁用和完整读取检查。
- 开启任一工作流时清除旧的技能、插件、连接器、智能体及命令选择，避免旧调用目标限制新流程。
- 八个工作流统一要求加载实际插件，并通过 view_text_file 读取该安装的技能，避免读取同名内置副本或使用 cat 导致未登记完整读取。
- 发品和资料检查保留 skill_not_loaded 的 409 错误与可恢复提示，不再误报为输入格式错误。

## 自动验证

- 111 项后端相关测试通过，包括八个业务领域、导入插件、默认选择、权限撤销和渐进加载。
- 新增阶段矩阵：实际导入 50 个技能，覆盖八类工作流的阶段调用及资料检查，执行两轮，验证每轮读取门槛、真实业务分派与禁用后的拒绝。
- 前端脚本验证八类开关、互斥、队列快照、草稿隔离、旧调用选择清除及统一加载提示，通过。
- 前端完整 build 和 git diff --check 通过。

## 浏览器验证

- 八类菜单入口已逐一点击，正确显示对应 Active 开关，未跳转到不存在的应用。
- 获客 profile：实际工具 ok=true，profile_id=profile-455d5d128a4b5b95，status=draft。首次读取内置副本被拒绝后读取指定插件版成功；随后补充统一加载指引。
- 其余七类最小阶段案例已在同一真实聊天依次完成，逐项展开工具回执确认 ok=true；此次没有技能加载失败或 cat 调用。

| 工作流 | 实际 action | 业务 status |
|---|---|---|
| 背调 | identity-check | insufficient_data |
| 沟通 | clarify | needs_clarification |
| 谈单 | negotiation-strategy | review_required |
| 复盘 | deal-timeline | draft_review_required |
| 成交 | closing-readiness | needs_rules |
| 发品 | normalize | needs_products |
| 采购 | requirements | needs_input |

发品 input_hash：d30b9e306b2770057ce91dc153f8cff3b8245393f8d3b81bfcd734ac55de519a。
采购最小输入 input_hash：5a977797bfd71b03ab7c3e922c1d67aa7f191a71b0736ab6439e4af859578542。

模拟数据仅用于检查调用与缺项反馈，不代表真实客户、订单或完整业务流程完成。可展开回执摘录见 live-tool-evidence.txt。

## 验证范围

自动阶段测试不代替真实模型端到端业务验收；本轮不联系客户、不发布商品、不下单、不付款。外部搜索、图片处理、正式合同与支付集成不在本轮最小调用验收范围内。

## 有数据的两轮续聊

同一模拟采购案 UI-PROC-20261101，两轮真实 requirements 调用均 ok=true、status=review_required。

| 输入 | 工具净量 | input_hash |
|---|---|---|
| 需求100，库存20，在途10，安全5，v1 | 75 pcs | 1856baa7e08396d9b63cbf22f324ed7b3ac76bd3122ec07eeb50f9eba7b2d7ee |
| 需求120，其余库存不变，v2 | 95 pcs | cf69572803b37974f8a8f36246e3adf502e40e5b1761fdb02971a0843d56207f |

已展开两次工具回执核对，见 procurement-two-turns.txt 和 frontend-success.png。最小案例验证并非八个完整业务流程的全阶段人工验收。

## 新对话获客实测：修复前未通过（2026-11-01）

聊天：http://localhost:3001/c/chat_20261101_151341_mwgknu

通过前端新建独立对话、开启 Find buyers，并发送用户原始虚构供应商资料（500ml/304、MOQ500、颜色MOQ1000、月产50000、FOB USD4.5–6、30–40天、食品接触报告覆盖与有效期未知）。

开关为 Active；load_plugin 成功，回执列出 trade_buyer_research、trade_buyer_search 等工具，但未列出实际技能 ID 或 SKILL.md 路径。模型据此停止并要求用户提供技术路径，没有调用 profile 或 search。它同时追问目标市场、买家类型、候选数量及排除条件。

结论：前述已有聊天的阶段回归通过不能证明新聊天首次启动通过。本次新对话获客未通过，应修复技能发现/加载回执与工作流提示之间的断点，不能要求商家提供内部路径。截图：acquisition-new-chat.png。未进行客户搜索或对外发送。

## 新对话缺陷修复进展（2026-11-01 15:46）

1. 默认目录解析：聊天入口 resolve_all_runtime_enabled 已经把默认技能解析成列表，导致工厂中仅在 None 时执行的插件技能补全不生效。现在在统一默认目录解析处补全当前用户已授权的实际插件技能，且在 TTL 缓存之外执行，避免禁用后继续提供旧授权。显式请求列表不经过这一补全入口。
2. 延迟加载后的读取：skill_registration 原先只给启动时立即加载的技能设置文件目录白名单，插件延迟加载后虽然路径正确，view_text_file 仍拒绝读取。现在白名单涵盖当前运行已冻结的技能绑定；读取工具继续逐次核对绑定、所有权、禁用状态及实际路径，不开放整个能力根目录。

新增回归从聊天默认目录缓存开始，经过实际插件解析、运行冻结、延迟加载、返回路径和真实 view_text_file 读取，确认完整读取标记、越界拒绝和插件禁用后的拒绝。

验证结果：
- 42 项导入业务工具/渐进插件测试通过。
- 31 项冻结绑定/技能路径别名/可用运行测试通过。
- 额外目录检查 28 项通过、3 项失败；将本次修改的 resolver 替换为 HEAD 版本在测试进程中对照，仍出现相同 3 项失败（hybrid 本地插件筛选、两项无 revision 的插件详情测试）。未将这组测试宣称为全部通过。
- git diff --check 通过。

前端中间复测聊天：http://localhost:3001/c/chat_20261101_154251_3morne 。用户原始案例成功加载了 50 个实际插件技能的目录，六次 view_text_file 已发起，暴露了第 2 项读取白名单缺陷。第 2 项修复已部署，但再次重启使登录会话失效；最终新对话真实读取验收等待用户重新登录。此时不能声称前端端到端验收完成，也没有进行买家搜索或对外发送。

## 最终新对话前端验收：启动与读取通过（2026-11-01 15:53）

用户重新登录后，在前端新建对话并开启 Find buyers，发送完全相同的保温杯虚构测试资料。
聊天：http://localhost:3001/c/chat_20261101_155053_6wd4he

- load_plugin 成功；逐一展开六项技能卡，均显示 Skill Loaded：trade-customer-profile、trade-buyer-search、trade-buyer-due-diligence、trade-buyer-contact-discovery、trade-lead-prioritization、trade-personalized-outreach，实际 ID 均带 -c01d3b 后缀。
- 实际调用 trade_buyer_research 返回 ok=true；profile_id=profile-62e7932b14ef5572，version=1，status=draft，cite_id=e3。
- 工具结果保留虚构测试声明及用户原始供货条件，目标市场和买家类型为空，食品接触报告适用范围及有效期标记 unknown，未宣称已验证合规。
- 前端正常展示业务追问卡（1/3）：请提供1–2个目标国家或地区。没有再要求商家提供内部路径，也没有 Access denied / skill_not_loaded 阻断。
- 停在真实缺失业务输入节点，未代替用户选择市场；买家搜索及后续阶段尚未执行。本次证明新对话启动、六技能读取、客户画像调用与追问交互通过，不代表完整获客全阶段已经完成。

证据：acquisition-fresh-chat-passed.png、acquisition-fresh-chat-passed.txt。沿用上轮73项相关回归结果，本轮未修改业务代码。
