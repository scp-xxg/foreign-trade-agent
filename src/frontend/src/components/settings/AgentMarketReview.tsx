import { useEffect, useState } from 'react';
import { Alert, Button, Input, Modal, Space, Table, Tag, message } from 'antd';
import { getAgentSubmission, listAgentSubmissions, reviewAgentSubmission, type AgentSubmission } from '../../api';
import { t } from '../../i18n';

export function AgentMarketReview() {
  const [items,setItems]=useState<AgentSubmission[]>([]);
  const [detail,setDetail]=useState<AgentSubmission>();
  const [note,setNote]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function load(){setBusy(true);try{setItems(await listAgentSubmissions());setError('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  useEffect(()=>{void load();},[]);
  async function review(approve:boolean){
    if(!detail||!note.trim())return;
    setBusy(true);try{await reviewAgentSubmission(detail.submission_id,approve,note.trim());setDetail(undefined);await load();message.success(t('审核已保存'));}catch(e){message.error((e as Error).message);}finally{setBusy(false);}
  }
  return <section style={{marginTop:32}}><Space><h2>{t('智能体市场审核')}</h2><Button loading={busy} onClick={()=>void load()}>{t('刷新')}</Button></Space>
    <p>{t('检查提示词、绑定能力和使用边界，填写理由后审核；通过后团队成员可安装独立副本。')}</p>
    {error&&<Alert type="error" title={error}/>}
    <Table rowKey="submission_id" loading={busy} dataSource={items} pagination={{pageSize:8}} columns={[
      {title:t('名称'),dataIndex:'name'}, {title:t('申请人'),dataIndex:'submitter_name'},
      {title:t('状态'),dataIndex:'status',render:(v:string)=><Tag>{v==='pending'?t('待审核'):v==='approved'?t('已上架'):t('已驳回')}</Tag>},
      {title:t('操作'),render:(_:unknown,row:AgentSubmission)=><Button onClick={async()=>{try{setDetail(await getAgentSubmission(row.submission_id));setNote('');}catch(e){message.error((e as Error).message);}}}>{t('查看与审核')}</Button>},
    ]}/>
    <Modal title={t('智能体上架审核')} open={!!detail} width={760} onCancel={()=>setDetail(undefined)} footer={<Space><Button onClick={()=>setDetail(undefined)}>{t('关闭')}</Button><Button danger disabled={detail?.status==='rejected'||!note.trim()} loading={busy} onClick={()=>void review(false)}>{detail?.status==='approved'?t('下架'):t('驳回')}</Button><Button type="primary" disabled={detail?.status!=='pending'||!note.trim()} loading={busy} onClick={()=>void review(true)}>{t('审核通过并上架')}</Button></Space>}>
      <h3>{detail?.name}</h3><p>{detail?.summary}</p><p>{detail?.note}</p><pre style={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{detail?.system_prompt}</pre>
      <details><summary>{t('绑定能力')}</summary><pre>{JSON.stringify(detail?.bindings,null,2)}</pre></details>
      {detail?.review_note&&<p>{detail.review_note}</p>}
      <Input.TextArea aria-label={t('审核说明')} placeholder={t('审核说明')} maxLength={2000} value={note} onChange={e=>setNote(e.target.value)} rows={3}/>
    </Modal>
  </section>;
}
