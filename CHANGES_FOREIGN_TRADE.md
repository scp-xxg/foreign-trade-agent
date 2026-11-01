# foreign-trade-agent changes

This public derivative is based on ZJU-REAL/HugAgentOS Community Edition
`desktop-v1.0.2`, commit `d16a09be1e408c1acf3ef6ff89523cda1341ef41`.
The original LICENSE, NOTICE and Git history are retained.

On 2026-10-28 this public derivative was synchronized with upstream main
`d969492ffb77819a48b34d948b1993a4fc99809b` (2026-10-27). Old core patches that
are covered by upstream are replaced by the corresponding upstream modules.

## Added by the foreign-trade-agent contributors (2026-10-21)

- Synthetic eight-SKU product catalog and deterministic Decimal quotation tools.
- Inquiry-to-quote skill, local MCP service and repeatable per-account installation.
- Foreign-trade homepage, example questions and assistant instructions.
- Bilingual PDF / Excel exports from validated calculation snapshots.
- Stable quotation identifiers and read-back/export regression checks.
- Team setup, isolated data directories, deployment documentation and CI.
- Scenario-one inquiry workspace: owner-scoped persistence, bounded public website/GLEIF evidence, grounded AI extraction, bilingual draft replies and follow-up tasks.
- Scenario-two product content workspace: bounded document/photo uploads, confirmed source facts, AI English fact translations, listing/FAQ drafts, original-photo layouts, provenance-preserving downloads and an attributed Raspberry Pi 5 public example.
- Version 0.2.0 chat-first trade plugin: three skills, authenticated native inquiry/content tools, activation and cross-turn restoration, attachment import and version-checked content download cards. Existing workspaces remain auxiliary views of the same records.

## Public framework fixes

- Normalize text-only model messages for compatible model endpoints.
- Give model tool calls unique response identifiers across turns.
- Restore per-user local plugin capabilities in follow-up turns.
- Use the actual sandbox Python interpreter instead of a fixed environment path.
- Allow isolated team installs to skip repository environment files.
- Extend progressive plugin activation to stage authenticated native tools together with skills/connectors; retain the execution-surface refresh and plugin gates. The activation checkpoint regression fixture explicitly summarizes its short history instead of retaining all of it.
- Reject malformed JSON before trade business writes and require full skill loading with current user enablement. Use non-streaming completion only for requests containing these stateful trade tools to avoid a verified compatible-gateway streamed-argument defect; ordinary requests keep their configured transport.
- Match persisted and live tool results by call ID before legacy name fallback, preventing concurrent same-name operations from exchanging receipts.
- Stop with an explicit incomplete-run error when context summarization fails, preserving the original context and committed tool results instead of manufacturing a successful placeholder summary.
- Correct package license metadata to reference the full existing LICENSE.

Source files changed from the upstream baseline carry a modification notice.
The repository name is `foreign-trade-agent`; the application brand is SailAgent. Model credentials, accounts, databases and conversations
are local deployment state and are not distributed.

## Public synchronization and collaboration (2026-10-28)

- Adopt the new AgentScope/MCP 2.x runtime, module layout, application registry and frontend architecture.
- Move trade services to core/foreign_trade; migrate authenticated native tools and preserve strict arguments, skill visibility and record ownership.
- Add four-skill/seven-native-tool plugin 0.3.0 with source-versioned role coordination, human review and guarded internal handoff downloads.
- Add explicitly synthetic DESK-001 source material for a single-order demonstration, separate from the real Raspberry Pi example.
- Add snapshot-first local SQLite upgrades, legacy model protocol preservation and explicit non-deleting duplicate filename repair.
- Validate real MCP 2.x queries and quotations and preserve existing bilingual exports. Runtime and real-model acceptance are recorded separately from automated checks.
- Add explicit no-model template mode for confirmed English product facts; include public demo sources and licenses in the plugin archive.
- Preserve the stored provider protocol in AI helper calls using the upstream resolved configuration contract.

## Team handoff and main deployment (2026-10-29)

- Document main-branch setup, existing-instance updates, old-database migration order and concrete three-scenario demonstrations.
- Keep no-model workbench demonstrations separate from model-dependent chat acceptance.
- Make the quick-check command select explicit unittest suites and the configured Python environment; retain full business regression in CI.
- Include the deployment and walkthrough guides in the public plugin archive.

## Hackathon readiness and sourced review (2026-10-31)

- Add versioned SQLite rule knowledge and immutable owner-scoped localization reviews for Alibaba RFQ and Amazon US non-media listings, with text annotations, risk labels, source-bound exports and two-round comparison.
- Upgrade the trade package to 0.4.0 with five skills and eight authenticated native business tools.
- Repair imported-plugin identity, device-registry skill activation across turns, full-read identity and error projection; preserve strict authorization.
- Detect failed/incomplete Responses streams, preserve cancellations and avoid duplicate reasoning replay.
- Tighten per-SKU inquiry extraction, review source/role requirements, and concurrent export checks; retain explicit unknown commercial terms.
- Support configurable loopback web ports, explicit Chinese build defaults, required chat model context windows, historical inquiry receipts, stable record URLs and English demo CSV downloads.
- Add scenario scripts and offline regression coverage; actual runtime acceptance is recorded separately.

## 2026-10-31 · 本地私有知识库

