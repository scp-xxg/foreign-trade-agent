import sys,os,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('team','extensions/foreign_trade/team.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ.update(m.runtime_env(Path('/root/.foreign-trade-agent')));sys.path.insert(0,'src/backend')
from cli import apply_local_env
apply_local_env(3001)
from features import register_package_sources, register_resource_owners, register_run_capabilities
register_package_sources();register_resource_owners();register_run_capabilities()
from core.db.engine import SessionLocal
from core.db.models import UserShadow
from core.harness.registry import device_catalog
from features.desktop.capabilities import registry
with SessionLocal() as db:
 users=db.query(UserShadow).all()
 for u in users:
  entries=device_catalog.plugin_entries(u.user_id)
  for e in entries:
   if 'foreign-trade' in str(e):
    print('ACCOUNT',u.username,'ENTRY', {k:v for k,v in e.items() if k in ['install_id','slug','enabled','callable','skill_ids','components']})
    r=registry.get(e['install_id']);print('ROW',r.resolved_revision,r.payload.get('components'))
