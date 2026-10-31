import assert from 'node:assert/strict';
import { resolveLanguage } from '../src/i18n/defaultLanguage';
for (const community of [true, false]) {
  assert.equal(resolveLanguage('zh-CN', 'en', community), 'zh-CN', 'saved choice overrides the build');
  assert.equal(resolveLanguage('en', 'zh-CN', community), 'en', 'saved English is preserved');
  assert.equal(resolveLanguage(null, 'zh-CN', community), 'zh-CN', 'explicit Chinese works in a fresh CE origin');
  assert.equal(resolveLanguage(undefined, 'en', community), 'en');
  assert.equal(resolveLanguage('unknown', 'zh-CN', community), 'zh-CN');
  assert.equal(resolveLanguage(null, undefined, community), community ? 'en' : 'zh-CN', 'upstream edition fallback is preserved');
  assert.equal(resolveLanguage(null, 'unknown', community), community ? 'en' : 'zh-CN');
}
console.log('default language: saved preference, explicit build language and edition fallback PASS');
