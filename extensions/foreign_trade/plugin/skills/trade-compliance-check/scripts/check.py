"""Scope routing and evidence-review reuse; not legal determination or release approval."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
EU=set('AT BE BG HR CY CZ DE DK EE ES FI FR GR HU IE IT LT LU LV MT NL PL PT RO SE SI SK'.split())
STAGES={'outreach','communication','listing','contract','procurement','shipment','retrospective'}
FEATURES={'food_contact','children','medical','environmental_claim'}

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def date(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('时间必须带时区')
    return t

def obj(value,allowed,required=()):
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value):raise ValueError('对象字段缺失或含未知键')
def text(value):
    if not isinstance(value,str) or not value.strip():raise ValueError('文本字段必须非空')
def validate(data):
    obj(data,{'case_id','as_of','markets','product','channel','stage','fields','evidence','reviews'}, {'case_id','as_of','product','stage'})
    text(data['case_id']);date(data['as_of'])
    if data['stage'] not in STAGES:raise ValueError('不支持的业务阶段')
    obj(data['product'],{'id','revision','category','features'},{'id','revision'})
    text(data['product']['id']);text(data['product']['revision'])
    if 'category' in data['product']:text(data['product']['category'])
    features=data['product'].get('features',{});obj(features,FEATURES)
    if any(v is not None and type(v) is not bool for v in features.values()):raise ValueError('特征必须为true/false/null')
    markets=data.get('markets',[])
    if not isinstance(markets,list) or len(markets)>30:raise ValueError('markets必须为最多30项的列表')
    if any(not isinstance(m,str) or len(m)!=2 or not m.isascii() or not m.isalpha() or m!=m.upper() for m in markets):raise ValueError('市场用两位大写代码或EU')
    if len(markets)!=len(set(markets)):raise ValueError('市场重复')
    if 'channel' in data:text(data['channel'])
    for key in ['evidence','reviews','fields']:
        if not isinstance(data.get(key,[]),list) or len(data.get(key,[]))>500:raise ValueError('列表无效或超过500项')
    evidence=data.get('evidence',[]);ids=set()
    for e in evidence:
        obj(e,{'id','reference','text','retrieved_at','valid_until'},{'id','reference','text','retrieved_at','valid_until'})
        for key in ['id','reference','text']:text(e[key])
        if e['id'] in ids:raise ValueError('证据id重复')
        ids.add(e['id'])
        if date(e['retrieved_at'])>date(e['valid_until']):raise ValueError('证据时间顺序错误')
    ids=set()
    for r in data.get('reviews',[]):
        obj(r,{'check_id','scope_hash','rule_hash','evidence_hash','evidence_ids','decision','reviewer','note','reviewed_at','valid_until'}, {'check_id','scope_hash','rule_hash','evidence_hash','evidence_ids','decision','reviewer','note','reviewed_at','valid_until'})
        for key in ['check_id','scope_hash','rule_hash','evidence_hash','reviewer','note']:text(r[key])
        if r['check_id'] in ids:raise ValueError('同一检查项只能提供一份当前审核')
        ids.add(r['check_id'])
        if r['decision'] not in ['satisfied','not_applicable','failed']:raise ValueError('审核结论无效')
        if not isinstance(r['evidence_ids'],list) or not r['evidence_ids'] or any(not isinstance(x,str) for x in r['evidence_ids']) or len(set(r['evidence_ids']))!=len(r['evidence_ids']):raise ValueError('审核须引用不重复的证据id')
        if date(r['reviewed_at'])>date(r['valid_until']):raise ValueError('审核有效期错误')
    return data

def choose(value,choices):
    if '*' in choices:return 'selected'
    if not value:return 'potential'
    return 'selected' if value in choices else 'excluded'

def check(data,packs=None):
    validate(data)
    packs=packs or json.loads((ROOT/'references/packs.json').read_text())
    now=date(data['as_of']);product=data['product'];features=product.get('features',{})
    fields=data.get('fields',[]);evidence={e['id']:e for e in data.get('evidence',[])}
    reviews={r['check_id']:r for r in data.get('reviews',[])}
    checks=[];excluded=[];gaps=[]
    if not data.get('markets'):gaps.append('missing_target_market')
    if not data.get('channel'):gaps.append('missing_channel')
    elif data['channel'] not in ['email','alibaba','amazon','website','social','offline']:gaps.append('channel_pack_missing')
    if not product.get('category'):gaps.append('missing_product_category')
    if not fields:gaps.append('text_not_provided_sensitive_scan_not_run')
    if data['stage']=='retrospective':gaps.append('select_original_business_stage_for_substantive_review')
    for market in data.get('markets') or [None]:
        if market and market not in packs['supported_markets']:
            gaps.append(market+(':national_pack_missing_EU_topics_only' if market in EU else ':market_pack_missing'))
        if market=='EU':gaps.append('specific_EU_destination_country_required')
        for rule in packs['rules']:
            market_state='selected' if '*' in rule['markets'] or market in rule['markets'] or market in EU and 'EU' in rule['markets'] else 'potential' if market is None else 'excluded'
            decisions=[market_state,choose(product.get('category'),rule['categories']),choose(data['stage'],rule['stages']),choose(data.get('channel'),rule['channels'])]
            for key,want in rule['features'].items():
                value=features.get(key)
                decisions.append('potential' if value is None else 'selected' if value==want else 'excluded')
            check_id=(market or 'UNKNOWN')+':'+rule['id']
            if 'excluded' in decisions:
                excluded.append(dict(check_id=check_id,reason='scope_does_not_match_declared_context'));continue
            selection='potential' if 'potential' in decisions else 'selected'
            scope=dict(product=product,market=market,channel=data.get('channel'),stage=data['stage'])
            if rule['depends_on_text']:scope['fields']=fields
            row=dict(check_id=check_id,title=rule['title'],selection=selection,scope_hash=digest(scope),rule_hash=digest(rule),
                evidence_request=rule['evidence_request'],official_research_entry=rule['official_research_entry'],
                basis=rule['basis'],official_rule_verified=False,status='scope_confirmation_required' if selection=='potential' else 'evidence_required',
                supplied_review_reused=False,issues=[])
            r=reviews.get(check_id)
            if r:
                linked=[evidence[x] for x in sorted(r['evidence_ids']) if x in evidence]
                if len(linked)!=len(r['evidence_ids']):row['issues'].append('missing_evidence')
                if r['scope_hash']!=row['scope_hash']:row['issues'].append('scope_changed')
                if r['rule_hash']!=row['rule_hash']:row['issues'].append('rule_changed')
                if r['evidence_hash']!=digest(linked):row['issues'].append('evidence_changed')
                if not date(r['reviewed_at'])<=now<=date(r['valid_until']):row['issues'].append('review_not_current')
                if any(not date(e['retrieved_at'])<=date(r['reviewed_at'])<=now<=date(e['valid_until']) for e in linked):row['issues'].append('evidence_not_current_at_review_and_now')
                if selection=='potential':row['issues'].append('scope_unconfirmed')
                if row['issues']:row['status']='review_invalidated'
                else:
                    row.update(status={'satisfied':'reviewed_with_supplied_evidence','not_applicable':'not_applicable_per_supplied_review','failed':'issue_reported'}[r['decision']],supplied_review_reused=True,reviewer=r['reviewer'],review_note=r['note'])
            checks.append(row)
    lexical=None
    if fields:
        path=ROOT.parent/'trade-sensitive-word-check/scripts/scan.py'
        if path.is_file():
            spec=importlib.util.spec_from_file_location('trade_sensitive_scan',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            lexical=module.scan({'fields':fields,'context':dict(platform=data.get('channel',''),market=','.join(data.get('markets',[])),category=product.get('category',''),purpose=data['stage'])})
        else:gaps.append('sensitive_skill_unavailable')
    known={r['check_id'] for r in checks}
    ignored=[key for key in reviews if key not in known]
    unresolved=[r['check_id'] for r in checks if r['status'] not in ['reviewed_with_supplied_evidence','not_applicable_per_supplied_review']]
    lexical_pending=lexical is not None and (lexical['status']!='no_lexical_hits' or not lexical['scan_complete'])
    return dict(case_id=data['case_id'],as_of=data['as_of'],pack_version=packs['version'],input_hash=digest(data),
        status='needs_review' if unresolved or gaps or lexical_pending else 'scoped_checklist_reviewed',
        legal_compliance='not_determined',release_authorized=False,external_action_executed=False,
        checks=checks,excluded_checks=excluded,coverage_gaps=gaps,unresolved_checks=unresolved,ignored_previous_reviews=ignored,
        sensitive_scan=lexical,evidence_manifest={key:digest(e) for key,e in evidence.items()},
        reuse_summary=dict(reused=sum(r['supplied_review_reused'] for r in checks),invalidated=sum(r['status']=='review_invalidated' for r in checks)),
        limitations=['仅完成所选内部清单的证据与时效检查，不是全法规审查。','来源链接仅为研究入口，工具未联网查询最新规则。','审核人和证据来自输入，工具没有认证其身份或证明内容真实性。','未覆盖国家、州、地区、渠道、产品要求应进一步核查；排除只依据声明的上下文。'])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True);parser.add_argument('--output');args=parser.parse_args()
    try:
        p=Path(args.input)
        if p.stat().st_size>3000000:raise ValueError('输入过大，请按产品和市场拆分')
        report=check(json.loads(p.read_text(encoding='utf-8')));payload=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            with Path(args.output).open('x',encoding='utf-8') as f:f.write(payload)
        else:print(payload,end='')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2
    return 0
if __name__=='__main__':sys.exit(main())
