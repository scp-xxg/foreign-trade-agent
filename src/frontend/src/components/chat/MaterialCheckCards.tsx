import { useState } from 'react';
import { Alert, Button, Popover, Tag } from 'antd';
import { t } from '../../i18n';
import type { ToolCall } from '../../types';
import { chatDraftKey, readComposer } from '../../stores/composerStore';
import { checkRowState, extractMaterialChecks, markedSegments, type MaterialReceipt } from '../../utils/materialCheckReceipt';
import './MaterialCheckCards.css';

export function MaterialCheckCard({record,chatId,readOnly=false}: {record: MaterialReceipt;chatId: string;readOnly?: boolean}) {
  const [ready,setReady]=useState(false);
  const queue=(action: 'recheck'|'evidence'|'rewrite')=>{
    const draft=readComposer(chatDraftKey(chatId));
    const prompt=action==='rewrite'?t('请针对这份检查中的命中表达提出逐条修改建议，展示原文与建议，不补造认证、参数或承诺。'):action==='evidence'?t('请列出这份检查最先需要补充的资料。我会在此对话上传或补充，随后请重新检查。'):t('请基于本对话最新文案和附件重新检查；先核对版本，缺少资料时询问，不复用失效审核。');
    draft.patch({materialCheckMode:true,input:[draft.input,`${prompt}\n${t('检查记录')}：${record.check_id}`].filter(Boolean).join('\n\n'),document:null});setReady(true);
  };
  const hits=record.sensitive?.hits || [];const c=record.compliance;
  const count=(state: string)=>c?.checks.filter(r=>checkRowState(r)===state).length || 0;
  const rows=c?.checks.filter(r=>checkRowState(r)!=='done') || [];
  const renderRows=(items: typeof rows)=>items.map(row=><article className="jx-materialRow" key={row.check_id}>
    <Tag color={checkRowState(row)==='issue'?'error':checkRowState(row)==='done'?'success':'warning'}>{checkRowState(row)==='issue'?t('发现冲突'):checkRowState(row)==='done'?t('范围内已核对'):checkRowState(row)==='missing'?t('缺少证明'):t('需复核')}</Tag><strong>{row.title}</strong><p>{row.evidence_request}</p>
  </article>);
  return <section className="jx-materialCheck" aria-label={t('资料检查结果')}>
    <header><strong>{t('文字检查')}</strong><Tag color={hits.length?'warning':'default'}>{!record.sensitive?t('尚未检查文字'):hits.length?t('发现 {count} 处待核实表达',{count:hits.length}):t('未发现词库命中')}</Tag></header>
    {record.sensitive && !record.sensitive.scan_complete && <Alert type="warning" message={t('文字扫描未完成，请拆分后重新检查。')} />}
    {record.fields.map(field=><details key={field.id} open={record.fields.length===1 || hits.some(h=>h.field_id===field.id)} className="jx-materialText"><summary>{field.placement || field.id}</summary><div>{markedSegments(field,hits).map(part=>part.hits.length?<Popover key={part.start} trigger={['click']} content={<div className="jx-materialPopover">{part.hits.map(h=><div key={h.rule_id}><strong>{h.level==='L1'||h.level==='L2'?t('建议调整'):t('需核实依据')}</strong><p>{h.reason}</p><p>{h.suggestion}</p><small>{h.rule_id} · {h.level}</small></div>)}</div>}><button type="button" className="jx-materialMark" aria-label={t('查看表达检查：{text}',{text:part.text})}>{part.text}</button></Popover>:<span key={part.start}>{part.text}</span>)}</div></details>)}
    {!readOnly && !!hits.length && <Button size="small" onClick={()=>queue('rewrite')}>{t('查看修改建议')}</Button>}
    {record.notices.map((note,i)=><Alert key={i} type="warning" message={note} />)}
    {c && <section className="jx-materialCompliance"><header><strong>{t('合规检查')}</strong><Tag color={c.status==='needs_review'?'warning':'default'}>{c.status==='needs_review'?t('待补充或复核'):t('本次范围已核对')}</Tag></header>
      <p>{t('本次 {total} 项：已核对 {done} · 缺资料 {missing} · 需复核 {review} · 冲突 {issues}',{total:c.checks.length,done:count('done'),missing:count('missing'),review:count('review'),issues:count('issue')})}</p>
      {renderRows(rows.slice(0,3))}
      <details><summary>{t('查看全部检查项（{count}）',{count:c.checks.length})}</summary>{renderRows(c.checks)}</details>
      {!!c.coverage_gaps.length && <Alert type="warning" message={t('还有未覆盖或未明确的范围，请补充资料后确认。')} />}
      <Button size="small" onClick={()=>queue('evidence')}>{t('补充检查资料')}</Button>
    </section>}
    <footer>{!readOnly && <Button size="small" onClick={()=>queue('recheck')}>{t('重新检查最新资料')}</Button>}<span>{t('本结果为当时资料快照，不代表全面合规或发布批准。')}</span></footer>
    {ready && <p role="status">{t('请求已放入输入框，可补充文字或上传文件后发送。')}</p>}
    <details><summary>{t('查看检查范围与依据')}</summary><pre>{JSON.stringify({check_id:record.check_id,rule_version:record.sensitive?.rule_version,pack_version:c?.pack_version,as_of:c?.as_of,input_hash:c?.input_hash||record.sensitive?.input_sha256,coverage_gaps:c?.coverage_gaps},null,2)}</pre></details>
  </section>;
}
export function MaterialCheckCards({tools,chatId}: {tools: ToolCall[];chatId: string}) {
  const records=extractMaterialChecks(tools);
  const truncated=tools.some(x=>x.name==='trade_material_check' && x.status==='success' && x.outputTruncated && !x.outputLoaded);
  return <>{records.map(record=><MaterialCheckCard key={record.check_id} record={record} chatId={chatId}/>)}{truncated && <p>{t('历史检查结果已精简，请在对话中请求重新检查最新资料。')}</p>}</>;
}
