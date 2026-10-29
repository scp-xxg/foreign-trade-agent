// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import type { ToolCall } from '../types';
import type { InquiryRecord } from './foreignTradeInquiryApi';

export interface TradeInquiryReceipt {
  id: string; revision: number; title: string; buyerCardStatus: string | null;
  factCount: number; draftState: 'missing' | 'stale' | 'ready'; pendingFollowups: number;
}
const isRecord = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const positiveInt = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
export const isTradeInquiryTool = (name: string) => name === 'trade_inquiry' || name === 'trade_save_inquiry';
export function summarizeTradeInquiry(value: unknown): TradeInquiryReceipt | null {
  if (!isRecord(value) || typeof value.id !== 'string' || !/^inq_[a-f0-9]{32}$/.test(value.id) || !positiveInt(value.revision) ||
    typeof value.title !== 'string' || !value.title.trim() || value.title.length > 300 || !Array.isArray(value.followups) || value.followups.length > 1000) return null;
  const buyer = value.buyer_card;
  if (!(buyer === null || (isRecord(buyer) && typeof buyer.status === 'string' && Array.isArray(buyer.facts) && buyer.facts.length <= 200))) return null;
  let draftState: TradeInquiryReceipt['draftState'] = 'missing';
  const draft = value.drafts;
  if (draft !== null) {
    if (!isRecord(draft) || typeof draft.stale !== 'boolean' || typeof draft.zh !== 'string' || typeof draft.en !== 'string') return null;
    draftState = draft.stale ? 'stale' : draft.zh.trim() || draft.en.trim() ? 'ready' : 'missing';
  }
  let pendingFollowups = 0;
  for (const task of value.followups) {
    if (!isRecord(task) || !['pending', 'completed', 'cancelled'].includes(String(task.status))) return null;
    if (task.status === 'pending') pendingFollowups++;
  }
  return { id: value.id, revision: value.revision, title: value.title, buyerCardStatus: buyer === null ? null : String(buyer.status),
    factCount: buyer === null ? 0 : (buyer.facts as unknown[]).length, draftState, pendingFollowups };
}
function unwrap(value: unknown, depth = 0): TradeInquiryReceipt | null {
  if (depth > 6) return null;
  if (typeof value === 'string') {
    if (value.length > 500000) return null;
    try { return unwrap(JSON.parse(value), depth + 1); } catch { return null; }
  }
  if (Array.isArray(value)) {
    if (value.length > 50) return null;
    for (const part of value) { const result = unwrap(part, depth + 1); if (result) return result; }
    return null;
  }
  if (!isRecord(value) || value.isError === true || value.ok === false) return null;
  if (value.ok === true && Array.isArray(value.errors) && value.errors.length === 0) {
    const result = summarizeTradeInquiry(value.data); if (result) return result;
  }
  for (const key of ['structuredContent', 'content', 'result', 'output']) {
    if (key in value) { const result = unwrap(value[key], depth + 1); if (result) return result; }
  }
  if (value.type === 'text' && typeof value.text === 'string') return unwrap(value.text, depth + 1);
  return null;
}
export function extractTradeInquiryReceipts(tools: ToolCall[]): TradeInquiryReceipt[] {
  const receipts = new Map<string, TradeInquiryReceipt>();
  for (const tool of tools) {
    if (!isTradeInquiryTool(tool.name) || tool.status !== 'success' || (tool.outputTruncated && !tool.outputLoaded)) continue;
    const receipt = unwrap(tool.output); if (!receipt) continue;
    const previous = receipts.get(receipt.id);
    if (!previous || previous.revision < receipt.revision) receipts.set(receipt.id, receipt);
  }
  return [...receipts.values()];
}
export const safeInquirySourceUrl = (value?: string): string | undefined => {
  if (!value) return undefined;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; }
  catch { return undefined; }
};
export async function readCurrentTradeInquiry(id: string, read: (id: string) => Promise<InquiryRecord>): Promise<InquiryRecord> {
  if (!/^inq_[a-f0-9]{32}$/.test(id)) throw new Error('invalid_inquiry');
  const current = await read(id);
  if (current.id !== id || !summarizeTradeInquiry(current)) throw new Error('invalid_inquiry');
  return current;
}
export function canCopyInquiryDraft(record: InquiryRecord, language: 'zh' | 'en'): boolean {
  return !!record.drafts && record.drafts.stale === false && !!record.drafts[language]?.trim();
}
