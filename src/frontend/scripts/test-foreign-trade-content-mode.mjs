import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const output = resolve('node_modules/.tmp/foreign-trade-content-mode.mjs');
await mkdir(resolve('node_modules/.tmp'), { recursive: true });
await build({ entryPoints: ['src/utils/foreignTradeContentApi.ts'], outfile: output, bundle: true, platform: 'node', format: 'esm',
  plugins: [{ name: 'request-capture', setup(builder) {
    builder.onResolve({ filter: /^\.\.\/api$/ }, args => args.importer.endsWith('foreignTradeContentApi.ts') ? { path: 'api', namespace: 'capture' } : undefined);
    builder.onLoad({ filter: /.*/, namespace: 'capture' }, () => ({ contents: `
      export async function apiRequest(path, options) { globalThis.__tradeContentRequests.push({path, ...options}); return {data:{pack_id:'pack_test'}}; }
      export async function authFetch(path) { if (!globalThis.__allowDemoDownload) throw new Error('Unexpected binary/network call'); globalThis.__tradeBinaryRequests.push(path); return new Response('label,value,source_url\\n', {headers:{'Content-Type':'text/csv','Content-Disposition':'attachment; filename=product_facts_en.csv'}}); }
      export function getApiUrl() { return '/api'; }
    ` }));
  } }],
});
globalThis.__tradeContentRequests = [];
try {
  const { generateContentPack, downloadContentDemo } = await import(pathToFileURL(output).href);
  await generateContentPack('pack_test', 7);
  await generateContentPack('pack_test', 8, 'template');
  await generateContentPack('pack_test', 9, 'ai');
  assert.equal(globalThis.__tradeContentRequests.length, 3);
  const [defaultAi, local, explicitAi] = globalThis.__tradeContentRequests;
  for (const request of globalThis.__tradeContentRequests) {
    assert.equal(request.path, '/v1/foreign-trade/content-packs/pack_test/generate');
    assert.equal(request.method, 'POST');
    assert.equal(JSON.parse(request.body).confirmed, true);
  }
  assert.deepEqual(JSON.parse(defaultAi.body), { revision: 7, confirmed: true, generation_mode: 'ai' });
  assert.deepEqual(JSON.parse(local.body), { revision: 8, confirmed: true, generation_mode: 'template' });
  assert.deepEqual(JSON.parse(explicitAi.body), { revision: 9, confirmed: true, generation_mode: 'ai' });
  globalThis.__allowDemoDownload = true; globalThis.__tradeBinaryRequests = [];
  let downloadedName = '';
  globalThis.document = { body: { appendChild() {} }, createElement: () => ({ href: '', download: '', click() { downloadedName = this.download; }, remove() {} }) };
  globalThis.window = { setTimeout(callback) { callback(); return 0; } };
  await downloadContentDemo('facts-en');
  assert.deepEqual(globalThis.__tradeBinaryRequests, ['/api/v1/foreign-trade/content-packs/demo/facts-en']);
  assert.equal(downloadedName, 'product_facts_en.csv');
  console.log('foreign-trade content generation modes: default AI, explicit template/AI and confirmation/version request fields PASS');
} finally { delete globalThis.__tradeContentRequests; delete globalThis.__allowDemoDownload; delete globalThis.__tradeBinaryRequests; delete globalThis.document; delete globalThis.window; }
