/**
 * STATIC CHECKER (not behavioral coverage) for the app-detail JSON-LD block.
 * Run: npm test  (from web/frontend)
 *
 * page.tsx is a Next.js server component and cannot be imported by node:test.
 * generateStructuredData() feeds app name/description/author — all
 * community-supplied marketplace fields — into dangerouslySetInnerHTML via
 * JSON.stringify, which does not escape `<`. Without the `\u003c` escape a
 * `</script>` inside app metadata closes the ld+json element and injects
 * markup into the public app page.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const PAGE = new URL('../app/apps/[id]/page.tsx', import.meta.url);
const source = readFileSync(PAGE, 'utf8');

describe('apps/[id] JSON-LD serialization (static checker)', () => {
  it('escapes < in the JSON.stringify output used for ld+json', () => {
    assert.match(source, /JSON\.stringify\([\s\S]*?\)\.replace\(\/<\/g,\s*'\\\\u003c'\)/);
  });
});
