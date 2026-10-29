import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import * as XLSX from 'xlsx';

import type { ToolCall } from '../src/types';
import { extractTradeQuotes, type TradeQuote } from '../src/utils/foreignTradeQuote';
import { buildTradeQuoteHtml, buildTradeQuoteWorkbook, quoteFilename } from '../src/utils/foreignTradeQuoteExport';

// Generate fixtures from the real public engine. No model, service, database,
// browser, or filesystem output is required for this regression check.
const root = resolve(process.cwd(), '../..');
const python = process.env.FOREIGN_TRADE_TEST_PYTHON || resolve(root, '.venv/bin/python');
const fixtures = JSON.parse(execFileSync(python, ['-c', `
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'extensions'))
from foreign_trade.engine import calculate_quote
base = [{"sku": "DESK-001", "quantity": 500}]
revised = [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}]
print(json.dumps({
    "base": calculate_quote(base, "Spain"),
    "same": calculate_quote(base, "Spain"),
    "revised": calculate_quote(revised, "Spain"),
    "deadline": calculate_quote(revised, "Spain", 10),
    "missingDestination": calculate_quote(base),
    "invalid": calculate_quote([{"sku": "DESK-001", "quantity": 1}], "Spain"),
    "multiple": calculate_quote([{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}, {"sku": "DESK-002", "quantity": 500}], "Spain"),
}))
`], { cwd: root, encoding: 'utf8', timeout: 10000 }));

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const call = (output: unknown, extra: Partial<ToolCall> = {}): ToolCall => ({
  name: 'foreign_trade.calculate_quote', status: 'success', output, ...extra,
});
const extract = (output: unknown, extra: Partial<ToolCall> = {}) => extractTradeQuotes([call(output, extra)]);
const one = (output: unknown): TradeQuote => {
  const result = extract(output);
  assert.equal(result.length, 1);
  return result[0];
};
let cases = 0;
const test = (name: string, run: () => void) => {
  try { run(); cases++; } catch (error) { throw new Error(`${name}: ${String(error)}`, { cause: error }); }
};

test('real engine standard/custom quote totals and revision identity', () => {
  const base = one(fixtures.base), revision = one(fixtures.revised);
  assert.equal(base.data.subtotal, '2400.00');
  assert.equal(revision.data.merchandise_subtotal, '4800.00');
  assert.equal(revision.data.packaging_subtotal, '300.00');
  assert.equal(revision.data.subtotal, '5100.00');
  assert.equal(one(fixtures.same).quoteId, base.quoteId);
  assert.notEqual(base.quoteId, revision.quoteId);
  assert.notEqual(one(fixtures.deadline).quoteId, revision.quoteId);
});

test('MCP structured/text/string/result wrappers are accepted', () => {
  for (const output of [
    fixtures.base,
    JSON.stringify(fixtures.base),
    { structuredContent: fixtures.base },
    { content: [{ type: 'text', text: JSON.stringify(fixtures.base) }] },
    { result: { content: [{ type: 'text', text: JSON.stringify(fixtures.base) }] } },
    [{ type: 'text', text: JSON.stringify(fixtures.base) }],
    { output: JSON.stringify(fixtures.base) },
  ]) assert.equal(one(output).quoteId, fixtures.base.data.quote_id);
});

test('tool namespaces accepted while unrelated tools are rejected', () => {
  for (const name of ['calculate_quote', 'foreign_trade.calculate_quote', 'mcp:foreign_trade:calculate_quote', 'mcp_foreign_trade_calculate_quote']) {
    assert.equal(extract(fixtures.base, { name }).length, 1);
  }
  for (const name of ['get_product', 'recalculate_quote', 'calculate_quote_text', 'bash']) {
    assert.equal(extract(fixtures.base, { name }).length, 0);
  }
});

