// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import { memo, useMemo, useState } from 'react';
import { Button } from 'antd';
import { DownloadOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons';
import { t } from '../../i18n';
import { getToolCallResult } from '../../api';
import { useChatStore } from '../../stores';
import type { ToolCall } from '../../types';
import { navigateTo, pathForPanel } from '../../routing/navigation';
import { getCollaboration, downloadCollaborationHandoff, type CollaborationRecord } from '../../utils/foreignTradeCollaborationApi';
import { canDownloadHandoff, downloadVerifiedHandoff, extractCollaborations, readCurrentCollaboration } from '../../utils/foreignTradeCollaborationReceipt';
import { CollaborationDetails } from '../foreign-trade/CollaborationDetails';
import '../foreign-trade/CollaborationWorkspace.css';
export const CollaborationCard = memo(function CollaborationCard({ receipt }: { receipt: CollaborationRecord }) {
  const [current, setCurrent] = useState<CollaborationRecord | null>(null);
  const [expanded, setExpanded] = useState(false); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const record = current || receipt;
  const refresh = async () => {
    if (busy) return; setBusy('read'); setError('');
    try { setCurrent(await readCurrentCollaboration(receipt.collaboration_id, getCollaboration)); setExpanded(true); }
    catch { setCurrent(null); setExpanded(false); setError(t('无法读取当前协同记录，请确认登录账号并重试。')); } finally { setBusy(''); }
  };
  const download = async (kind: 'md' | 'json') => {
    if (busy || !current || !canDownloadHandoff(current)) return; setBusy(kind); setError('');
    try { await downloadVerifiedHandoff(current, kind, { getCurrent: getCollaboration, download: downloadCollaborationHandoff }); }
    catch { setCurrent(null); setError(t('交接下载被阻止：记录或来源可能已变化，请刷新并重新核对验收状态。')); } finally { setBusy(''); }
  };
  return <section className="jx-collaborationCard" aria-label={t('跨岗位协同记录')} data-collaboration-id={record.collaboration_id}>
    <header><strong><TeamOutlined /> {t('跨岗位协同记录')}</strong><small>{t('版本 {revision}', { revision: record.revision })}</small></header>
    <h4>{record.title}</h4><p>{t('已验收 {done}/{total} · 阻塞 {blocked} · 过期 {stale}', { done: record.workflow_status.done_tasks, total: record.workflow_status.total_tasks, blocked: record.workflow_status.blocked_tasks, stale: record.workflow_status.stale_tasks })}</p>
    <p className="jx-collaborationScope">{t('状态来自工具记录；展开时读取当前账号可访问的最新协同。')}</p>
    <div className="jx-collaborationActions"><Button loading={busy === 'read'} disabled={!!busy} icon={<ReloadOutlined />} onClick={() => void refresh()}>{t('查看当前协同')}</Button>
      <Button disabled={!!busy} onClick={() => navigateTo(pathForPanel('trade_collaboration', record.collaboration_id))}>{t('打开协同工作台')}</Button>
      {current && canDownloadHandoff(current) && <><Button disabled={!!busy} icon={<DownloadOutlined />} onClick={() => void download('md')}>{t('下载交接 Markdown')}</Button><Button disabled={!!busy} onClick={() => void download('json')}>{t('下载交接 JSON')}</Button></>}
      {expanded && <Button type="text" onClick={() => setExpanded(false)}>{t('收起详情')}</Button>}
    </div>{error && <p role="alert" className="jx-collaborationWarning">{error}</p>}
    {expanded && current && <><p>{current.revision !== receipt.revision ? t('原工具回执为版本 {original}，以下是当前版本 {current}。', { original: receipt.revision, current: current.revision }) : t('已读取当前版本 {revision}。', { revision: current.revision })}</p><CollaborationDetails record={current} /></>}
  </section>;
});
function HistoricalCollaboration({ tool, chatId, messageId }: { tool: ToolCall; chatId: string; messageId: string }) {
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const apply = useChatStore(s => s.applyToolCallOutput);
  const load = async () => {
    if (loading || !tool.id) return; setLoading(true); setError('');
    try {
      const detail = await getToolCallResult(chatId, messageId, tool.id);
      const complete = { ...tool, output: detail.result, outputTruncated: false, outputLoaded: true };
      if (detail.truncated || detail.status !== 'success' || !extractCollaborations([complete]).length) throw new Error('invalid_receipt');
      apply(chatId, messageId, tool.id, detail.result);
    } catch { setError(t('完整协同回执不可用，请让助手重新读取当前协同。')); } finally { setLoading(false); }
  };
  return <section className="jx-collaborationCard"><strong>{t('跨岗位协同记录')}</strong><p>{t('历史回执已精简，加载完整工具记录后查看协同状态。')}</p>
    <Button loading={loading} icon={<ReloadOutlined />} onClick={() => void load()}>{t('加载完整协同回执')}</Button>
    {error && <p role="alert" className="jx-collaborationWarning">{error}</p>}</section>;
}
export const CollaborationCards = memo(function CollaborationCards({ tools, chatId, messageId }: { tools: ToolCall[]; chatId: string; messageId?: string }) {
  const records = useMemo(() => extractCollaborations(tools), [tools]);
  const historical = useMemo(() => tools.filter(tool => tool.name === 'trade_collaboration' && tool.status === 'success' && tool.id && tool.outputTruncated && !tool.outputLoaded), [tools]);
  if (!records.length && (!messageId || !historical.length)) return null;
  return <div className="jx-collaborationCards">{records.map(record => <CollaborationCard key={`${record.collaboration_id}:${record.revision}`} receipt={record} />)}
    {messageId && historical.map(tool => <HistoricalCollaboration key={tool.id} tool={tool} chatId={chatId} messageId={messageId} />)}</div>;
});
