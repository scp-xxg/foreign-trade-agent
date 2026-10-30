// Modified by foreign-trade-agent contributors, 2026-10-31; see CHANGES_FOREIGN_TRADE.md.
import type { ToolCall } from '../types';
import type { ToolCallResultPayload } from '../api';
import type { TradeReviewRecord, TradeReviewSummary, TradeReviewSeverity, TradeReviewAnnotation } from './foreignTradeReviewApi';
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max = 10000): value is string => typeof value === 'string' && value.length <= max;
const nonempty = (value: unknown, max = 300): value is string => text(value, max) && !!value.trim();
const integer = (value: unknown, max = 1000): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max;
const revision = (value: unknown): value is number => integer(value, Number.MAX_SAFE_INTEGER) && value > 0;
const strings = (value: unknown, max = 100, maxText = 10000): value is string[] => Array.isArray(value) && value.length <= max && value.every(v => text(v, maxText));
const categories = ['platform_rules', 'quotation_terms'];
const severities = ['high','medium','low','info'];
export const validTradeReviewId = (value: unknown): value is string => typeof value === 'string' && /^review_[a-f0-9]{32}$/.test(value);
export function safeReviewSourceUrl(value: unknown): string | undefined {
  if (!text(value, 4000) || !value) return undefined;
  try { const url = new URL(value); return ['https:','http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; } catch { return undefined; }
}
function validSummary(value: unknown): value is TradeReviewSummary {
  if (!object(value) || !integer(value.issue_count) || !integer(value.needs_confirmation_count)) return false;
  return value.review_status === (value.issue_count ? 'needs_revision' : value.needs_confirmation_count ? 'needs_confirmation' : 'no_issues_detected');
}
/** Only the known bounded document structure is rendered; model prose is never a review. */
export function parseTradeReview(value: unknown): TradeReviewRecord | null {
  if (!object(value) || value.document_type !== 'foreign_trade_review' || value.document_version !== 1 ||
    !validTradeReviewId(value.review_id) || !(value.previous_review_id === null || validTradeReviewId(value.previous_review_id)) ||
    value.previous_review_id === value.review_id || !['alibaba_rfq','amazon_listing'].includes(String(value.channel)) ||
    value.role !== (value.channel === 'alibaba_rfq' ? 'sales' : 'operations') || value.not_sent !== true || value.not_published !== true ||
    !nonempty(value.rule_version, 200) || !nonempty(value.created_at, 100) || !Number.isFinite(Date.parse(value.created_at))) return null;
  const source = value.source;
  if (!object(source) || !['inquiry','content_pack'].includes(String(source.type)) || !nonempty(source.id, 100) ||
    !(source.type === 'inquiry' ? /^inq_[a-f0-9]{32}$/ : /^pack_[a-f0-9]{32}$/).test(source.id) ||
    !revision(source.revision) || !text(source.fingerprint, 64) || !/^[a-f0-9]{64}$/.test(source.fingerprint) ||
    !(source.current_revision === null || revision(source.current_revision)) || typeof source.stale !== 'boolean' ||
    (source.current_revision === null && !source.stale) || !(source.stale_reason == null || text(source.stale_reason, 2000))) return null;
  const draft = value.draft;
  if (!object(draft) || !text(draft.title, 2000) || !(draft.item_highlights === undefined || text(draft.item_highlights, 5000)) ||
    !text(draft.body, 100000) || !strings(draft.bullets, 50, 10000) || !['en','es'].includes(String(draft.language)) || !nonempty(draft.locale, 100)) return null;
  if (!Array.isArray(value.rule_evidence) || value.rule_evidence.length > 200 || !Array.isArray(value.text_annotations) || value.text_annotations.length > 500 ||
    !Array.isArray(value.risk_labels) || value.risk_labels.length > 200 || !validSummary(value.summary)) return null;
  const ruleIds = new Set<string>();
  for (const rule of value.rule_evidence) {
    if (!object(rule) || !nonempty(rule.rule_id, 200) || ruleIds.has(rule.rule_id) || !nonempty(rule.rule_version, 200) ||
      !categories.includes(String(rule.category)) || !strings(rule.channels, 10, 100) || !nonempty(rule.title, 1000) ||
      !text(rule.summary, 20000) || !text(rule.source_url, 4000) || !text(rule.source_publisher, 500) ||
      !text(rule.verified_at, 100) || !text(rule.effective_from, 100) || !text(rule.scope_note, 20000)) return null;
    ruleIds.add(rule.rule_id);
  }
  const annotationIds = new Set<string>(); let issues = 0; let confirmations = 0;
  for (const annotation of value.text_annotations) {
    if (!object(annotation) || !nonempty(annotation.annotation_id, 200) || annotationIds.has(annotation.annotation_id) ||
      !nonempty(annotation.rule_id, 200) || !ruleIds.has(annotation.rule_id) || !categories.includes(String(annotation.category)) ||
      !nonempty(annotation.field, 200) || !text(annotation.quote, 20000) || !severities.includes(String(annotation.severity)) ||
      !['issue','needs_confirmation'].includes(String(annotation.status)) || !text(annotation.message, 20000) || !text(annotation.suggestion, 20000)) return null;
    annotationIds.add(annotation.annotation_id);
    if (annotation.status === 'issue') issues++; else confirmations++;
  }
  if (value.summary.issue_count !== issues || value.summary.needs_confirmation_count !== confirmations) return null;
  for (const label of value.risk_labels) if (!object(label) || !nonempty(label.code, 200) || !text(label.label, 1000) ||
    !severities.includes(String(label.severity)) || !integer(label.count, 500)) return null;
  if (value.checks !== undefined) {
    if (!Array.isArray(value.checks) || value.checks.length > 200) return null;
    for (const check of value.checks) if (!object(check) || !nonempty(check.rule_id, 200) ||
      !['passed','issue','needs_confirmation','not_applicable'].includes(String(check.status)) || !integer(check.annotation_count, 500)) return null;
  }
  const comparison = value.comparison;
  if (comparison !== null) {
    if (!object(comparison) || !validTradeReviewId(comparison.previous_review_id) || comparison.previous_review_id !== value.previous_review_id ||
      !strings(comparison.resolved_rule_ids, 200, 200) || !strings(comparison.persisting_rule_ids, 200, 200) || !strings(comparison.new_rule_ids, 200, 200) ||
      !validSummary(comparison.previous_summary) || typeof comparison.source_changed !== 'boolean' || typeof comparison.rules_changed !== 'boolean') return null;
  } else if (value.previous_review_id !== null) return null;
  return { ...value, draft: { ...draft, item_highlights: draft.item_highlights || '' } } as unknown as TradeReviewRecord;
}
function unwrap(value: unknown, depth = 0): TradeReviewRecord[] {
  if (depth > 6) return [];
  if (typeof value === 'string') { if (value.length > 1000000) return []; try { return unwrap(JSON.parse(value), depth + 1); } catch { return []; } }
  if (Array.isArray(value)) return value.length > 50 ? [] : value.flatMap(v => unwrap(v, depth + 1));
  if (!object(value) || value.ok === false || value.isError === true || ('errors' in value && (!Array.isArray(value.errors) || value.errors.length > 0))) return [];
  const direct = parseTradeReview(value); if (direct) return [direct];
  if (value.ok === true && 'data' in value) return unwrap(value.data, depth + 1);
  for (const key of ['structuredContent','content','output','result']) {
    if (key in value) { const records = unwrap(value[key], depth + 1); if (records.length) return records; }
  }
  return value.type === 'text' ? unwrap(value.text, depth + 1) : [];
}
export function extractTradeReviews(tools: ToolCall[]): TradeReviewRecord[] {
  const records = new Map<string, TradeReviewRecord>();
  for (const tool of tools) {
    if (tool.name !== 'trade_review' || tool.status !== 'success' || tool.outputTruncated && !tool.outputLoaded) continue;
    for (const review of unwrap(tool.output)) records.set(review.review_id, review);
  }
  return [...records.values()];
}
export class TradeReviewAccessError extends Error {
  readonly reason: 'stale' | 'unavailable';
  constructor(reason: 'stale' | 'unavailable') { super(reason); this.name = 'TradeReviewAccessError'; this.reason = reason; }
}
export async function readCurrentTradeReview(id: string, get: (id: string) => Promise<unknown>): Promise<TradeReviewRecord> {
  if (!validTradeReviewId(id)) throw new TradeReviewAccessError('unavailable');
  const review = parseTradeReview(await get(id));
  if (!review || review.review_id !== id) throw new TradeReviewAccessError('unavailable');
  return review;
}
function stableJson(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(stableJson).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).filter(key => value[key] !== undefined).sort().map(key => JSON.stringify(key) + ':' + stableJson(value[key])).join(',') + '}';
  return JSON.stringify(value) ?? 'null';
}
/** Mutable freshness flags are excluded; every immutable reviewed field is bound to the shown receipt. */
export function tradeReviewSignature(review: TradeReviewRecord): string {
  return stableJson({ review_id: review.review_id, previous_review_id: review.previous_review_id,
    channel: review.channel, role: review.role, source: { type: review.source.type, id: review.source.id, revision: review.source.revision, fingerprint: review.source.fingerprint },
    draft: review.draft, rule_version: review.rule_version, rule_evidence: review.rule_evidence, text_annotations: review.text_annotations,
    risk_labels: review.risk_labels, checks: review.checks || [], summary: review.summary, comparison: review.comparison, created_at: review.created_at });
}
export async function downloadVerifiedTradeReview(receipt: TradeReviewRecord, kind: 'md' | 'json', access: {
  getCurrent: (id: string) => Promise<unknown>; download: (id: string, kind: 'md' | 'json') => Promise<void>;
}): Promise<void> {
  if (!['md','json'].includes(kind) || !parseTradeReview(receipt)) throw new TradeReviewAccessError('unavailable');
  const current = await readCurrentTradeReview(receipt.review_id, access.getCurrent);
  if (current.source.stale || current.source.current_revision !== current.source.revision) throw new TradeReviewAccessError('stale');
  if (tradeReviewSignature(current) !== tradeReviewSignature(receipt)) throw new TradeReviewAccessError('unavailable');
  // Risks do not block an audit-report export. This never approves customer delivery or publishing.
  await access.download(current.review_id, kind);
}
export async function readHistoricalTradeReview(tool: ToolCall, chatId: string, messageId: string,
  read: (chatId: string, messageId: string, toolId: string) => Promise<ToolCallResultPayload>): Promise<unknown> {
  if (tool.name !== 'trade_review' || tool.status !== 'success' || !tool.id || !chatId || !messageId) throw new TradeReviewAccessError('unavailable');
  const detail = await read(chatId, messageId, tool.id);
  const complete: ToolCall = { ...tool, output: detail.result, outputTruncated: false, outputLoaded: true };
  if (detail.tool_id !== tool.id || detail.status !== 'success' || detail.truncated ||
    detail.tool_name && detail.tool_name !== 'trade_review' || !extractTradeReviews([complete]).length) throw new TradeReviewAccessError('unavailable');
  return detail.result;
}
export interface ReviewTextSegment { text: string; start: number; annotationIds: string[]; severity?: TradeReviewSeverity }
const severityRank: Record<TradeReviewSeverity, number> = { high: 4, medium: 3, low: 2, info: 1 };
export const reviewCharacterCount = (value: string) => Array.from(value).length;
/** Exact snippets are highlighted as text nodes; no HTML or inferred quote offsets are executed. */
export function highlightedReviewText(value: string, field: string, annotations: TradeReviewAnnotation[]): ReviewTextSegment[] {
  const ranges: { start: number; end: number; id: string; severity: TradeReviewSeverity }[] = [];
  for (const annotation of annotations) {
    if (annotation.field !== field || !annotation.quote) continue;
    let from = 0;
    for (let count = 0; count < 50; count++) {
      const at = value.indexOf(annotation.quote, from); if (at < 0) break;
      ranges.push({ start: at, end: at + annotation.quote.length, id: annotation.annotation_id, severity: annotation.severity });
      from = at + Math.max(1, annotation.quote.length);
    }
  }
  const boundaries = [...new Set([0,value.length,...ranges.flatMap(range => [range.start,range.end])])].sort((a,b) => a-b);
  return boundaries.slice(0,-1).map((start,i) => {
    const end = boundaries[i+1]; const active = ranges.filter(range => range.start < end && range.end > start);
    active.sort((a,b) => severityRank[b.severity]-severityRank[a.severity]);
    return { text: value.slice(start,end), start, annotationIds: [...new Set(active.map(range => range.id))], ...(active[0] ? {severity:active[0].severity} : {}) };
  });
}
