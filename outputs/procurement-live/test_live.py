import sys,json,copy,importlib.util
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'src/backend')
from core.foreign_trade.public_data import _fetch_public,_parse_html
from core.foreign_trade.procurement import ProcurementInput,prepare,STAGES
from pydantic import ValidationError
out=Path('outputs/procurement-live')
sources=[]
for name,url in [('customer','https://www.lyreco.com/group/'),('customer-contact','https://www.lyreco.com/group/contacts')]:
 try:
  page=_fetch_public(url);text=_parse_html(page).text
  d={'url':page.url,'retrieved_at':page.retrieved_at,'text':text}
  (out/(name+'-source.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2))
  sources.append(dict(id=name,reference=page.url,text=text[:60000]))
  print(name,'retrieved',len(text),flush=True)
 except Exception as e:print(name,'FAILED',str(e),flush=True)
real=ProcurementInput(case_id='PUBLIC-RESEARCH-NO-ACTUAL-ORDER',as_of=datetime.now(timezone.utc),sources=sources)
real_results={stage:prepare(real,stage) for stage in STAGES}
(out/'public-only-input.json').write_text(real.model_dump_json(indent=2))
(out/'public-only-results.json').write_text(json.dumps(real_results,ensure_ascii=False,indent=2))
# Independent synthetic fixture: none of these numbers or approvals describe the real firms.
spec=importlib.util.spec_from_file_location('procurement_tests','tests/test_trade_procurement.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
f=m.ProcurementTests();base=f.settlement();base['case_id']='SYNTHETIC-ONLY-NOT-LYRECO-NOT-RASPBERRYPI';base['sources'][0]['reference']='SYNTHETIC TEST RECORD: test-only approvals, not real approvals'
base['quality_checks']=[f.quality()];base['milestones']=[f.milestone()]
r={stage:prepare(ProcurementInput(**base),stage) for stage in STAGES}
(out/'synthetic-input.json').write_text(json.dumps(base,ensure_ascii=False,indent=2))
(out/'synthetic-results.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
checks=[]
def check(n,c):checks.append({'name':n,'passed':bool(c)})
check('实时读取两个公开来源',len(sources)==2)
check('仅公开资料时七阶段均提示缺输入',all(x['status']=='needs_input' for x in real_results.values()))
check('模拟净需求100+5-20-10=75',r['requirements']['items'][0]['net_purchase_quantity']=='75')
check('模拟可用产能100-25=75',r['capability']['items'][0]['capacities'][0]['available']=='75')
check('模拟报价75x10+20=770',r['comparison']['items'][0]['offers'][0]['normalized_known_cost']=='770')
check('模拟核对余额75x10-100=650',r['settlement']['items'][0]['reconciled_balance']=='650')
check('所有结果无外部执行',all(not x['executed_external_action'] and x['approval_required'] for x in [*r.values(),*real_results.values()]))
variants={}
d=copy.deepcopy(base);d['offers'][0]['costs']['freight']=None
variants['unknown-freight']=prepare(ProcurementInput(**d),'comparison')
check('未知运费不得参与成本排名',variants['unknown-freight']['items'][0]['offers'][0]['cost_rank'] is None)
d=copy.deepcopy(base);d['quality_checks'][0]['measured_value']=12
variants['quality-out-of-bounds']=prepare(ProcurementInput(**d),'quality')
check('实测12超出9至11被检出',any(x['code']=='measurement_out_of_bounds' for x in variants['quality-out-of-bounds']['items'][0]['issues']))
d=copy.deepcopy(base);d['receipts'][0].update(accepted=70,rejected=5)
variants['quality-settlement']=prepare(ProcurementInput(**d),'settlement')
check('验收差异不输出已核对余额',variants['quality-settlement']['items'][0]['reconciled_balance'] is None)
d=copy.deepcopy(base);d['requirements'][0]['inventory_confirmed']=False
variants['unknown-inventory']=prepare(ProcurementInput(**d),'requirements')
check('未确认库存不计算净需求',variants['unknown-inventory']['items'][0]['net_purchase_quantity'] is None)
d=copy.deepcopy(base);d['invoices'].append({**d['invoices'][0],'id':'duplicate'})
try:ProcurementInput(**d);rejected=False
except ValidationError:rejected=True
check('重复发票被拒绝',rejected)
d=copy.deepcopy(base);d['offers'][0]['unit_price']=11
check('改价后输入指纹更新',prepare(ProcurementInput(**d),'comparison')['input_hash']!=r['comparison']['input_hash'])
d=copy.deepcopy(base);d['orders']=[];d['receipts']=[];d['invoices']=[];d['adjustments']=[]
variants['missing-po-delivery']=prepare(ProcurementInput(**d),'delivery')
po_gate=any(x['code'] in ('missing_purchase_order','order_review_required') for x in variants['missing-po-delivery']['items'][0]['issues'])
(out/'boundary-results.json').write_text(json.dumps(variants,ensure_ascii=False,indent=2))
summary={'tested_at':datetime.now(timezone.utc).isoformat(),'scope':'Real public reads + production prepare functions. Synthetic business records are separate. No real purchase, live LLM, authenticated API or browser acceptance.','checks':checks,'known_gap':{'delivery_requires_approved_po_enforced':po_gate},'stages':{k:v['status'] for k,v in r.items()}}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
assert all(x['passed'] for x in checks)
