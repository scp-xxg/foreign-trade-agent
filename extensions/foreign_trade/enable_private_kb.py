"""Explicitly enable private-KB creation for an existing local administrator.

.venv/bin/python extensions/foreign_trade/enable_private_kb.py --app-home PATH --username NAME --enable-create
No passwords, models, existing KBs or other account capabilities are changed.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import os
import sqlite3


def grant_existing_admin(db, username: str) -> dict:
    from core.db.models import UserShadow
    from core.db.repository import AuditLogRepository
    row = db.query(UserShadow).filter(UserShadow.username == username).one_or_none()
    if row is None:
        raise ValueError('Existing account was not found; no account created.')
    metadata = dict(row.extra_data or {})
    if metadata.get('role') != 'super_admin':
        raise PermissionError('This helper is limited to the existing local administrator.')
    if metadata.get('can_create_private_kb') is True:
        return {'changed':False, 'can_create_private_kb':True}
    previous = metadata.get('can_create_private_kb')
    row.extra_data = {**metadata, 'can_create_private_kb':True}
    AuditLogRepository(db).create({'user_id':row.user_id, 'action':'kb.private_creation.enabled',
        'resource_type':'user_capability','resource_id':row.user_id,'status':'success',
        'details':{'capability':'can_create_private_kb','previous':previous,'enabled':True}})
    db.commit()
    return {'changed':True,'can_create_private_kb':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-home',required=True,type=Path)
    parser.add_argument('--username',required=True)
    parser.add_argument('--enable-create',action='store_true')
    args=parser.parse_args()
    if not args.enable_create:parser.error('The explicit --enable-create action is required.')
    home=args.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():raise SystemExit('Existing data.db not found.')
    folder=home/'upgrade-backups';folder.mkdir(exist_ok=True,mode=0o700)
    backup=folder/('before-private-kb-permission-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
    descriptor=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(descriptor)
    with sqlite3.connect('file:'+str(home/'data.db')+'?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:src.backup(dst)
    backup.chmod(0o600)
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home))
    from core.db.engine import SessionLocal
    with SessionLocal() as db:result=grant_existing_admin(db,args.username)
    print(json.dumps({**result,'backup':str(backup),'other_capabilities_changed':False},ensure_ascii=False))

if __name__=='__main__':main()
