"""Owned, durable Tripo jobs. Official CLI owns credentials; no key enters model args."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
CLI=ROOT/'.runtime/tripo-cli/node_modules/tripo-cli/dist/cli.js'
REFERENCE_URL='https://connect.clo-set.com/detail/75d34f3dcfaa40dc91d297eaa08555f0'
MODEL='tripo-v3.1'
PARAMS=['--model',MODEL,'--param','texture=true','--param','pbr=true','--param','texture_quality=detailed','--param','face_limit=120000']


def account_dir(home,user):return home/'tripo/accounts'/hashlib.sha256(user.encode()).hexdigest()
def jobs_dir(home,user,chat):return home/'tripo/jobs'/hashlib.sha256((user+'\0'+chat).encode()).hexdigest()
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name('.'+uuid4().hex+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.chmod(0o600);temp.replace(path)
def read(path):return json.loads(path.read_text(encoding='utf-8'))

@contextmanager
def locked(folder):
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (folder/'operation.lock').open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('当前账号正在执行另一个操作，请稍后查询同一计划；本次未提交。')
        yield


def cli_env(home,user,node):
    env=os.environ.copy()
    for key in list(env):
        if key.startswith('TRIPO_'):env.pop(key)
    env.update({'TRIPO_HOME':str(account_dir(home,user)),'TRIPO_PROFILE':'hugagent','TRIPO_ANALYTICS_ENABLED':'0','TRIPO_CLIENT_APP':'hugagent-public/0.1.0','PATH':str(Path(node).parent)+':/usr/local/bin:/usr/bin:/bin','NO_COLOR':'1'})
    return env


async def run_cli(home,user,args,*,cwd=None,timeout=150):
    settings=read(home/'tripo/runtime.json');node=settings['node']
    process=await asyncio.create_subprocess_exec(node,str(CLI),*map(str,args),'--json','--no-open',cwd=cwd or ROOT,env=cli_env(home,user,node),stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:output,_=await asyncio.wait_for(process.communicate(),timeout)
    except (asyncio.TimeoutError,asyncio.CancelledError):
        if process.returncode is None:
            process.terminate()
            try:await asyncio.wait_for(process.communicate(),3)
            except asyncio.TimeoutError:process.kill();await process.communicate()
        raise
    if len(output)>4*1024*1024:raise RuntimeError('CLI回执超出限制。')
    result=None
    for line in reversed(output.decode('utf-8',errors='replace').splitlines()):
        try:result=json.loads(line);break
        except ValueError:continue
    return process.returncode,result


def validate_image(data):
    from PIL import Image
    if not 0<len(data)<=12*1024*1024:raise ValueError('参考图须小于12MB。')
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {'PNG','JPEG','WEBP'}:raise ValueError('参考图支持PNG/JPEG/WEBP。')
        if min(image.size)<128 or max(image.size)>8192:raise ValueError('参考图尺寸应为128–8192像素。')
        image.verify()
        return {'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[image.format]


def public_job(job):
    allowed={'plan_id','title','state','estimated_credits','task_id','progress','provider_status','credits_consumed','artifacts','reference','model','notice'}
    result={key:value for key,value in job.items() if key in allowed}
    if isinstance(result.get('reference'),dict) and result['reference'].get('file_id'):
        result['reference']={**result['reference'],'url':'/files/'+result['reference']['file_id']}
    return result


def load_job(home,user,chat,plan_id):
    if not re.fullmatch(r'[a-f0-9]{32}',str(plan_id)):raise ValueError('无效计划编号。')
    folder=jobs_dir(home,user,chat)/plan_id
    if not (folder/'job.json').is_file():raise PermissionError('此计划不存在或不属于当前账号与会话。')
    return folder,read(folder/'job.json')


async def prepare(home,user,chat,*,title,prompt='',reference_file_id=None):
    if not isinstance(title,str) or not 1<=len(title)<=100:raise ValueError('title应为1–100字符。')
    if not isinstance(prompt,str) or len(prompt)>2000:raise ValueError('prompt最多2000字符。')
    plan_id=uuid4().hex;folder=jobs_dir(home,user,chat)/plan_id;folder.mkdir(parents=True,mode=0o700)
    reference=None
    if reference_file_id:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',reference_file_id):raise ValueError('无效参考图编号。')
        from core.files.artifact_bytes import download_artifact_bytes
        data=download_artifact_bytes(reference_file_id,'reference.png','tripo-reference',user_id=user)
        if data is None:raise PermissionError('参考图不存在或不属于当前账号。')
        extension=validate_image(data);source=folder/('reference'+extension);source.write_bytes(data)
        input_value=str(source)
        reference={'file_id':reference_file_id,'sha256':hashlib.sha256(data).hexdigest(),'kind':'owned-reference-image'}
    else:
        if not prompt.strip():raise ValueError('请提供参考图file_id或明确建模描述。')
        input_value=prompt
    code,plan=await run_cli(home,user,['make',input_value,*PARAMS,'--dry-run'],cwd=folder)
    if code or not isinstance(plan,dict) or not plan.get('valid'):raise ValueError('官方CLI预检失败；未提交、未扣积分。')
    estimate=plan.get('generation_credits_estimate')
    if type(estimate) not in (int,float) or estimate<=0:raise ValueError('没有可靠的官方积分估算，不能自动提交。')
    if plan.get('candidates')!=1 or len(plan.get('steps',[]))!=1:raise ValueError('本插件只自动提交单个生成任务，不包含隐式收费后处理。')
    job={'plan_id':plan_id,'title':title,'state':'prepared','model':plan['model'],'estimated_credits':estimate,'reference':reference,'input':input_value,'notice':'云端AI外观网格生成，非纸样/布料仿真；参考图不是3D结果。'}
    atomic(folder/'job.json',job)
    return {'ok':True,**public_job(job),'next':'注册登录并核对免费额度后，调用tripo_submit_asset；不会自动充值。'}


async def account_status(home,user):
    code,result=await run_cli(home,user,['balance'],timeout=80)
    if code==3:return {'ok':False,'status':'auth_required','action':'请在本机运行项目的Tripo登录命令，在官方网页授权；不把密钥发到聊天。'}
    if code or not isinstance(result,dict):return {'ok':False,'status':'service_unavailable','exit_code':code,'action':'检查Tripo账号站点及网络；尚未提交生成。'}
    policy_path=account_dir(home,user)/'budget.json';policy=read(policy_path) if policy_path.exists() else {}
    return {'ok':True,'balance':result.get('balance'),'frozen':result.get('frozen'),'authorized_remaining_credits':policy.get('remaining_credits',0),'authorized_remaining_jobs':policy.get('remaining_jobs',0),'trial_budget_verified':policy.get('trial_verified',False),'budget_funding_mode':policy.get('funding_mode','none')}


def reserve(policy,estimate):
    if not (policy.get('trial_verified') or policy.get('paid_budget_authorized')):raise PermissionError('可用预算尚未核验，不能自动生成；不会转为未授权付费。')
    if datetime.fromisoformat(policy['expires_at'])<=datetime.now(timezone.utc):raise PermissionError('本次生成授权已过期，请重新核对免费额度。')
    if policy.get('remaining_jobs',0)<1 or policy.get('remaining_credits',0)<estimate:raise PermissionError('超过本次免费生成预算；不会自动追加或充值。')
    return {**policy,'remaining_jobs':policy['remaining_jobs']-1,'remaining_credits':policy['remaining_credits']-estimate}


async def recover(home,user,job):
    code,history=await run_cli(home,user,['history','--limit','20'],timeout=20)
    if not code and isinstance(history,list):
        for row in history:
            if row.get('name')=='hug-'+job['plan_id'] and re.fullmatch(r'[A-Za-z0-9_-]{8,128}',str(row.get('task_id',''))):
                return row['task_id']
    return None


async def submit(home,user,chat,plan_id):
    folder,job=load_job(home,user,chat,plan_id)
    with locked(account_dir(home,user)):
        job=read(folder/'job.json')
        if job['state']!='prepared':
            if job['state'] in {'submitting','submission_unknown'} and not job.get('task_id'):
                task=await recover(home,user,job)
                if task:job.update(task_id=task,state='submitted');atomic(folder/'job.json',job)
            return {'ok':bool(job.get('task_id')),'reused_existing_submission':True,**public_job(job)}
        budget=account_dir(home,user)/'budget.json'
        if not budget.exists():raise PermissionError('尚未授权使用本次积分预算，请先完成账号与额度核验。')
        policy=read(budget);reserved=reserve(policy,job['estimated_credits'])
        status=await account_status(home,user)
        if not status.get('ok'):return status
        if float(status.get('balance') or 0)<job['estimated_credits']:return {'ok':False,'status':'insufficient_credits','action':'免费额度不足，未提交；不会自动充值。'}
        # Reserve locally BEFORE the create request. Unknown outcomes never trigger a second create.
        atomic(budget,reserved);job['state']='submitting';atomic(folder/'job.json',job)
        try:
            code,result=await run_cli(home,user,['make',job['input'],*PARAMS,'--name','hug-'+plan_id,'--out',str(folder/'output'),'--no-wait','--no-download'],cwd=folder,timeout=150)
        except BaseException:
            job['state']='submission_unknown';atomic(folder/'job.json',job);raise
        task=result.get('task_id') if isinstance(result,dict) else None
        if task and re.fullmatch(r'[A-Za-z0-9_-]{8,128}',str(task)):
            job.update(task_id=task,state='submitted');atomic(folder/'job.json',job)
            return {'ok':True,**public_job(job),'next':'查询或等待同一计划，不要重复创建。'}
        if code in {2,3,4,5}:
            atomic(budget,policy);job['state']='prepared';atomic(folder/'job.json',job)
            return {'ok':False,'status':'request_rejected','exit_code':code,'notice':'服务拒绝请求；保留计划，未新建第二任务。'}
        job['state']='submission_unknown';atomic(folder/'job.json',job)
        return {'ok':False,**public_job(job),'action':'提交结果不确定；只查询此计划或核对服务后台，不自动重发。'}


@contextmanager
def render_lock(home):
    root=home/'blender';root.mkdir(exist_ok=True,mode=0o700)
    with (root/'general-engine.lock').open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Blender正在处理其他场景；模型已保留，稍后重试交付，不重新生成。')
        yield


def validate_glb(path):
    if path.is_symlink() or not path.is_file() or not 20<=path.stat().st_size<=128*1024*1024:raise ValueError('GLB缺失、过大或不是普通文件。')
    data=path.read_bytes()
    if struct.unpack('<4sII',data[:12])!=(b'glTF',2,len(data)):raise ValueError('GLB文件头/长度无效。')
    size,kind=struct.unpack('<II',data[12:20])
    if kind!=0x4E4F534A or size>len(data)-20:raise ValueError('GLB JSON段无效。')
    model=json.loads(data[20:20+size])
    if not model.get('meshes'):raise ValueError('GLB没有真实网格。')
    if any('uri' in item for item in model.get('buffers',[])+model.get('images',[])):raise ValueError('GLB存在外部资源引用，尚不能独立交付。')
    return {'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'meshes':len(model['meshes']),'images':len(model.get('images',[]))}


def publish_file(path,*,name,mime,user,chat,source,metadata=None):
    from core.files.artifacts.generated import store_generated_file_path
    from core.db.engine import SessionLocal
    from core.db.models import Artifact
    details={'source':source,'chat_id':chat,'ai_generated':True,**(metadata or {})}
    ref=store_generated_file_path(path,name=name,mime_type=mime,user_id=user,source=source,extra_metadata=details)
    if not ref:raise RuntimeError('下载登记失败。')
    with SessionLocal() as db:
        db.add(Artifact(artifact_id=ref['file_id'],chat_id=chat,user_id=user,type='other',title=name,filename=name,size_bytes=ref['size'],mime_type=mime,storage_key=ref['storage_key'],extra_data=details))
        db.commit()
    return ref


async def postprocess(home,user,chat,folder,job,model):
    import sys
    sys.path.insert(0,str(ROOT/'extensions/blender'))
    from general import worker,execute,EXPORT,INSPECT,facts
    work=folder/'render';work.mkdir(exist_ok=True);shutil.copyfile(model,work/'source.glb')
    # The original downloaded GLB is preserved; Blender creates a matching render/editable source.
    with render_lock(home):
        async with worker(work) as client:
            await execute(client,"import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete(use_global=False)\nbpy.ops.import_scene.gltf(filepath='/workspace/source.glb')\nprint('Imported actual Tripo output')",'Render and inspect the actual generated Tripo model without replacing its geometry.')
            await execute(client,EXPORT,'Render and save the imported generated garment.')
            inspection=facts(await execute(client,INSPECT,'Inspect the actual generated garment.'))
    from PIL import Image,ImageDraw
    with Image.open(work/'preview.png') as image:
        image=image.convert('RGB');draw=ImageDraw.Draw(image);draw.rectangle((0,738,1024,768),fill='white');draw.text((16,748),'Tripo generated 3D | Blender render | Powered by HugAgentOS | Concept, not garment pattern',fill='#334455');image.save(work/'preview.png')
    refs=[]
    for path,name,mime in [(model,'tripo-'+job['plan_id'][:8]+'.glb','model/gltf-binary'),(work/'preview.png','tripo-'+job['plan_id'][:8]+'-render.png','image/png'),(work/'scene.blend','tripo-'+job['plan_id'][:8]+'.blend','application/x-blender')]:
        ref=publish_file(path,name=name,mime=mime,user=user,chat=chat,source='tripo-cloud',metadata={'task_id':job['task_id'],'reference':job.get('reference')})
        if not ref:raise RuntimeError('文件已生成但下载登记失败；可对同一任务重试交付，不重新生成。')
        refs.append({**ref,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return refs,inspection


async def status(home,user,chat,plan_id,wait=False):
    folder,job=load_job(home,user,chat,plan_id)
    with locked(account_dir(home,user)):
        job=read(folder/'job.json')
        if job['state']=='completed':return {'ok':True,**public_job(job)}
        if not job.get('task_id'):
            if job['state'] in {'submitting','submission_unknown'}:
                task=await recover(home,user,job)
                if task:job.update(task_id=task,state='submitted');atomic(folder/'job.json',job)
            if not job.get('task_id'):return {'ok':False,**public_job(job),'action':'此计划尚未取得任务编号，不能假称生成成功，也不重复提交。'}
        output=folder/'output';output.mkdir(exist_ok=True)
        args=['task','watch' if wait else 'get',job['task_id'],'--download','--out',str(output)]
        if wait:args.extend(['--timeout','90'])
        code,result=await run_cli(home,user,args,cwd=folder,timeout=130)
        if code:
            check,result=await run_cli(home,user,['task','get',job['task_id']],timeout=80)
            if check or not isinstance(result,dict):return {'ok':False,**public_job(job),'status':'query_unavailable','action':'保留任务编号稍后继续查询，不重新生成。'}
        provider_status=result.get('status') if isinstance(result,dict) else None
        job.update(provider_status=provider_status,progress=result.get('progress',0))
        if provider_status!='success':
            job['state']='provider_failed' if provider_status in {'failed','cancelled','banned','expired'} else 'processing'
            atomic(folder/'job.json',job);return {'ok':provider_status not in {'failed','cancelled','banned','expired'},**public_job(job)}
        models=[p for p in output.rglob('*.glb') if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(output.resolve())]
        if not models:
            code,result=await run_cli(home,user,['task','get',job['task_id'],'--download','--out',str(output)],cwd=folder,timeout=130)
            models=[p for p in output.rglob('*.glb') if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(output.resolve())]
        if not models:raise RuntimeError('云端任务已完成，但GLB尚未下载；继续查询同一计划，不重新生成。')
        proof=validate_glb(models[0]);job.update(state='rendering',credits_consumed=result.get('credits_consumed'),model_proof=proof);atomic(folder/'job.json',job)
        try:refs,inspection=await postprocess(home,user,chat,folder,job,models[0])
        except Exception:
            job['state']='delivery_pending';atomic(folder/'job.json',job);raise
        job.update(state='completed',artifacts=refs,inspection=inspection,notice='真实Tripo生成网格，PNG为Blender实际渲染；AI外观模型，非服装纸样或合体仿真。')
        atomic(folder/'job.json',job)
        return {'ok':True,**public_job(job),'model_proof':proof,'facts':inspection}
