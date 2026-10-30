import assert from 'node:assert/strict';
import { contextLengthIssue } from '../src/utils/modelContextLength';
for (const value of [null, undefined, '', '   ']) {
  assert.equal(contextLengthIssue(value, true), 'required', 'unknown chat context cannot be silently saved');
  assert.equal(contextLengthIssue(value, false), null, 'other provider uses remain optional');
}
for (const value of [0, -1, 1.5, '1.5', 'unknown', Infinity, Number.MAX_SAFE_INTEGER + 1, {}, true]) {
  assert.equal(contextLengthIssue(value, true), 'positive_integer');
}
for (const value of [1, 4096, '128000', ' 32768 ']) assert.equal(contextLengthIssue(value, true), null);
console.log('model context window: required chat budget, positive integer validation and optional non-chat budget PASS');
