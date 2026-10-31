// Modified by foreign-trade-agent contributors, 2026-10-31; see CHANGES_FOREIGN_TRADE.md.
import { apiRequest } from '../api';
export interface BuyerInput {
  product_terms: string[]; buyer_terms: string[]; markets: string[]; queries: string[]; excluded_domains: string[];
  profile?: Record<string, unknown>; target_count: number; max_queries: number; max_pages: number; max_seconds: number;
}
export interface BuyerPlan { queries: string[]; search_available: boolean; note: string }
export interface BuyerCandidate {
  id: string; name: string; domain: string; discovery_url: string; query: string; summary: string;
  page_status: string; page_excerpt: string; page_read_at: string | null; discovered_at: string;
  decision: string; unresolved: string[]; rule_results: { rule_id: string; result: string; reason: string }[];
}
export interface BuyerRun {
  plan: BuyerPlan; candidates: BuyerCandidate[]; stop_reason: string; warnings: string[]; limitations: string[];
  search_log: unknown[]; metrics: { candidate_count: number; queries_executed: number; pages_read: number; elapsed_seconds: number };
}
export const splitTerms = (text: string) => [...new Set(text.split(/\r?\n/).map(s => s.trim()).filter(Boolean))];
export type Audit = 'suitable' | 'unsuitable' | 'unknown';
export function auditMetrics(labels: Record<string, Audit>, ids: string[]) {
  const suitable = ids.filter(id => labels[id] === 'suitable').length;
  const unsuitable = ids.filter(id => labels[id] === 'unsuitable').length;
  const reviewed = ids.filter(id => labels[id]).length;
  return { suitable, unsuitable, reviewed, rate: suitable + unsuitable ? suitable / (suitable + unsuitable) : null,
    coverage: ids.length ? reviewed / ids.length : null };
}
export function parseProfile(text: string): Record<string, unknown> | undefined {
  if (!text.trim()) return undefined;
  if (text.length > 100000) throw new Error('画像文件过大');
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('画像须为 JSON 对象');
  return value as Record<string, unknown>;
}
export async function buyerRequest<T>(action: 'plan' | 'run', input: BuyerInput, signal: AbortSignal): Promise<T> {
  return (await apiRequest<{ data: T }>(`/v1/foreign-trade/buyer-search/${action}`, { method: 'POST', body: JSON.stringify(input), signal })).data;
}
