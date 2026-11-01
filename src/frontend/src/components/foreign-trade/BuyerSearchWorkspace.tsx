// Modified by foreign-trade-agent contributors, 2026-10-31; see CHANGES_FOREIGN_TRADE.md.
import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Empty, Input, InputNumber, Select, Tag } from 'antd';
import { t } from '../../i18n';
import { auditMetrics, buyerRequest, parseProfile, splitTerms, type Audit, type BuyerInput, type BuyerPlan, type BuyerRun } from '../../utils/foreignTradeBuyerApi';
import './BuyerSearchWorkspace.css';
function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const percent = (value: number | null) => value === null ? '—' : `${(value * 100).toFixed(1)}%`;
export function BuyerSearchWorkspace() {
  const [product, setProduct] = useState(''); const [buyers, setBuyers] = useState('distributor\nimporter');
  const [markets, setMarkets] = useState(''); const [queries, setQueries] = useState('');
  const [excluded, setExcluded] = useState(''); const [profile, setProfile] = useState('');
  const [budget, setBudget] = useState({ target_count: 10, max_queries: 4, max_pages: 8, max_seconds: 90 });
  const [plan, setPlan] = useState<BuyerPlan>(); const [result, setResult] = useState<BuyerRun>();
  const [labels, setLabels] = useState<Record<string, Audit>>({}); const [error, setError] = useState('');
  const [busy, setBusy] = useState(false); const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const edit = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLTextAreaElement>) => { setter(e.target.value); setPlan(undefined); };
  async function execute(action: 'plan' | 'run') {
    setError(''); setBusy(true); controller.current?.abort(); const request = new AbortController(); controller.current = request;
    try {
      const input: BuyerInput = { ...budget, product_terms: splitTerms(product), buyer_terms: splitTerms(buyers), markets: splitTerms(markets),
        queries: splitTerms(queries), excluded_domains: splitTerms(excluded), profile: parseProfile(profile) };
      if (action === 'plan') setPlan(await buyerRequest<BuyerPlan>('plan', input, request.signal));
      else { setResult(undefined); setLabels({}); const run = await buyerRequest<BuyerRun>('run', input, request.signal); setResult(run); setPlan(run.plan); }
    } catch (e) { if (!request.signal.aborted) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  const metrics = auditMetrics(labels, result?.candidates.map(c => c.id) || []);
  return <main className="buyer-search">
    <header><div><h1>{t('潜在买家搜索')}</h1><p>{t('从客户画像出发，查找有来源的候选网站，再由人工确认线索价值。')}</p></div><Tag>{t('候选发现 · 第二个 Skill')}</Tag></header>
    <div className="buyer-search-grid"><section className="buyer-search-form">
      {[[t('产品关键词（每行一项）'), product, setProduct], [t('买家类型词（每行一项）'), buyers, setBuyers], [t('目标市场（每行一项）'), markets, setMarkets],
        [t('自定义查询（优先使用）'), queries, setQueries], [t('排除域名（每行一项）'), excluded, setExcluded]].map(([label, value, setter]) =>
        <label key={String(label)}>{String(label)}<Input.TextArea aria-label={String(label)} rows={2} value={String(value)} onChange={edit(setter as (v: string) => void)} disabled={busy} /></label>)}
      <label>{t('导入客户画像 JSON')}<input type="file" accept=".json,application/json" disabled={busy} onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return;
        try { if (file.size > 100000) throw new Error(t('画像文件过大')); const text = await file.text(); parseProfile(text); setProfile(text); setPlan(undefined); setError(''); }
        catch (e) { setError(String(e)); } e.target.value = '';
      }} /></label>
      <Input.TextArea aria-label={t('客户画像 JSON')} placeholder={t('可粘贴第一个 Skill 的画像输出，包含 rules 和 search_plan。')} rows={3} value={profile} onChange={edit(setProfile)} disabled={busy} />
      <div className="buyer-budget">{([
        ['target_count', t('候选目标'), 1, 50], ['max_queries', t('查询上限'), 1, 12], ['max_pages', t('网页读取上限'), 0, 30], ['max_seconds', t('时限（秒）'), 5, 120],
      ] as const).map(([key, label, min, max]) => <label key={key}>{label}<InputNumber aria-label={label} min={min} max={max} value={budget[key]} disabled={busy} onChange={value => { setBudget(b => ({ ...b, [key]: value ?? min })); setPlan(undefined); }} /></label>)}</div>
      <div className="buyer-actions"><Button disabled={busy} onClick={() => void execute('plan')}>{t('预览搜索计划')}</Button><Button type="primary" loading={busy} onClick={() => void execute('run')}>{t('开始买家搜索')}</Button></div>
      <p>{t('结果保留在本次页面中，请及时导出；离开页面不会自动保存。')}</p>
    </section><section className="buyer-search-results">
      {error && <Alert type="error" showIcon title={error} />}
      {plan && <article><h2>{t('搜索计划')}</h2><ol>{plan.queries.map(q => <li key={q}>{q}</li>)}</ol><p>{plan.note}</p>{!plan.search_available && <Alert type="warning" title={t('尚未配置搜索服务，请在服务配置中设置搜索引擎及 API Key。')} />}</article>}
      {!result && <Empty description={busy ? t('正在搜索并读取公开网页…') : t('设置搜索条件后开始，结果将显示来源与待核实事项。')} />}
      {result && <><article><div className="buyer-actions"><h2>{t('搜索结果')}</h2><Button onClick={() => download('buyer-candidates.json', { ...result, human_review: labels, human_metrics: metrics })}>{t('导出候选与审核')}</Button><Button onClick={() => download('search-log.json', { plan: result.plan, log: result.search_log, stop_reason: result.stop_reason, metrics: result.metrics })}>{t('导出搜索日志')}</Button></div>
        <p>{t('候选数 / 查询数 / 已读网页 / 耗时（秒）')}：{result.metrics.candidate_count} / {result.metrics.queries_executed} / {result.metrics.pages_read} / {result.metrics.elapsed_seconds}</p>
        <p>{t('人工审核覆盖率')}：{percent(metrics.coverage)} · {t('有效线索率（有效 ÷ 有效与无效合计）')}：{percent(metrics.rate)} ({metrics.suitable}/{metrics.suitable + metrics.unsuitable})</p>
        <p>{t('证据不足不计入有效率分母；单条有效线索成本需供应商账单，当前未计算。')}</p>
        <p>{t('停止原因')}：{t(({ target_reached: '达到候选目标', queries_exhausted: '查询计划已完成', time_budget: '达到时间预算', low_yield: '连续三次无新增候选', search_error: '搜索服务异常' } as Record<string, string>)[result.stop_reason] || result.stop_reason)}</p>
        {result.warnings.map(w => <Alert key={w} type="warning" title={w} />)}{result.candidates.length === 0 && <Empty description={t('没有候选结果，请调整关键词或检查搜索服务。')} />}
      </article>{result.candidates.map(c => <article key={c.id}>
        <div className="buyer-actions"><h3>{c.name}</h3><Tag>{c.decision === 'qualified' ? t('域名规则通过') : t('待核实')}</Tag><Tag>{t('企业身份未核验')}</Tag></div>
        <a href={c.discovery_url} target="_blank" rel="noopener noreferrer">{c.domain}</a><p>{t('命中查询')}：{c.query}</p><p>{c.summary}</p>
        <details><summary>{t('网页证据与筛选依据')}</summary><p>{t('发现时间')}：{c.discovered_at}</p><p>{t('网页状态')}：{c.page_status} · {c.page_read_at || '—'}</p><pre>{c.page_excerpt || t('未获取网页正文')}</pre>{c.rule_results.map(r => <p key={r.rule_id}>{r.rule_id}: {r.result} — {r.reason}</p>)}<p>{c.unresolved.join('；')}</p></details>
        <label>{t('人工审核')}<Select aria-label={`${t('人工审核')} ${c.domain}`} style={{ minWidth: 160 }} placeholder={t('未审核')} value={labels[c.id]} onChange={(value: Audit) => setLabels(l => ({ ...l, [c.id]: value }))} options={[{ value: 'suitable', label: t('适合进入背调') }, { value: 'unsuitable', label: t('不适合') }, { value: 'unknown', label: t('证据不足') }]} /></label>
      </article>)}</>}
    </section></div>
  </main>;
}
