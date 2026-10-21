import { memo, useMemo, useState } from 'react';
import { Button } from 'antd';
import { FileExcelOutlined, FilePdfOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ToolCall } from '../../types';
import { getToolCallResult } from '../../api';
import { useChatStore } from '../../stores';
import { t } from '../../i18n';
import { extractTradeQuotes, isTradeQuoteTool, type TradeQuote } from '../../utils/foreignTradeQuote';
import { exportTradeQuoteExcel, exportTradeQuotePdf } from '../../utils/foreignTradeQuoteExport';
import './TradeQuoteCard.css';

/** Export the immutable calculation result associated with this message. */
export const TradeQuoteCard = memo(function TradeQuoteCard({ quote }: { quote: TradeQuote }) {
  const [exporting, setExporting] = useState<'pdf' | 'excel' | null>(null);
  const [error, setError] = useState('');
  const quantity = quote.data.items.reduce((total, item) => total + BigInt(item.quantity), 0n).toString();

  const download = async (format: 'pdf' | 'excel') => {
    if (exporting) return;
    setExporting(format);
    setError('');
    try {
      if (format === 'pdf') await exportTradeQuotePdf(quote);
      else await exportTradeQuoteExcel(quote);
    } catch {
      setError(t('报价单导出失败，请重试。'));
    } finally {
      setExporting(null);
    }
  };

  return (
    <section className="jx-tradeQuote" aria-label={t('中英文报价单')} data-quote-id={quote.quoteId}>
      <div className="jx-tradeQuote-heading">
        <div className="jx-tradeQuote-title"><FileTextOutlined /><strong>{t('中英文报价单')}</strong></div>
        <span className="jx-tradeQuote-demo">DEMO</span>
      </div>
      <div className="jx-tradeQuote-id">{t('报价编号：{id}', { id: quote.quoteId })}</div>
      <div className="jx-tradeQuote-summary">
        <div>
          <div className="jx-tradeQuote-total">{quote.data.currency} {quote.data.subtotal}</div>
          <div className="jx-tradeQuote-muted">{t('货值与包装费小计，不含运费和进口税费')}</div>
        </div>
        <div className="jx-tradeQuote-facts">
          <span>{t('{lines} 款产品 · 共 {quantity} 件', { lines: quote.data.items.length, quantity })}</span>
          <span>{t('目的国：{country}', { country: quote.data.destination_country || t('待确认') })}</span>
        </div>
      </div>
      <p className="jx-tradeQuote-notice">{t('模拟数据，仅供演示；两种文件均包含中英文内容、价格明细、来源和待确认条件。')}</p>
      <div className="jx-tradeQuote-actions" aria-busy={exporting !== null}>
        <Button type="primary" icon={<FilePdfOutlined />} loading={exporting === 'pdf'} disabled={exporting === 'excel'} onClick={() => void download('pdf')}>
          {t('下载中英文 PDF')}
        </Button>
        <Button icon={<FileExcelOutlined />} loading={exporting === 'excel'} disabled={exporting === 'pdf'} onClick={() => void download('excel')}>
          {t('下载中英文 Excel')}
        </Button>
      </div>
      {error && <p className="jx-tradeQuote-error" role="alert">{error}</p>}
    </section>
  );
});

/** Fetch a clipped historical result only after an explicit request. */
function HistoricalTradeQuote({ tool, chatId, messageId }: { tool: ToolCall; chatId: string; messageId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const applyToolCallOutput = useChatStore((state) => state.applyToolCallOutput);

  const load = async () => {
    if (!tool.id || loading) return;
    setLoading(true);
    setError('');
    try {
      const detail = await getToolCallResult(chatId, messageId, tool.id);
      if (detail.truncated) {
        setError(t('报价内容不完整，请重新报价后下载。'));
        return;
      }
      const complete: ToolCall = { ...tool, output: detail.result, outputTruncated: false, outputLoaded: true };
      if (detail.status !== 'success' || extractTradeQuotes([complete]).length === 0) {
        setError(t('此历史报价不支持导出，请重新报价后下载。'));
        return;
      }
      applyToolCallOutput(chatId, messageId, tool.id, detail.result);
    } catch {
      setError(t('加载报价失败，请重试。'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="jx-tradeQuote jx-tradeQuote--history" aria-label={t('历史报价单')}>
      <div className="jx-tradeQuote-title"><FileTextOutlined /><strong>{t('历史报价单')}</strong></div>
      <p className="jx-tradeQuote-muted">{t('加载本次报价的完整记录后，可下载中英文 PDF 和 Excel。')}</p>
      <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>{t('加载报价单下载选项')}</Button>
      {error && <p className="jx-tradeQuote-error" role="alert">{error}</p>}
    </section>
  );
}

export const TradeQuoteCards = memo(function TradeQuoteCards({ tools, chatId, messageId }: {
  tools: ToolCall[];
  chatId: string;
  messageId?: string;
}) {
  const quotes = useMemo(() => extractTradeQuotes(tools), [tools]);
  const historical = useMemo(() => tools.filter((tool) =>
    isTradeQuoteTool(tool.name) && tool.status === 'success' && !!tool.id
      && tool.outputTruncated && !tool.outputLoaded,
  ), [tools]);

  if (!quotes.length && (!messageId || !historical.length)) return null;
  return (
    <div className="jx-tradeQuotes">
      {quotes.map((quote) => <TradeQuoteCard key={quote.quoteId} quote={quote} />)}
      {messageId && historical.map((tool) => (
        <HistoricalTradeQuote key={tool.id} tool={tool} chatId={chatId} messageId={messageId} />
      ))}
    </div>
  );
});
