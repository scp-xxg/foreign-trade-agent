// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import type { ToolCall } from '../types';
import type { ContentAssetKind, ContentDownloadKind } from './foreignTradeContentApi';

export interface ProductContentReceipt {
  document_type: 'foreign_trade_content_pack'; document_version: 1;
  pack_id: string; revision: number; title: string; product_name: string;
  generated_at: string; not_published: true;
  assets: { kind: ContentAssetKind; filename: string; width: number; height: number }[];
}
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max = 300): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= max;
const positiveInt = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const imageKinds: ContentAssetKind[] = ['square', 'landscape', 'spec'];
export const isProductContentTool = (name: string) => name === 'trade_product_content';

function validAssets(value: unknown): value is ProductContentReceipt['assets'] {
  if (!Array.isArray(value) || value.length > 3) return false;
  const kinds = new Set<string>();
  for (const asset of value) {
    if (!record(asset) || !imageKinds.includes(asset.kind as ContentAssetKind) ||
      typeof asset.kind !== 'string' || kinds.has(asset.kind) || !text(asset.filename, 200) ||
      !/^[^\\/\u0000-\u001f]+\.png$/i.test(asset.filename) ||
      !positiveInt(asset.width) || asset.width > 8192 || !positiveInt(asset.height) || asset.height > 8192) return false;
    kinds.add(asset.kind);
  }
  return true;
}
function validate(value: unknown): ProductContentReceipt | null {
  if (!record(value) || value.ok !== true || !Array.isArray(value.errors) || value.errors.length !== 0 || !Array.isArray(value.warnings)) return null;
  const data = value.data;
  if (!record(data) || data.document_type !== 'foreign_trade_content_pack' || data.document_version !== 1 ||
    typeof data.pack_id !== 'string' || !/^pack_[0-9a-f]{32}$/.test(data.pack_id) || !positiveInt(data.revision) ||
    !text(data.title) || !text(data.product_name) || data.not_published !== true || !text(data.generated_at, 80) ||
    !/^\d{4}-\d{2}-\d{2}T/.test(data.generated_at) || !Number.isFinite(Date.parse(data.generated_at)) || !validAssets(data.assets)) return null;
  // Keep only the bounded typed receipt. Tool-provided URLs and model prose are never used.
  return {
    document_type: 'foreign_trade_content_pack', document_version: 1,
    pack_id: data.pack_id, revision: data.revision, title: data.title, product_name: data.product_name,
    generated_at: data.generated_at, not_published: true,
    assets: data.assets.map((asset) => ({ kind: asset.kind, filename: asset.filename, width: asset.width, height: asset.height })),
  };
}
function unwrap(value: unknown, depth = 0): ProductContentReceipt | null {
  if (depth > 6) return null;
  if (typeof value === 'string') {
    if (value.length > 500000) return null;
    try { return unwrap(JSON.parse(value), depth + 1); } catch { return null; }
  }
  if (Array.isArray(value)) {
    if (value.length > 50) return null;
    for (const part of value) { const receipt = unwrap(part, depth + 1); if (receipt) return receipt; }
    return null;
  }
  if (!record(value) || value.isError === true || value.ok === false) return null;
  const receipt = validate(value);
  if (receipt) return receipt;
  for (const key of ['structuredContent', 'content', 'result', 'output']) {
    if (key in value) { const result = unwrap(value[key], depth + 1); if (result) return result; }
  }
  if (value.type === 'text' && typeof value.text === 'string') return unwrap(value.text, depth + 1);
  return null;
}
export function extractProductContentReceipts(tools: ToolCall[]): ProductContentReceipt[] {
  const receipts = new Map<string, ProductContentReceipt>();
  for (const tool of tools) {
    if (!isProductContentTool(tool.name) || tool.status !== 'success' || (tool.outputTruncated && !tool.outputLoaded)) continue;
    const receipt = unwrap(tool.output);
    if (receipt) receipts.set(`${receipt.pack_id}:${receipt.revision}`, receipt);
  }
  return [...receipts.values()];
}
export function productContentDownloads(receipt: ProductContentReceipt): ContentDownloadKind[] {
  return ['zip', 'listing', 'faq', ...receipt.assets.map((asset) => asset.kind)];
}
export class ProductContentReceiptError extends Error {
  readonly reason: 'stale' | 'unavailable';
  constructor(reason: 'stale' | 'unavailable') { super(reason); this.name = 'ProductContentReceiptError'; this.reason = reason; }
}
/** Compare with the owner-authenticated record before offering this immutable revision. */
export function assertCurrentProductContent(receipt: ProductContentReceipt, current: unknown): void {
  if (!record(current) || current.pack_id !== receipt.pack_id) throw new ProductContentReceiptError('unavailable');
  if (current.revision !== receipt.revision || current.title !== receipt.title || current.product_name !== receipt.product_name ||
    !record(current.outputs) || current.outputs.not_published !== true || current.outputs.generated_at !== receipt.generated_at || !validAssets(current.outputs.assets)) {
    throw new ProductContentReceiptError('stale');
  }
  const signature = (assets: ProductContentReceipt['assets']) => assets.map((asset) => JSON.stringify(asset)).sort().join('|');
  const normalized = current.outputs.assets.map((asset) => ({ kind: asset.kind, filename: asset.filename, width: asset.width, height: asset.height }));
  if (signature(normalized) !== signature(receipt.assets)) throw new ProductContentReceiptError('stale');
}
/** Dependency injection makes the get-before-download boundary directly testable. */
export async function downloadVerifiedProductContent(
  receipt: ProductContentReceipt, kind: ContentDownloadKind,
  access: { getCurrent: (id: string) => Promise<unknown>; download: (id: string, kind: ContentDownloadKind, revision: number) => Promise<void> },
): Promise<void> {
  if (!productContentDownloads(receipt).includes(kind)) throw new ProductContentReceiptError('unavailable');
  const current = await access.getCurrent(receipt.pack_id);
  assertCurrentProductContent(receipt, current);
  // The API also checks revision, closing the race after the read above.
  await access.download(receipt.pack_id, kind, receipt.revision);
}
