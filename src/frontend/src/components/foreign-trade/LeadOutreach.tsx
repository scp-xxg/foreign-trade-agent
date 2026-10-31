import { useState } from 'react';
import { Alert, Button, Checkbox, Input, Select, Tag } from 'antd';
import { apiRequest } from '../../api';
import { t } from '../../i18n';

type Dimension = 'product' | 'buyer_type' | 'market' | 'supply';
type Assessment = { dimension: Dimension; result: string; excerpt: string; source_url: string; retrieved_at: string };
export type LeadResult = { fit_score: number | null; evidence_coverage: number; ranking_score: number; priority: string; next_action: string; input_snapshot: Record<string, unknown> };
type Draft = { subject_options: string[]; body: string; body_zh: string; translation_note: string; buyer_evidence: unknown[]; supplier_claims: unknown[]; channel_evidence: unknown; checks: unknown; review_status: string };
export type LeadRecord = { score?: LeadResult; draft?: Draft; approved_at?: string; review_started_at?: string };
type Channel = { channel: string; type: string; source_url: string; retrieved_at: string };
const dimensions: [Dimension, string][] = [['product', '产品与用途'], ['buyer_type', '买家类型'], ['market', '市场与渠道'], ['supply', '供货条件']];
export const priorityLabel = (p: string) => ({ follow_up: t('优先跟进'), research_first: t('优先补资料'), defer: t('暂缓跟进'), stop: t('停止联系') })[p] || p;

