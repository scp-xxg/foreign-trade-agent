# foreign-trade-agent changes

This public derivative is based on ZJU-REAL/HugAgentOS Community Edition
`desktop-v1.0.2`, commit `d16a09be1e408c1acf3ef6ff89523cda1341ef41`.
The original LICENSE, NOTICE and Git history are retained.

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
