import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,'src/backend')
from core.foreign_trade.diligence import DiligenceInput,run_stage
async def main():
 req=DiligenceInput(company_name='LYRECO',website='https://www.lyreco.com/',country='FR',seller_product='办公用品和办公收纳产品（项目演示产品方向，不代表用户实际供货声明）',seller_constraints='未提供真实MOQ、认证、交期和价格；不得推定采购意向')
 out=Path('outputs/diligence-live');out.mkdir(parents=True,exist_ok=True)
 for stage in ['identity-check','decision-chain']:
  r=await run_stage(req,stage)
  (out/(stage+'-initial.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2))
  print(json.dumps({'stage':stage,'public':r.get('public_research',r.get('public_channels'))},ensure_ascii=False),flush=True)
asyncio.run(main())
