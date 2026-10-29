import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const output = resolve('node_modules/.tmp/collaboration-browser');
await mkdir(output, { recursive: true });
const fixture = JSON.parse(await readFile('scripts/fixtures/foreign-trade-collaboration.json', 'utf8'));
let record = structuredClone(fixture); record.tasks[0].status = 'in_review'; record.tasks[0].review = null;
record.workflow_status.done_tasks = 5; record.workflow_status.ready_for_handoff = false;
await build({ alias: { react: resolve('node_modules/react'), 'react-dom': resolve('node_modules/react-dom') },
  stdin: { contents: `
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { AppThemeProvider } from './src/AppThemeProvider';
import { CollaborationWorkspace } from './src/components/foreign-trade/CollaborationWorkspace';
import { CollaborationCard } from './src/components/chat/CollaborationCard';
import { bindRouter } from './src/routing/navigation';
import './src/styles/index';
const fixture = ${JSON.stringify(fixture)};
const router = createBrowserRouter([{path:'/trade-collaboration/:id?',element:<CollaborationWorkspace/>},{path:'/card',element:<CollaborationCard receipt={fixture}/>},{path:'*',element:<p>Source destination</p>}]);
bindRouter(router);
createRoot(document.getElementById('root')).render(<AppThemeProvider><RouterProvider router={router}/></AppThemeProvider>);
`, resolveDir: process.cwd(), loader: 'tsx' }, outdir: output, entryNames: 'fixture', splitting: true, bundle: true, format: 'esm', jsx: 'automatic',
  define: { 'import.meta.env': '{}' }, loader: { '.css': 'css', '.svg': 'dataurl', '.woff': 'dataurl', '.woff2': 'dataurl', '.ttf': 'dataurl' },
  external: ['/loader.gif','/loader-done.png'],
});
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 1000 } });
const origin = 'http://127.0.0.1:5248'; const errors = []; const mutations = []; let handoffs = 0;
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => localStorage.setItem('jx_lang','zh-CN'));
try {
  await page.route(origin + '/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname;
    if (path.endsWith('.js') || path.endsWith('.css')) return route.fulfill({ contentType: path.endsWith('.css') ? 'text/css' : 'text/javascript', body: await readFile(resolve(output,path.slice(1))) });
    if (!path.startsWith('/api/')) return route.fulfill({ contentType: 'text/html', body: '<html><head><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>' });
    const base = '/api/v1/foreign-trade/collaborations';
    if (path === base) return route.fulfill({ json: { code:10000,data:[record] } });
    if (path === base + '/' + record.collaboration_id) return route.fulfill({ json: { code:10000,data:record } });
    if (path === base + '/' + record.collaboration_id + '/review') {
      const data = route.request().postDataJSON(); mutations.push(data);
      assert.equal(data.revision,record.revision); assert.equal(data.confirmed,true); assert.equal(data.task_id,'sales_requirements'); assert.ok(data.review_note.trim());
      record.tasks[0].status = 'done'; record.tasks[0].review = { actor_user_id:'test-owner',at:new Date().toISOString(),note:data.review_note };
      record.revision++; record.workflow_status.done_tasks = 6; record.workflow_status.ready_for_handoff = true;
      return route.fulfill({ json: {code:10000,data:record} });
    }
    if (path.endsWith('/handoff')) { handoffs++; assert.equal(Number(url.searchParams.get('revision')),record.revision); return route.fulfill({ contentType:'text/markdown',headers:{'Content-Disposition':'attachment; filename="handoff.md"'},body:'# Internal handoff' }); }
    return route.fulfill({ json: { code:10000,data:[] } });
  });
  await page.goto(origin + '/trade-collaboration/' + record.collaboration_id);
  await page.getByRole('heading',{name:'跨岗位协同',exact:true}).waitFor();
  const download = page.getByRole('button',{name:'下载交接 Markdown',exact:true});
  assert.equal(await download.isDisabled(),true,'unreviewed record cannot download');
  assert.equal(mutations.length,0,'reading records cannot accept tasks');
  await page.getByRole('button',{name:'编辑与验收',exact:true}).first().click();
  const review = page.getByRole('button',{name:'确认人工验收',exact:true});
  assert.equal(await review.isDisabled(),true);
  await page.getByLabel('人工验收说明',{exact:true}).fill('Checked current source evidence and retained open questions.');
  assert.equal(await review.isDisabled(),true,'note without explicit checkbox is insufficient');
  await page.getByRole('checkbox').check(); await review.click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(mutations.length,1); assert.ok(record.tasks[0].unresolved_items.length,'review must preserve genuine unresolved items');
  assert.equal(await download.isDisabled(),false);
  const downloaded = page.waitForEvent('download'); await download.click(); await downloaded; assert.equal(handoffs,1);
  await page.screenshot({ path:resolve(output,'workspace.png'),fullPage:true });
  await page.setViewportSize({width:390,height:844}); await page.screenshot({path:resolve(output,'workspace-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1),false,'mobile view has no horizontal overflow');
  await page.goto(origin + '/card'); await page.getByRole('button',{name:'查看当前协同',exact:true}).click();
  await page.getByText('当前账号人工确认',{exact:false}).first().waitFor();
  record.revision++;
  await page.getByRole('button',{name:'下载交接 Markdown',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'交接下载被阻止'}).waitFor();
  assert.equal(handoffs,1,'card stale read prevents download');
  assert.deepEqual(errors,[]);
  console.log('collaboration browser PASS: explicit human review, preserved unknowns, revision-bound download, stale-card guard, desktop/mobile render');
} finally { await browser.close(); }
