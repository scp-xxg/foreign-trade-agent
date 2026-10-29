// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { normalizeToolId, resolveToolCardIndex } from '../src/utils/toolMatching';
import type { ToolCall } from '../src/types';
import type { InquiryRecord } from '../src/utils/foreignTradeInquiryApi';
import { canCopyInquiryDraft, extractTradeInquiryReceipts, readCurrentTradeInquiry, safeInquirySourceUrl, summarizeTradeInquiry } from '../src/utils/foreignTradeInquiryReceipt';
import { assertCurrentProductContent, downloadVerifiedProductContent, extractProductContentReceipts,
  isProductContentTool, productContentDownloads, ProductContentReceiptError,
} from '../src/utils/foreignTradeContentReceipt';

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const data = {
  document_type: 'foreign_trade_content_pack', document_version: 1,
  pack_id: `pack_${'a'.repeat(32)}`, revision: 7, title: 'Reviewed product pack', product_name: 'Raspberry Pi 5',
  generated_at: '2026-10-21T08:00:00+00:00', not_published: true,
  assets: [
    { kind: 'square', filename: 'product-square.png', width: 1200, height: 1200 },
    { kind: 'landscape', filename: 'product-landscape.png', width: 1600, height: 900 },
    { kind: 'spec', filename: 'product-spec.png', width: 1200, height: 1600 },
  ],
};
const envelope = { ok: true, data, errors: [], warnings: [] };
const call = (output: unknown, extra: Partial<ToolCall> = {}): ToolCall => ({ name: 'trade_product_content', status: 'success', output, ...extra });
const extract = (output: unknown, extra: Partial<ToolCall> = {}) => extractProductContentReceipts([call(output, extra)]);
const current = () => ({ pack_id: data.pack_id, revision: data.revision, title: data.title, product_name: data.product_name,
  outputs: { generated_at: data.generated_at, not_published: true, assets: clone(data.assets) } });
const receipt = () => { const results = extract(clone(envelope)); assert.equal(results.length, 1); return results[0]; };
let cases = 0;
async function test(name: string, work: () => void | Promise<void>) {
  try { await work(); cases++; } catch (error) { throw new Error(`${name}: ${String(error)}`, { cause: error }); }
}

