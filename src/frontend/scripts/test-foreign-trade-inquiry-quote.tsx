import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { CurrentInquiryQuoteCard } from '../src/components/chat/TradeInquiryCard';
import { currentInquiryQuote, readVerifiedInquiryQuote } from '../src/utils/foreignTradeInquiryReceipt';
import type { InquiryRecord } from '../src/utils/foreignTradeInquiryApi';

const root = resolve(process.cwd(), '../..');
const python = process.env.FOREIGN_TRADE_TEST_PYTHON || resolve(root, '.venv/bin/python');
// CI's quote-and-web job deliberately has a stdlib-only Python environment.
// Use the real deterministic engine, then wrap it in a synthetic inquiry shape.
// The backend service/CAS contract is covered by test_two_workflow_journey.py
// and test_trade_update_drafts.py in the backend CI job.
const engineQuote = JSON.parse(execFileSync(python, ['-c', `
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'extensions'))
from foreign_trade.engine import calculate_quote
print(json.dumps(calculate_quote([{'sku':'DESK-001','quantity':1000,'custom_packaging':True}],'Spain')))
`], { cwd: root, encoding: 'utf8', timeout: 10000 }));
const fixture: InquiryRecord = {
  id:'inq_'+'a'.repeat(32),revision:8,title:'Synthetic inquiry quote rendering',
  buyer:{company_name:'Demo buyer',website:'',email:'',country:''},buyer_card:null,
  raw_inquiry:'DEMO DESK-001 1000 units, custom packaging to Spain',
  items:[{sku:'DESK-001',quantity:1000,custom_packaging:true}],
  destination_country:'Spain',requested_lead_days:null,is_demo_inquiry:true,
  quote:engineQuote,quote_revision:5,
  drafts:{zh:'演示报价5100美元',en:'DEMO total USD 5100.00',kind:'quotation',not_sent:true,stale:false,quote_revision:5},
  followups:[{id:'followup-demo',title:'Test follow-up',due_at:'2030-01-02T08:00:00+00:00',timezone:'Europe/Madrid',status:'pending'}],
  history:[],created_at:'2026-11-01T00:00:00Z',updated_at:'2026-11-01T00:00:00Z',replied_at:null,
};
const clone = <T,>(v:T):T => JSON.parse(JSON.stringify(v));
const quote = currentInquiryQuote(fixture);
assert.ok(quote);
assert.equal(quote.data.subtotal, '5100.00');
assert.ok(fixture.quote_revision! < fixture.revision, 'draft/followup revisions do not invalidate a current quote');
const html = renderToStaticMarkup(<CurrentInquiryQuoteCard record={fixture}/>);
assert.match(html, /下载中英文 PDF/);
assert.match(html, /下载中英文 Excel/);
assert.match(html, new RegExp(quote.quoteId));
assert.match(html, /5100.00/);
for (const patch of [
  {quote:null}, {quote:{ok:false}}, {quote_revision:null}, {quote_revision:fixture.revision+1},
  {items:[{sku:'DESK-001',quantity:500,custom_packaging:true}]},
  {items:[{sku:'DESK-001',quantity:1000,custom_packaging:false}]},
  {destination_country:'Canada'}, {requested_lead_days:10},
]) {
  const invalid = {...clone(fixture), ...patch} as InquiryRecord;
  assert.equal(currentInquiryQuote(invalid), null);
  assert.equal(renderToStaticMarkup(<CurrentInquiryQuoteCard record={invalid}/>), '');
}
const stale = clone(fixture); (stale.quote as any).stale=true;
assert.equal(currentInquiryQuote(stale), null);
const incomplete=clone(fixture); delete (incomplete.quote as any).data.items[0].unit_price;
assert.equal(currentInquiryQuote(incomplete),null);
assert.equal(currentInquiryQuote('Assistant says this is a quote: '+JSON.stringify(fixture)),null);
const oldDraft=clone(fixture); oldDraft.drafts!.stale=true;
assert.ok(currentInquiryQuote(oldDraft), 'a newly valid quote can coexist with an old draft awaiting revision');
let reads=0, refreshed:InquiryRecord|null=null;
const allowed=clone(fixture);allowed.revision+=1;
assert.equal((await readVerifiedInquiryQuote(fixture,async id=>{assert.equal(id,fixture.id);reads++;return allowed;},row=>{refreshed=row;})).quoteId,quote.quoteId);
assert.equal(reads,1);assert.equal(refreshed,allowed);
for (const latest of [
  {...fixture,quote:null},
  {...fixture,items:[{sku:'DESK-001',quantity:500,custom_packaging:true}]},
  {...fixture,id:'inq_'+'b'.repeat(32)},
]) await assert.rejects(()=>readVerifiedInquiryQuote(fixture,async()=>latest as InquiryRecord));
const changed=clone(fixture);(changed.quote as any).data.items[0].name='Different quote content under the same ID';
await assert.rejects(()=>readVerifiedInquiryQuote(fixture,async()=>changed),/quote_changed/);
await assert.rejects(()=>readVerifiedInquiryQuote(fixture,async()=>{throw new Error('403');}),/403/);
function reordered(v:unknown):unknown {return Array.isArray(v)?v.map(reordered):v && typeof v==='object'?Object.fromEntries(Object.entries(v).reverse().map(([k,x])=>[k,reordered(x)])):v;}
assert.ok(await readVerifiedInquiryQuote(fixture,async()=>reordered(allowed) as InquiryRecord));
if (process.argv[2]) {
  const real = JSON.parse(readFileSync(process.argv[2],'utf8')) as InquiryRecord;
  const parsed = currentInquiryQuote(real);
  assert.ok(parsed, 'the specified authenticated demo record remains downloadable');
  assert.equal(parsed.data.subtotal,'5100.00');
  assert.match(renderToStaticMarkup(<CurrentInquiryQuoteCard record={real}/>), /下载中英文 PDF/);
  console.log(`Specified demo record PASS: inquiry revision ${real.revision}, quote revision ${real.quote_revision}, total ${parsed.data.subtotal}`);
}
console.log('Inquiry quote card PASS: stdlib engine-backed inquiry, PDF/Excel controls, current input match, current-user reread, stale/malformed/prose rejection.');