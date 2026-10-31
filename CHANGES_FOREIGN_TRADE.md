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
The temporary repository name is `foreign-trade-agent`; product renaming and a
new logo are deferred. Model credentials, accounts, databases and conversations
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