await test('only native content tool success can create a download card', () => {
  assert.equal(isProductContentTool('trade_product_content'), true);
  for (const name of ['assistant', 'bash', 'trade_inquiry', 'trade_product_content_other', 'not_trade_product_content', 'mcp.trade_product_content']) {
    assert.equal(extract(envelope, { name }).length, 0);
  }
  for (const status of [undefined, 'running', 'pending', 'error', 'interrupted'] as const) assert.equal(extract(envelope, { status }).length, 0);
  assert.equal(extract('The model says a file was generated: ' + JSON.stringify(envelope)).length, 0);
  assert.equal(extract({ text: JSON.stringify(envelope) }).length, 0);
});
await test('native and MCP structured/text wrappers retain the typed receipt', () => {
  for (const value of [envelope, JSON.stringify(envelope), { structuredContent: envelope },
    { content: [{ type: 'text', text: JSON.stringify(envelope) }] },
    { result: { output: JSON.stringify(envelope) } }, [{ type: 'text', text: JSON.stringify(envelope) }]]) {
    assert.equal(extract(value)[0]?.pack_id, data.pack_id);
  }
});
await test('untrusted prose URLs and extra output data are discarded', () => {
  const value = { ...clone(envelope), data: { ...clone(data), download_url: 'https://malicious.example/secret', listing: { title: 'Other title' }, token: 'not-a-real-secret' } };
  const parsed = extract(value)[0];
  assert.deepEqual(Object.keys(parsed).sort(), Object.keys(data).sort());
  assert.ok(!JSON.stringify(parsed).includes('malicious.example'));
  assert.ok(!JSON.stringify(parsed).includes('not-a-real-secret'));
});
await test('error envelopes and incomplete historical outputs do not create cards', () => {
  assert.equal(extract({ ...envelope, ok: false }).length, 0);
  assert.equal(extract({ ...envelope, errors: ['failed'] }).length, 0);
  assert.equal(extract({ isError: true, structuredContent: envelope }).length, 0);
  assert.equal(extract({ ok: false, result: envelope }).length, 0);
  assert.equal(extract(envelope, { outputTruncated: true }).length, 0);
  assert.equal(extract(envelope, { outputTruncated: true, outputLoaded: true }).length, 1);
  assert.equal(extract(JSON.stringify(envelope).slice(0, -2)).length, 0);
});
await test('schema markers, owner record identity and revision must be well formed', () => {
  for (const field of ['document_type', 'document_version', 'pack_id', 'revision', 'generated_at', 'not_published', 'assets']) {
    const value: any = clone(envelope); delete value.data[field]; assert.equal(extract(value).length, 0, field);
  }
  for (const id of ['../../outside', 'pack_/../secret', 'pack_123', `pack_${'A'.repeat(32)}`, `https://example.com/${data.pack_id}`]) {
    const value = clone(envelope); value.data.pack_id = id; assert.equal(extract(value).length, 0);
  }
  for (const version of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    const value = clone(envelope); value.data.revision = version; assert.equal(extract(value).length, 0);
  }
  const unsupported = clone(envelope); unsupported.data.document_version = 2; assert.equal(extract(unsupported).length, 0);
  const published = clone(envelope); published.data.not_published = false; assert.equal(extract(published).length, 0);
  const invalidDate = clone(envelope); invalidDate.data.generated_at = 'yesterday'; assert.equal(extract(invalidDate).length, 0);
});
await test('only bounded PNG assets with unique known kinds are accepted', () => {
  for (const keyValue of [ ['kind', 'pdf'], ['filename', '../../private.png'], ['filename', 'https://example.com/img.png'], ['filename', 'run.exe'], ['width', 0], ['height', 100000], ['width', 10.5] ] as const) {
    const value: any = clone(envelope); value.data.assets[0][keyValue[0]] = keyValue[1]; assert.equal(extract(value).length, 0);
  }
  const duplicate = clone(envelope); duplicate.data.assets.push(clone(duplicate.data.assets[0])); assert.equal(extract(duplicate).length, 0);
});
await test('text-only packs expose no PNG choices', () => {
  const value = clone(envelope); value.data.assets = [];
  assert.deepEqual(productContentDownloads(extract(value)[0]), ['zip', 'listing', 'faq']);
});
await test('duplicate receipts collapse by pack and revision but preserve later revisions', () => {
  const next = clone(envelope); next.data.revision += 1;
  const parsed = extractProductContentReceipts([call(envelope), call(clone(envelope)), call(next)]);
  assert.equal(parsed.length, 2); assert.deepEqual(parsed.map((item) => item.revision), [7, 8]);
});
await test('parsed receipt owns its nested data and cannot drift with streaming state', () => {
  const value = clone(envelope); const parsed = extract(value)[0];
  value.data.assets[0].kind = 'spec'; value.data.product_name = 'Changed';
  assert.equal(parsed.assets[0].kind, 'square'); assert.equal(parsed.product_name, 'Raspberry Pi 5');
});
await test('recursive and excessively large wrapped payloads are bounded', () => {
  let wrapped: unknown = envelope; for (let n = 0; n < 10; n++) wrapped = { output: wrapped };
  assert.equal(extract(wrapped).length, 0); assert.equal(extract(' '.repeat(500001)).length, 0);
  assert.equal(extract(Array.from({ length: 51 }, () => envelope)).length, 0);
});
await test('matching owner-authenticated current record is accepted independent of asset order', () => {
  const value = current(); value.outputs.assets.reverse(); assertCurrentProductContent(receipt(), value);
});
await test('different record, newer revision, cleared outputs and changed image evidence are blocked', () => {
  for (const change of [
    (value: any) => { value.pack_id = `pack_${'b'.repeat(32)}`; },
    (value: any) => { value.revision++; }, (value: any) => { value.outputs = null; },
    (value: any) => { value.outputs.generated_at = '2026-10-21T09:00:00+00:00'; },
    (value: any) => { value.outputs.assets[0].filename = 'changed.png'; },
    (value: any) => { value.title = 'Updated title'; },
    (value: any) => { value.outputs.not_published = false; },
  ]) { const value = current(); change(value); assert.throws(() => assertCurrentProductContent(receipt(), value), ProductContentReceiptError); }
});
await test('downloads read the authenticated record first and bind the exact revision', async () => {
  const calls: unknown[] = [];
  await downloadVerifiedProductContent(receipt(), 'zip', {
    getCurrent: async (id) => { calls.push(['get', id]); return current(); },
    download: async (...args) => { calls.push(['download', ...args]); },
  });
  assert.deepEqual(calls, [['get', data.pack_id], ['download', data.pack_id, 'zip', 7]]);
});
await test('denied owner access never reaches the binary download', async () => {
  let downloads = 0; const denied = new Error('HTTP 404');
  await assert.rejects(downloadVerifiedProductContent(receipt(), 'faq', {
    getCurrent: async () => { throw denied; }, download: async () => { downloads++; },
  }), (error) => error === denied);
  assert.equal(downloads, 0);
});
await test('stale records never download or silently switch to the latest version', async () => {
  let downloads = 0; const changed = current(); changed.revision++;
  await assert.rejects(downloadVerifiedProductContent(receipt(), 'listing', {
    getCurrent: async () => changed, download: async () => { downloads++; },
  }), ProductContentReceiptError);
  assert.equal(downloads, 0);
});
await test('absent image kinds are rejected before either request', async () => {
  const value = clone(envelope); value.data.assets = []; let requests = 0;
  await assert.rejects(downloadVerifiedProductContent(extract(value)[0], 'square', {
    getCurrent: async () => { requests++; return current(); }, download: async () => { requests++; },
  }), ProductContentReceiptError);
  assert.equal(requests, 0);
});
await test('a server conflict after the fresh read propagates without an unversioned retry', async () => {
  let requests = 0; const conflict = new Error('HTTP 409');
  await assert.rejects(downloadVerifiedProductContent(receipt(), 'spec', {
    getCurrent: async () => current(), download: async (_id, _kind, revision) => { requests++; assert.equal(revision, 7); throw conflict; },
  }), (error) => error === conflict);
  assert.equal(requests, 1);
});

