// Modified by foreign-trade-agent contributors, 2026-10-31; see CHANGES_FOREIGN_TRADE.md.
import { apiRequest, authFetch, getApiUrl } from '../api';
import { createApiResponseError } from './apiError';
export type TradeReviewChannel = 'alibaba_rfq' | 'amazon_listing';
export type TradeReviewSeverity = 'high' | 'medium' | 'low' | 'info';
export type TradeReviewStatus = 'needs_revision' | 'needs_confirmation' | 'no_issues_detected';
export type TradeReviewCategory = 'platform_rules' | 'quotation_terms';
export interface TradeReviewDraft { title: string; item_highlights: string; body: string; bullets: string[]; language: 'en' | 'es'; locale: string }
export interface TradeReviewSummary { issue_count: number; needs_confirmation_count: number; review_status: TradeReviewStatus }
export interface TradeReviewEvidence {
  rule_id: string; rule_version: string; category: TradeReviewCategory; channels: string[];
  title: string; summary: string; source_url: string; source_publisher: string; verified_at: string; effective_from: string; scope_note: string;
}
export interface TradeReviewAnnotation {
  annotation_id: string; rule_id: string; category: TradeReviewCategory; field: string; quote: string;
  severity: TradeReviewSeverity; status: 'issue' | 'needs_confirmation'; message: string; suggestion: string;
}
export interface TradeReviewRecord {
  document_type: 'foreign_trade_review'; document_version: 1; review_id: string; previous_review_id: string | null;
  channel: TradeReviewChannel; role: 'sales' | 'operations';
  source: { type: 'inquiry' | 'content_pack'; id: string; revision: number; fingerprint: string; current_revision: number | null; stale: boolean; stale_reason?: string | null };
  draft: TradeReviewDraft; rule_version: string; rule_evidence: TradeReviewEvidence[];
  text_annotations: TradeReviewAnnotation[]; risk_labels: { code: string; label: string; severity: TradeReviewSeverity; count: number }[];
  checks?: { rule_id: string; status: 'passed' | 'issue' | 'needs_confirmation' | 'not_applicable'; annotation_count: number }[];
  summary: TradeReviewSummary;
  comparison: { previous_review_id: string; resolved_rule_ids: string[]; persisting_rule_ids: string[]; new_rule_ids: string[]; previous_summary: TradeReviewSummary; source_changed: boolean; rules_changed: boolean } | null;
  created_at: string; not_sent: true; not_published: true;
}
export interface TradeReviewInput { source_type: 'inquiry' | 'content_pack'; source_id: string; source_revision: number; channel: TradeReviewChannel; draft: TradeReviewDraft; previous_review_id?: string }
const base = '/v1/foreign-trade/reviews';
async function request<T>(path = '', method = 'GET', body?: unknown): Promise<T> {
  const result = await apiRequest<{ data: T }>(base + path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  return result.data;
}
export const createTradeReview = (input: TradeReviewInput) => request<TradeReviewRecord>('', 'POST', input);
export const getTradeReview = (id: string) => request<TradeReviewRecord>(`/${encodeURIComponent(id)}`);
export const listTradeReviews = (sourceType?: 'inquiry' | 'content_pack', sourceId?: string) => {
  const query = new URLSearchParams();
  if (sourceType) query.set('source_type', sourceType);
  if (sourceId) query.set('source_id', sourceId);
  return request<TradeReviewRecord[]>(query.size ? `?${query}` : '');
};
/** IDs are immutable. The server rechecks source ownership/version/fingerprint at download time. */
export async function downloadTradeReview(id: string, kind: 'md' | 'json'): Promise<void> {
  if (!/^review_[a-f0-9]{32}$/.test(id) || !['md','json'].includes(kind)) throw new Error('invalid_review_download');
  const response = await authFetch(`${getApiUrl()}${base}/${encodeURIComponent(id)}/download?kind=${kind}`);
  if (!response.ok) throw createApiResponseError(response.status, await response.json().catch(() => ({})), `Download failed (${response.status})`);
  const contentType = response.headers.get('Content-Type') || '';
  if (kind === 'json' ? !contentType.includes('application/json') : !/^text\/(markdown|plain)(?:;|$)/i.test(contentType)) throw new Error('invalid_review_download');
  const blob = await response.blob(); if (!blob.size) throw new Error('empty_review_download');
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `${id}.${kind}`; document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
