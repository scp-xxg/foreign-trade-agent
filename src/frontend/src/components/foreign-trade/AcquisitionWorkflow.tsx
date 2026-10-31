import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Input, Modal, Select, Steps, Tabs, Tag } from 'antd';
import { apiRequest } from '../../api';
import { t } from '../../i18n';
import { buyerRequest, parseProfile, splitTerms, type BuyerRun, type BuyerCandidate } from '../../utils/foreignTradeBuyerApi';
import { BuyerSearchWorkspace } from './BuyerSearchWorkspace';
import './BuyerSearchWorkspace.css';
import { LeadOutreach, priorityLabel, type LeadRecord } from './LeadOutreach';

type Dossier = { buyer_id: string; dossier_version: string; decision: string; evidence: { facts: unknown[]; sources: unknown[]; warnings: string[] }; rule_results: unknown[]; unresolved: string[] };
type Contact = { buyer_id: string; channels: { channel: string; type: string; source_url: string; retrieved_at: string; role_status: string; employment_status: string; deliverability: string }[]; warnings: string[]; unresolved: string[] };
type Review = { decision: 'suitable' | 'unsuitable' | 'unknown'; reason: string; reviewed_at: string; dossier_version: string };
function exportJSON(value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'acquisition-workflow.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function stage<T>(action: string, input: unknown, signal: AbortSignal): Promise<T> {
  return (await apiRequest<{ data: T }>(`/v1/foreign-trade/buyer-search/${action}`, { method: 'POST', body: JSON.stringify(input), signal })).data;
}
export function AcquisitionWorkflow() {
  const [product, setProduct] = useState(''); const [markets, setMarkets] = useState('');
  const [buyers, setBuyers] = useState('distributor\nimporter'); const [constraints, setConstraints] = useState('');
  const [profileText, setProfileText] = useState(''); const [confirmed, setConfirmed] = useState(false);
  const [run, setRun] = useState<BuyerRun>(); const [dossiers, setDossiers] = useState<Record<string, Dossier>>({});
  const [contacts, setContacts] = useState<Record<string, Contact>>({}); const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [leads, setLeads] = useState<Record<string, LeadRecord>>({});
  function clearLead(id: string) { setLeads(v => { const n = {...v}; delete n[id]; return n; }); }
  const [excluded, setExcluded] = useState(''); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const [progressRevision,setProgressRevision]=useState(0);
  const [savedAt,setSavedAt]=useState('');
  async function saveProgress(){
    await perform('save-progress',async signal=>{
      const payload={product,markets,buyers,constraints,profileText,confirmed,run:run||null,dossiers,contacts,reviews,leads,excluded};
      const result=await apiRequest<{data:{revision:number;updated_at:string}}>('/v1/foreign-trade/buyer-search/progress',{method:'PUT',body:JSON.stringify({revision:progressRevision,payload}),signal});
      setProgressRevision(result.data.revision);setSavedAt(result.data.updated_at);
    });
  }
  async function restoreProgress(){
    await perform('restore-progress',async signal=>{
      type Snapshot={product:string;markets:string;buyers:string;constraints:string;profileText:string;confirmed:boolean;run:BuyerRun|null;dossiers:Record<string,Dossier>;contacts:Record<string,Contact>;reviews:Record<string,Review>;leads:Record<string,LeadRecord>;excluded:string};
      const result=await apiRequest<{data:{revision:number;updated_at:string|null;payload:Snapshot|null}}>('/v1/foreign-trade/buyer-search/progress',{signal});
      const v=result.data.payload;if(!v)throw new Error(t('没有已保存的获客进度'));
      setProduct(v.product||'');setMarkets(v.markets||'');setBuyers(v.buyers||'');setConstraints(v.constraints||'');setProfileText(v.profileText||'');setConfirmed(v.confirmed===true);setRun(v.run||undefined);setDossiers(v.dossiers||{});setContacts(v.contacts||{});setReviews(v.reviews||{});setLeads(v.leads||{});setExcluded(v.excluded||'');setProgressRevision(result.data.revision);setSavedAt(result.data.updated_at||'');
    });
  }
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  function invalidate() { setConfirmed(false); setRun(undefined); setDossiers({}); setContacts({}); setReviews({}); setLeads({}); }
  async function perform(label: string, work: (signal: AbortSignal) => Promise<void>) {
    controller.current?.abort(); const c = new AbortController(); controller.current = c; setBusy(label); setError('');
    try { await work(c.signal); } catch (e) { if (!c.signal.aborted) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (!c.signal.aborted) setBusy(''); }
  }
  const researchInput = (c: BuyerCandidate) => ({ company_name: c.name, website: c.discovery_url, profile: parseProfile(profileText), excluded_channels: splitTerms(excluded), max_pages: 3 });
  const ids = run?.candidates.map(c => c.id) || [];
  const reviewed = Object.values(reviews); const suitable = reviewed.filter(r => r.decision === 'suitable').length;
  const negative = reviewed.filter(r => r.decision === 'unsuitable').length;
  const eligible = ids.filter(id => reviews[id]?.decision === 'suitable');
  const withChannel = eligible.filter(id => contacts[id]?.channels.length).length;
  const current = !confirmed ? 0 : !run ? 1 : Object.keys(dossiers).length < ids.length ? 2 : !withChannel ? 3 : !Object.values(leads).some(v => v.score) ? 4 : 5;
  return <main className="buyer-search">
    <header><div><h1>{t('获客工作流')}</h1><p>{t('确认画像与背调，发现公开渠道，评估优先级并生成待审开发信。')}</p></div><Button disabled={!profileText || !!busy} onClick={() => { try { exportJSON({ schema_version: '1.1', exported_at: new Date().toISOString(), profile: parseProfile(profileText), profile_confirmed: confirmed, search: run, dossiers, reviews, contacts, leads }); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } }}>{t('导出完整获客记录')}</Button></header>
    <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',marginBottom:12}}><Button disabled={!!busy||!product.trim()&&!profileText.trim()} loading={busy==='save-progress'} onClick={()=>void saveProgress()}>{t('保存获客进度')}</Button><Button disabled={!!busy} loading={busy==='restore-progress'} onClick={()=>{Modal.confirm({title:t('恢复已保存的进度'),content:t('将替换当前未保存内容；只恢复本账号进度，不会重新搜索或联系买家。'),onOk:restoreProgress});}}>{t('恢复已保存的进度')}</Button>{savedAt&&<span>{t('已保存')}：{new Date(savedAt).toLocaleString()}</span>}</div>
    <Steps size="small" current={current} items={[{ title: t('客户画像') }, { title: t('买家搜索') }, { title: t('买家背调') }, { title: t('联系人发现') }, { title: t('线索优先级') }, { title: t('开发信草稿') }]} />
    <Alert type="info" showIcon title={t('进度可按账号保存并在刷新后恢复；修改后请再次保存。来源不足保留未知，流程不会发送开发信。')} />
    <details><summary>{t('查看工作流与验收指标')}</summary><ol>
      <li>{t('画像：填写产品、市场、买家类型及限制，生成草案或粘贴已有画像，人工确认后搜索。自由文本限制需转为 rules 才能自动筛选。')}</li>
      <li>{t('搜索：每次最多4次查询、5家候选、8页网页、90秒；失败保留部分结果，可调整画像重跑。')}</li>
      <li>{t('背调：逐家读取官网及公开法人登记，分别展示规则匹配与证据。人工填写审核理由，信息不足不算无效。')}</li>
      <li>{t('联系人：审核适合后读取最多3页官网，提取公开邮箱和联系页，保留来源和时间；具名负责人、在职与投递状态保持未知。')}</li>
      <li>{t('排序与开发信：依据四维证据计算匹配分及覆盖率，为优先跟进买家生成已核对事实的英文草稿；人工批准仍不会发送。')}</li>
      <li>{t('验收：有效率=适合÷(适合+不适合)；渠道覆盖率=有公开渠道的审核适合买家÷审核适合买家。准确率需人工抽样，退信率需实际发送数据。')}</li>
    </ol><p>{t('更改画像将清空后续结果；重新背调使原审核与联系人结果失效。导出包含画像版本、搜索日志、证据、审核及联系人。')}</p></details>
    {error && <Alert type="error" showIcon title={error} />}
    <div className="buyer-search-grid"><section className="buyer-search-form">
      {[[t('产品'),product,setProduct],[t('目标市场（每行一项）'),markets,setMarkets],[t('买家类型词（每行一项）'),buyers,setBuyers],[t('供货限制与补充资料'),constraints,setConstraints]].map(([label,value,setter]) => <label key={String(label)}>{String(label)}<Input.TextArea aria-label={String(label)} value={String(value)} disabled={!!busy} rows={2} onChange={e => { (setter as (v: string) => void)(e.target.value); setProfileText(''); invalidate(); }} /></label>)}
      <Button loading={busy === 'profile'} disabled={!!busy || !product.trim()} onClick={() => void perform('profile', async signal => { const p = await stage<Record<string, unknown>>('profile', { product, markets: splitTerms(markets), buyer_types: splitTerms(buyers), constraints }, signal); invalidate(); setProfileText(JSON.stringify(p,null,2)); })}>{t('生成画像草案')}</Button>
      <label>{t('客户画像 JSON')}<Input.TextArea aria-label={t('客户画像 JSON')} rows={8} value={profileText} disabled={!!busy} onChange={e => {setProfileText(e.target.value); invalidate();}} /></label>
      <Checkbox checked={confirmed} disabled={!profileText || !!busy || !!run} onChange={e => {try {parseProfile(profileText); setConfirmed(e.target.checked); setError('');} catch(e) {setError(String(e));}}}>{t('我已核对画像与搜索范围')}</Checkbox>
      <Button type="primary" loading={busy === 'search'} disabled={!confirmed || !!busy} onClick={() => void perform('search', async signal => {
        const result = await buyerRequest<BuyerRun>('run', { product_terms: [], buyer_terms: [], markets: [], queries: [], excluded_domains: [], profile: parseProfile(profileText), target_count: 5, max_queries: 4, max_pages: 8, max_seconds: 90 }, signal);
        setRun(result); setDossiers({}); setContacts({}); setReviews({}); setLeads({});
      })}>{t('按画像搜索买家')}</Button>
      <label>{t('排除已有联系渠道（每行一项）')}<Input.TextArea value={excluded} disabled={!!busy} rows={2} onChange={e => {setExcluded(e.target.value); setContacts({}); setLeads({});}} /></label>
    </section><section className="buyer-search-results">
      {run && <article><h2>{t('工作流进度与效果')}</h2><h3>{t('跟进优先级队列')}</h3>{Object.entries(leads).filter(([,v]) => v.score).sort(([,a],[,b]) => { const order = ['follow_up','research_first','defer','stop']; return order.indexOf(a.score!.priority) - order.indexOf(b.score!.priority) || b.score!.ranking_score - a.score!.ranking_score; }).map(([id,v]) => <p key={id}>{run.candidates.find(c => c.id === id)?.name} · {priorityLabel(v.score!.priority)} · {v.score!.fit_score ?? '—'} / {(v.score!.evidence_coverage*100).toFixed(0)}%</p>)}<p>{t('候选 / 背调 / 已审核 / 有渠道')}：{ids.length} / {Object.keys(dossiers).length} / {reviewed.length} / {withChannel}</p><p>{t('有效线索率')}：{suitable+negative ? `${(100*suitable/(suitable+negative)).toFixed(1)}%` : '—'} · {t('渠道覆盖率')}：{eligible.length ? `${(100*withChannel/eligible.length).toFixed(1)}%` : '—'}</p>{run.warnings.map(w => <Alert key={w} type="warning" title={w} />)}{!ids.length && <p>{t('没有候选结果，请调整关键词或检查搜索服务。')}</p>}<details><summary>{t('搜索日志')}</summary><pre>{JSON.stringify(run.search_log,null,2)}</pre></details></article>}
      {run?.candidates.map(c => <article key={c.id}><h3>{c.name}</h3><a href={c.discovery_url} target="_blank" rel="noopener noreferrer">{c.domain}</a><p>{c.summary}</p>
        <Button disabled={!!busy} loading={busy === `dossier:${c.id}`} onClick={() => void perform(`dossier:${c.id}`, async signal => {
          const value = await stage<Dossier>('due-diligence',researchInput(c),signal); setDossiers(v => ({...v,[c.id]:value})); clearLead(c.id);
          setReviews(v => {const n={...v}; delete n[c.id]; return n;}); setContacts(v => {const n={...v}; delete n[c.id]; return n;});
        })}>{t('执行买家背调')}</Button>
        {dossiers[c.id] && <><Tag>{t('待人工核验')}</Tag><details><summary>{t('背调证据与规则')}</summary><pre>{JSON.stringify(dossiers[c.id],null,2)}</pre></details>
          <label>{t('审核理由')}<Input aria-label={`${t('审核理由')} ${c.domain}`} disabled={!!busy} value={reviews[c.id]?.reason || ''} onChange={e => {
            clearLead(c.id); setReviews(v => ({...v,[c.id]: {decision:'unknown',reason:e.target.value,reviewed_at:new Date().toISOString(),dossier_version:dossiers[c.id].dossier_version}}));
            setContacts(v => {const n={...v}; delete n[c.id]; return n;});
          }} /></label>
          <Select aria-label={`${t('背调审核')} ${c.domain}`} disabled={!!busy || !reviews[c.id]?.reason.trim()} value={reviews[c.id]?.decision} placeholder={t('人工审核')} style={{width:'100%'}} options={[{value:'suitable',label:t('适合进入联系人发现')},{value:'unsuitable',label:t('不适合')},{value:'unknown',label:t('证据不足')}]} onChange={(decision: Review['decision']) => {clearLead(c.id); setReviews(v => ({...v,[c.id]:{...v[c.id],decision,reviewed_at:new Date().toISOString()}})); setContacts(v => {const n={...v}; delete n[c.id]; return n;});}} />
          <Button disabled={!!busy || reviews[c.id]?.decision !== 'suitable' || dossiers[c.id].decision === 'rejected'} loading={busy === `contacts:${c.id}`} onClick={() => void perform(`contacts:${c.id}`, async signal => {const value=await stage<Contact>('contacts',researchInput(c),signal); setContacts(v=>({...v,[c.id]:value})); clearLead(c.id);})}>{t('发现公开联系渠道')}</Button>
          {dossiers[c.id].decision === 'rejected' && <p>{t('命中硬性排除规则，请调整画像后重跑。')}</p>}
        </>}
        {contacts[c.id] && <><h4>{t('公开联系渠道')}</h4>{contacts[c.id].channels.map(channel => <div key={channel.channel}><p>{channel.channel} · {channel.type}</p><a href={channel.source_url} target="_blank" rel="noopener noreferrer">{t('来源')}</a><p>{channel.retrieved_at}</p><p>{t('岗位 / 在职 / 可投递：均未核实')}</p></div>)}{!contacts[c.id].channels.length && <p>{t('未找到公开渠道')}</p>}{contacts[c.id].warnings.map(w=><Alert key={w} type="warning" title={w}/>)}<p>{contacts[c.id].unresolved.join('；')}</p></>}
        {dossiers[c.id] && reviews[c.id]?.reason.trim() && <LeadOutreach key={JSON.stringify([c.id,dossiers[c.id].dossier_version,reviews[c.id],contacts[c.id]])} buyerId={c.id} company={c.name} website={c.discovery_url} dossierVersion={dossiers[c.id].dossier_version} review={reviews[c.id]} hardExcluded={dossiers[c.id].decision === 'rejected'} channels={contacts[c.id]?.channels || []} busy={!!busy} record={leads[c.id] || {}} onChange={value => setLeads(v => ({...v,[c.id]:value}))} perform={perform} />}
      </article>)}
    </section></div>
  </main>;
}
export function AcquisitionWorkspace() {
  return <Tabs className="acquisition-workspace" destroyOnHidden={false} defaultActiveKey="workflow" items={[{key:'workflow',label:t('获客工作流'),children:<AcquisitionWorkflow/>},{key:'search',label:t('独立买家搜索'),children:<BuyerSearchWorkspace/>}]} />;
}