export function LeadOutreach({ buyerId, company, website, dossierVersion, review, hardExcluded, channels, busy, record, onChange, perform }: {
  buyerId: string; company: string; website: string; dossierVersion: string;
  review: { decision: string; reason: string; reviewed_at: string }; hardExcluded: boolean; channels: Channel[];
  busy: boolean; record: LeadRecord; onChange: (value: LeadRecord) => void;
  perform: (label: string, work: (signal: AbortSignal) => Promise<void>) => Promise<void>;
}) {
  const [assessments, setAssessments] = useState<Assessment[]>(dimensions.map(([dimension]) => ({ dimension, result: 'unknown', excerpt: '', source_url: website, retrieved_at: '' })));
  const [blocked, setBlocked] = useState(false);
  const [sender, setSender] = useState(''); const [product, setProduct] = useState('');
  const [claim, setClaim] = useState(''); const [reference, setReference] = useState('');
  const [fact, setFact] = useState(''); const [factDimension, setFactDimension] = useState<Dimension>('product');
  const [channel, setChannel] = useState(channels[0]?.channel || '');
  const [goal, setGoal] = useState('find_contact'); const [confirmed, setConfirmed] = useState(false);
  const selected = channels.find(c => c.channel === channel);
  const lead = { buyer_id: buyerId, dossier_version: dossierVersion, review_version: review.reviewed_at, review_decision: review.decision,
    review_reason: review.reason, hard_excluded: hardExcluded, do_not_contact: blocked, has_channel: channels.length > 0, assessments };
  async function post<T>(action: string, input: unknown, signal: AbortSignal): Promise<T> {
    return (await apiRequest<{ data: T }>(`/v1/foreign-trade/buyer-search/${action}`, { method: 'POST', body: JSON.stringify(input), signal })).data;
  }
  function editSupplier(setter: (v: string) => void, value: string) { setter(value); setConfirmed(false); onChange({ score: record.score }); }
  return <section className="lead-outreach">
    <h4>{t('线索评分与跟进优先级')}</h4>
    <p>{t('请依据已读证据判断四个维度。未知不算不匹配；默认权重35/25/20/20，门槛尚未经过业务校准。')}</p>
    {assessments.map((a, index) => <fieldset key={a.dimension} disabled={busy}><legend>{t(dimensions[index][1])}</legend>
      <Select aria-label={`${t(dimensions[index][1])} ${company}`} value={a.result} style={{ width: '100%' }} disabled={busy} options={[
        { value: 'unknown', label: t('未知') }, { value: 'match', label: t('符合') }, { value: 'partial', label: t('部分符合') }, { value: 'mismatch', label: t('不符合') },
      ]} onChange={result => { setAssessments(v => v.map((x, i) => i === index ? { ...x, result } : x)); onChange({}); }} />
      {a.result !== 'unknown' && <>{(['excerpt', 'source_url', 'retrieved_at'] as const).map((field, i) => <label key={field}>{t(['证据摘录', '证据来源 URL', '证据获取时间'][i])}<Input aria-label={`${a.dimension} ${field} ${company}`} value={a[field]} disabled={busy} onChange={e => { setAssessments(v => v.map((x, j) => j === index ? { ...x, [field]: e.target.value } : x)); onChange({}); }} /></label>)}</>}
    </fieldset>)}
    <Checkbox checked={blocked} disabled={busy} onChange={e => { setBlocked(e.target.checked); onChange({}); }}>{t('已有拒绝联系记录，停止联系')}</Checkbox>
    <Button disabled={busy || !review.reason.trim()} onClick={() => void perform(`prioritize:${buyerId}`, async signal => { const score = await post<LeadResult>('prioritize', lead, signal); onChange({ score }); })}>{t('计算跟进优先级')}</Button>
    {record.score && <><Tag>{priorityLabel(record.score.priority)}</Tag><p>{t('匹配分 / 证据覆盖率')}：{record.score.fit_score ?? '—'} / {(record.score.evidence_coverage * 100).toFixed(0)}%</p><p>{record.score.next_action}</p></>}
    <h4>{t('个性化开发信')}</h4>
    <p>{t('基于已审核英文资料生成模板草稿。仅优先跟进线索可生成；通用渠道使用团队称呼，不推断负责人。')}</p>
    <label>{t('联系渠道')}<Select aria-label={`${t('联系渠道')} ${company}`} style={{ width: '100%' }} disabled={busy} value={channel || undefined} options={channels.map(c => ({ value: c.channel, label: c.channel }))} onChange={v => editSupplier(setChannel, v)} /></label>
    {[[t('发件公司（英文）'), sender, setSender], [t('产品名称（英文）'), product, setProduct], [t('供货声明（英文）'), claim, setClaim], [t('供货声明来源或资料编号'), reference, setReference], [t('买家事实（英文，可留空）'), fact, setFact]].map(([label, value, setter]) => <label key={String(label)}>{String(label)}<Input aria-label={`${String(label)} ${company}`} value={String(value)} disabled={busy} onChange={e => editSupplier(setter as (v: string) => void, e.target.value)} /></label>)}
    {fact.trim() && <label>{t('个性化事实关联维度')}<Select aria-label={t('个性化事实关联维度')} value={factDimension} disabled={busy} style={{ width: '100%' }} options={dimensions.map(([value, label]) => ({ value, label: t(label) }))} onChange={v => { setFactDimension(v); setConfirmed(false); onChange({ score: record.score }); }} /></label>}
    <label>{t('沟通目标')}<Select aria-label={t('沟通目标')} value={goal} disabled={busy} style={{ width: '100%' }} options={[{ value: 'find_contact', label: t('确认负责人') }, { value: 'share_catalog', label: t('征询发送目录') }, { value: 'confirm_interest', label: t('确认品类兴趣') }]} onChange={v => editSupplier(setGoal, v)} /></label>
    <Checkbox checked={confirmed} disabled={busy} onChange={e => { setConfirmed(e.target.checked); onChange({ score: record.score }); }}>{t('我已核对联系用途、英文事实及供货承诺')}</Checkbox>
    <Button disabled={busy || record.score?.priority !== 'follow_up' || !selected || !confirmed || !sender.trim() || !product.trim() || !claim.trim() || !reference.trim()} onClick={() => void perform(`outreach:${buyerId}`, async signal => {
      const draft = await post<Draft>('outreach', { lead, channel: selected!.channel, channel_type: selected!.type, channel_source_url: selected!.source_url, channel_retrieved_at: selected!.retrieved_at, company_name: company, sender_company: sender, product_en: product, supplier_claim_en: claim, supplier_claim_reference: reference, buyer_fact_en: fact, buyer_fact_dimension: factDimension, goal, facts_confirmed: confirmed }, signal);
      onChange({ score: record.score, draft, review_started_at: new Date().toISOString() });
    })}>{t('生成开发信草稿')}</Button>
    {record.draft && <><Tag>{record.approved_at ? t('已批准草稿') : t('待审核草稿')}</Tag>
      <label>{t('邮件主题')}<Select aria-label={t('邮件主题')} style={{ width: '100%' }} defaultValue={record.draft.subject_options[0]} options={record.draft.subject_options.map(value => ({ value, label: value }))} disabled={busy} onChange={value => onChange({ ...record, approved_at: undefined, draft: { ...record.draft!, subject_options: [value, ...record.draft!.subject_options.filter(s => s !== value)], review_status: 'draft' } })} /></label>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{record.draft.body}</pre><pre style={{ whiteSpace: 'pre-wrap' }}>{record.draft.body_zh}</pre>
      <Alert type="info" title={record.draft.translation_note} />
      <details><summary>{t('开发信证据与检查')}</summary><pre>{JSON.stringify({ buyer_evidence: record.draft.buyer_evidence, supplier_claims: record.draft.supplier_claims, channel_evidence: record.draft.channel_evidence, checks: record.draft.checks }, null, 2)}</pre></details>
      <Checkbox disabled={busy} checked={!!record.approved_at} onChange={e => onChange({ ...record, approved_at: e.target.checked ? new Date().toISOString() : undefined, draft: { ...record.draft!, review_status: e.target.checked ? 'approved' : 'draft' } })}>{t('我已审核此草稿（不会发送）')}</Checkbox>
    </>}
  </section>;
}
