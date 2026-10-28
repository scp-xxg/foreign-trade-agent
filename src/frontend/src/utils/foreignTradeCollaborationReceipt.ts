// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import type { ToolCall } from '../types';
import type { CollaborationRecord } from './foreignTradeCollaborationApi';
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max = 10000): value is string => typeof value === 'string' && value.length <= max;
const strings = (value: unknown, max = 100): value is string[] => Array.isArray(value) && value.length <= max && value.every(v => text(v));
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
export const validCollaborationId = (value: unknown): value is string => typeof value === 'string' && /^collab_[a-f0-9]{32}$/.test(value);
/** Validate the bounded business record rather than accepting model prose or tool-supplied URLs. */
export function parseCollaboration(value: unknown): CollaborationRecord | null {
  if (!record(value) || value.document_type !== 'foreign_trade_collaboration' || value.document_version !== 1 ||
    !validCollaborationId(value.collaboration_id) || !count(value.revision) || value.revision < 1 ||
    !text(value.title, 300) || !value.title.trim() || value.scope !== 'current_user_role_coordination' ||
    typeof value.is_demo_transaction !== 'boolean' || !text(value.source_note) ||
    !Array.isArray(value.tasks) || value.tasks.length !== 6 || !Array.isArray(value.source_refs) || value.source_refs.length > 3 ||
    !Array.isArray(value.history) || value.history.length > 10000 || !text(value.created_at, 100) || !text(value.updated_at, 100)) return null;
  const external = value.external_actions;
  if (!record(external) || external.messages_sent !== false || external.published !== false) return null;
  const ids = new Set<string>();
  for (const task of value.tasks) {
    if (!record(task) || !text(task.id, 100) || !['sales_requirements','procurement_quote','design_assets','operations_content','compliance_review','sales_handoff'].includes(task.id) || ids.has(task.id) ||
      !text(task.title, 300) || !['sales','procurement','design','operations','compliance'].includes(String(task.role)) ||
      !text(task.assignee_label, 200) || !['todo','in_progress','in_review','done','cancelled'].includes(String(task.status)) ||
      !strings(task.depends_on, 6) || !strings(task.source_keys, 3) || !strings(task.acceptance_criteria) || !text(task.result_note) ||
      !strings(task.unresolved_items) || !strings(task.risks) || !strings(task.blockers) || typeof task.stale !== 'boolean' || typeof task.blocked !== 'boolean') return null;
    if (task.review !== null && (!record(task.review) || !text(task.review.actor_user_id, 200) || !text(task.review.at, 100) || !text(task.review.note))) return null;
    if (task.status === 'done' && task.review === null) return null;
    ids.add(task.id);
  }
  for (const task of value.tasks) if ((task as { depends_on: string[] }).depends_on.some(id => !ids.has(id))) return null;
  for (const source of value.source_refs) {
    if (!record(source) || !['inquiry','quote','content_pack'].includes(String(source.key)) || !text(source.kind, 100) ||
      !text(source.id, 100) || !count(source.revision) || !text(source.fingerprint, 200) || !text(source.relationship, 100) || typeof source.stale !== 'boolean') return null;
  }
  for (const entry of value.history) {
    if (!record(entry) || !text(entry.event, 100) || !text(entry.at, 100) || !count(entry.revision) || !text(entry.actor_user_id, 200) ||
      (entry.task_id !== undefined && (!text(entry.task_id, 100) || !ids.has(entry.task_id)))) return null;
  }
  const status = value.workflow_status;
  if (!record(status) || status.total_tasks !== 6 || !count(status.done_tasks) || status.done_tasks > 6 ||
    !count(status.blocked_tasks) || status.blocked_tasks > 6 || !count(status.stale_tasks) || status.stale_tasks > 6 || typeof status.ready_for_handoff !== 'boolean') return null;
  return value as unknown as CollaborationRecord;
}
function unwrap(value: unknown, depth = 0): CollaborationRecord[] {
  if (depth > 6) return [];
  if (typeof value === 'string') { if (value.length > 500000) return []; try { return unwrap(JSON.parse(value), depth + 1); } catch { return []; } }
  if (Array.isArray(value)) return value.length > 50 ? [] : value.flatMap(item => unwrap(item, depth + 1));
  if (!record(value) || value.ok === false || value.isError === true) return [];
  if (value.ok === true && Array.isArray(value.errors) && value.errors.length === 0) {
    const data = Array.isArray(value.data) ? value.data : [value.data];
    if (data.length > 50) return [];
    return data.map(parseCollaboration).filter((item): item is CollaborationRecord => !!item);
  }
  for (const key of ['structuredContent', 'content', 'result', 'output']) {
    if (key in value) { const found = unwrap(value[key], depth + 1); if (found.length) return found; }
  }
  return value.type === 'text' ? unwrap(value.text, depth + 1) : [];
}
export function extractCollaborations(tools: ToolCall[]): CollaborationRecord[] {
  const records = new Map<string, CollaborationRecord>();
  for (const tool of tools) {
    if (tool.name !== 'trade_collaboration' || tool.status !== 'success' || tool.outputTruncated && !tool.outputLoaded) continue;
    for (const item of unwrap(tool.output)) {
      const prior = records.get(item.collaboration_id);
      if (!prior || item.revision > prior.revision) records.set(item.collaboration_id, item);
    }
  }
  return [...records.values()];
}
export function canDownloadHandoff(record: CollaborationRecord): boolean {
  return record.workflow_status.ready_for_handoff && record.workflow_status.done_tasks === 6 &&
    record.source_refs.every(source => !source.stale) && record.tasks.every(task => task.status === 'done' &&
      !!task.review?.note.trim() && !task.stale && !task.blocked);
}
export async function readCurrentCollaboration(id: string, read: (id: string) => Promise<unknown>): Promise<CollaborationRecord> {
  if (!validCollaborationId(id)) throw new Error('invalid_collaboration');
  const current = parseCollaboration(await read(id));
  if (!current || current.collaboration_id !== id) throw new Error('invalid_collaboration');
  return current;
}
/** Server checks the same revision again, closing the race after the authenticated read. */
export async function downloadVerifiedHandoff(receipt: CollaborationRecord, kind: 'md' | 'json', access: {
  getCurrent: (id: string) => Promise<unknown>; download: (id: string, kind: 'md' | 'json', revision: number) => Promise<void>;
}): Promise<void> {
  if (!['md','json'].includes(kind)) throw new Error('invalid_handoff_kind');
  const current = await readCurrentCollaboration(receipt.collaboration_id, access.getCurrent);
  if (current.revision !== receipt.revision) throw new Error('stale_collaboration');
  if (!canDownloadHandoff(current)) throw new Error('handoff_not_ready');
  await access.download(current.collaboration_id, kind, current.revision);
}