test('failed/interrupted/running and incomplete results are never exported', () => {
  for (const status of ['pending', 'running', 'error', 'interrupted'] as const) {
    assert.equal(extract(fixtures.base, { status }).length, 0);
  }
  assert.equal(extract(fixtures.invalid).length, 0);
  assert.equal(extract({ isError: true, structuredContent: fixtures.base }).length, 0);
  assert.equal(extract(fixtures.base, { outputTruncated: true }).length, 0);
  assert.equal(extract(fixtures.base, { outputTruncated: true, outputLoaded: true }).length, 1);
  assert.equal(extract(JSON.stringify(fixtures.base).slice(0, -10)).length, 0);
});

test('legacy or invalid document markers are rejected', () => {
  for (const field of ['document_type', 'document_version', 'quote_id']) {
    const value = clone(fixtures.base); delete value.data[field];
    assert.equal(extract(value).length, 0);
  }
  const version = clone(fixtures.base); version.data.document_version = 999;
  assert.equal(extract(version).length, 0);
  const wrongKind = clone(fixtures.base); wrongKind.data.document_type = 'product';
  assert.equal(extract(wrongKind).length, 0);
});

test('mismatched line, unit, and order amounts are rejected', () => {
  for (const field of ['unit_price', 'packaging_unit_surcharge', 'effective_unit_price', 'merchandise_subtotal', 'packaging_subtotal', 'line_subtotal']) {
    const value = clone(fixtures.revised); value.data.items[0][field] = '999.99';
    assert.equal(extract(value).length, 0, field);
  }
  for (const field of ['merchandise_subtotal', 'packaging_subtotal', 'subtotal']) {
    const value = clone(fixtures.revised); value.data[field] = '999.99';
    assert.equal(extract(value).length, 0, field);
  }
});

test('duplicate SKUs and untraceable sources are rejected', () => {
  const duplicate = clone(fixtures.base); duplicate.data.items.push(clone(duplicate.data.items[0]));
  duplicate.data.merchandise_subtotal = '4800.00'; duplicate.data.subtotal = '4800.00';
  assert.equal(extract(duplicate).length, 0);
  const source = clone(fixtures.base); source.source.record_refs = [];
  assert.equal(extract(source).length, 0);
});

test('successful snapshot cannot drift when tool output is updated', () => {
  const value = clone(fixtures.base), quote = one(value);
  value.data.subtotal = '9999.99';
  value.data.items[0].quantity = 1;
  assert.equal(quote.data.subtotal, '2400.00');
  assert.equal(quote.data.items[0].quantity, 500);
});

test('deduplication preserves separate quantity and packaging revisions', () => {
  const quotes = extractTradeQuotes([call(fixtures.base), call(fixtures.same), call(fixtures.revised)]);
  assert.equal(quotes.length, 2);
  assert.deepEqual(quotes.map(q => q.quoteId), [fixtures.base.data.quote_id, fixtures.revised.data.quote_id]);
});

function roundTrip(quote: TradeQuote): XLSX.WorkBook {
  const bytes = XLSX.write(buildTradeQuoteWorkbook(quote), { type: 'buffer', bookType: 'xlsx', compression: true });
  assert.ok(bytes.byteLength > 1000);
  return XLSX.read(bytes, { type: 'buffer', cellNF: true });
}

test('Excel round-trip retains bilingual sheets and numeric currency cells', () => {
  const wb = roundTrip(one(fixtures.revised));
  assert.deepEqual(wb.SheetNames, ['中文报价单', 'English Quotation']);
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const values = { C8: 1000, E8: 4.8, F8: 0.3, G8: 4800, H8: 300, I8: 5100, J8: 18, G9: 4800, H9: 300, I9: 5100 };
    for (const [cell, value] of Object.entries(values)) {
      assert.equal(ws[cell].t, 'n', `${name}!${cell} must be numeric`);
      assert.equal(ws[cell].v, value, `${name}!${cell} amount`);
      assert.equal(ws[cell].f, undefined);
    }
    assert.match(ws.I9.z, /USD/);
    assert.ok(XLSX.utils.sheet_to_csv(ws).includes(fixtures.revised.data.quote_id));
  }
});

