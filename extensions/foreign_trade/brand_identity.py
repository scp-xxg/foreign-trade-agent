"""Migrate only public product identity; keep all business data and upstream notices."""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

IDENTITY_REPLACEMENTS={
    'system/00_role': [('你是 HugAgentOS 外贸助手，','你是 sailagent 外贸出海助手，')],
    'system/40_format': [('以"HugAgentOS"身份输出','以"sailagent"身份输出')],
}


def identity_parts(parts):
    changed=deepcopy(parts)
    for part in changed:
        text=part.get('content','')
        for old,new in IDENTITY_REPLACEMENTS.get(part.get('part_id'),[]):text=text.replace(old,new)
        part['content']=text
    return changed


def apply_identity_prompt(db):
    from core.llm import prompt_versions as prompts
    active=prompts.get_active_version('system',db=db)
    if not active:return None,False
    parts=identity_parts(active['parts'])
    if parts==active['parts']:return active['id'],False
    digest=hashlib.sha256(json.dumps(parts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    version='sailagent-brand-'+digest
    existing=prompts.get_version('system',version,db=db)
    if existing and existing.get('parts')!=parts:version+='-'+uuid4().hex[:8];existing=None
    if not existing:
        prompts.upsert_version('system',version,name='sailagent · 外贸出海助手',description='Only the assistant product identity changed; HugAgentOS attribution and business rules retained.',parts=parts,db=db,updated_by='sailagent-branding')
    prompts.activate_version('system',version,db=db)
    return version,True


def counts(database):
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
        names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name:db.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in names}


def apply(home,quiet=False):
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from core.db.engine import SessionLocal
    from core.db.models import ContentBlock
    from core.files.content.branding import enforce_ce_branding
    from core.files.content.content_blocks_constants import DEFAULT_PAGE_CONFIG
    from core.llm import prompt_versions as prompts
    before=counts(home/'data.db')
    with SessionLocal() as db:
        row=db.query(ContentBlock).filter(ContentBlock.id=='page_config').one()
        payload=deepcopy(row.payload);old=payload.get('branding') or {}
        active=prompts.get_active_version('system',db=db)
        default=DEFAULT_PAGE_CONFIG['branding']
        keys=('product_name','page_title','logo_url','wordmark_url','favicon_url')
        nav=payload.get('navigation') or {}
        needs=any(old.get(k)!=default[k] for k in keys) or (payload.get('homepage') or {}).get('logo_url')!=default['logo_url']
        needs=needs or (nav.get('admin_header') or {}).get('title')!='sailagent — 后台管理' or (nav.get('admin_platform') or {}).get('product_name')!='sailagent'
        needs=needs or (payload.get('auth') or {}).get('allow_register') is not False
        needs=needs or bool(active and identity_parts(active['parts'])!=active['parts'])
        if not needs:
            result={'ok':True,'changed':False,'brand':'sailagent','prompt_version':active['id'] if active else None}
        else:
            backup=home/'brand-backups'/('before-sailagent-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json');backup.parent.mkdir(exist_ok=True,mode=0o700)
            snapshot={'branding':{k:old.get(k) for k in keys},'homepage_logo_url':(payload.get('homepage') or {}).get('logo_url'),'admin_header_title':(nav.get('admin_header') or {}).get('title'),'admin_platform_name':(nav.get('admin_platform') or {}).get('product_name'),'active_prompt_version':active['id'] if active else None,'table_counts':before}
            descriptor=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:json.dump(snapshot,stream,ensure_ascii=False,indent=2)
            branding_changed=enforce_ce_branding(db)
            version,prompt_changed=apply_identity_prompt(db)
            result={'ok':True,'changed':branding_changed or prompt_changed,'brand':'sailagent','prompt_version':version,'backup':str(backup)}
    after=counts(home/'data.db')
    result['table_count_changes']={name:{'before':value,'after':after.get(name)} for name,value in before.items() if after.get(name)!=value}
    if any(after.get(name,0)<value for name,value in before.items()):raise RuntimeError('Unexpected table row decrease; inspect before continuing.')
    if not quiet or result['changed']:print(json.dumps(result,ensure_ascii=False))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--app-home',required=True,type=Path);parser.add_argument('--quiet',action='store_true');args=parser.parse_args()
    home=args.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():parser.error('Existing public application data.db required; no database created.')
    apply(home,args.quiet)
if __name__=='__main__':main()
