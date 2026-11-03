// Modified by SailAgent contributors.
import type { ToolCall } from '../types';
import type { ToolCallResultPayload } from '../api';
import type { InquiryRecord } from './foreignTradeInquiryApi';
import { parseTradeQuoteSnapshot, type TradeQuote } from './foreignTradeQuote';

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

/** Fetch only the exact historical invocation; never derive a receipt from clipped prose. */
export async function readHistoricalTradeInquiry(tool: ToolCall, chatId: string, messageId: string,
  read: (chatId: string, messageId: string, toolId: string) => Promise<ToolCallResultPayload>): Promise<unknown> {
  if (!chatId || !messageId || !tool.id || tool.status !== 'success' || !isTradeInquiryTool(tool.name)) throw new Error('invalid_inquiry_receipt');
  const detail = await read(chatId, messageId, tool.id);
  const complete: ToolCall = { ...tool, output: detail.result, outputTruncated: false, outputLoaded: true };
  if (detail.tool_id !== tool.id || detail.status !== 'success' || detail.truncated ||
    (detail.tool_name && detail.tool_name !== tool.name) || !extractTradeInquiryReceipts([complete]).length) {
    throw new Error('invalid_inquiry_receipt');
  }
  return detail.result;
}

/** Only a structured current inquiry read can supply this embedded quote. */
export function currentInquiryQuote(record: unknown): TradeQuote | null {
  if (!isRecord(record) || !summarizeTradeInquiry(record) || !positiveInt(record.quote_revision) ||
      !positiveInt(record.revision) || record.quote_revision > record.revision || !Array.isArray(record.items) ||
      typeof record.destination_country !== 'string' ||
      !(record.requested_lead_days === null || positiveInt(record.requested_lead_days))) return null;
  const quote = parseTradeQuoteSnapshot(record.quote);
  if (!quote || !isRecord(record.quote) || record.quote.stale === true ||
      quote.data.destination_country.trim() !== record.destination_country.trim() ||
      quote.data.requested_lead_days !== record.requested_lead_days || quote.data.items.length !== record.items.length) return null;
  const seen = new Set<string>();
  for (const item of record.items) {
    if (!isRecord(item) || typeof item.sku !== 'string' || seen.has(item.sku)) return null;
    const line = quote.data.items.find(row => row.sku === item.sku);
    if (!line || line.quantity !== item.quantity || line.custom_packaging !== item.custom_packaging) return null;
    seen.add(item.sku);
  }
  return quote;
}

function quoteContent(value: unknown): string {
  const stable = (item: unknown): unknown => Array.isArray(item) ? item.map(stable)
    : isRecord(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key, stable(item[key])])) : item;
  return JSON.stringify(stable(value));
}

/** A later draft/follow-up revision may keep the same valid quote; business changes may not. */
export async function readVerifiedInquiryQuote(record: InquiryRecord, read: (id: string) => Promise<InquiryRecord>,
  onRead?: (latest: InquiryRecord) => void): Promise<TradeQuote> {
  const expected = currentInquiryQuote(record);
  if (!expected) throw new Error('invalid_current_quote');
  const latest = await readCurrentTradeInquiry(record.id, read);
  onRead?.(latest);
  const current = currentInquiryQuote(latest);
  if (!current || current.quoteId !== expected.quoteId || quoteContent(current.data) !== quoteContent(expected.data)) throw new Error('quote_changed');
  return current;
}
