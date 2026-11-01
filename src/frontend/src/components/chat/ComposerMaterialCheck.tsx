import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Modal } from 'antd';
import { SafetyCertificateOutlined } from '@ant-design/icons';
import { authFetch, getApiUrl } from '../../api';
import { useComposerDraft, useComposerStore } from '../../stores/composerStore';
import { t } from '../../i18n';
import { parseMaterialReceipt, type MaterialReceipt } from '../../utils/materialCheckReceipt';
import { MaterialCheckCard } from './MaterialCheckCards';

export function ComposerMaterialCheck({draftKey}: {draftKey: string}) {
  const draft=useComposerDraft(draftKey);
  const epoch=useComposerStore(s=>s.epoch);
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [result,setResult]=useState<MaterialReceipt|null>(null);
  const [snapshot,setSnapshot]=useState<{text:string;files:File[];ids:string[]}|null>(null);
  const controller=useRef<AbortController|null>(null);
  const ids=draft.importedSpaceFiles.map(f=>f.file_id);
  const changed=!!snapshot && (snapshot.text!==draft.input || snapshot.files.length!==draft.uploadedFiles.length || snapshot.files.some((f,i)=>f!==draft.uploadedFiles[i]) || snapshot.ids.join('|')!==ids.join('|'));
  useEffect(()=>{ controller.current?.abort();setOpen(false);setBusy(false);setResult(null);setSnapshot(null);return ()=>controller.current?.abort(); },[draftKey,epoch]);
  async function scan() {
    controller.current?.abort();const ctl=new AbortController();controller.current=ctl;
    setOpen(true);setBusy(true);setError('');setResult(null);
    const captured={text:draft.input,files:[...draft.uploadedFiles],ids:[...ids]};setSnapshot(captured);
    try {
      if(!captured.text.trim() && !captured.files.length && !captured.ids.length)throw new Error(t('请先在输入框填写文字或添加文件。'));
      if(captured.files.length+captured.ids.length>10)throw new Error(t('一次最多检查10个文件。'));
      const form=new FormData();form.append('text',captured.text);form.append('file_ids',JSON.stringify(captured.ids));
      captured.files.forEach(f=>form.append('files',f,f.name));
      const response=await authFetch(`${getApiUrl()}/v1/foreign-trade/buyer-search/material-check`,{method:'POST',body:form,signal:ctl.signal});
      const payload=await response.json();
      if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:t('资料检查失败，请重试。'));
      const receipt=parseMaterialReceipt(payload.data);
      if(!receipt)throw new Error(t('检查结果不完整，请重试。'));
      if(!ctl.signal.aborted)setResult(receipt);
    } catch(e) { if(!ctl.signal.aborted)setError(e instanceof Error?e.message:t('资料检查失败，请重试。')); }
    finally {if(!ctl.signal.aborted)setBusy(false);}
  }
  const close=()=>{controller.current?.abort();setBusy(false);setOpen(false);};
  return <><button type="button" className="jx-composerChip" aria-label={t('资料检查')} title={t('直接检查当前文字和文件')} onClick={()=>void scan()} disabled={busy}><SafetyCertificateOutlined/><span>{t('资料检查')}</span></button>
    <Modal title={t('资料检查')} open={open} onCancel={close} width={840} footer={<><Button onClick={close}>{t('关闭')}</Button><Button type="primary" loading={busy} onClick={()=>void scan()}>{t('重新检查')}</Button></>}>
      <p>{t('检查当前输入框文字与所选文件，不发送对话消息。')}</p>
      {busy && <p role="status">{t('正在检查文字和文件…')}</p>}
      {changed && <Alert type="warning" message={t('文字或文件已变化，请重新检查最新内容。')}/>}
      {error && <Alert type="error" message={error}/>}
      {result && <MaterialCheckCard record={result} chatId="" readOnly/>}
    </Modal>
  </>;
}
