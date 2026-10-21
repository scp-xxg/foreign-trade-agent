import type { ToolCall } from '../types';

export interface QuoteLine {
  sku: string; name: string; name_zh: string; quantity: number; currency: 'USD';
  custom_packaging: boolean; unit_price: string; packaging_unit_surcharge: string;
  effective_unit_price: string; merchandise_subtotal: string; packaging_subtotal: string;
  line_subtotal: string; production_lead_days: number; source: { record_ref: string };
}
export interface QuoteData {
  document_type: 'foreign_trade_quote'; document_version: 1; quote_id: string;
  quote_status: 'simulation_only'; currency: 'USD'; items: QuoteLine[];
  merchandise_subtotal: string; packaging_subtotal: string; subtotal: string;
  destination_country: string; requested_lead_days: number | null;
  requested_delivery_status: string; production_lead_days: number;
  subtotal_excludes_freight: true; subtotal_excludes_taxes_and_duties: true;
  freight: { status: 'pending_confirmation'; amount: null };
}
export interface TradeQuote {
  quoteId: string; data: QuoteData;
  snapshot: { ok: true; is_simulated: true; data: QuoteData; catalog_version: string;
    warnings: { code: string; message: string }[]; errors: unknown[];
    source: { type: string; record_refs: string[] } };
}
const record = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 2000;
const positiveInt = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
// Keep decimal cents exact during validation, before conversion into numeric Excel cells.
const money = (v: unknown): v is string => typeof v === 'string' && /^\d{1,12}\.\d{2}$/.test(v);
const cents = (s: string) => BigInt(s.replace('.', ''));
export const isTradeQuoteTool = (name: string) => /(?:^|[.:_])calculate_quote$/.test(name);

function validate(value: unknown): TradeQuote | null {
  if (!record(value) || value.ok !== true || value.is_simulated !== true ||
      !Array.isArray(value.errors) || value.errors.length || !text(value.catalog_version)) return null;
  const d = value.data;
  if (!record(d) || d.document_type !== 'foreign_trade_quote' || d.document_version !== 1 ||
      typeof d.quote_id !== 'string' || !/^DEMO-[A-F0-9]{16}$/.test(d.quote_id) ||
      d.quote_status !== 'simulation_only' || d.currency !== 'USD' ||
      !Array.isArray(d.items) || !d.items.length || d.items.length > 50 ||
      d.subtotal_excludes_freight !== true || d.subtotal_excludes_taxes_and_duties !== true ||
      !record(d.freight) || d.freight.status !== 'pending_confirmation' || d.freight.amount !== null ||
      typeof d.destination_country !== 'string' || d.destination_country.length > 500 ||
      !positiveInt(d.production_lead_days) || !(d.requested_lead_days === null || positiveInt(d.requested_lead_days)) ||
      !['not_requested', 'requires_confirmation', 'cannot_meet_production_window'].includes(d.requested_delivery_status)) return null;
  if (![d.merchandise_subtotal, d.packaging_subtotal, d.subtotal].every(money)) return null;
  if (!record(value.source) || !text(value.source.type) || !Array.isArray(value.source.record_refs) ||
      !value.source.record_refs.every(text) || !Array.isArray(value.warnings) ||
      !value.warnings.every(w => record(w) && text(w.code) && text(w.message))) return null;
  let goods = 0n, packaging = 0n;
  const skus = new Set<string>();
  for (const line of d.items) {
    if (!record(line) || !text(line.sku) || skus.has(line.sku) || !text(line.name) || !text(line.name_zh) ||
        !positiveInt(line.quantity) || !positiveInt(line.production_lead_days) || line.currency !== 'USD' ||
        typeof line.custom_packaging !== 'boolean' || !record(line.source) || !text(line.source.record_ref) ||
        !value.source.record_refs.includes(line.source.record_ref) ||
        ![line.unit_price, line.packaging_unit_surcharge, line.effective_unit_price,
          line.merchandise_subtotal, line.packaging_subtotal, line.line_subtotal].every(money)) return null;
    const unit = cents(line.unit_price), fee = cents(line.packaging_unit_surcharge), qty = BigInt(line.quantity);
    if (unit + fee !== cents(line.effective_unit_price) || unit * qty !== cents(line.merchandise_subtotal) ||
        fee * qty !== cents(line.packaging_subtotal) || (unit + fee) * qty !== cents(line.line_subtotal)) return null;
    goods += cents(line.merchandise_subtotal); packaging += cents(line.packaging_subtotal); skus.add(line.sku);
  }
  if (goods !== cents(d.merchandise_subtotal) || packaging !== cents(d.packaging_subtotal) ||
      goods + packaging !== cents(d.subtotal)) return null;
  // Own a detached snapshot: later streaming/history updates cannot mutate an export in progress.
  const snapshot = JSON.parse(JSON.stringify(value)) as TradeQuote['snapshot'];
  return { quoteId: d.quote_id, data: snapshot.data, snapshot };
}

function unwrap(value: unknown, depth = 0): TradeQuote | null {
  if (depth > 6) return null;
  if (typeof value === 'string') {
    if (value.length > 500000) return null;
    try { return unwrap(JSON.parse(value), depth + 1); } catch { return null; }
  }
  if (Array.isArray(value)) {
    for (const part of value) { const result = unwrap(part, depth + 1); if (result) return result; }
    return null;
  }
  if (!record(value) || value.isError === true) return null;
  const quote = validate(value);
  if (quote) return quote;
  for (const key of ['structuredContent', 'content', 'result', 'output']) {
    if (key in value) { const result = unwrap(value[key], depth + 1); if (result) return result; }
  }
  if (value.type === 'text' && typeof value.text === 'string') return unwrap(value.text, depth + 1);
  return null;
}

export function extractTradeQuotes(toolCalls: ToolCall[]): TradeQuote[] {
  const quotes = new Map<string, TradeQuote>();
  for (const tool of toolCalls) {
    if (!isTradeQuoteTool(tool.name) || (tool.status != null && tool.status !== 'success') ||
        (tool.outputTruncated && !tool.outputLoaded)) continue;
    const quote = unwrap(tool.output);
    if (quote) quotes.set(quote.quoteId, quote);
  }
  return [...quotes.values()];
}
