"""Project-local Tripo setup and explicit account onboarding. Never accepts a key flag."""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from engine import account_dir,atomic,CLI


def user_context(home,username):
    if not (home/'data.db').is_file():raise ValueError('Existing public HugAgent home required.')
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow
    with SessionLocal() as db:
        user=db.query(UserShadow).filter(UserShadow.username==username).one_or_none()
        if user is None:raise ValueError('Existing account not found; no account created.')
        return user.user_id


def setup(home,node):
    runtime=ROOT/'.runtime/tripo-cli';runtime.mkdir(parents=True,exist_ok=True)
    for name in ('package.json','package-lock.json'):shutil.copyfile(HERE/'runtime-package'/name,runtime/name)
    npm=node.parent/'npm';env=os.environ.copy();env['PATH']=str(node.parent)+':/usr/local/bin:/usr/bin:/bin'
    subprocess.run([str(npm),'ci','--prefix',str(runtime),'--ignore-scripts','--no-audit','--no-fund'],env=env,check=True)
    version=subprocess.check_output([str(node),str(CLI),'--version'],text=True).strip()
    if version!='0.8.0':raise RuntimeError('Unexpected Tripo CLI version.')
    atomic(home/'tripo/runtime.json',{'node':str(node),'cli_version':version})
    return {'ok':True,'version':version,'scope':'public checkout only'}


def install(home,user):
    if not (home/'tripo/runtime.json').is_file():raise ValueError('Run setup first.')
    from features import register_package_sources,register_resource_owners,register_run_capabilities
    register_package_sources();register_resource_owners();register_run_capabilities()
    from features.desktop.local.plugins import service
    from core.capabilities.skills.installation import compute_install_id
    from features.desktop.capabilities import registry
    package=ROOT/'.runtime/tripo-plugin';shutil.copytree(HERE/'plugin',package,dirs_exist_ok=True)
    config={'mcpServers':{'tripo':{'type':'stdio','command':str(ROOT/'.venv/bin/python'),'args':[str(HERE/'bridge.py'),'--app-home',str(home)]}}}
    (package/'mcp.json').write_text(json.dumps(config,indent=2)+'\n')
    identifier=registry.install_id('plugin','local',compute_install_id('foreign-trade-tripo',user))
    previous=next((p for p in service.list_plugins(user) if p['install_id']==identifier),None)
    if previous:result=service.update(user,identifier,str(package),previous['revision'])
    else:result=service.install(user,str(package))
    service.set_presentation(user,result['install_id'],{'display_name':'高质量3D生成（Tripo）','category':'设计创意'})
    item=service.get(user,result['install_id'])
    return {'ok':True,'install_id':item['install_id'],'enabled':item['enabled'],'version':item['version']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','install','login','grant-free-budget','publish-reference'])
    parser.add_argument('--app-home',required=True,type=Path)
    parser.add_argument('--username')
    parser.add_argument('--node',type=Path)
    parser.add_argument('--region',choices=['cn','ov'])
    parser.add_argument('--credits',type=int)
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--verified-trial',action='store_true')
    parser.add_argument('--authorized-paid',action='store_true')
    parser.add_argument('--chat-id')
    parser.add_argument('--image',type=Path)
    args=parser.parse_args();home=args.app_home.expanduser().resolve()
    if args.action=='setup':
        node=(args.node or Path(shutil.which('node') or '/missing')).resolve()
        if not node.is_file():parser.error('Node20+ executable required via --node.')
        result=setup(home,node)
    else:
        if not args.username:parser.error('--username required')
        user=user_context(home,args.username)
        if args.action=='install':result=install(home,user)
        elif args.action=='login':
            if not args.region:parser.error('Choose --region cn or ov explicitly.')
            from engine import cli_env,read
            node=read(home/'tripo/runtime.json')['node'];directory=account_dir(home,user);directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
            # Interactive terminal only: device codes and credentials are never sent through the model/tool logs.
            if not sys.stdin.isatty() or not sys.stdout.isatty():parser.error('Run login in your own interactive terminal.')
            os.execve(node,[node,str(CLI),'login','--region',args.region,'--profile','hugagent','--no-open'],cli_env(home,user,node))
        elif args.action=='grant-free-budget':
            if args.verified_trial==args.authorized_paid or not args.credits or not 1<=args.credits<=300 or not 1<=args.jobs<=3:parser.error('Verify actual trial credits OR explicit paid authorization, then set a bounded budget. Never recharge automatically.')
            policy={'trial_verified':args.verified_trial,'paid_budget_authorized':args.authorized_paid,'funding_mode':'free_trial' if args.verified_trial else 'paid_authorized','remaining_credits':args.credits,'remaining_jobs':args.jobs,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()}
            atomic(account_dir(home,user)/'budget.json',policy);result={'ok':True,'budget_credits':args.credits,'max_jobs':args.jobs,'expires_at':policy['expires_at']}
        else:
            if not args.chat_id or not args.image:parser.error('--chat-id and --image required.')
            from core.db.engine import SessionLocal
            from core.db.models import ChatSession
            with SessionLocal() as db:
                if not db.query(ChatSession).filter(ChatSession.chat_id==args.chat_id,ChatSession.user_id==user,ChatSession.deleted_at.is_(None)).one_or_none():raise PermissionError('Chat not owned by account.')
            image=args.image.resolve()
            if not image.is_relative_to(ROOT) or image.is_symlink():raise ValueError('Reference must be an operator-selected image inside this public checkout.')
            from engine import validate_image,REFERENCE_URL
            validate_image(image.read_bytes())
            from engine import publish_file
            result=publish_file(image,name='qipao-champagne-ai-reference.png',mime='image/png',user=user,chat=args.chat_id,source='generated-reference',metadata={'inspiration_url':REFERENCE_URL,'kind':'AI-generated concept reference; not the purchased 3D asset'})
            if not result:raise RuntimeError('Reference registration failed.')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
