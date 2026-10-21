// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { apiRequest } from '../api';

export interface InquiryBuyer { company_name: string; website: string; email: string; country: string }
export interface InquiryItem { sku: string; quantity: number; custom_packaging: boolean }
export interface InquiryInput {
  title: string; buyer: InquiryBuyer; raw_inquiry: string; items: InquiryItem[];
  destination_country: string; requested_lead_days: number | null; is_demo_inquiry: boolean;
}
export interface BuyerFact { key: string; label: string; value: string; status: string; source_url?: string; evidence?: string }
export interface BuyerCard {
  status: string; checked_at: string; facts: BuyerFact[];
  sources: { url: string; title: string; retrieved_at: string; status: string }[]; warnings: string[];
}
export interface InquiryFollowup {
  id: string; title: string; due_at: string; timezone: string; status: string; completed_at?: string | null;
}
export interface InquiryRecord extends InquiryInput {
  id: string; revision: number; buyer_card: BuyerCard | null; quote: unknown | null; quote_revision: number | null;
  drafts: { zh: string; en: string; kind: string; method?: string; not_sent?: boolean; quote_revision: number | null; stale: boolean } | null;
  followups: InquiryFollowup[]; history: { revision: number; event: string; at: string }[];
  created_at: string; updated_at: string; replied_at: string | null;
}
export interface InquiryProduct {
  sku: string; name: string; name_zh: string; material: string; dimensions_cm: string;
  moq: number; currency: string; production_lead_days: number;
  price_tiers: { min_quantity: number; max_quantity: number | null; unit_price: string }[];
  packaging: { custom: { moq: number; unit_surcharge: string; additional_production_days: number } };
}
interface Envelope<T> { data: T }
const base = '/v1/foreign-trade';
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const result = await apiRequest<Envelope<T>>(`${base}${path}`, {
    method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return result.data;
}
export const listInquiries = () => request<InquiryRecord[]>('/inquiries');
export const getInquiry = (id: string) => request<InquiryRecord>(`/inquiries/${encodeURIComponent(id)}`);
export const createInquiry = (input: InquiryInput) => request<InquiryRecord>('/inquiries', 'POST', input);
export const updateInquiry = (id: string, revision: number, input: InquiryInput) => {
  const { is_demo_inquiry: _isDemo, ...fields } = input;
  return request<InquiryRecord>(`/inquiries/${encodeURIComponent(id)}`, 'PATCH', { ...fields, revision });
};
export const inquiryAction = (id: string, revision: number, action: 'verify-buyer' | 'quote' | 'draft' | 'mark-replied' | 'resume-followups') =>
  request<InquiryRecord>(`/inquiries/${encodeURIComponent(id)}/${action}`, 'POST', { revision });
export const addInquiryFollowup = (id: string, revision: number, title: string, due_at: string, timezone: string) =>
  request<InquiryRecord>(`/inquiries/${encodeURIComponent(id)}/followups`, 'POST', { revision, title, due_at, timezone });
export const updateInquiryFollowup = (id: string, revision: number, task: string, status: 'completed' | 'cancelled') =>
  request<InquiryRecord>(`/inquiries/${encodeURIComponent(id)}/followups/${encodeURIComponent(task)}`, 'PATCH', { revision, status });
export const searchInquiryProducts = (query: string) =>
  request<{ ok: boolean; data: { products: InquiryProduct[]; total_matches: number } }>(`/products?query=${encodeURIComponent(query)}`);

export interface InquiryInterpretation {
  revision: number; method: 'ai' | 'rules'; suggestions: { items?: { sku: string; quantity?: number; custom_packaging?: boolean }[]; destination_country?: string; requested_lead_days?: number | null };
  evidence: { field: string; quote: string }[]; warnings: string[];
}
export const interpretInquiry = (id: string, revision: number) =>
  request<InquiryInterpretation>(`/inquiries/${encodeURIComponent(id)}/interpret`, 'POST', { revision });
