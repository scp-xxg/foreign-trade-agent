import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pathForPanel, panelFromPath } from '../src/routing/navigation';
import { parseCollaboration, extractCollaborations, canDownloadHandoff, downloadVerifiedHandoff } from '../src/utils/foreignTradeCollaborationReceipt';
import { resolveToolCardIndex } from '../src/utils/toolMatching';
import type { CollaborationRecord } from '../src/utils/foreignTradeCollaborationApi';
import type { ToolCall } from '../src/types';
const ids = ['sales_requirements','procurement_quote','design_assets','operations_content','compliance_review','sales_handoff'];
function fixture(): CollaborationRecord {
  return { document_type: 'foreign_trade_collaboration', document_version: 1, collaboration_id: 'collab_' + 'a'.repeat(32), revision: 3,
    title: 'DESK demo collaboration', scope: 'current_user_role_coordination', is_demo_transaction: true, source_note: 'Simulated DESK transaction; Raspberry Pi is independent.',
    source_refs: [{ key: 'inquiry', kind: 'inquiry', id: 'inq_' + 'b'.repeat(32), revision: 2, fingerprint: 'f'.repeat(64), relationship: 'transaction', stale: false }],
    tasks: ids.map((id, i) => ({ id, title: id, role: i === 0 || i === 5 ? 'sales' : ['sales','procurement','design','operations','compliance'][i] as 'sales',
      assignee_label: 'Demo owner', status: 'done', depends_on: i ? [ids[i - 1]] : [], source_keys: ['inquiry'], acceptance_criteria: ['Evidence reviewed'],
      result_note: 'Reviewed evidence', unresolved_items: [], risks: [], review: { actor_user_id: 'owner', at: '2026-10-28T00:00:00Z', note: 'Human checked' }, stale: false, blocked: false, blockers: [] })),
    history: [], workflow_status: { total_tasks: 6, done_tasks: 6, blocked_tasks: 0, stale_tasks: 0, ready_for_handoff: true },
    external_actions: { messages_sent: false, published: false }, created_at: '2026-10-28T00:00:00Z', updated_at: '2026-10-28T00:00:00Z' };
}
for (const [panel, route] of [['trade_inquiries','/trade-inquiries'],['trade_content','/trade-content'],['trade_collaboration','/trade-collaboration']] as const) {
  assert.equal(pathForPanel(panel), route); assert.equal(panelFromPath(route), panel);
  assert.equal(pathForPanel(panel, 'record-id'), route + '/record-id'); assert.equal(panelFromPath(route + '/record-id'), panel);
}
// Produced by the backend service integration test using only a simulated transaction.
const backendFixture = parseCollaboration(JSON.parse(readFileSync('scripts/fixtures/foreign-trade-collaboration.json','utf8')));
assert.ok(backendFixture); assert.equal(canDownloadHandoff(backendFixture), true);
const source = fixture();
const tool = (output: unknown, patch: Partial<ToolCall> = {}): ToolCall => ({ id: 'call-1', name: 'trade_collaboration', status: 'success', output, ...patch });
const envelope = (data: unknown) => ({ ok: true, data, errors: [], warnings: [] });
assert.ok(parseCollaboration(source));
assert.equal(extractCollaborations([tool(envelope(source))]).length, 1);
assert.equal(extractCollaborations([tool({ content: [{ type: 'text', text: JSON.stringify(envelope(source)) }] })]).length, 1);
assert.equal(extractCollaborations([tool(envelope([source, { ...source, revision: 4 }]))])[0]?.revision, 4);
assert.equal(extractCollaborations([tool(source)]).length, 0, 'bare prose-like objects are not successful tool envelopes');
assert.equal(extractCollaborations([tool(envelope(source), { name: 'unrelated' })]).length, 0);
assert.equal(extractCollaborations([tool(envelope(source), { status: 'error' })]).length, 0);
assert.equal(extractCollaborations([tool(envelope(source), { outputTruncated: true })]).length, 0);
assert.equal(extractCollaborations([tool({ ...envelope(source), ok: false })]).length, 0);
assert.equal(extractCollaborations([tool({ ...envelope(source), errors: ['failed'] })]).length, 0);
assert.equal(parseCollaboration({ ...source, collaboration_id: '../private' }), null);
assert.equal(parseCollaboration({ ...source, scope: 'multi_user_permissions' }), null);
assert.equal(parseCollaboration({ ...source, external_actions: { messages_sent: true, published: false } }), null);
const noReview = fixture(); noReview.tasks[0].review = null; assert.equal(parseCollaboration(noReview), null);
const duplicate = fixture(); duplicate.tasks[1].id = duplicate.tasks[0].id; assert.equal(parseCollaboration(duplicate), null);
assert.equal(canDownloadHandoff(source), true);
for (const mutate of [
  (v: CollaborationRecord) => { v.source_refs[0].stale = true; },
  (v: CollaborationRecord) => { v.tasks[0].stale = true; },
  (v: CollaborationRecord) => { v.tasks[0].blocked = true; },
  (v: CollaborationRecord) => { v.tasks[0].status = 'in_review'; },
  (v: CollaborationRecord) => { v.tasks[0].review!.note = ''; },
]) { const changed = fixture(); mutate(changed); assert.equal(canDownloadHandoff(changed), false); }
const withUnknowns = fixture(); withUnknowns.tasks[0].unresolved_items = ['Freight remains unconfirmed'];
assert.equal(canDownloadHandoff(withUnknowns), true, 'reviewed internal handoffs preserve unknowns without forcing their removal');
let downloads = 0;
const download = async (id: string, kind: 'md' | 'json', revision: number) => { assert.equal(id, source.collaboration_id); assert.equal(kind, 'md'); assert.equal(revision, 3); downloads++; };
await downloadVerifiedHandoff(source, 'md', { getCurrent: async () => fixture(), download }); assert.equal(downloads, 1);
await assert.rejects(() => downloadVerifiedHandoff(source, 'md', { getCurrent: async () => ({ ...fixture(), revision: 4 }), download }), /stale_collaboration/);
await assert.rejects(() => downloadVerifiedHandoff(source, 'md', { getCurrent: async () => { throw new Error('403'); }, download }), /403/);
await assert.rejects(() => downloadVerifiedHandoff(source, 'md', { getCurrent: async () => ({ ...fixture(), collaboration_id: 'collab_' + 'b'.repeat(32) }), download }), /invalid_collaboration/);
await assert.rejects(() => downloadVerifiedHandoff(source, 'md', { getCurrent: async () => { const v = fixture(); v.tasks[0].stale = true; return v; }, download }), /handoff_not_ready/);
assert.equal(downloads, 1, 'stale, unauthorized and invalid reads never download');
assert.equal(resolveToolCardIndex([{ id: 'call-a', name: 'trade_collaboration', status: 'running' }], 'call-b', 'trade_collaboration'), -1, 'ID mismatch must not claim a same-named invocation');
console.log('foreign-trade collaboration parsing, review/download guards and tool identity: PASS');
