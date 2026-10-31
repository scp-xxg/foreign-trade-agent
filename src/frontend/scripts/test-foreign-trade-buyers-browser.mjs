import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const output = resolve('node_modules/.tmp/buyers-browser');
await mkdir(output, {recursive:true});
await build({ alias:{react:resolve('node_modules/react'),'react-dom':resolve('node_modules/react-dom')},
  stdin:{contents:`import { createRoot } from 'react-dom/client';
import { AppThemeProvider } from './src/AppThemeProvider';
import { BuyerSearchWorkspace } from './src/components/foreign-trade/BuyerSearchWorkspace';
import './src/styles/index';
createRoot(document.getElementById('root')).render(<AppThemeProvider><BuyerSearchWorkspace/></AppThemeProvider>);`,resolveDir:process.cwd(),loader:'tsx'},
  outdir:output,entryNames:'fixture',bundle:true,format:'esm',jsx:'automatic',define:{'import.meta.env':'{}'},
  loader:{'.css':'css','.svg':'dataurl','.woff':'dataurl','.woff2':'dataurl','.ttf':'dataurl'},external:['/loader.gif','/loader-done.png'] });
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1366,height:1000}});
const errors=[]; const requests=[]; let available=true;
page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>localStorage.setItem('jx_lang','zh-CN'));
const plan={queries:['drinkware distributor Germany'],search_available:true,note:'Fixture search plan'};
const candidates=['example.com','example.org','example.net'].map((domain,i)=>({id:`buyer-${i+1}`,name:`Fixture buyer ${i+1}`,domain,discovery_url:`https://${domain}`,query:plan.queries[0],summary:'Public search source',page_status:'read',page_excerpt:'Public website evidence',page_read_at:'2026-10-31T00:00:00Z',discovered_at:'2026-10-31T00:00:00Z',decision:'needs_review',rule_results:[],unresolved:['Identity unverified']}));
const run={plan,candidates,search_log:[{query:plan.queries[0],status:'complete'}],stop_reason:'queries_exhausted',warnings:[],limitations:[],metrics:{candidate_count:3,queries_executed:1,pages_read:3,elapsed_seconds:1}};
try {
 await page.route('http://127.0.0.1:5249/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('.js')||path.endsWith('.css'))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(resolve(output,path.slice(1)))});
  if(!path.startsWith('/api/'))return route.fulfill({contentType:'text/html',body:'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>'});
  if(path.includes('/buyer-search/')){requests.push(route.request().postDataJSON());return route.fulfill({json:{code:10000,data:path.endsWith('/plan')?{...plan,search_available:available}:run}});}
  return route.fulfill({json:{code:10000,data:[]}});
 });
 await page.goto('http://127.0.0.1:5249/trade-buyers');
 await page.getByRole('heading',{name:'潜在买家搜索',exact:true}).waitFor();
 await page.locator('input[type=file]').setInputFiles({name:'profile.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({profile_id:'fixture',rules:[],search_plan:[{queries:plan.queries}]}))});
 await page.getByRole('button',{name:'预览搜索计划',exact:true}).click();
 await page.getByText(plan.queries[0],{exact:true}).waitFor();
 assert.equal(requests[0].profile.profile_id,'fixture');
 await page.getByRole('button',{name:'开始买家搜索',exact:true}).click();
 await page.getByRole('heading',{name:'Fixture buyer 1'}).waitFor();
 for (const [i,label] of ['适合进入背调','不适合','证据不足'].entries()) {
   await page.getByRole('combobox',{name:`人工审核 ${candidates[i].domain}`,exact:true}).click();
   await page.getByText(label,{exact:true}).last().click();
 }
 await page.getByText(/人工审核覆盖率.*100.0%.*50.0%/).waitFor();
 const downloaded=page.waitForEvent('download');
 await page.getByRole('button',{name:'导出候选与审核',exact:true}).click();
 const exportFile=await downloaded;
 const exported=JSON.parse(await readFile(await exportFile.path(),'utf8'));
 assert.equal(exported.human_metrics.rate,0.5);assert.equal(exported.human_metrics.coverage,1);assert.equal(exported.candidates.length,3);
 await page.getByText('网页证据与筛选依据',{exact:true}).first().click();
 await page.getByText('Public website evidence',{exact:true}).first().waitFor();
 await page.screenshot({path:resolve(output,'workspace.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:resolve(output,'workspace-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'no mobile horizontal overflow');
 available=false;
 await page.getByRole('button',{name:'预览搜索计划',exact:true}).click();
 await page.getByText('尚未配置搜索服务，请在服务配置中设置搜索引擎及 API Key。',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('buyers browser PASS: profile import, preview, results, source evidence, human metric denominator, JSON export, missing configuration, desktop/mobile');
}finally{await browser.close();}
