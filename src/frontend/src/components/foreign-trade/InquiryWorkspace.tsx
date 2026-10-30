// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Empty, Input, InputNumber, Select, Tag } from 'antd';
import { CheckCircleOutlined, CopyOutlined, GlobalOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { t } from '../../i18n';
import { useRouteSubs } from '../../routing/usePanel';
import { navigateTo, panelFromPath, pathForPanel } from '../../routing/navigation';
import { canApplyRecordRead, canReplaceRecord, shouldPreserveRecordDraft } from '../../utils/foreignTradeRecordView';
import { TradeQuoteCard } from '../chat/TradeQuoteCard';
import { extractTradeQuotes } from '../../utils/foreignTradeQuote';
import { ApiResponseError } from '../../utils/apiError';
import { addInquiryFollowup, createInquiry, getInquiry, inquiryAction, listInquiries, searchInquiryProducts,
  updateInquiry, updateInquiryFollowup, interpretInquiry, type InquiryInterpretation, type InquiryInput, type InquiryProduct, type InquiryRecord,
} from '../../utils/foreignTradeInquiryApi';
import './InquiryWorkspace.css';

const blankInquiry = (): InquiryInput => ({
  title: '', buyer: { company_name: '', website: '', email: '', country: '' }, raw_inquiry: '',
  items: [], destination_country: '', requested_lead_days: null, is_demo_inquiry: true,
});
const sampleInquiry = (): InquiryInput => ({
  title: t('Lyreco 公开资料核验 · 演示询盘'),
  buyer: { company_name: 'LYRECO', website: 'https://www.lyreco.com/group/', email: '', country: 'FR' },
  raw_inquiry: 'DEMONSTRATION ONLY — constructed by our team, not an actual Lyreco inquiry or order.\n\nWe are evaluating office storage products for delivery to Spain. Please quote 500 units of DESK-001 Modular Desk Organizer with standard packaging. Please provide the specifications, minimum order quantity and production lead time. Freight and import charges should be confirmed separately.',
  items: [{ sku: 'DESK-001', quantity: 500, custom_packaging: false }],
  destination_country: 'Spain', requested_lead_days: null, is_demo_inquiry: true,
});
function inputFrom(record: InquiryRecord): InquiryInput {
  return { title: record.title, buyer: { ...record.buyer }, raw_inquiry: record.raw_inquiry,
    items: record.items.map((item) => ({ ...item })), destination_country: record.destination_country,
    requested_lead_days: record.requested_lead_days, is_demo_inquiry: record.is_demo_inquiry };
}
function safePublicLink(value?: string): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; }
  catch { return undefined; }
}
function dateText(value?: string | null, timezone?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  try { return date.toLocaleString(undefined, { timeZone: timezone || undefined, hour12: false }); }
  catch { return date.toLocaleString(); }
}
function statusText(status: string): string {
  if (status === 'registry_match') return t('登记名称匹配');
  if (status === 'user_provided') return t('用户提供');
  if (status === 'retrieved') return t('已获取');
  if (status === 'pending') return t('待跟进');
  if (status === 'completed') return t('已完成');
  if (status === 'cancelled') return t('已取消');
  if (['verified', 'confirmed', 'official_source'].includes(status)) return t('已核验');
  if (['self_reported', 'official_self_reported', 'public_statement'].includes(status)) return t('官网自述');
  if (['unknown', 'unverified', 'not_found', 'not_provided'].includes(status)) return t('未核实');
  if (['failed', 'unavailable', 'fetch_failed'].includes(status)) return t('未能获取');
  return status;
}
function eventText(event: string): string {
  const labels: Record<string, string> = { created: t('创建询盘'), inquiry_updated: t('更新询盘条件'), buyer_verified: t('核验买家公开资料'), quote_calculated: t('计算报价'), draft_generated: t('生成回复草稿'), followup_created: t('安排跟进'), followup_completed: t('完成跟进'), followup_cancelled: t('取消跟进'), buyer_replied: t('记录客户回复'), followups_resumed: t('恢复跟进') };
  return labels[event] || t('更新记录');
}
function errorText(error: unknown): string {
  const messages: string[] = [];
  if (error instanceof ApiResponseError && error.status === 409) return t('此询盘已在其他页面更新。请点击刷新记录，再核对并重试。');
  if (error instanceof Error) messages.push(error.message);
  if (error instanceof ApiResponseError) {
    const payload = error.payload as { detail?: { errors?: { message?: string }[]; details?: { errors?: { message?: string }[] } }; data?: { errors?: { message?: string }[] } };
    for (const issue of payload?.detail?.details?.errors || payload?.detail?.errors || payload?.data?.errors || []) if (issue.message) messages.push(issue.message);
  }
  return [...new Set(messages)].join(' · ') || t('操作失败，请重试。');
}

