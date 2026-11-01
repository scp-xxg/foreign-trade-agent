"""Install exactly three owner-scoped role agents; preserve existing human edits."""
import json
from pathlib import Path
from core.db.models import UserAgent
from core.capabilities.agents.edition import UserAgentService

ROLE_FILE=Path(__file__).with_name('core_roles.json')

def install_core_roles(db,user_id,plugin_id):
    definitions=json.loads(ROLE_FILE.read_text(encoding='utf-8'))
    from core.auth.capabilities import user_has_capability
    if not user_has_capability(db,user_id,'can_add_agent'):
        return [{'role':r['key'],'action':'permission_required'} for r in definitions['roles']]
    service=UserAgentService(db)
    rows=db.query(UserAgent).filter_by(owner_type='user',user_id=user_id).all()
    names={row.name for row in rows}
    result=[]
    for role in definitions['roles']:
        existing=[row for row in rows if (row.extra_config or {}).get('sailagent_core_role')==role['key']]
        if len(existing)>1:
            raise ValueError('Duplicate core-role identity; inspect before installation')
        if existing:
            result.append({'role':role['key'],'agent_id':existing[0].agent_id,'name':existing[0].name,'action':'preserved'})
            continue
        name=role['name'];index=2
        while name in names:
            name=role['name']+' · '+str(index);index+=1
        data={k:role[k] for k in ('description','system_prompt','welcome_message','suggested_questions')}
        data.update(name=name,plugin_ids=[plugin_id],skill_ids=[],mcp_server_ids=[],kb_ids=[],max_iters=20,timeout=300,
                    extra_config={'sailagent_core_role':role['key'],'template_version':definitions['version']})
        saved=service.create(user_id=user_id,operator_name='SailAgent role installer',owner_type='user',data=data)
        names.add(name)
        result.append({'role':role['key'],'agent_id':saved['agent_id'],'name':name,'action':'created'})
    return result