const inquiryData = () => ({ id: `inq_${'c'.repeat(32)}`, revision: 4, title: 'Public buyer evidence demo', buyer_card: null,
  drafts: null, followups: [] } as unknown as InquiryRecord);
const inquiryEnvelope = (value: InquiryRecord) => ({ ok: true, data: value, errors: [], warnings: [] });
const inquiryCall = (value: InquiryRecord, extra: Partial<ToolCall> = {}): ToolCall => ({ name: 'trade_inquiry', status: 'success', output: inquiryEnvelope(value), ...extra });
await test('inquiry card requires the native success tool with an exact owned inquiry id', () => {
  const value = inquiryData();
  assert.equal(extractTradeInquiryReceipts([inquiryCall(value)]).length, 1);
  for (const name of ['assistant', 'trade_product_content', 'other_trade_inquiry', 'mcp.trade_inquiry']) assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { name })]).length, 0);
  for (const status of [undefined, 'error', 'running', 'pending', 'interrupted'] as const) assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { status })]).length, 0);
  for (const id of ['../private', 'inq_short', `inq_${'A'.repeat(32)}`]) { value.id = id; assert.equal(extractTradeInquiryReceipts([inquiryCall(value)]).length, 0); }
});
await test('inquiry states come from structured fields rather than prose or workflow claims', () => {
  const value = { ...inquiryData(), workflow_status: { draft_generated: true }, message: 'A draft has been generated' };
  const parsed = extractTradeInquiryReceipts([inquiryCall(value)])[0];
  assert.equal(parsed.draftState, 'missing'); assert.equal(parsed.pendingFollowups, 0); assert.equal(parsed.buyerCardStatus, null);
  assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { output: 'Draft ready: ' + JSON.stringify(inquiryEnvelope(value)) })]).length, 0);
});
await test('same inquiry has one highest-revision card regardless of tool order', () => {
  const older = inquiryData(); const newer = inquiryData(); newer.revision = 9;
  newer.drafts = { zh: '草稿', en: 'Draft', kind: 'quote', quote_revision: 8, stale: false };
  const another = inquiryData(); another.id = `inq_${'d'.repeat(32)}`;
  const parsed = extractTradeInquiryReceipts([inquiryCall(newer), inquiryCall(older), inquiryCall(another), inquiryCall(newer)]);
  assert.equal(parsed.length, 2); assert.equal(parsed[0].revision, 9); assert.equal(parsed[0].draftState, 'ready');
});
await test('missing, empty, current and stale inquiry drafts have distinct real states', () => {
  const value = inquiryData(); assert.equal(summarizeTradeInquiry(value)?.draftState, 'missing');
  value.drafts = { zh: '', en: '', kind: 'quote', quote_revision: 2, stale: false };
  assert.equal(summarizeTradeInquiry(value)?.draftState, 'missing'); assert.equal(canCopyInquiryDraft(value, 'en'), false);
  value.drafts.en = 'Reviewed draft'; assert.equal(summarizeTradeInquiry(value)?.draftState, 'ready'); assert.equal(canCopyInquiryDraft(value, 'en'), true); assert.equal(canCopyInquiryDraft(value, 'zh'), false);
  value.drafts.stale = true; assert.equal(summarizeTradeInquiry(value)?.draftState, 'stale'); assert.equal(canCopyInquiryDraft(value, 'en'), false);
});
await test('inquiry facts and pending task counts reflect only actual stored entries', () => {
  const value = inquiryData();
  value.buyer_card = { status: 'partial', checked_at: data.generated_at, facts: [{ key: 'name', label: 'Name', value: 'Demo', status: 'self_reported' }], sources: [], warnings: [] };
  value.followups = ['pending', 'completed', 'cancelled', 'pending'].map((status, i) => ({ id: String(i), title: 'Task', status, due_at: data.generated_at, timezone: 'UTC' }));
  const result = summarizeTradeInquiry(value); assert.equal(result?.buyerCardStatus, 'partial'); assert.equal(result?.factCount, 1); assert.equal(result?.pendingFollowups, 2);
});
await test('inquiry errors, clipped output and malformed structured status are not shown', () => {
  const value = inquiryData();
  for (const output of [{ ok: false, data: value, errors: [] }, { ok: true, data: value, errors: ['failed'] }, { isError: true, content: [{ type: 'text', text: JSON.stringify(inquiryEnvelope(value)) }] }]) assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { output })]).length, 0);
  assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { outputTruncated: true })]).length, 0);
  assert.equal(extractTradeInquiryReceipts([inquiryCall(value, { outputTruncated: true, outputLoaded: true })]).length, 1);
  (value as any).followups = [{ status: 'invented' }]; assert.equal(summarizeTradeInquiry(value), null);
});
await test('current inquiry reads permit updated records but reject changed ownership identifiers', async () => {
  const latest = inquiryData(); latest.revision = 20;
  assert.equal((await readCurrentTradeInquiry(latest.id, async () => latest)).revision, 20);
  await assert.rejects(readCurrentTradeInquiry(latest.id, async () => ({ ...latest, id: `inq_${'e'.repeat(32)}` })));
  let calls = 0; await assert.rejects(readCurrentTradeInquiry('../private', async () => { calls++; return latest; })); assert.equal(calls, 0);
  const denied = new Error('HTTP 404'); await assert.rejects(readCurrentTradeInquiry(latest.id, async () => { throw denied; }), (error) => error === denied);
});
await test('inquiry source links exclude executable schemes, credentials and relative paths', () => {
  assert.equal(safeInquirySourceUrl('https://www.example.com/source'), 'https://www.example.com/source');
  assert.equal(safeInquirySourceUrl('http://www.example.com/source'), 'http://www.example.com/source');
  for (const value of ['javascript:alert(1)', 'data:text/html,hello', 'file:///tmp/file', 'https://user:password@example.com/', '//example.com/', '/api/private']) assert.equal(safeInquirySourceUrl(value), undefined);
});


