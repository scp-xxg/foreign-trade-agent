// Modified by foreign-trade-agent contributors, 2026-10-31; see CHANGES_FOREIGN_TRADE.md.
import { memo, useMemo, useState } from 'react';
import { Alert, Button, Tag } from 'antd';
import { AuditOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { getToolCallResult } from '../../api';
import { t } from '../../i18n';
import { useChatStore } from '../../stores';
import type { ToolCall } from '../../types';
import { navigateTo, pathForPanel } from '../../routing/navigation';
import { ApiResponseError } from '../../utils/apiError';
import { getTradeReview, downloadTradeReview, type TradeReviewRecord, type TradeReviewAnnotation, type TradeReviewSeverity, type TradeReviewStatus } from '../../utils/foreignTradeReviewApi';
import { downloadVerifiedTradeReview, extractTradeReviews, highlightedReviewText, readCurrentTradeReview, readHistoricalTradeReview,
  reviewCharacterCount, safeReviewSourceUrl, tradeReviewSignature, TradeReviewAccessError } from '../../utils/foreignTradeReviewReceipt';
import './TradeReviewCard.css';
const severityLabel = (value: TradeReviewSeverity) => ({ high: t('高风险'), medium: t('中风险'), low: t('低风险'), info: t('提示') })[value];
const severityColor = (value: TradeReviewSeverity) => ({ high: 'error', medium: 'warning', low: 'gold', info: 'processing' })[value];
const statusLabel = (value: TradeReviewStatus) => ({ needs_revision: t('需要修改'), needs_confirmation: t('仍需确认'), no_issues_detected: t('未检出所列规则问题') })[value];
function fieldLabel(field: string): string {
  if (field === 'title') return t('标题');
  if (field === 'item_highlights') return 'Item Highlights';
  if (field === 'body') return t('正文');
  if (field === 'draft') return t('整份稿件');
  const bullet = /^bullets\[(\d+)\]$/.exec(field);
  return bullet ? t('卖点 {index}', { index: Number(bullet[1]) + 1 }) : field;
}
function draftFields(record: TradeReviewRecord) {
  return [{ field: 'title', text: record.draft.title }, ...(record.channel === 'amazon_listing' || record.draft.item_highlights ? [{ field: 'item_highlights', text: record.draft.item_highlights }] : []),
    { field: 'body', text: record.draft.body }, ...record.draft.bullets.map((text, i) => ({ field: `bullets[${i}]`, text }))];
}
function safeDate(value: string): string { const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleString() : value; }
function reviewError(error: unknown): string {
  if (error instanceof TradeReviewAccessError && error.reason === 'stale' || error instanceof ApiResponseError && error.status === 409) {
    return t('审核来源已变化或不可读取，请基于当前资料重新审核后下载。');
  }
  if (error instanceof ApiResponseError && [401,403,404].includes(error.status)) return t('当前账号无法读取这份审核，请确认登录账号后重试。');
  return t('审核记录读取或下载失败，请重试。');
}
function MarkedField({ field, text, annotations }: { field: string; text: string; annotations: TradeReviewAnnotation[] }) {
  const related = annotations.filter(annotation => annotation.field === field);
  const segments = highlightedReviewText(text, field, related);
  return <article className="jx-tradeReviewField" data-review-field={field}>
    <header><strong>{fieldLabel(field)}</strong><small>{t('{count} 字符', { count: reviewCharacterCount(text) })}</small>
      {related.length > 0 && <Tag color="warning">{t('{count} 条批注', { count: related.length })}</Tag>}</header>
    <pre>{text ? segments.map(segment => segment.severity
      ? <mark key={segment.start} className={`jx-tradeReviewMark jx-tradeReviewMark--${segment.severity}`} title={segment.annotationIds.join(' · ')}>{segment.text}</mark>
      : <span key={segment.start}>{segment.text}</span>) : <span className="jx-tradeReviewMuted">{t('未填写')}</span>}</pre>
  </article>;
}
export function TradeReviewDetails({ record }: { record: TradeReviewRecord }) {
  const rules = new Map(record.rule_evidence.map(rule => [rule.rule_id, rule]));
  return <div className="jx-tradeReviewDetails">
    <section><h5>{t('反馈一：稿件风险标记')}</h5>
      <div className="jx-tradeReviewLegend">{(['high','medium','low','info'] as const).map(severity => <Tag key={severity} color={severityColor(severity)}>{severityLabel(severity)}</Tag>)}</div>
      <p className="jx-tradeReviewMuted">{t('颜色对应批注风险；缺失项与整稿检查见下方文字批注。字符数按实际文本计算，限制以当前规则及适用范围为准。')}</p>
      {record.channel === 'amazon_listing' && <p className="jx-tradeReviewMuted">{t('标题与 Item Highlights 合计 {count} 字符', { count: reviewCharacterCount(record.draft.title) + reviewCharacterCount(record.draft.item_highlights) })}</p>}
      <div className="jx-tradeReviewFields">{draftFields(record).map(item => <MarkedField key={item.field} {...item} annotations={record.text_annotations} />)}</div>
    </section>
    <section><h5>{t('反馈二：逐条文字批注')}</h5>
      {!record.text_annotations.length && <p className="jx-tradeReviewMuted">{t('当前规则未产生批注，仍需人工核对平台适用范围和实际商务条件。')}</p>}
      <div className="jx-tradeReviewAnnotations">{record.text_annotations.map((annotation, index) => {
        const rule = rules.get(annotation.rule_id); const url = safeReviewSourceUrl(rule?.source_url);
        return <article key={annotation.annotation_id} className={`jx-tradeReviewAnnotation jx-tradeReviewAnnotation--${annotation.severity}`} data-annotation-id={annotation.annotation_id}>
          <header><strong>{t('批注 {index}', { index: index + 1 })} · {fieldLabel(annotation.field)}</strong>
            <Tag color={severityColor(annotation.severity)}>{severityLabel(annotation.severity)}</Tag>
            <Tag>{annotation.status === 'issue' ? t('需要修改') : t('仍需确认')}</Tag></header>
          <small>{rule?.title || annotation.rule_id} · {annotation.category === 'platform_rules' ? t('平台规则') : t('报价与商务条件')}</small>
          <dl><div><dt>{t('原片段')}</dt><dd><blockquote>{annotation.quote || t('缺失项或整稿范围，暂无可标记片段。')}</blockquote></dd></div>
            <div><dt>{t('原因')}</dt><dd>{annotation.message}</dd></div><div><dt>{t('修改建议')}</dt><dd>{annotation.suggestion}</dd></div></dl>
          {rule && <p className="jx-tradeReviewMuted">{rule.scope_note}</p>}
          {url ? <a href={url} target="_blank" rel="noopener noreferrer">{t('查看规则来源')} · {rule?.source_publisher || rule?.title} ↗</a> : <small>{t('未提供可打开的规则来源链接。')}</small>}
        </article>;
      })}</div>
    </section>
    {!!record.checks?.length && <details className="jx-tradeReviewEvidence"><summary>{t('检查覆盖：{count} 项规则', { count: record.checks.length })}</summary>
      <ul>{record.checks.map(check => <li key={check.rule_id}><strong>{rules.get(check.rule_id)?.title || check.rule_id}</strong> · {check.status === 'passed' ? t('本项未检出问题') : check.status === 'not_applicable' ? t('本项不适用') : check.status === 'issue' ? t('需要修改') : t('仍需确认')} · {t('{count} 条批注', { count: check.annotation_count })}</li>)}</ul>
    </details>}
    <details className="jx-tradeReviewEvidence"><summary>{t('规则版本、来源与适用范围')}</summary>
      {record.rule_evidence.map(rule => <article key={rule.rule_id}><strong>{rule.title}</strong><p>{rule.summary}</p>
        <p>{rule.scope_note}</p><small>{rule.rule_version} · {t('资料核对：{date}', { date: rule.verified_at })}{rule.effective_from ? ' · ' + t('生效信息：{date}', { date: rule.effective_from }) : ''}</small>
        {safeReviewSourceUrl(rule.source_url) && <p><a href={safeReviewSourceUrl(rule.source_url)} target="_blank" rel="noopener noreferrer">{rule.source_publisher} ↗</a></p>}
      </article>)}
    </details>
  </div>;
}
export const TradeReviewCard = memo(function TradeReviewCard({ receipt }: { receipt: TradeReviewRecord }) {
  const [current, setCurrent] = useState<TradeReviewRecord | null>(null); const [previous, setPrevious] = useState<TradeReviewRecord | null>(null);
  const [expanded, setExpanded] = useState(true); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const record = current || receipt; const comparison = record.comparison;
  const verifiedRead = async (id: string) => {
    const latest = await readCurrentTradeReview(id, getTradeReview);
    if (tradeReviewSignature(latest) !== tradeReviewSignature(receipt)) throw new TradeReviewAccessError('unavailable');
    setCurrent(latest); return latest;
  };
  const run = async (name: string, operation: () => Promise<void>) => {
    if (busy) return; setBusy(name); setError('');
    try { await operation(); } catch (err) { setError(reviewError(err)); } finally { setBusy(''); }
  };
  const ruleTitle = (id: string) => record.rule_evidence.find(rule => rule.rule_id === id)?.title || previous?.rule_evidence.find(rule => rule.rule_id === id)?.title || id;
  return <section className="jx-tradeReviewCard" aria-label={t('平台文案审核反馈')} data-review-id={record.review_id}>
    <header className="jx-tradeReviewHeading"><strong><AuditOutlined /> {t('平台文案审核反馈')}</strong>
      <Tag color={record.summary.issue_count ? 'error' : record.summary.needs_confirmation_count ? 'warning' : 'processing'}>{statusLabel(record.summary.review_status)}</Tag></header>
    <div className="jx-tradeReviewMeta"><strong>{record.channel === 'alibaba_rfq' ? 'Alibaba RFQ · ' + t('销售回复') : 'Amazon Listing · ' + t('运营文案')}</strong>
      <span>{record.draft.language === 'en' ? 'English' : 'Español'} · {record.draft.locale}</span><small>{safeDate(record.created_at)}</small></div>
    <p>{t('需修改 {issues} 项 · 待确认 {confirmations} 项', { issues: record.summary.issue_count, confirmations: record.summary.needs_confirmation_count })}</p>
    <div className="jx-tradeReviewLabels">{record.risk_labels.map(label => <Tag key={label.code} color={severityColor(label.severity)}>{label.label} · {label.count}</Tag>)}</div>
    <p className="jx-tradeReviewMuted">{t('这是基于所列规则和来源版本的辅助审核，不代表认证或完整合规结论；未向客户发送，也未发布。')}</p>
    <div className="jx-tradeReviewSource"><span>{record.source.type === 'inquiry' ? t('来源询盘') : t('来源资料包')} · {t('版本 {revision}', { revision: record.source.revision })}</span>
      <small>{t('规则版本：{version}', { version: record.rule_version })}</small>
      <Button size="small" disabled={!!busy} onClick={() => navigateTo(pathForPanel(record.source.type === 'inquiry' ? 'trade_inquiries' : 'trade_content', record.source.id))}>{t('打开来源工作台')}</Button></div>
    {record.source.stale && <Alert type="warning" showIcon title={t('审核来源已变化或不可读取，请基于当前资料重新审核后下载。')} description={record.source.current_revision === null ? t('当前来源不可读取。') : t('当前来源版本：{revision}', { revision: record.source.current_revision })} />}
    <div className="jx-tradeReviewActions"><Button icon={<ReloadOutlined />} loading={busy === 'read'} disabled={!!busy} onClick={() => void run('read', async () => { await verifiedRead(record.review_id); })}>{t('核对当前来源状态')}</Button>
      {(['md','json'] as const).map(kind => <Button key={kind} icon={<DownloadOutlined />} loading={busy === kind} disabled={!!busy || record.source.stale}
        onClick={() => void run(kind, () => downloadVerifiedTradeReview(record, kind, { getCurrent: verifiedRead, download: downloadTradeReview }))}>{kind === 'md' ? t('下载审核 Markdown') : t('下载审核 JSON')}</Button>)}
      <Button type="text" onClick={() => setExpanded(value => !value)}>{expanded ? t('收起审核详情') : t('展开审核详情')}</Button></div>
    <small className="jx-tradeReviewMuted">{t('下载的是含风险与待确认项的审核报告，不是对外发送或上架批准。下载前会重新核对账号权限及来源版本。')}</small>
    {error && <p role="alert" className="jx-tradeReviewError">{error}</p>}
    {comparison && <section className="jx-tradeReviewComparison"><h5>{t('前后审核变化')}</h5>
      {(comparison.source_changed || comparison.rules_changed) && <Alert type="info" showIcon title={t('来源或规则已变化，以下差异不只反映文案修改效果。')} />}
      <table><thead><tr><th>{t('审核版本')}</th><th>{t('需修改')}</th><th>{t('待确认')}</th><th>{t('审核状态')}</th></tr></thead><tbody>
        <tr><th>{t('上一份审核')}</th><td>{comparison.previous_summary.issue_count}</td><td>{comparison.previous_summary.needs_confirmation_count}</td><td>{statusLabel(comparison.previous_summary.review_status)}</td></tr>
        <tr><th>{t('本次审核')}</th><td>{record.summary.issue_count}</td><td>{record.summary.needs_confirmation_count}</td><td>{statusLabel(record.summary.review_status)}</td></tr>
      </tbody></table>
      <div className="jx-tradeReviewChangeLists">{[
        { label: t('本次未再出现的反馈'), ids: comparison.resolved_rule_ids },
        { label: t('仍有反馈的规则'), ids: comparison.persisting_rule_ids },
        { label: t('本次新增反馈'), ids: comparison.new_rule_ids },
      ].map(group => <div key={group.label}><strong>{group.label}</strong>{group.ids.length ? <ul>{group.ids.map(id => <li key={id}>{ruleTitle(id)}</li>)}</ul> : <p>{t('无')}</p>}</div>)}</div>
      <Button size="small" disabled={!!busy} loading={busy === 'previous'} onClick={() => void run('previous', async () => { setPrevious(await readCurrentTradeReview(comparison.previous_review_id, getTradeReview)); })}>{t('读取上一份审核稿与批注')}</Button>
      {previous && <details className="jx-tradeReviewPrevious"><summary>{t('上一份审核详情')} · {safeDate(previous.created_at)}</summary><TradeReviewDetails record={previous} /></details>}
    </section>}
    {expanded && <TradeReviewDetails record={record} />}
  </section>;
});
function HistoricalTradeReview({ tool, chatId, messageId }: { tool: ToolCall; chatId: string; messageId: string }) {
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const apply = useChatStore(state => state.applyToolCallOutput);
  const load = async () => {
    if (!tool.id || loading) return; setLoading(true); setError('');
    try { apply(chatId, messageId, tool.id, await readHistoricalTradeReview(tool, chatId, messageId, getToolCallResult)); }
    catch { setError(t('完整审核回执不可用，请让助手重新读取该审核。')); } finally { setLoading(false); }
  };
  return <section className="jx-tradeReviewCard"><strong>{t('平台文案审核反馈')}</strong><p>{t('历史审核回执已精简，加载完整工具记录后查看两种反馈。')}</p>
    <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>{t('加载完整审核反馈')}</Button>{error && <p role="alert" className="jx-tradeReviewError">{error}</p>}</section>;
}
export const TradeReviewCards = memo(function TradeReviewCards({ tools, chatId, messageId }: { tools: ToolCall[]; chatId: string; messageId?: string }) {
  const reviews = useMemo(() => extractTradeReviews(tools), [tools]);
  const historical = useMemo(() => tools.filter(tool => tool.name === 'trade_review' && tool.status === 'success' && tool.id && tool.outputTruncated && !tool.outputLoaded), [tools]);
  if (!reviews.length && (!messageId || !historical.length)) return null;
  return <div className="jx-tradeReviewCards">{reviews.map(review => <TradeReviewCard key={review.review_id} receipt={review} />)}
    {messageId && historical.map(tool => <HistoricalTradeReview key={tool.id} tool={tool} chatId={chatId} messageId={messageId} />)}</div>;
});
