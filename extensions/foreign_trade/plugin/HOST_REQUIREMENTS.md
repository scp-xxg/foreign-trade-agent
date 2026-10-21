# Host requirements for foreign-trade-demo 0.2.0

This package targets the public scp-xxg/foreign-trade-agent fork of HugAgentOS.
Keep the installed plugin slug foreign-trade-demo when upgrading.

The existing loopback MCP at http://127.0.0.1:9120/mcp still provides exactly
search_products, get_product and calculate_quote for the synthetic catalog.
The ZIP includes that legacy standalone quotation runtime.

The buyer-inquiry-followup and product-content skills additionally require this
fork's authenticated native trade_save_inquiry, trade_import_product,
trade_confirm_product_facts, trade_inquiry, trade_calculate_quote and
trade_product_content adapters, database services, attachment checks and result
cards. They are injected only for the visible, active plugin and are bound to
the current conversation user. They are NOT HTTP MCP tools on port 9120.
Do not expose them by accepting a user_id supplied by a model or by embedding
database credentials, browser sessions or per-user tokens in this package.

Upgrade the fork source and install dependencies/build the web client, then
reinstall this package for each intended local account. A ZIP-only import into
an unmodified upstream HugAgentOS installation does not provide those adapters.
Use the repository docs/CHAT_PLUGIN.md or bundled CHAT_PLUGIN.md for the full
workflow and upgrade instructions.

Keep the original HugAgentOS attribution and license. Public buyer/company
evidence, synthetic quote data and licensed product photographs have different
sources and must remain clearly identified. Nothing in this package sends email,
publishes product listings or executes purchases/payments.
