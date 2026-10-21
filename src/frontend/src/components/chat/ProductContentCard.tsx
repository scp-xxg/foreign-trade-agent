// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { memo, useMemo, useState } from 'react';
import { Button } from 'antd';
import { DownloadOutlined, FileImageOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import { getToolCallResult } from '../../api';
import { t } from '../../i18n';
import { useChatStore } from '../../stores';
import type { ToolCall } from '../../types';
import { ApiResponseError } from '../../utils/apiError';
import { downloadContentAsset, getContentPack, type ContentDownloadKind } from '../../utils/foreignTradeContentApi';
import { downloadVerifiedProductContent, extractProductContentReceipts, isProductContentTool, ProductContentReceiptError, type ProductContentReceipt } from '../../utils/foreignTradeContentReceipt';
import './ProductContentCard.css';

function downloadLabel(kind: ContentDownloadKind): string {
  return { zip: t('下载全部资料 ZIP'), listing: t('下载文案'), faq: t('下载 FAQ'),
    square: t('下载方形商品图 PNG'), landscape: t('下载横版展示图 PNG'), spec: t('下载规格信息图 PNG') }[kind];
}
export const ProductContentCard = memo(function ProductContentCard({ receipt }: { receipt: ProductContentReceipt }) {
  const [downloading, setDownloading] = useState<ContentDownloadKind | null>(null);
  const [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  const download = async (kind: ContentDownloadKind) => {
    if (downloading || unavailable) return;
    setDownloading(kind); setError('');
    try {
      await downloadVerifiedProductContent(receipt, kind, { getCurrent: getContentPack, download: downloadContentAsset });
    } catch (err) {
      if (err instanceof ProductContentReceiptError || (err instanceof ApiResponseError && err.status === 409)) {
        setUnavailable(true); setError(t('这条资料包记录已过期或不可用。请让助手重新读取当前资料包后下载。'));
      } else if (err instanceof ApiResponseError && [401, 403, 404].includes(err.status)) {
        setUnavailable(true); setError(t('当前账号无法访问这份资料包，请登录有权限的账号后重新读取。'));
      } else {
        setError(t('资料包下载失败，请重试。'));
      }
    } finally { setDownloading(null); }
  };
  return <section className="jx-contentDownloadCard" aria-label={t('商品资料包下载')} data-content-pack-id={receipt.pack_id} data-content-pack-revision={receipt.revision}>
    <div className="jx-contentDownloadHeading"><div><FileTextOutlined /><strong>{t('商品资料包下载')}</strong></div><span>{t('尚未发布')}</span></div>
    <h4>{receipt.product_name}</h4>
    <div className="jx-contentDownloadMeta"><span>{receipt.title}</span><span>{t('版本 {revision}', { revision: receipt.revision })} · {new Date(receipt.generated_at).toLocaleString(undefined, { hour12: false })}</span></div>
    <p>{t('文案、FAQ 与 {count} 张图片；下载前核对当前账号权限和资料版本。', { count: receipt.assets.length })}</p>
    <div className="jx-contentDownloadButtons" aria-busy={downloading !== null}>
      {(['zip', 'listing', 'faq'] as const).map((kind) => <Button key={kind} type={kind === 'zip' ? 'primary' : 'default'} icon={<DownloadOutlined />} loading={downloading === kind} disabled={unavailable || (downloading !== null && downloading !== kind)} onClick={() => void download(kind)}>{downloadLabel(kind)}</Button>)}
      {receipt.assets.map((asset) => <Button key={asset.kind} icon={<FileImageOutlined />} loading={downloading === asset.kind} disabled={unavailable || (downloading !== null && downloading !== asset.kind)} onClick={() => void download(asset.kind)}>{downloadLabel(asset.kind)}</Button>)}
    </div>
    <small>{t('生成结果仍需人工审阅，系统未自动上架或发送。')}</small>
    {error && <p className="jx-contentDownloadError" role="alert">{error}</p>}
  </section>;
});

function HistoricalProductContent({ tool, chatId, messageId }: { tool: ToolCall; chatId: string; messageId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const applyToolCallOutput = useChatStore((state) => state.applyToolCallOutput);
  const load = async () => {
    if (!tool.id || loading) return;
    setLoading(true); setError('');
    try {
      const detail = await getToolCallResult(chatId, messageId, tool.id);
      const complete: ToolCall = { ...tool, output: detail.result, outputTruncated: false, outputLoaded: true };
      if (detail.truncated || detail.status !== 'success' || extractProductContentReceipts([complete]).length === 0) {
        setError(t('历史资料包回执不完整或无可下载结果，请让助手重新读取资料包。')); return;
      }
      applyToolCallOutput(chatId, messageId, tool.id, detail.result);
    } catch { setError(t('加载资料包记录失败，请重试。')); }
    finally { setLoading(false); }
  };
  return <section className="jx-contentDownloadCard" aria-label={t('历史商品资料包')}>
    <div className="jx-contentDownloadHeading"><div><FileTextOutlined /><strong>{t('历史商品资料包')}</strong></div></div>
    <p>{t('加载工具的完整成功记录后，可查看这次生成的资料下载选项。')}</p>
    <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>{t('加载资料包下载选项')}</Button>
    {error && <p className="jx-contentDownloadError" role="alert">{error}</p>}
  </section>;
}
export const ProductContentCards = memo(function ProductContentCards({ tools, chatId, messageId }: { tools: ToolCall[]; chatId: string; messageId?: string }) {
  const receipts = useMemo(() => extractProductContentReceipts(tools), [tools]);
  const historical = useMemo(() => tools.filter((tool) => isProductContentTool(tool.name) && tool.status === 'success' && !!tool.id && tool.outputTruncated && !tool.outputLoaded), [tools]);
  if (!receipts.length && (!messageId || !historical.length)) return null;
  return <div className="jx-contentDownloadCards">
    {receipts.map((receipt) => <ProductContentCard key={`${receipt.pack_id}:${receipt.revision}`} receipt={receipt} />)}
    {messageId && historical.map((tool) => <HistoricalProductContent key={tool.id} tool={tool} chatId={chatId} messageId={messageId} />)}
  </div>;
});
