// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { apiRequest, authFetch, getApiUrl } from '../api';
import { createApiResponseError } from './apiError';

export interface ProductFact { label: string; value: string; source_url: string }
export interface ContentPackInput {
  title: string; product_name: string; brand: string; model: string; source_url: string;
  raw_text: string; facts: ProductFact[]; image_credit: string;
}
export type ContentAssetKind = 'square' | 'landscape' | 'spec';
export type ContentDownloadKind = ContentAssetKind | 'zip' | 'listing' | 'faq';
export type DemoFileKind = 'txt' | 'csv' | 'photo';
export interface ContentPackOutputs {
  listing: { title: string; bullets: string[]; description: string };
  faq: { question: string; answer: string; source_refs: number[] }[];
  translated_facts: { label: string; value: string; source_refs: number[] }[];
  method: 'ai_grounded' | 'template'; warnings: string[];
  assets: { kind: ContentAssetKind; filename: string; width: number; height: number }[];
  generated_at: string; not_published: true;
}
export interface ContentPackDocument {
  file_id: string; name: string; kind: 'image' | 'document'; mime_type: string; size: number; text?: string; url: string;
}
export interface ContentPackRecord extends ContentPackInput {
  pack_id: string; revision: number; suggested_facts: ProductFact[]; documents: ContentPackDocument[];
  outputs: ContentPackOutputs | null; created_at: string; updated_at: string; warnings: string[];
}
interface Envelope<T> { data: T }
const base = '/v1/foreign-trade/content-packs';
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const result = await apiRequest<Envelope<T>>(`${base}${path}`, {
    method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return result.data;
}
export const listContentPacks = () => request<ContentPackRecord[]>('');
export const getContentPack = (id: string) => request<ContentPackRecord>(`/${encodeURIComponent(id)}`);
export const createContentPack = (title: string) => request<ContentPackRecord>('', 'POST', { title });
export const updateContentPack = (id: string, revision: number, input: ContentPackInput) =>
  request<ContentPackRecord>(`/${encodeURIComponent(id)}`, 'PATCH', { ...input, revision });
export const generateContentPack = (id: string, revision: number) =>
  request<ContentPackRecord>(`/${encodeURIComponent(id)}/generate`, 'POST', { revision, confirmed: true });
export async function uploadContentPackFile(id: string, revision: number, file: File): Promise<ContentPackRecord> {
  const form = new FormData(); form.append('revision', String(revision)); form.append('file', file);
  const response = await authFetch(`${getApiUrl()}${base}/${encodeURIComponent(id)}/upload`, { method: 'POST', body: form });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw createApiResponseError(response.status, payload, `Upload failed (${response.status})`);
  return (payload as Envelope<ContentPackRecord>).data;
}
async function binary(path: string): Promise<{ blob: Blob; filename: string }> {
  const response = await authFetch(`${getApiUrl()}${base}${path}`);
  if (!response.ok) throw createApiResponseError(response.status, await response.json().catch(() => ({})), `Download failed (${response.status})`);
  const disposition = response.headers.get('Content-Disposition') || '';
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const ascii = /filename="?([^";]+)"?/i.exec(disposition);
  let filename = ascii?.[1] || 'product-content';
  try { if (utf8) filename = decodeURIComponent(utf8[1]); } catch { /* use safe fallback */ }
  filename = filename.replace(/[\\/\u0000-\u001f]/g, '_');
  return { blob: await response.blob(), filename };
}
function saveBinary(result: { blob: Blob; filename: string }) {
  const url = URL.createObjectURL(result.blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = result.filename;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const previewContentFile = async (id: string, fileId: string) =>
  (await binary(`/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}`)).blob;
export const previewContentAsset = async (id: string, kind: ContentAssetKind, revision: number) =>
  (await binary(`/${encodeURIComponent(id)}/download/${kind}?revision=${revision}`)).blob;
export const downloadContentAsset = async (id: string, kind: ContentDownloadKind, revision: number) =>
  saveBinary(await binary(`/${encodeURIComponent(id)}/download/${kind}?revision=${revision}`));
export const downloadContentDemo = async (kind: DemoFileKind) => saveBinary(await binary(`/demo/${kind}`));