- 在独立本地模式下接通私有知识库入口，保留账号归属与其他应用的可用性边界。
- 修复社区版建库/更新字段、Wiki 路由注册与知识地图接口；缺少 embedding 时默认 Wiki，写入前明确检查模型能力。
- 将索引类型传入对话与连接器，Wiki 定位后读取原文，避免误用向量检索；模式修改会刷新提示缓存。
- 增加旧管理员的显式建库配置脚本、数据备份与审计；不覆盖其他权限。
- 增加隔离测试、真实网页上传示例与操作文档。

## 2026-10-31：Blender MCP 概念打样插件

- 新增独立 foreign-trade-blender 插件0.2和 product-3d-sampling 技能，复用 HugAgent 原生插件生命周期、会话身份和文件下载。
- 固定 Blender 5.2.3 LTS、MCP for Blender 2.2.6，隔离 SDK1/SDK2；通用动态bpy、场景持久化、多轮局部修改、真实GLB/PNG/Blend导出及渲染图反馈。没有物体类别白名单。
- 动态代码运行于仅挂载本次场景的bubblewrap文件系统；宿主私有源码、数据库、密钥和其他会话不挂载。GLB导出兼容网格、曲线、文字等几何并保留可编辑源对象。
- 增加场景边界、版本冲突、账号/会话、隔离、导出校验测试与部署说明；真实验证花纹旗袍两轮改稿，不更改报价目录，不包含私有源代码。

## sailagent branding (2026-10-31)

- Adopt the lowercase public product name sailagent with original sail/route SVG, PNG, ICO and loading assets.
- Update public UI, login, browser metadata, assistant identity and new quotation export headings; retain Powered by HugAgentOS, LICENSE and upstream NOTICE.
- Add an explicit, idempotent public-home brand migration with a limited brand-field snapshot; retain authored business copy, data, model configuration and previous prompt versions.
- Validate the public extension suite (617 passed), CE frontend build, quotation export regressions (15 groups), two branding checks and actual Chrome login/homepage. See docs/SAILAGENT_BRAND.md for scope and pre-existing upstream navigation-test failures.
## 2026-10-31 潜在买家搜索（0.5.0）

新增 trade-buyer-search 技能和当前会话绑定的 trade_buyer_search 工具；新增认证计划/运行 API 与 /trade-buyers 工作台、导航默认值和旧配置补齐。复用真实搜索服务及受限公网读取器，支持画像导入、域名去重/排除、预算停止、来源与日志导出、人工标签及明确分母的效果指标。未知语义条件保留待核实，身份和采购意向不推断。页面结果临时保留，未接入费用账单；聊天与工作台无共享搜索记录。不涉及邮件发送或自动成交。

## 2026-10-31 四阶段获客工作流

- 将前四个获客技能加入内置目录，能力中心自动补入；外贸插件0.6.0包含9个技能、10个业务工具。
- 实现认证画像草案、公开证据背调、同域公开邮箱/联系页发现接口；未知身份、岗位和投递情况不推断为验证通过。
- 对话工具栏新增“获客”，打开画像确认→搜索→背调审核→渠道发现，支持完整 JSON 导出、旧结果失效和明确指标分母。
- 详细流程、预算、指标和当前能力范围见 docs/ACQUISITION_WORKFLOW.md。

- 2026-10-31：增加线索评分与跟进优先级、个性化开发信两个内置/插件技能，认证API与聊天工具；前端六阶段流程、证据评分、优先级队列、英文事实模板草稿及人工批准与导出，不发送。

## 2026-10-31：第七/第八技能与对话客户跟进工作流

- 新增「跟进节奏规划」及「客户回复识别与分流」，包含证据契约、人工确认、未校准指标及停止规则，加入插件和能力中心。
- 新增认证cadence/reply-triage接口及聊天工具动作，按完整记录计算，任何回复暂停，退订/拒绝/退信停止；无自动发送和后台调度。
- 对话新增互斥「客户跟进」开关，组合第四、第五、第七、第八技能，支持普通和排队消息，保留按聊天/账号隔离。
- 详见docs/FOLLOWUP_WORKFLOW.md；默认时区工作日与3/7/14天节奏为待校准建议，当前计算无持久化。

## SailAgent final integration (2026-11-01)

- Merge Max-channel acquisition/follow-up skills, discovery, account management and reviewed marketplace workflow while retaining the public trade and 3D integrations.
- Connect the same DESK-001 inquiry to its product-content pack, versioned review and role tasks through the sales-to-listing skill; keep files, facts and prices grounded.
- Persist account-scoped acquisition checkpoints with revision guards and ft_0001 migration; add browser marketplace review and explicit member agent permissions.
- Fix ambiguous same-name marketplace clones and missing device-plugin binding options without sharing private knowledge or credentials.
- Verify 697 public/selected compatibility tests, frontend build, quote export regressions, real multi-round conversation, Wiki original-source reasoning and browser file downloads. See docs/FINAL_DEMO_20261101.md for score mapping, reproducible prompts and configured-service limits.

## 客户背调四技能

新增企业身份、业务采购匹配、联系人决策链核验、交易风险四技能与受认证接口，接入聊天逐技能权限检查。对话框以客户背调替代客户跟进，保留原跟进技能。报告区分真实公开读取、输入证据关联与未查询来源。详见 docs/DILIGENCE_WORKFLOW.md。
