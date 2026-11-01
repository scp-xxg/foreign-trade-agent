import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdir,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const output=resolve('node_modules/.tmp/direct-check-browser');await mkdir(output,{recursive:true});
await build({stdin:{contents:`
import {createRoot} from 'react-dom/client';
import {AppThemeProvider} from './src/AppThemeProvider';
import {ComposerMaterialCheck} from './src/components/chat/ComposerMaterialCheck';
import {useComposerStore} from './src/stores/composerStore';
useComposerStore.getState().activate('fixture',{input:'best price',uploadedFiles:[new File(['CE certified lamp'],'spec.txt',{type:'text/plain'})]});
window.store=useComposerStore;
createRoot(document.getElementById('root')).render(<AppThemeProvider><ComposerMaterialCheck draftKey="fixture"/></AppThemeProvider>);
`,resolveDir:process.cwd(),loader:'tsx'},outdir:output,entryNames:'fixture',bundle:true,format:'esm',jsx:'automatic',define:{'import.meta.env':'{}'},loader:{'.css':'css','.svg':'dataurl','.woff':'dataurl','.woff2':'dataurl','.ttf':'dataurl'}});
const fixture=JSON.parse(await readFile('scripts/fixtures/material-check-receipt.json','utf8'));
fixture.action='sensitive';fixture.compliance=null;
const browser=await chromium.launch({headless:true});
try{
const page=await browser.newPage();const errors=[];let calls=0;let body='';
page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>localStorage.setItem('jx_lang','zh-CN'));
await page.route('http://127.0.0.1:5252/**',async route=>{
 const path=new URL(route.request().url()).pathname;
 if(path.includes('/material-check')){calls++;body=route.request().postData()||'';return route.fulfill({contentType:'application/json',body:JSON.stringify({data:fixture})});}
 return route.fulfill(path.endsWith('.js')||path.endsWith('.css')?{contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(resolve(output,path.slice(1)))}:{contentType:'text/html',body:'<html><head><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>'});
});
await page.goto('http://127.0.0.1:5252/');
await page.getByRole('button',{name:'资料检查',exact:true}).click();
await page.getByRole('button',{name:'查看表达检查：CE certified',exact:true}).waitFor();
assert.equal(calls,1);assert.ok(body.includes('best price'));assert.ok(body.includes('spec.txt'));assert.ok(body.includes('CE certified lamp'));
const snapshot=await page.evaluate(()=>{const s=window.store.getState();return {text:s.drafts[s.scopes.fixture].input,count:s.drafts[s.scopes.fixture].uploadedFiles.length};});
assert.deepEqual(snapshot,{text:'best price',count:1});
await page.getByRole('button',{name:'重新检查',exact:true}).click();
await page.getByRole('button',{name:'查看表达检查：CE certified',exact:true}).waitFor();assert.equal(calls,2);
await page.locator('.ant-modal-footer button').first().click();
await page.evaluate(()=>window.store.getState().resetForUser('next-user'));
await page.getByRole('button',{name:'资料检查',exact:true}).click();
await page.getByText('请先在输入框填写文字或添加文件。',{exact:true}).waitFor();assert.equal(calls,2);
assert.deepEqual(errors,[]);console.log('Direct composer button: text + file upload, highlights, recheck, draft preservation and empty input PASS');
}finally{await browser.close();}
