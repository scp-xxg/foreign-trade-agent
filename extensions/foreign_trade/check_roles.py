"""Read-only core-role dependency check; no model calls or business writes."""
import argparse,json,os
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-home',type=Path,required=True)
    parser.add_argument('--username',required=True)
    from foreign_trade.team import runtime_env,web_port_number
    parser.add_argument('--port',type=web_port_number,default=3001)
    args=parser.parse_args();home=args.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():parser.error('Existing app-home data.db required')
    os.environ.update(runtime_env(home,args.port))
    from features import register_package_sources,register_resource_owners,register_run_capabilities,register_product_tools
    register_package_sources();register_resource_owners();register_run_capabilities();register_product_tools()
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow,UserAgent
    from core.capabilities.mcp.service import McpServerConfigService
    from core.llm.factory.selection.capabilities import _expand_plugin_bindings
    results=[]
    with SessionLocal() as db:
        user=db.query(UserShadow.user_id).filter_by(username=args.username).one_or_none()
        if user is None:parser.error('Existing account not found')
        service=McpServerConfigService.get_instance()
        available={**service.get_all_servers(enabled_only=True),**service.get_owned_servers(user[0],enabled_only=False)}
        rows=db.query(UserAgent).filter_by(owner_type='user',user_id=user[0]).all()
        for key in ('sales','procurement','operations'):
            matches=[r for r in rows if (r.extra_config or {}).get('sailagent_core_role')==key]
            if len(matches)!=1:
                results.append({'role':key,'ok':False,'reason':'missing_or_duplicate_role'});continue
            row=matches[0];skills,mcps=_expand_plugin_bindings(row.plugin_ids or [],user_id=user[0])
            missing=sorted(set(mcps)-set(available))
            results.append({'role':key,'name':row.name,'ok':bool(row.is_enabled and skills and mcps and not missing),'skills':len(skills),'connectors':len(mcps),'missing_connectors':missing})
    passed=all(r['ok'] for r in results)
    print(json.dumps({'ok':passed,'checks':results,'scope':'bindings only; run team.py check --running for connection health'},ensure_ascii=False,indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
