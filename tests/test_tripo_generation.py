"""Offline safety/state tests. These do not claim a live paid/free generation."""
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
import struct
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]/'extensions/tripo'
spec=importlib.util.spec_from_file_location('tripo_engine_test',HERE/'engine.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


def policy(credits=40,jobs=1):return {'trial_verified':True,'remaining_credits':credits,'remaining_jobs':jobs,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}

def pending(tmp_path):
    job={'plan_id':'a'*32,'title':'test','state':'prepared','model':'v3.1-20260211','estimated_credits':40,'input':'an ivory dress','reference':None}
    folder=engine.jobs_dir(tmp_path,'owner','chat')/job['plan_id'];engine.atomic(folder/'job.json',job)
    engine.atomic(engine.account_dir(tmp_path,'owner')/'budget.json',policy())
    return folder,job


def test_budget_expired_unverified_or_too_small():
    cases=[{**policy(),'trial_verified':False},{**policy(),'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()},policy(39),policy(jobs=0)]
    for item in cases:
        with pytest.raises(PermissionError):engine.reserve(item,40)
    original=policy();reserved=engine.reserve(original,40)
    assert reserved['remaining_credits']==0 and reserved['remaining_jobs']==0
    assert original['remaining_credits']==40


def test_accounts_and_chat_jobs_do_not_share_paths(tmp_path):
    assert engine.account_dir(tmp_path,'a')!=engine.account_dir(tmp_path,'b')
    assert engine.jobs_dir(tmp_path,'a','chat')!=engine.jobs_dir(tmp_path,'a','other')
    assert engine.jobs_dir(tmp_path,'../x','../../y').is_relative_to(tmp_path/'tripo/jobs')
    with pytest.raises(ValueError):engine.load_job(tmp_path,'a','chat','../other')


def test_public_receipt_excludes_input_paths_and_credentials():
    value=engine.public_job({'plan_id':'a','state':'prepared','input':'/private/path','api_key':'never','output_url':'signed-url'})
    assert value=={'plan_id':'a','state':'prepared'}


@pytest.mark.asyncio
async def test_preparation_is_only_one_official_dry_run(monkeypatch,tmp_path):
    calls=[]
    async def cli(home,user,args,**kw):
        calls.append(args)
        return 0,{'valid':True,'generation_credits_estimate':40,'candidates':1,'steps':[{}],'model':'v3.1-20260211'}
    monkeypatch.setattr(engine,'run_cli',cli)
    result=await engine.prepare(tmp_path,'owner','chat',title='Concept',prompt='An embroidered dress')
    assert result['state']=='prepared' and result['estimated_credits']==40
    assert len(calls)==1 and '--dry-run' in calls[0] and '--model' in calls[0]
    assert not (engine.account_dir(tmp_path,'owner')/'budget.json').exists()


@pytest.mark.asyncio
async def test_unknown_price_never_prepares_a_billable_job(monkeypatch,tmp_path):
    async def cli(*a,**k):return 0,{'valid':True,'generation_credits_estimate':None}
    monkeypatch.setattr(engine,'run_cli',cli)
    with pytest.raises(ValueError,match='积分估算'):await engine.prepare(tmp_path,'owner','chat',title='Concept',prompt='A dress')


@pytest.mark.asyncio
async def test_submit_reuses_task_and_never_creates_twice(monkeypatch,tmp_path):
    folder,job=pending(tmp_path);creates=[]
    async def account(*a):return {'ok':True,'balance':100}
    async def cli(home,user,args,**kw):creates.append(args);return 0,{'task_id':'task_1234567890'}
    monkeypatch.setattr(engine,'account_status',account);monkeypatch.setattr(engine,'run_cli',cli)
    one=await engine.submit(tmp_path,'owner','chat',job['plan_id']);two=await engine.submit(tmp_path,'owner','chat',job['plan_id'])
    assert one['task_id']==two['task_id']=='task_1234567890' and two['reused_existing_submission']
    assert len(creates)==1
    assert engine.read(engine.account_dir(tmp_path,'owner')/'budget.json')['remaining_jobs']==0


@pytest.mark.asyncio
async def test_uncertain_create_keeps_reservation_and_is_not_resent(monkeypatch,tmp_path):
    folder,job=pending(tmp_path);creates=[]
    async def account(*a):return {'ok':True,'balance':100}
    async def cli(home,user,args,**kw):
        if args[0]=='history':return 0,[]
        creates.append(args);raise TimeoutError('network')
    monkeypatch.setattr(engine,'account_status',account);monkeypatch.setattr(engine,'run_cli',cli)
    with pytest.raises(TimeoutError):await engine.submit(tmp_path,'owner','chat',job['plan_id'])
    result=await engine.submit(tmp_path,'owner','chat',job['plan_id'])
    assert result['state']=='submission_unknown' and not result['ok']
    assert len(creates)==1 and engine.read(engine.account_dir(tmp_path,'owner')/'budget.json')['remaining_jobs']==0


@pytest.mark.asyncio
async def test_auth_rejection_restores_local_budget(monkeypatch,tmp_path):
    folder,job=pending(tmp_path)
    async def account(*a):return {'ok':True,'balance':100}
    async def cli(*a,**k):return 3,None
    monkeypatch.setattr(engine,'account_status',account);monkeypatch.setattr(engine,'run_cli',cli)
    result=await engine.submit(tmp_path,'owner','chat',job['plan_id'])
    assert not result['ok'] and engine.read(folder/'job.json')['state']=='prepared'
    assert engine.read(engine.account_dir(tmp_path,'owner')/'budget.json')['remaining_jobs']==1


@pytest.mark.asyncio
async def test_balance_too_low_never_submits(monkeypatch,tmp_path):
    folder,job=pending(tmp_path)
    async def account(*a):return {'ok':True,'balance':39}
    async def cli(*a,**k):raise AssertionError('must not create')
    monkeypatch.setattr(engine,'account_status',account);monkeypatch.setattr(engine,'run_cli',cli)
    result=await engine.submit(tmp_path,'owner','chat',job['plan_id'])
    assert result['status']=='insufficient_credits'
    assert engine.read(engine.account_dir(tmp_path,'owner')/'budget.json')['remaining_jobs']==1


def test_external_resource_glb_is_not_publishable(tmp_path):
    target=tmp_path/'model.glb';blob=json.dumps({'meshes':[{}],'buffers':[{'uri':'external.bin'}]}).encode()
    target.write_bytes(struct.pack('<4sII',b'glTF',2,len(blob)+20)+struct.pack('<II',len(blob),0x4E4F534A)+blob)
    with pytest.raises(ValueError,match='外部资源'):engine.validate_glb(target)
    target.write_bytes(b'glTF')
    with pytest.raises(ValueError):engine.validate_glb(target)


def test_paid_budget_requires_explicit_separate_authorization():
    value={**policy(),"trial_verified":False,"paid_budget_authorized":False}
    with pytest.raises(PermissionError):engine.reserve(value,40)
    paid={**value,"paid_budget_authorized":True,"funding_mode":"paid_authorized"}
    result=engine.reserve(paid,40)
    assert result["funding_mode"]=="paid_authorized" and not result["trial_verified"] and result["remaining_jobs"]==0


def test_reference_preview_uses_the_owned_download_route():
    job={"plan_id":"a","reference":{"file_id":"owned-file","sha256":"digest"}}
    result=engine.public_job(job)
    assert result["reference"]["url"]=="/files/owned-file"
    assert "url" not in job["reference"]
