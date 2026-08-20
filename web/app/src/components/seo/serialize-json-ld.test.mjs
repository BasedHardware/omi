import assert from 'node:assert/strict';
import test from 'node:test';

import { serializeJsonLd } from './serialize-json-ld.mjs';

test('serializeJsonLd escapes angle brackets and ampersands', () => {
  const html = serializeJsonLd({
    name: '</script><script>alert(1)</script>',
    note: 'a & b > c',
  });
  assert.equal(html.includes('<'), false);
  assert.equal(html.includes('>'), false);
  assert.equal(html.includes('&'), false);
  assert.ok(html.includes('\\u003c'));
  assert.ok(html.includes('\\u003e'));
  assert.ok(html.includes('\\u0026'));
  assert.deepEqual(JSON.parse(html), {
    name: '</script><script>alert(1)</script>',
    note: 'a & b > c',
  });
});