test('multi-line Excel total is at the correct row', () => {
  const quote = one(fixtures.multiple), wb = roundTrip(quote);
  assert.equal(quote.data.items.length, 2);
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    assert.equal(ws.I10.t, 'n');
    assert.equal(ws.I10.v, Number(quote.data.subtotal));
    assert.equal(ws.G10.v, Number(quote.data.merchandise_subtotal));
    assert.equal(ws.H10.v, Number(quote.data.packaging_subtotal));
  }
});

test('unknown freight remains pending and is never exported as a zero price', () => {
  const quote = one(fixtures.missingDestination);
  assert.equal(quote.data.freight.amount, null);
  assert.equal(quote.data.freight.status, 'pending_confirmation');
  const wb = roundTrip(quote);
  const english = XLSX.utils.sheet_to_csv(wb.Sheets['English Quotation']);
  const chinese = XLSX.utils.sheet_to_csv(wb.Sheets['中文报价单']);
  assert.match(english, /Destination: Pending confirmation/);
  assert.match(english, /Pending: freight/);
  assert.match(english, /freight is not zero/);
  assert.match(chinese, /运费待确认，不等于零/);
  assert.doesNotMatch(english, /Freight(?: price| amount)?:\s*(?:USD )?0(?:\.00)?(?:,|$)/i);
  const html = buildTradeQuoteHtml(quote);
  assert.match(html, /Pending confirmation/);
  assert.match(html, /Freight, taxes, duties/);
  assert.match(html, /freight is not zero/);
});

test('HTML escapes all textual source and product fields', () => {
  const value = clone(fixtures.base);
  const unsafe = `<img src=x onerror="alert('export')"> & </script>`;
  value.data.destination_country = unsafe;
  value.data.items[0].name = unsafe;
  value.data.items[0].name_zh = unsafe;
  value.data.items[0].source.record_ref = unsafe;
  value.source.record_refs = [unsafe];
  value.catalog_version = unsafe;
  value.warnings.push({ code: unsafe, message: unsafe });
  const html = buildTradeQuoteHtml(one(value));
  assert.ok(!html.includes(unsafe));
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('</script>'));
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(&#39;export&#39;\)&quot;&gt; &amp; &lt;\/script&gt;/);
});

test('Excel text beginning with formula syntax remains text after round-trip', () => {
  const value = clone(fixtures.base);
  value.data.items[0].name = '=HYPERLINK("https://invalid.example","sample")';
  value.data.items[0].name_zh = '+1+1';
  const wb = roundTrip(one(value));
  for (const [name, text] of [['中文报价单', '+1+1'], ['English Quotation', value.data.items[0].name]]) {
    assert.equal(wb.Sheets[name].B8.t, 's');
    assert.equal(wb.Sheets[name].B8.v, text);
    assert.equal(wb.Sheets[name].B8.f, undefined);
  }
});

test('PDF source and export filenames retain attribution and revision identity', () => {
  const quote = one(fixtures.revised), html = buildTradeQuoteHtml(quote);
  assert.match(html, /报价单/);
  assert.match(html, /QUOTATION/);
  assert.match(html, /USD 5,100.00/);
  assert.match(html, /模拟数据，非真实商业报价/);
  assert.match(html, /Powered by HugAgentOS/);
  assert.ok(html.includes(quote.quoteId));
  assert.equal(quoteFilename(quote, 'pdf'), `${quote.quoteId}-ZH-EN.pdf`);
  assert.equal(quoteFilename(quote, 'xlsx'), `${quote.quoteId}-ZH-EN.xlsx`);
});

console.log(`foreign-trade-quote: ${cases} regression groups passed (real engine fixtures; Excel in-memory round-trip).`);