// Execute the upstream modular reducer helpers and ontology branch, preserving
// behavior coverage while avoiding the browser store graph in this Node test.
const streamAst = ts.createSourceFile('messageReducer.ts', readFileSync('src/hooks/chatStream/messageReducer.ts', 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const lifecycleAst = ts.createSourceFile('lifecycleAndTools.ts', readFileSync('src/hooks/chatStream/lifecycleAndTools.ts', 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const helperNames = new Set(['getEventToolId', 'getEventToolRawName', 'findToolCallIndex']);
const streamHelpers = new Map<string, string>();
let ontologyResultBranch = '';
function visitHelpers(node: ts.Node) {
  if (ts.isFunctionDeclaration(node) && node.name && helperNames.has(node.name.text)) streamHelpers.set(node.name.text, node.getText(streamAst).replace(/^export /, ''));
  ts.forEachChild(node, visitHelpers);
}
function visitLifecycle(node: ts.Node) {
  if (ts.isIfStatement(node)) {
    const condition = node.expression.getText(lifecycleAst);
    if (condition.includes('ontologyRevisionTool') && condition.includes("eventType === 'tool_result'")) ontologyResultBranch = node.thenStatement.getText(lifecycleAst);
  }
  ts.forEachChild(node, visitLifecycle);
}
visitHelpers(streamAst); visitLifecycle(lifecycleAst);
assert.equal(streamHelpers.size, helperNames.size); assert.ok(ontologyResultBranch);
const helperSource = [...streamHelpers.values()].join('\n');
const compileStream = (body: string) => ts.transpileModule(helperSource + '\n' + body, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText;
const matchingCode = compileStream('globalThis.testResult = findToolCallIndex(s, eventObj);');
const ontologyCode = compileStream(`function applyResult() ${ontologyResultBranch}\napplyResult();`);
const streamCall = (id: string, status: ToolCall['status'] = 'running'): ToolCall => ({ id, name: 'trade_inquiry', input: { call_id: id }, status });
function matchStream(tools: ToolCall[], event: Record<string, unknown>): number {
  const context = { s: { toolCalls: tools, normalizeToolId }, eventObj: event, resolveToolCardIndex, stripMcpToolPrefix: (value: string) => value, testResult: -99 };
  vm.runInNewContext(matchingCode, context); return context.testResult;
}
function applyOntology(tools: ToolCall[], event: Record<string, unknown>): ToolCall[] {
  const revision = { toolCalls: tools, toolPending: true };
  const context = { s: { toolCalls: tools, normalizeToolId, allCitations: [] }, eventObj: event, obj: event, resolveToolCardIndex, stripMcpToolPrefix: (value: string) => value,
    ensureOntologyRevision: () => revision, appendOrUpdate: () => {}, t: (value: string) => value, toolStartedAt: () => 1 };
  vm.runInNewContext(ontologyCode, context); return revision.toolCalls;
}
await test('main stream never binds an unknown id to a same-name running sibling', () => {
  assert.equal(matchStream([streamCall('first'), streamCall('second')], { tool_id: 'unknown', tool_name: 'trade_inquiry' }), -1);
});
await test('main stream resolves existing ids before legacy names and keeps no-id fallback', () => {
  const calls = [streamCall('first'), streamCall('second')];
  assert.equal(matchStream(calls, { tool_id: 'second', tool_name: 'trade_inquiry' }), 1);
  assert.equal(matchStream(calls, { tool_id: 'first', tool_name: 'trade_inquiry' }), 0);
  assert.equal(matchStream(calls, { tool_name: 'trade_inquiry' }), 1);
  assert.equal(matchStream([streamCall('done', 'success')], { tool_id: 'unknown', tool_name: 'trade_inquiry' }), -1);
});
await test('ontology result with unknown id creates its own card without overwriting siblings', () => {
  const result = applyOntology([streamCall('first'), streamCall('second')], { tool_id: 'unknown', tool_name: 'trade_inquiry', result: { own_id: 'unknown' } });
  assert.equal(result.length, 3); assert.equal(result[0].output, undefined); assert.equal(result[1].output, undefined);
  assert.equal(result[2].id, 'unknown'); assert.equal(result[2].output.own_id, 'unknown');
});
await test('ontology result resolves exact ids and preserves no-id legacy matching', () => {
  const exact = applyOntology([streamCall('first'), streamCall('second')], { tool_id: 'second', tool_name: 'trade_inquiry', result: { own_id: 'second' } });
  assert.equal(exact.length, 2); assert.equal(exact[0].output, undefined); assert.equal(exact[1].output.own_id, 'second');
  const legacy = applyOntology([streamCall('first')], { tool_name: 'trade_inquiry', result: { legacy: true } });
  assert.equal(legacy.length, 1); assert.equal(legacy[0].output.legacy, true);
});


await test('explicit save-inquiry alias is accepted and shares highest-revision deduplication', () => {
  const older = inquiryData(); const newer = inquiryData(); newer.revision = older.revision + 1;
  const parsed = extractTradeInquiryReceipts([
    inquiryCall(older, { name: 'trade_save_inquiry' }), inquiryCall(newer), inquiryCall(older),
  ]);
  assert.equal(parsed.length, 1); assert.equal(parsed[0].revision, newer.revision);
  assert.equal(extractTradeInquiryReceipts([inquiryCall(newer, { name: 'trade_save_inquiry' })]).length, 1);
  for (const name of ['mcp.trade_save_inquiry', 'not_trade_save_inquiry', 'trade_save_inquiry_other']) {
    assert.equal(extractTradeInquiryReceipts([inquiryCall(newer, { name })]).length, 0);
  }
});

console.log(`foreign-trade-content-card: ${cases} regression groups passed (structured receipts, verified inquiry states, permissions boundary and version-bound downloads).`);
