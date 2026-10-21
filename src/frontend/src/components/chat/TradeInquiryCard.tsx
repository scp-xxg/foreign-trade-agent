// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { memo, useMemo, useState } from 'react';
import { Button, Select } from 'antd';
import { CopyOutlined, DownOutlined, FileSearchOutlined, ReloadOutlined, UpOutlined } from '@ant-design/icons';
import { t } from '../../i18n';
import type { ToolCall } from '../../types';
import { ApiResponseError } from '../../utils/apiError';
import { getInquiry, type InquiryRecord } from '../../utils/foreignTradeInquiryApi';
import { canCopyInquiryDraft, extractTradeInquiryReceipts, readCurrentTradeInquiry, safeInquirySourceUrl,
  summarizeTradeInquiry, type TradeInquiryReceipt } from '../../utils/foreignTradeInquiryReceipt';
import './TradeInquiryCard.css';

function sourceStatus(status: string | null): string {
  if (status === null) return t('尚未查询公开资料');
  if (status === 'verified_public') return t('网站与登记来源已查询');
  if (status === 'partial') return t('部分公开来源可用');
  if (status === 'unavailable') return t('公开来源暂不可用');
  return t('已查询公开资料');
}
function factStatus(status: string): string {
  if (status === 'registry_match') return t('登记名称匹配');
  if (status === 'self_reported') return t('官网自述');
  if (status === 'verified') return t('已核验');
  if (status === 'user_provided') return t('用户提供');
  return t('未核实');
}
function dateText(value: string, timezone?: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  try { return date.toLocaleString(undefined, { timeZone: timezone, hour12: false }); } catch { return date.toLocaleString(); }
}
export const TradeInquiryCard = memo(function TradeInquiryCard({ receipt }: { receipt: TradeInquiryReceipt }) {
  const [current, setCurrent] = useState<InquiryRecord | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [language, setLanguage] = useState<'zh' | 'en'>('en');
  const summary = current ? summarizeTradeInquiry(current) || receipt : receipt;
  const read = async () => {
    if (busy) return; setBusy('read'); setError(''); setNotice('');
    try { setCurrent(await readCurrentTradeInquiry(receipt.id, getInquiry)); setExpanded(true); }
    catch (err) {
      setCurrent(null); setExpanded(false);
      setError(err instanceof ApiResponseError && [401, 403, 404].includes(err.status)
        ? t('当前账号无法读取这条询盘，请登录有权限的账号后重试。') : t('读取询盘记录失败，请重试。'));
    } finally { setBusy(''); }
  };
  const copy = async () => {
    if (busy || !current || !canCopyInquiryDraft(current, language)) return;
    setBusy('copy'); setError(''); setNotice('');
    try {
      const latest = await readCurrentTradeInquiry(receipt.id, getInquiry); setCurrent(latest);
      if (latest.revision !== current.revision) { setError(t('询盘已有更新，已显示最新记录。请核对当前草稿后再次复制。')); return; }
      if (!canCopyInquiryDraft(latest, language)) { setError(t('当前没有可复制的有效草稿，请让助手生成或更新草稿。')); return; }
      await navigator.clipboard.writeText(latest.drafts![language]); setNotice(t('草稿已复制，请审阅后自行发送。'));
    } catch { setError(t('读取或复制草稿失败，请重试。')); }
    finally { setBusy(''); }
  };
  return <section className="jx-inquiryStatusCard" aria-label={t('询盘处理记录')} data-inquiry-id={receipt.id} data-inquiry-revision={summary.revision}>
    <div className="jx-inquiryStatusHeading"><div><FileSearchOutlined /><strong>{t('询盘处理记录')}</strong></div><small>{t('版本 {revision}', { revision: summary.revision })}</small></div>
    <h4>{summary.title}</h4>
    <dl className="jx-inquiryStatusSummary"><div><dt>{t('买家公开资料')}</dt><dd>{sourceStatus(summary.buyerCardStatus)}</dd></div>
      <div><dt>{t('回复草稿')}</dt><dd>{summary.draftState === 'ready' ? t('已生成，待人工审阅') : summary.draftState === 'stale' ? t('已过期，需重新生成') : t('尚未生成')}</dd></div>
      <div><dt>{t('跟进待办')}</dt><dd>{t('{count} 项待处理', { count: summary.pendingFollowups })}</dd></div></dl>
    <p className="jx-inquiryStatusNote">{t('状态来自工具记录；展开时读取当前账号可访问的最新询盘。')}</p>
    <div className="jx-inquiryStatusActions"><Button icon={expanded ? <UpOutlined /> : <DownOutlined />} loading={busy === 'read'} disabled={!!busy && busy !== 'read'} onClick={() => expanded ? setExpanded(false) : void read()}>{expanded ? t('收起详情') : t('查看事实、草稿与待办')}</Button>
      {expanded && <Button type="text" icon={<ReloadOutlined />} disabled={!!busy} onClick={() => void read()}>{t('刷新当前记录')}</Button>}</div>
    {error && <p className="jx-inquiryStatusError" role="alert">{error}</p>}{notice && <p className="jx-inquiryStatusNote" role="status">{notice}</p>}
    {expanded && current && <div className="jx-inquiryStatusDetails">
      <p className="jx-inquiryStatusNote">{current.revision !== receipt.revision
        ? t('原工具回执为版本 {original}，以下是当前版本 {current}。', { original: receipt.revision, current: current.revision })
        : t('已读取当前版本 {revision}。', { revision: current.revision })}</p>
      <div className="jx-inquiryStatusSection"><h5>{t('买家事实卡')}</h5>
        {!current.buyer_card ? <p>{t('尚未查询公开资料')}</p> : <>
          <p className="jx-inquiryStatusNote">{t('核验时间：{time}', { time: dateText(current.buyer_card.checked_at) })}</p>
          <div className="jx-inquiryStatusFacts">{current.buyer_card.facts.map((fact, index) => <article key={`${fact.key}-${index}`}><div><strong>{fact.label}</strong><small>{factStatus(fact.status)}</small></div><p>{fact.value || t('未核实')}</p>
            {fact.evidence && <small>{fact.evidence}</small>}
            {safeInquirySourceUrl(fact.source_url) && <a href={safeInquirySourceUrl(fact.source_url)} target="_blank" rel="noopener noreferrer">{t('查看原始来源')} ↗</a>}
          </article>)}</div>
          {!!current.buyer_card.warnings.length && <ul className="jx-inquiryStatusWarnings">{current.buyer_card.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
        </>}
      </div>
      <div className="jx-inquiryStatusSection"><div className="jx-inquiryStatusDraftHeading"><h5>{t('回复草稿')}</h5>{current.drafts && <div className="jx-inquiryStatusActions"><Select aria-label={t('回复语言')} value={language} onChange={setLanguage} options={[{ value: 'en', label: 'English' }, { value: 'zh', label: t('中文') }]} /><Button icon={<CopyOutlined />} loading={busy === 'copy'} disabled={!!busy || !canCopyInquiryDraft(current, language)} onClick={() => void copy()}>{t('复制当前草稿')}</Button></div>}</div>
        {!current.drafts ? <p>{t('工具尚未生成回复草稿。可继续告诉助手：请生成这条询盘的中英文回复草稿。')}</p> : <>
          {current.drafts.stale && <p className="jx-inquiryStatusWarnings">{t('报价条件已修改，此草稿已过期。请重新计算报价并生成草稿。')}</p>}
          <pre>{current.drafts[language]}</pre><small>{t('草稿供人工审阅和复制，系统不会自动发邮件。')}</small>
        </>}
      </div>
      <div className="jx-inquiryStatusSection"><h5>{t('跟进待办')}</h5>{!current.followups.length ? <p>{t('尚未安排跟进。')}</p> : <ul className="jx-inquiryStatusTasks">{current.followups.map((task) => <li key={task.id}><strong>{task.title}</strong><span>{dateText(task.due_at, task.timezone)} · {task.timezone}</span><small>{task.status === 'pending' ? t('待跟进') : task.status === 'completed' ? t('已完成') : t('已取消')}</small></li>)}</ul>}</div>
    </div>}
  </section>;
});
export const TradeInquiryCards = memo(function TradeInquiryCards({ tools }: { tools: ToolCall[] }) {
  const receipts = useMemo(() => extractTradeInquiryReceipts(tools), [tools]);
  if (!receipts.length) return null;
  return <div className="jx-inquiryStatusCards">{receipts.map((receipt) => <TradeInquiryCard key={`${receipt.id}:${receipt.revision}`} receipt={receipt} />)}</div>;
});
