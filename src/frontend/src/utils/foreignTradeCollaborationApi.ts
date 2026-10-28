// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import { apiRequest, authFetch, getApiUrl } from '../api';
import { createApiResponseError } from './apiError';
export type CollaborationRole = 'sales' | 'procurement' | 'design' | 'operations' | 'compliance';
export type CollaborationTaskStatus = 'todo' | 'in_progress' | 'in_review' | 'done' | 'cancelled';
export interface CollaborationTask {
  id: string; title: string; role: CollaborationRole; assignee_label: string; status: CollaborationTaskStatus;
  depends_on: string[]; source_keys: string[]; acceptance_criteria: string[]; result_note: string;
  unresolved_items: string[]; risks: string[]; review: null | { actor_user_id: string; at: string; note: string };
  stale: boolean; blocked: boolean; blockers: string[];
}
export interface CollaborationRecord {
  document_type: 'foreign_trade_collaboration'; document_version: 1; collaboration_id: string;
  revision: number; title: string; scope: 'current_user_role_coordination'; is_demo_transaction: boolean; source_note: string;
  source_refs: { key: string; kind: string; id: string; revision: number; fingerprint: string; relationship: string; stale: boolean }[];
  tasks: CollaborationTask[]; history: { event: string; at: string; revision: number; actor_user_id: string; task_id?: string }[];
  workflow_status: { total_tasks: number; done_tasks: number; blocked_tasks: number; stale_tasks: number; ready_for_handoff: boolean };
  external_actions: { messages_sent: false; published: false }; created_at: string; updated_at: string;
}
export interface CollaborationInput {
  title: string; inquiry_id: string; content_pack_id?: string; content_relationship: 'transaction' | 'independent_reference';
  assignees?: Partial<Record<CollaborationRole, string>>; prepare_catalog_content?: boolean;
}
export interface CollaborationTaskPatch {
  assignee_label?: string; status?: Exclude<CollaborationTaskStatus, 'done'>; result_note?: string;
  unresolved_items?: string[]; risks?: string[]; depends_on?: string[];
}
const base = '/v1/foreign-trade/collaborations';
async function request<T>(path = '', method = 'GET', body?: unknown): Promise<T> {
  const result = await apiRequest<{ data: T }>(base + path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  return result.data;
}
export const listCollaborations = () => request<CollaborationRecord[]>();
export const getCollaboration = (id: string) => request<CollaborationRecord>(`/${encodeURIComponent(id)}`);
export const createCollaboration = (input: CollaborationInput) => request<CollaborationRecord>('', 'POST', input);
export const updateCollaborationTask = (id: string, taskId: string, revision: number, patch: CollaborationTaskPatch) =>
  request<CollaborationRecord>(`/${encodeURIComponent(id)}/tasks/${encodeURIComponent(taskId)}`, 'PATCH', { ...patch, revision });
export const reviewCollaborationTask = (id: string, taskId: string, revision: number, note: string) =>
  request<CollaborationRecord>(`/${encodeURIComponent(id)}/review`, 'POST', { revision, task_id: taskId, confirmed: true, review_note: note });
export const refreshCollaborationSources = (id: string, revision: number) =>
  request<CollaborationRecord>(`/${encodeURIComponent(id)}/refresh-sources`, 'POST', { revision });
export async function downloadCollaborationHandoff(id: string, kind: 'md' | 'json', revision: number): Promise<void> {
  const response = await authFetch(`${getApiUrl()}${base}/${encodeURIComponent(id)}/handoff?revision=${revision}&kind=${kind}`);
  if (!response.ok) throw createApiResponseError(response.status, await response.json().catch(() => ({})), `Download failed (${response.status})`);
  const blob = await response.blob();
  if (!blob.size) throw new Error('empty_handoff');
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `collaboration-${id}-r${revision}.${kind}`;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
