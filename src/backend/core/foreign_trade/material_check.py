"""Native adapter for the bundled, versioned material-check skills."""
from functools import lru_cache
import importlib.util
from pathlib import Path
from uuid import uuid4

@lru_cache(maxsize=2)
def _skill(slug,script):
    path=Path(__file__).resolve().parents[2]/'extensions/skills/default'/slug/'scripts'/script
    spec=importlib.util.spec_from_file_location(slug.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def prepare(action,data,attachments=()):
    from copy import deepcopy
    data=deepcopy(data)
    if action not in {'sensitive','compliance'}:raise ValueError('不支持的检查类型')
    fields=data.setdefault('fields',[])
    if not isinstance(fields,list):raise ValueError('fields必须为列表')
    notices=[]
    for file_id,filename,parsed in attachments:
        notices.extend(str(w) for w in parsed.get('warnings',[]))
        if parsed.get('text','').strip():
            fields.append(dict(id='attachment:'+file_id,text=parsed['text'],placement=filename))
        else:notices.append(filename+'：未取得可检查文字，请提供可读文本或经核对的OCR结果。')
    if sum(len(f.get('text','')) for f in fields if isinstance(f,dict))>200000:raise ValueError('文字超过20万字符，请拆分')
    compliance=None;sensitive=None
    if action=='sensitive':
        if fields:sensitive=_skill('trade-sensitive-word-check','scan.py').scan(data)
        elif set(data)-{'fields','context'}:raise ValueError('未知输入字段')
    else:
        compliance=_skill('trade-compliance-check','check.py').check(data)
        sensitive=compliance['sensitive_scan']
        if notices:
            compliance['coverage_gaps'].extend(notices)
            compliance['status']='needs_review'
    if not fields:notices.append('没有待检查文字，敏感词检查尚未执行。')
    return dict(document_type='trade_material_check',document_version=1,check_id='check_'+uuid4().hex,
        action=action,fields=fields,sensitive=sensitive,compliance=compliance,notices=notices,
        release_authorized=False,external_action_executed=False)
