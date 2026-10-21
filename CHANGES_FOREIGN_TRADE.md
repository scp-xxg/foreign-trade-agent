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

## Public framework fixes

- Normalize text-only model messages for compatible model endpoints.
- Give model tool calls unique response identifiers across turns.
- Restore per-user local plugin capabilities in follow-up turns.
- Use the actual sandbox Python interpreter instead of a fixed environment path.
- Allow isolated team installs to skip repository environment files.
- Correct package license metadata to reference the full existing LICENSE.

Source files changed from the upstream baseline carry a modification notice.
The temporary repository name is `foreign-trade-agent`; product renaming and a
new logo are deferred. Model credentials, accounts, databases and conversations
are local deployment state and are not distributed.
