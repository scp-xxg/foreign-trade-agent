import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { useKbTab } from '../src/routing/subPages';

function Category() { return <span>{useKbTab()}</span>; }

// The URL can already point at the destination while React still displays the
// previous route. A departing KB panel must not interpret that URL as "public"
// and trigger CE's redirect back to private KBs.
for (const destination of ['/ability-center', '/settings', '/user-management', '/', '/projects']) {
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { pathname: destination } } });
  assert.equal(renderToStaticMarkup(<MemoryRouter initialEntries={['/my-space/kb/private']}><Category /></MemoryRouter>), '<span>private</span>', destination);
}
Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { pathname: '/my-space/kb/private' } } });
assert.equal(renderToStaticMarkup(<MemoryRouter initialEntries={['/my-space/kb/public']}><Category /></MemoryRouter>), '<span>public</span>');
console.log('KB tab uses the mounted route snapshot during navigation: passed');
