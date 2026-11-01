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
from core.llm.foreign_trade_plugin import _enabled_skill_ids
from features.desktop.plugin_resolution import resolve_desktop_progressive_plugins
for u in users:
 if u.username!='max':continue
 enabled=_enabled_skill_ids(u.user_id)
 print('ENABLED_PROCUREMENT',sorted(x for x in enabled if 'procurement' in x))
 from core.capabilities.catalog.resolver import resolve_all_runtime_enabled
 with SessionLocal() as db:
  vals=resolve_all_runtime_enabled(db,u.user_id)
 print('RUNTIME_PROCUREMENT',sorted(x for x in vals[0] if 'procurement' in x))
 from features.desktop.plugin_resolution import prepare_desktop_plugin_skill_defaults
 selected=prepare_desktop_plugin_skill_defaults(u.user_id,vals[0])
 plan=resolve_desktop_progressive_plugins(user_id=u.user_id,enabled_skill_ids=selected,enabled_mcp_ids=vals[1])
 print('FIXED_TARGETS',[(p.slug,[s for s in p.skill_ids if 'procurement' in s]) for p in plan.directory if 'foreign-trade' in p.slug])