export function InquiryWorkspace() {
  const [routeId] = useRouteSubs();
  const [records, setRecords] = useState<InquiryRecord[]>([]);
  const [record, setRecord] = useState<InquiryRecord | null>(null);
  const [form, setForm] = useState<InquiryInput>(blankInquiry);
  const [busy, setBusy] = useState('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [products, setProducts] = useState<InquiryProduct[] | null>(null);
  const [dueAt, setDueAt] = useState('');
  const [followupTitle, setFollowupTitle] = useState('');
  const [draftLanguage, setDraftLanguage] = useState<'zh' | 'en'>('en');
  const [showOnlyPending, setShowOnlyPending] = useState(false);
  const [interpretation, setInterpretation] = useState<InquiryInterpretation | null>(null);
  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(record ? inputFrom(record) : blankInquiry()), [form, record]);
  const quote = useMemo(() => record?.quote && !dirty ? extractTradeQuotes([{ name: 'calculate_quote', status: 'success', output: record.quote }])[0] : undefined, [record?.quote, dirty]);
  const locked = !!busy;
  const updateForm = (patch: Partial<InquiryInput>) => setForm((current) => ({ ...current, ...patch }));
  const updateBuyer = (key: keyof InquiryInput['buyer'], value: string) => setForm((current) => ({ ...current, buyer: { ...current.buyer, [key]: value } }));
  const view = useRef({ record: null as InquiryRecord | null, path: pathForPanel('trade_inquiries', routeId), read: 0, mounted: true });
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const busyRef = useRef(busy); busyRef.current = busy;
  useEffect(() => { view.current.mounted = true; return () => { view.current.mounted = false; view.current.read++; }; }, []);
  const accept = (next: InquiryRecord) => {
    if (!view.current.mounted) return next;
    const previous = view.current.record;
    if (!canReplaceRecord({ id: next.id, revision: next.revision }, previous ? { id: previous.id, revision: previous.revision } : null)) {
      throw new Error(t('记录版本已变化，请刷新后重试。'));
    }
    view.current.record = next; view.current.read++;

    setRecord(next); setForm(inputFrom(next)); setInterpretation(null);
    setRecords((current) => [next, ...current.filter((item) => item.id !== next.id)].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    const nextPath = pathForPanel('trade_inquiries', next.id);
    view.current.path = nextPath;
    if (panelFromPath() === 'trade_inquiries') navigateTo(nextPath);
    return next;
  };
  useEffect(() => {
    const path = pathForPanel('trade_inquiries', routeId);
    if (shouldPreserveRecordDraft(view.current.path, path, dirtyRef.current, busyRef.current)) {
      setError(t('当前记录有未保存修改或操作正在进行，请完成后再切换。'));
      navigateTo(view.current.path, { replace: true });
      return;
    }
    view.current.path = path;
    // A successful save already installed this record; URL synchronization must
    // not clear the form or launch a stale read over a newer mutation response.
    if (routeId && view.current.record?.id === routeId) return;
    const request = ++view.current.read;
    let active = true; view.current.record = null;
    setBusy('loading'); setError(''); setRecord(null); setForm(blankInquiry()); setInterpretation(null);
    Promise.all([listInquiries(), routeId ? getInquiry(routeId) : Promise.resolve(null)]).then(([items, selected]) => {
      if (!active || request !== view.current.read || dirtyRef.current) return;
      setRecords(items);
      const initial = selected || items[0];
      const current = view.current.record;
      if (initial && canApplyRecordRead(request, view.current.read, dirtyRef.current,
        { id: initial.id, revision: initial.revision }, current ? { id: current.id, revision: current.revision } : null, routeId)) {
        accept(initial);
      }
      setBusy('');
    }).catch((err) => { if (active && request === view.current.read) setError(errorText(err)); })
      .finally(() => { if (active && request === view.current.read) setBusy(''); });
    return () => { active = false; };
  }, [routeId]);
  async function run(name: string, task: () => Promise<void>) {
    if (locked) return;
    setBusy(name); setError(''); setNotice('');
    try { await task(); } catch (err) { setError(errorText(err)); } finally { setBusy(''); }
  }
  async function ensureSaved(): Promise<InquiryRecord> {
    if (!form.raw_inquiry.trim()) throw new Error(t('请先粘贴询盘原文。'));
    const input = { ...form, title: form.title.trim() || form.buyer.company_name.trim() || t('未命名询盘') };
    if (!record) return accept(await createInquiry(input));
    if (dirty) return accept(await updateInquiry(record.id, record.revision, input));
    return record;
  }
  function act(action: 'verify-buyer' | 'quote' | 'draft' | 'mark-replied' | 'resume-followups') {
    void run(action, async () => {
      const saved = await ensureSaved();
      accept(await inquiryAction(saved.id, saved.revision, action));
      if (action === 'resume-followups') setNotice(t('已恢复跟进状态，请安排新的跟进待办。'));
      if (action === 'mark-replied') setNotice(t('已记录客户回复，未完成的跟进待办已取消。'));
    });
  }
  function newInquiry(sample = false) {
    view.current.record = null; view.current.read++;
    setRecord(null); setForm(sample ? sampleInquiry() : blankInquiry()); setProducts(null); setQuery('');
    setError(''); setNotice(''); setDueAt(''); setFollowupTitle(''); setInterpretation(null);
  }
  const filteredRecords = records.filter((item) => !showOnlyPending || item.followups.some((task) => task.status === 'pending'));
  const pendingCount = records.reduce((n, item) => n + item.followups.filter((task) => task.status === 'pending').length, 0);
  const draftStale = dirty || !!record?.drafts?.stale;
  const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

  return <main className="jx-inquiryWorkspace" aria-label={t('询盘工作台')}>
    <header className="jx-inquiryHeader">
      <div><div className="jx-inquiryEyebrow">FOREIGN TRADE · WORKSPACE</div><h1>{t('询盘工作台')}</h1>
        <p>{t('核验买家、准备报价、安排下一次跟进。')}</p></div>
      <Button icon={<GlobalOutlined />} disabled={locked || dirty} onClick={() => newInquiry(true)}>{t('体验 Lyreco 公开资料示例')}</Button>
    </header>
    <div className="jx-inquiryLayout">
      <aside className="jx-inquirySidebar" aria-label={t('询盘列表')}>
        <div className="jx-inquirySidebarTop"><strong>{t('我的询盘')}</strong><Tag>{records.length}</Tag></div>
        <Button block type="primary" icon={<PlusOutlined />} disabled={locked || dirty} onClick={() => newInquiry()}>{t('新建询盘')}</Button>
        <div className="jx-inquiryListTools"><Checkbox checked={showOnlyPending} onChange={(e) => setShowOnlyPending(e.target.checked)}>{t('只看待跟进')}</Checkbox>
          <Button type="text" size="small" icon={<ReloadOutlined />} aria-label={t('刷新记录')} disabled={locked || dirty} onClick={() => void run('refresh', async () => {
            const items = await listInquiries(); setRecords(items); if (record) accept(await getInquiry(record.id));
          })} /></div>
        <p className="jx-inquiryMuted">{t('{count} 项跟进待办', { count: pendingCount })}</p>
        <nav className="jx-inquiryList">
          {!filteredRecords.length && <p className="jx-inquiryMuted">{t('暂无询盘，先载入示例或新建。')}</p>}
          {filteredRecords.map((item) => <button key={item.id} className={`jx-inquiryListItem ${item.id === record?.id ? 'is-active' : ''}`} disabled={locked || dirty} onClick={() => void run('open', async () => { accept(await getInquiry(item.id)); setProducts(null); })}>
            <strong>{item.title || item.buyer.company_name || t('未命名询盘')}</strong>
            <span>{item.buyer.company_name || t('买家公司待补充')}</span>
            <small>{item.replied_at ? t('客户已回复') : item.quote ? t('已有报价') : t('待处理')} · {dateText(item.updated_at)}</small>
          </button>)}
        </nav>
      </aside>
      <div className="jx-inquiryMain" aria-busy={locked}>
        {error && <Alert type="error" showIcon title={error} />}
        {notice && <Alert type="success" showIcon title={notice} />}
        <div className="jx-inquiryRecordHeader"><div><h2>{record?.title || t('新的询盘')}</h2><span className="jx-inquiryMuted">{record ? t('记录版本 {revision} · 更新于 {time}', { revision: record.revision, time: dateText(record.updated_at) }) : t('保存后，报价、事实卡与跟进会保留在当前账号。')}</span></div>
          <div className="jx-inquiryActions"><Button disabled={locked || !dirty} onClick={() => { setForm(record ? inputFrom(record) : blankInquiry()); setError(''); }}>{t('放弃修改')}</Button>
          <Button type="primary" loading={busy === 'save'} disabled={locked || !dirty} onClick={() => void run('save', async () => { await ensureSaved(); setNotice(t('询盘已保存。')); })}>{t('保存询盘')}</Button></div></div>
        {dirty && record && <Alert type="warning" showIcon title={t('有未保存的修改。下一次核验、报价或生成草稿前会自动保存；旧报价与草稿需重新生成。')} />}
        <section className="jx-inquirySection">
          <div className="jx-inquirySectionHeading"><span className="jx-inquiryStep">01</span><div><h3>{t('买家与询盘')}</h3><p>{t('先核对来源，再决定如何回复。公开信息不等于信用担保。')}</p></div></div>
          {form.is_demo_inquiry && <Alert type="info" showIcon title={t('演示询盘')} description={t('可使用真实企业的公开资料；询盘由团队构造，非该企业真实订单或合作关系。产品与价格仍为模拟数据。')} />}
          <div className="jx-inquiryGrid">
            <label>{t('询盘标题')}<Input value={form.title} disabled={locked} maxLength={200} onChange={(e) => updateForm({ title: e.target.value })} /></label>
            <label>{t('买家公司')}<Input value={form.buyer.company_name} disabled={locked} maxLength={200} onChange={(e) => updateBuyer('company_name', e.target.value)} /></label>
            <label>{t('公司官网')}<Input value={form.buyer.website} disabled={locked} placeholder="https://www.example.com" onChange={(e) => updateBuyer('website', e.target.value)} /></label>
            <label>{t('买家邮箱（可留空）')}<Input value={form.buyer.email} disabled={locked} onChange={(e) => updateBuyer('email', e.target.value)} /></label>
            <label>{t('公司所在国（未核实可留空）')}<Input value={form.buyer.country} disabled={locked} onChange={(e) => updateBuyer('country', e.target.value)} /></label>
            <div className="jx-inquiryDemoControl"><Checkbox checked={form.is_demo_inquiry} disabled={locked || !!record} onChange={(e) => updateForm({ is_demo_inquiry: e.target.checked })}>{t('这是团队构造的演示询盘')}</Checkbox></div>
          </div>
          <label className="jx-inquiryField">{t('询盘原文')}<Input.TextArea value={form.raw_inquiry} disabled={locked} rows={5} maxLength={20000} onChange={(e) => updateForm({ raw_inquiry: e.target.value })} placeholder={t('粘贴客户询盘，或从页面右上角载入公开资料示例。')} /></label>
          <div className="jx-inquiryActions"><Button icon={<SearchOutlined />} loading={busy === 'verify-buyer'} disabled={locked || (!form.buyer.website.trim() && !form.buyer.company_name.trim())} onClick={() => act('verify-buyer')}>{t('核验公开信息')}</Button><Button loading={busy === 'interpret'} disabled={locked || !form.raw_inquiry.trim()} onClick={() => void run('interpret', async () => { const saved = await ensureSaved(); setInterpretation(await interpretInquiry(saved.id, saved.revision)); })}>{t('提取询盘需求建议')}</Button><span className="jx-inquiryMuted">{t('保留来源链接与核验时间；查不到的事项明确标为未核实。')}</span></div>
          {interpretation && !dirty && interpretation.revision === record?.revision && <div className="jx-inquiryInterpretation">
            <div className="jx-inquiryCardHeading"><h4>{t('待确认的需求建议')}</h4><Tag>{interpretation.method === 'ai' ? t('AI 提取') : t('规则提取')}</Tag></div>
            <p className="jx-inquiryMuted">{t('请对照询盘原文核对。采用建议会替换下方对应条件，保存后才会用于报价。')}</p>
            <div className="jx-inquiryItems">{interpretation.suggestions.items?.map((item, index) => <div className="jx-inquiryItem" key={index}><strong>{item.sku}</strong>
              <label>{t('采购数量')}<InputNumber min={1} precision={0} value={item.quantity} placeholder={t('待确认')} onChange={(value) => setInterpretation({ ...interpretation, suggestions: { ...interpretation.suggestions, items: interpretation.suggestions.items?.map((line, i) => i === index ? { ...line, quantity: value || undefined } : line) } })} /></label>
              <label>{t('包装方式')}<Select value={item.custom_packaging === undefined ? undefined : item.custom_packaging ? 'custom' : 'standard'} placeholder={t('待确认')} options={[{ value: 'standard', label: t('标准包装') }, { value: 'custom', label: t('定制包装') }]} onChange={(value) => setInterpretation({ ...interpretation, suggestions: { ...interpretation.suggestions, items: interpretation.suggestions.items?.map((line, i) => i === index ? { ...line, custom_packaging: value === 'custom' } : line) } })} /></label></div>)}</div><ul>
              {interpretation.suggestions.destination_country && <li>{t('交付目的国')}：{interpretation.suggestions.destination_country}</li>}
              {interpretation.suggestions.requested_lead_days != null && <li>{t('期望生产周期（天，可留空）')}：{interpretation.suggestions.requested_lead_days}</li>}</ul>
            {!!interpretation.evidence.length && <details><summary>{t('原文依据')}</summary><ul>{interpretation.evidence.map((evidence, index) => <li key={index}>{evidence.quote}</li>)}</ul></details>}
            {!!interpretation.warnings.length && <ul className="jx-inquiryWarnings">{interpretation.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
            <p className="jx-inquiryMuted">{t('未提取到的数量或包装留空，请人工确认后再采用。')}</p>
            <Button disabled={locked || !Object.keys(interpretation.suggestions).length || !!interpretation.suggestions.items?.some((item) => !item.quantity || item.custom_packaging === undefined)} onClick={() => {
              const { items, ...fields } = interpretation.suggestions;
              updateForm({ ...fields, ...(items?.length ? { items: items.map((item) => ({ sku: item.sku, quantity: item.quantity!, custom_packaging: item.custom_packaging! })) } : {}) });
              setInterpretation(null); setNotice(t('已填入建议，请核对条件后保存或计算报价。'));
            }}>{t('确认并采用建议')}</Button>
          </div>}
          {record?.buyer_card && <div className="jx-inquiryBuyerCard">
            <div className="jx-inquiryCardHeading"><h4>{t('买家事实卡')}</h4><span>{t('核验时间：{time}', { time: dateText(record.buyer_card.checked_at) })}</span></div>
            {dirty && <p className="jx-inquiryWarning">{t('当前事实卡对应已保存的买家资料；修改后请重新核验。')}</p>}
            <div className="jx-inquiryFacts">{record.buyer_card.facts.map((fact) => <article key={fact.key}>
              <div><strong>{fact.label}</strong><Tag>{statusText(fact.status)}</Tag></div><p>{typeof fact.value === 'string' ? fact.value || t('未核实') : JSON.stringify(fact.value)}</p>
              {fact.evidence && <small>{fact.evidence}</small>}
              {safePublicLink(fact.source_url) && <a href={safePublicLink(fact.source_url)} target="_blank" rel="noopener noreferrer">{t('查看原始来源')} ↗</a>}
            </article>)}</div>
            {!!record.buyer_card.warnings.length && <ul className="jx-inquiryWarnings">{record.buyer_card.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
            <details><summary>{t('公开来源与获取状态')}</summary><ul className="jx-inquirySourceList">{record.buyer_card.sources.map((source, i) => <li key={i}>
              {safePublicLink(source.url) ? <a href={safePublicLink(source.url)} target="_blank" rel="noopener noreferrer">{source.title || source.url} ↗</a> : <span>{source.title}</span>}
              <small>{statusText(source.status)} · {dateText(source.retrieved_at)}</small></li>)}</ul></details>
          </div>}
        </section>

        <section className="jx-inquirySection">
          <div className="jx-inquirySectionHeading"><span className="jx-inquiryStep">02</span><div><h3>{t('产品与报价')}</h3><p>{t('先确认商品、数量与包装，再使用已保存的规则计算。')}</p></div></div>
          <div className="jx-inquirySearch"><Input value={query} disabled={locked} aria-label={t('产品名称或 SKU')} placeholder={t('查询产品名称或 SKU，例如 DESK-001')} onChange={(e) => setQuery(e.target.value)} onPressEnter={() => void run('search', async () => { const result = await searchInquiryProducts(query); setProducts(result.data.products); })} />
            <Button icon={<SearchOutlined />} loading={busy === 'search'} disabled={locked} onClick={() => void run('search', async () => { const result = await searchInquiryProducts(query); setProducts(result.data.products); })}>{t('查询产品')}</Button></div>
          {products && <div className="jx-inquiryProducts">
            {!products.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('没有找到匹配产品，请换一个关键词。')} />}
            {products.map((product) => <article key={product.sku} className="jx-inquiryProduct">
              <div><strong>{product.name_zh}</strong><Tag>{product.sku}</Tag><Tag>DEMO</Tag></div>
              <p>{product.name} · {product.material} · {product.dimensions_cm} cm</p>
              <p>{t('起订量 {moq} 件 · 参考生产周期 {days} 天', { moq: product.moq, days: product.production_lead_days })}</p>
              <div className="jx-inquiryPriceTiers">{product.price_tiers.map((tier) => <span key={tier.min_quantity}>{tier.min_quantity}–{tier.max_quantity ?? '∞'} {t('件')} · {product.currency} {tier.unit_price}</span>)}</div>
              <p className="jx-inquiryMuted">{t('定制包装：{moq} 件起，每件加收 {currency} {fee}', { moq: product.packaging.custom.moq, currency: product.currency, fee: product.packaging.custom.unit_surcharge })}</p>
              <Button size="small" disabled={locked || form.items.some((item) => item.sku === product.sku)} onClick={() => updateForm({ items: [...form.items, { sku: product.sku, quantity: product.moq, custom_packaging: false }] })}>{t('加入报价')}</Button>
            </article>)}
          </div>}
          <div className="jx-inquiryItems">
            {form.items.map((item, index) => <div className="jx-inquiryItem" key={index}>
              <label>{t('产品 SKU')}<Input value={item.sku} disabled={locked} onChange={(e) => updateForm({ items: form.items.map((line, i) => i === index ? { ...line, sku: e.target.value } : line) })} /></label>
              <label>{t('采购数量')}<InputNumber min={1} precision={0} value={item.quantity} disabled={locked} onChange={(value) => updateForm({ items: form.items.map((line, i) => i === index ? { ...line, quantity: value || 0 } : line) })} /></label>
              <label>{t('包装方式')}<Select value={item.custom_packaging ? 'custom' : 'standard'} disabled={locked} options={[{ value: 'standard', label: t('标准包装') }, { value: 'custom', label: t('定制包装') }]} onChange={(value) => updateForm({ items: form.items.map((line, i) => i === index ? { ...line, custom_packaging: value === 'custom' } : line) })} /></label>
              <Button type="text" danger disabled={locked} onClick={() => updateForm({ items: form.items.filter((_, i) => i !== index) })}>{t('移除')}</Button>
            </div>)}
            <Button type="dashed" icon={<PlusOutlined />} disabled={locked} onClick={() => updateForm({ items: [...form.items, { sku: '', quantity: 1, custom_packaging: false }] })}>{t('添加产品行')}</Button>
          </div>
          <div className="jx-inquiryGrid">
            <label>{t('交付目的国')}<Input value={form.destination_country} disabled={locked} onChange={(e) => updateForm({ destination_country: e.target.value })} /></label>
            <label>{t('期望生产周期（天，可留空）')}<InputNumber min={1} precision={0} value={form.requested_lead_days} disabled={locked} onChange={(value) => updateForm({ requested_lead_days: value })} /></label>
          </div>
          <p className="jx-inquiryMuted">{t('公司所在国与交付目的国分别记录。生产周期不包含运输时间。')}</p>
          <div className="jx-inquiryActions"><Button type="primary" loading={busy === 'quote'} disabled={locked || !form.items.length} onClick={() => act('quote')}>{t('确认条件并计算报价')}</Button></div>
          {quote && <>
            <div className="jx-inquiryTableWrap"><table className="jx-inquiryQuoteTable"><thead><tr><th>SKU</th><th>{t('数量')}</th><th>{t('商品单价')}</th><th>{t('包装单价')}</th><th>{t('行小计')}</th></tr></thead>
              <tbody>{quote.data.items.map((line) => <tr key={line.sku}><td>{line.sku}<small>{line.name_zh}</small></td><td>{line.quantity}</td><td>{quote.data.currency} {line.unit_price}</td><td>{quote.data.currency} {line.packaging_unit_surcharge}</td><td>{quote.data.currency} {line.line_subtotal}</td></tr>)}</tbody></table></div>
            <p>{t('参考生产周期：{days} 天', { days: quote.data.production_lead_days })}</p>
            {!!quote.snapshot.warnings.length && <ul className="jx-inquiryWarnings">{quote.snapshot.warnings.map((warning, index) => <li key={index}>{warning.message}</li>)}</ul>}
            <TradeQuoteCard quote={quote} />
          </>}
        </section>
        <section className="jx-inquirySection">
          <div className="jx-inquirySectionHeading"><span className="jx-inquiryStep">03</span><div><h3>{t('回复草稿与跟进')}</h3><p>{t('草稿供人工审阅和复制，系统不会自动发邮件。')}</p></div></div>
          <div className="jx-inquiryActions"><Button loading={busy === 'draft'} disabled={locked} onClick={() => act('draft')}>{t('生成中英文回复草稿')}</Button>
            {record?.drafts && <Tag>{record.drafts.kind === 'quote' ? t('报价回复') : t('待澄清回复')}</Tag>}</div>
          {record?.drafts && <div className="jx-inquiryDraft">
            {draftStale && <Alert type="warning" showIcon title={t('报价条件已修改，此草稿已过期。请重新计算报价并生成草稿。')} />}
            <div className="jx-inquiryCardHeading"><Select aria-label={t('回复语言')} value={draftLanguage} onChange={setDraftLanguage} options={[{ value: 'en', label: 'English' }, { value: 'zh', label: t('中文') }]} />
              <Button icon={<CopyOutlined />} disabled={draftStale} onClick={() => void run('copy', async () => { await navigator.clipboard.writeText(record.drafts![draftLanguage]); setNotice(t('草稿已复制，请审阅后自行发送。')); })}>{t('复制草稿')}</Button></div>
            <p className="jx-inquiryMuted">{record.drafts.method === 'deterministic_template' ? t('根据已保存资料套用业务模板生成，未经人工审阅不得作为最终承诺。') : t('根据已保存资料生成的回复草稿，未经人工审阅不得作为最终承诺。')}</p>
            <pre>{record.drafts[draftLanguage]}</pre>
          </div>}
          <div className="jx-inquiryFollowups"><div className="jx-inquiryCardHeading"><h4>{t('跟进待办')}</h4>
            <Button icon={<CheckCircleOutlined />} loading={busy === 'mark-replied'} disabled={locked || !record || !!record.replied_at} onClick={() => act('mark-replied')}>{record?.replied_at ? t('客户已回复') : t('标记客户已回复')}</Button>{record?.replied_at && <Button disabled={locked} loading={busy === 'resume-followups'} onClick={() => act('resume-followups')}>{t('恢复跟进')}</Button>}</div>
            <p className="jx-inquiryMuted">{t('在工作台记录跟进时间；标记客户已回复后，未完成待办会自动取消。')}</p>
            {record?.followups.map((task) => <div className={`jx-inquiryTask ${task.status === 'pending' && new Date(task.due_at).getTime() < Date.now() ? 'is-overdue' : ''}`} key={task.id}>
              <div><strong>{task.title}</strong><span>{dateText(task.due_at, task.timezone)} · {task.timezone}</span></div>
              <Tag>{task.status === 'pending' && new Date(task.due_at).getTime() < Date.now() ? t('已到跟进时间') : statusText(task.status)}</Tag>
              {task.status === 'pending' && <div className="jx-inquiryActions">
                <Button size="small" disabled={locked} onClick={() => void run('task', async () => { const saved = await ensureSaved(); accept(await updateInquiryFollowup(saved.id, saved.revision, task.id, 'completed')); })}>{t('完成')}</Button>
                <Button size="small" disabled={locked} onClick={() => void run('task', async () => { const saved = await ensureSaved(); accept(await updateInquiryFollowup(saved.id, saved.revision, task.id, 'cancelled')); })}>{t('取消')}</Button>
              </div>}
            </div>)}
            {!record?.followups.length && <p className="jx-inquiryMuted">{t('尚未安排跟进。')}</p>}
            <div className="jx-inquiryGrid"><label>{t('跟进事项')}<Input value={followupTitle} disabled={locked || !!record?.replied_at} onChange={(e) => setFollowupTitle(e.target.value)} placeholder={t('例如：确认客户是否收到报价及包装需求')} /></label>
              <label>{t('跟进时间')}<input className="jx-inquiryDate" type="datetime-local" aria-label={t('跟进时间')} value={dueAt} disabled={locked || !!record?.replied_at} onChange={(e) => setDueAt(e.target.value)} /><small>{localTimezone}</small></label></div>
            <Button icon={<PlusOutlined />} loading={busy === 'followup'} disabled={locked || !followupTitle.trim() || !dueAt || !!record?.replied_at} onClick={() => void run('followup', async () => {
              const date = new Date(dueAt); if (!Number.isFinite(date.getTime())) throw new Error(t('请填写有效的跟进时间。'));
              const saved = await ensureSaved(); accept(await addInquiryFollowup(saved.id, saved.revision, followupTitle.trim(), date.toISOString(), localTimezone)); setFollowupTitle(''); setDueAt('');
            })}>{t('添加跟进待办')}</Button>
          </div>
          {record && <details className="jx-inquiryHistory"><summary>{t('处理记录')}</summary><ol>{record.history.map((event, i) => <li key={i}><span>{dateText(event.at)}</span> · {eventText(event.event)} · v{event.revision}</li>)}</ol></details>}
        </section>
        <footer className="jx-inquiryFooter">Powered by HugAgentOS · {t('公开资料可追溯，演示报价需人工核实。')}</footer>
      </div>
    </div>
  </main>;
}
