// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, Empty, Input, Modal, Select } from 'antd';
import { DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { t } from '../../i18n';
import { useRouteSubs } from '../../routing/usePanel';
import { navigateTo, pathForPanel } from '../../routing/navigation';
import { ApiResponseError } from '../../utils/apiError';
import { listInquiries, type InquiryRecord } from '../../utils/foreignTradeInquiryApi';
import { listContentPacks, type ContentPackRecord } from '../../utils/foreignTradeContentApi';
import { createCollaboration, downloadCollaborationHandoff, getCollaboration, listCollaborations, refreshCollaborationSources,
  reviewCollaborationTask, updateCollaborationTask, type CollaborationRecord, type CollaborationTask, type CollaborationTaskPatch,
} from '../../utils/foreignTradeCollaborationApi';
import { canDownloadHandoff, downloadVerifiedHandoff, parseCollaboration, readCurrentCollaboration } from '../../utils/foreignTradeCollaborationReceipt';
import { CollaborationDetails, collaborationStatusLabel } from './CollaborationDetails';
import './CollaborationWorkspace.css';
function errorText(error: unknown): string {
  if (error instanceof ApiResponseError && error.status === 409) return t('协同版本、来源或依赖条件已变化。请刷新记录，核对后重试。');
  if (error instanceof ApiResponseError && [401, 403, 404].includes(error.status)) return t('无法读取当前协同记录，请确认登录账号并重试。');
  return error instanceof Error ? error.message : t('操作失败，请重试。');
}
const lines = (value: string) => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
function TaskEditor({ record, task, busy, onSave, onReview, onClose }: {
  record: CollaborationRecord; task: CollaborationTask; busy: boolean; onSave: (patch: CollaborationTaskPatch) => void;
  onReview: (note: string) => void; onClose: () => void;
}) {
  const [assignee, setAssignee] = useState(task.assignee_label); const [status, setStatus] = useState(task.status);
  const [result, setResult] = useState(task.result_note); const [unresolved, setUnresolved] = useState(task.unresolved_items.join('\n'));
  const [risks, setRisks] = useState(task.risks.join('\n')); const [depends, setDepends] = useState(task.depends_on);
  const [confirmed, setConfirmed] = useState(false); const [note, setNote] = useState('');
  const dirty = assignee !== task.assignee_label || status !== task.status || result !== task.result_note ||
    unresolved !== task.unresolved_items.join('\n') || risks !== task.risks.join('\n') || JSON.stringify(depends) !== JSON.stringify(task.depends_on);
  const canReview = !dirty && task.status === 'in_review' && !task.blocked && !task.stale && !!task.result_note.trim() && !!task.assignee_label.trim() &&
    task.depends_on.every(id => record.tasks.find(item => item.id === id)?.status === 'done');
  return <Modal open title={task.title} onCancel={onClose} footer={null} width={680}>
    <div className="jx-collaborationForm">
      <label>{t('负责人姓名标签')}<Input value={assignee} maxLength={120} disabled={busy} onChange={e => setAssignee(e.target.value)} /></label>
      <label>{t('任务状态')}<Select value={status} disabled={busy} onChange={setStatus} options={(['todo','in_progress','in_review','done','cancelled'] as const).map(value => ({ value, label: collaborationStatusLabel(value), disabled: value === 'done' }))} /></label>
      {task.status === 'done' && <small>{t('修改已验收任务会重新打开该任务，相关后续验收需重新核对。')}</small>}
      <label>{t('依赖任务')}<Select mode="multiple" value={depends} disabled={busy} onChange={setDepends} options={record.tasks.filter(item => item.id !== task.id).map(item => ({ value: item.id, label: item.title }))} /></label>
      <label>{t('工作结果与证据')}<Input.TextArea value={result} rows={4} maxLength={5000} disabled={busy} onChange={e => setResult(e.target.value)} /></label>
      <label>{t('未解决事项，每行一项')}<Input.TextArea value={unresolved} rows={2} maxLength={8000} disabled={busy} onChange={e => setUnresolved(e.target.value)} /></label>
      <label>{t('风险提示，每行一项')}<Input.TextArea value={risks} rows={2} maxLength={8000} disabled={busy} onChange={e => setRisks(e.target.value)} /></label>
      <Button disabled={busy || !dirty} onClick={() => onSave({ assignee_label: assignee, status: status === 'done' ? 'in_progress' : status, result_note: result, unresolved_items: lines(unresolved), risks: lines(risks), depends_on: depends })}>{t('保存任务')}</Button>
      <Alert type="info" title={t('验收前请对照标准检查实际资料；状态不会自动视为验收通过。')} />
      <label>{t('人工验收说明')}<Input.TextArea value={note} maxLength={2000} rows={2} disabled={busy || !canReview} onChange={e => setNote(e.target.value)} /></label>
      <Checkbox checked={confirmed} disabled={busy || !canReview} onChange={e => setConfirmed(e.target.checked)}>{t('我已核对交付物、来源版本、依赖与未解决事项。')}</Checkbox>
      <Button type="primary" disabled={busy || !canReview || !confirmed || !note.trim()} onClick={() => onReview(note.trim())}>{t('确认人工验收')}</Button>
      {!canReview && <small>{t('仅已保存、待验收、无阻塞且来源有效的任务可验收。')}</small>}
    </div>
  </Modal>;
}
export function CollaborationWorkspace() {
  const [routeId] = useRouteSubs();
  const [records, setRecords] = useState<CollaborationRecord[]>([]); const [record, setRecord] = useState<CollaborationRecord | null>(null);
  const [inquiries, setInquiries] = useState<InquiryRecord[]>([]); const [packs, setPacks] = useState<ContentPackRecord[]>([]);
  const [title, setTitle] = useState(''); const [inquiryId, setInquiryId] = useState<string>(); const [packId, setPackId] = useState<string>();
  const [relationship, setRelationship] = useState<'transaction' | 'independent_reference'>('independent_reference');
  const [busy, setBusy] = useState('loading'); const [error, setError] = useState(''); const [taskId, setTaskId] = useState('');
  const accept = (value: unknown) => {
    const next = parseCollaboration(value); if (!next) throw new Error(t('协同记录格式无效，请刷新后重试。'));
    setRecord(next); setRecords(current => [next, ...current.filter(item => item.collaboration_id !== next.collaboration_id)]);
    return next;
  };
  useEffect(() => {
    let active = true; setBusy('loading'); setError(''); setRecord(null);
    void Promise.allSettled([listCollaborations(), listInquiries(), listContentPacks(), routeId ? getCollaboration(routeId) : Promise.resolve(null)]).then(results => {
      if (!active) return;
      const [collabs, sourceInquiries, sourcePacks, selected] = results;
      if (collabs.status === 'fulfilled') { const parsed = collabs.value.map(parseCollaboration).filter((item): item is CollaborationRecord => !!item); setRecords(parsed); if (!routeId && parsed[0]) setRecord(parsed[0]); }
      else setError(errorText(collabs.reason));
      if (sourceInquiries.status === 'fulfilled') setInquiries(sourceInquiries.value); else setError(errorText(sourceInquiries.reason));
      if (sourcePacks.status === 'fulfilled') setPacks(sourcePacks.value); else setError(errorText(sourcePacks.reason));
      if (selected.status === 'fulfilled' && selected.value) { try { accept(selected.value); } catch (err) { setError(errorText(err)); } }
      else if (selected.status === 'rejected') setError(errorText(selected.reason));
      setBusy('');
    });
    return () => { active = false; };
  }, [routeId]);
  async function run(name: string, work: () => Promise<void>) {
    if (busy) return; setBusy(name); setError('');
    try { await work(); } catch (err) { setError(errorText(err)); } finally { setBusy(''); }
  }
  const selectedTask = record?.tasks.find(task => task.id === taskId);
  return <section className="jx-collaborationWorkspace">
    <header className="jx-collaborationHeader"><div><h2>{t('跨岗位协同')}</h2><p>{t('在对话中发起分工；这里辅助核对来源、编辑任务与人工验收。')}</p></div>
      <Button onClick={() => navigateTo(pathForPanel('chat'))}>{t('回到对话')}</Button></header>
    <Alert type="info" title={t('当前账号下的角色协同；负责人为姓名标签，不代表独立账号权限。未发送通知或发布内容。')} />
    {error && <Alert type="error" title={error} role="alert" />}
    <details className="jx-collaborationCreate"><summary><PlusOutlined /> {t('从已有询盘创建协同')}</summary><div className="jx-collaborationForm">
      <label>{t('协同标题')}<Input value={title} maxLength={200} disabled={!!busy} onChange={e => setTitle(e.target.value)} /></label>
      <label>{t('来源询盘')}<Select value={inquiryId} disabled={!!busy} onChange={setInquiryId} options={inquiries.map(item => ({ value: item.id, label: `${item.title} · r${item.revision}` }))} /></label>
      <label>{t('产品资料包，可选')}<Select allowClear value={packId} disabled={!!busy} onChange={setPackId} options={packs.map(item => ({ value: item.pack_id, label: `${item.title} · r${item.revision}` }))} /></label>
      {packId ? <label>{t('资料包与交易关系')}<Select value={relationship} disabled={!!busy} onChange={setRelationship} options={[{ value: 'independent_reference', label: t('独立参考，不属于交易产品') }, { value: 'transaction', label: t('本次交易来源') }]} /></label> : <small>{t('未选择资料包时，按询盘中的模拟 SKU 准备候选资料，仍需人工确认后生成内容。')}</small>}
      <small>{t('Raspberry Pi 公开示例只能作为独立参考，不能充当 DESK 模拟产品的规格或报价来源。')}</small>
      <Button type="primary" loading={busy === 'create'} disabled={!!busy || !inquiryId || !title.trim()} onClick={() => void run('create', async () => {
        const next = accept(await createCollaboration({ title: title.trim(), inquiry_id: inquiryId!, ...(packId ? { content_pack_id: packId } : {}), content_relationship: relationship }));
        navigateTo(pathForPanel('trade_collaboration', next.collaboration_id));
      })}>{t('创建协同')}</Button>
    </div></details>
    <div className="jx-collaborationLayout"><aside className="jx-collaborationList" aria-label={t('协同记录列表')}>
      {records.map(item => <button type="button" disabled={!!busy} aria-current={record?.collaboration_id === item.collaboration_id} key={item.collaboration_id} onClick={() => { setTaskId(''); navigateTo(pathForPanel('trade_collaboration', item.collaboration_id)); }}><strong>{item.title}</strong><small>{t('已验收 {done}/{total}', { done: item.workflow_status.done_tasks, total: item.workflow_status.total_tasks })} · r{item.revision}</small></button>)}
    </aside><main>{!record ? <Empty description={busy ? t('正在加载…') : t('暂无协同记录，可在对话中创建或选择已有询盘。')} /> : <>
      <h3>{record.title} <small>r{record.revision}</small></h3><div className="jx-collaborationActions">
        <Button icon={<ReloadOutlined />} disabled={!!busy} onClick={() => void run('read', async () => { accept(await readCurrentCollaboration(record.collaboration_id, getCollaboration)); })}>{t('刷新当前记录')}</Button>
        <Button disabled={!!busy} onClick={() => void run('sources', async () => { accept(await refreshCollaborationSources(record.collaboration_id, record.revision)); })}>{t('更新来源版本并重置受影响验收')}</Button>
        {(['md','json'] as const).map(kind => <Button key={kind} icon={<DownloadOutlined />} disabled={!!busy || !canDownloadHandoff(record)} onClick={() => void run(kind, async () => {
          await downloadVerifiedHandoff(record, kind, { getCurrent: getCollaboration, download: downloadCollaborationHandoff });
        })}>{kind === 'md' ? t('下载交接 Markdown') : t('下载交接 JSON')}</Button>)}
      </div>{!canDownloadHandoff(record) && <p className="jx-collaborationScope">{t('全部任务完成有效人工验收、来源未变化后，才能下载交接文件。')}</p>}
      <CollaborationDetails record={record} onEdit={id => { if (!busy) setTaskId(id); }} />
      <details className="jx-collaborationHistory"><summary>{t('协同变更记录')}</summary><ul>{record.history.slice(-30).reverse().map((item, i) => <li key={i}>r{item.revision} · {item.event} · {new Date(item.at).toLocaleString()}{item.task_id ? ` · ${record.tasks.find(task => task.id === item.task_id)?.title || item.task_id}` : ''}</li>)}</ul></details>
    </>}</main></div>
    <footer className="jx-collaborationFooter">Powered by HugAgentOS</footer>
    {record && selectedTask && <TaskEditor key={`${record.collaboration_id}:${record.revision}:${selectedTask.id}`} record={record} task={selectedTask} busy={!!busy} onClose={() => { if (!busy) setTaskId(''); }}
      onSave={patch => void run('save', async () => { accept(await updateCollaborationTask(record.collaboration_id, selectedTask.id, record.revision, patch)); })}
      onReview={note => void run('review', async () => { accept(await reviewCollaborationTask(record.collaboration_id, selectedTask.id, record.revision, note)); setTaskId(''); })} />}
  </section>;
}
