# Host requirements for foreign-trade-demo 0.4.0

This package targets the public scp-xxg/foreign-trade-agent fork of HugAgentOS.
Keep the installed plugin slug foreign-trade-demo when upgrading.

The existing loopback MCP at http://127.0.0.1:9120/mcp still provides exactly
search_products, get_product and calculate_quote for the synthetic catalog.
The ZIP includes that legacy standalone quotation runtime.

The package contains five skills: inquiry-quote, buyer-inquiry-followup,
product-content and cross-role-collaboration. The latter three require this
fork's seven authenticated native tools: trade_save_inquiry, trade_inquiry,
trade_calculate_quote, trade_import_product, trade_confirm_product_facts,
trade_product_content, trade_collaboration and trade_review. The host must include their
database services, attachment checks, authenticated APIs and result cards.
These tools are injected only for a visible, active plugin in an eligible
writable conversation and are bound to its authenticated user. Required skills
must be enabled and read before business writes. They are NOT HTTP MCP tools
on port 9120; the three catalog MCP tools are separate from the eight native tools.
Do not expose them by accepting a user_id supplied by a model or by embedding
database credentials, browser sessions or per-user tokens in this package.

Upgrade the fork source with matching dependencies, migrate its existing data
and build the web client, then reinstall this package for each intended local
account. Use the repository's supported deployment/upgrade process and keep
its private recovery snapshot; do not substitute a ZIP import for schema or
source upgrades. A ZIP-only import into unmodified upstream HugAgentOS does not
provide these adapters. See repository docs/TEAM_SETUP.md and docs/CHAT_PLUGIN.md
(also bundled as CHAT_PLUGIN.md) for installation and conversation use.

Scenario three stores one current-user coordination record with six tasks for
sales, procurement, design, operations and compliance. Assignees are descriptive
role/name labels, not shared-account ACLs, invitations or delivery recipients.
The same user records explicit human acceptance after inspecting each task's
artifacts, criteria and unresolved items. Task creation, fact confirmation,
content generation and task acceptance are distinct operations. Only the review
action can mark a task done; required dependencies cannot be removed.

When no content pack is supplied, automatic preparation currently supports one
DESK-001 item line only. The installed foreign_trade Python package must retain
demo_product/desk-001-demo-specs.csv, desk-001-demo-schematic.png and
desk-001-demo-sources.json. These contain fictional catalog facts, a program-drawn
geometric illustration (not an actual product photograph), source declarations
and SHA256 checksums. Creation imports unconfirmed candidates and never generates
or accepts content. Other products can leave preparation disabled and later use
trade_collaboration's link_content action to attach an existing user-owned pack.

A transaction relationship requires the same synthetic catalog SKU binding.
Raspberry Pi 5 facts/photos and other external product packs are independent_reference
material only; they must not become DESK specifications or receive DESK prices.
Changing source facts, quotes, files or generated outputs invalidates affected
acceptances and downstream tasks. refresh_sources binds the current source
snapshot but does not re-approve tasks. link_content also invalidates affected
acceptances. Explicit per-task review remains required.

The host provides authenticated Markdown and JSON handoff downloads only when
all six tasks are currently accepted. Downloads bind to the requested revision,
recheck original files and reject obsolete/concurrently changed revisions with
409. Unresolved conditions may remain in an explicitly reviewed internal handoff;
readiness is not authorization to ship, publish or claim regulatory compliance.
See repository docs/SCENARIO_THREE.md for the complete simulated LYRECO/DESK
example and the tool/API contract. No browser or CI acceptance result is implied
by the presence of this package.

Keep the original HugAgentOS attribution and license. Public buyer/company
evidence, synthetic quote data and licensed product photographs have different
sources and must remain clearly identified. Nothing in this package sends email,
publishes product listings or executes purchases/payments.

Version 0.4 additionally requires owner-scoped ForeignTradeReview and versioned ForeignTradeKnowledgeRule tables, the authenticated review API, the trade_review native adapter, and revision/source-checked report cards. Importing only this ZIP into an unmodified upstream host does not install these backend/frontend features.
