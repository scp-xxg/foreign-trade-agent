import asyncio,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
from pydantic import ValidationError
sys.path.insert(0,'src/backend')
from core.foreign_trade.diligence import DiligenceInput,run_stage,assess,STAGES
out=Path('outputs/diligence-live')
sources={n:json.loads((out/(n+'-source.json')).read_text()) for n in ['website','contact','registry']}
evidence=[dict(id=n,source_url=s['url'],retrieved_at=s['retrieved_at'],source_type='registry' if n=='registry' else 'company_website',text=s['text']) for n,s in sources.items()]
findings=[dict(category='identity',subject='LYRECO',field='registeredAs',value='400423968',evidence_id='registry',excerpt='"registeredAs":"400423968"'),dict(category='business',subject='Lyreco Group website',field='business_scope',value='office supplies, furniture, IT equipment',evidence_id='website',excerpt='office supplies, furniture, IT equipment'),dict(category='contact',subject='Lyreco Group website',field='contact_page',value='公开联系表单；不代表采购负责人',evidence_id='contact',excerpt='Contact us')]
req=DiligenceInput(company_name='LYRECO',country='FR',website='https://www.lyreco.com/group/',registration_number='400423968',seller_product='办公用品与办公收纳（演示匹配方向）',seller_constraints='真实MOQ、价格、认证及交期均未提供',evidence=evidence,findings=findings)
(out/'input.json').write_text(req.model_dump_json(indent=2))
async def main():
 results={}
 for stage in STAGES:
  t=time.monotonic();r=await run_stage(req,stage);results[stage]=r
  (out/(stage+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2))
  print(stage,r['status'],round(time.monotonic()-t,2),flush=True)
 checks=[]
 def check(name,condition):checks.append({'name':name,'passed':bool(condition)})
 check('四阶段均返回实际结果',len(results)==4)
 check('所有阶段保留人工复核',all(r['needs_review'] for r in results.values()))
 check('未冒充已确认主体',not results['identity-check']['identity_review']['confirmed_by_user'])
 check('信用司法制裁保持未查询',all(x['status']=='not_queried' for x in results['transaction-risk']['query_coverage']))
 check('缺交易条件不放行',results['transaction-risk']['status']=='incomplete_checks')
 check('同输入的四阶段版本一致',len({r['report_version'] for r in results.values()})==1)
 try:
  bad=req.model_dump(mode='json');bad['findings'][0]['excerpt']='THIS TEXT IS NOT IN THE SOURCE';DiligenceInput(**bad)
  rejected=False
 except ValidationError:rejected=True
 check('伪造原文引用被拒绝',rejected)
 # Separate synthetic probe: these are NOT claims about LYRECO.
 probe=DiligenceInput(company_name='SYNTHETIC TEST ONLY',contract_entity='Synthetic A',payee_entity='Synthetic B',account_changed=True)
 r=assess(probe,'transaction-risk')
 check('独立模拟异常触发主体差异与账户变更',{'entity_mismatch','account_change'} <= {x['type'] for x in r['risks']})
 (out/'synthetic-risk-probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 summary={'tested_at':datetime.now(timezone.utc).isoformat(),'scope':'Real public retrieval and production service functions; no mocks. Not authenticated HTTP, browser chat, or LLM orchestration acceptance.','checks':checks,'stages':{k:{'status':r['status'],'report_version':r['report_version'],'findings':len(r['findings'])} for k,r in results.items()}}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
 assert all(c['passed'] for c in checks)
asyncio.run(main())
