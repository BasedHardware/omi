/**
 * STATIC CHECKER (not behavioral coverage) for the marketplace category map.
 * Run: npm test  (from web/frontend)
 *
 * category.ts imports lucide-react icon components, so it can't be loaded
 * directly by node:test without a TSX-aware loader. This asserts the
 * source-level contract instead: three known category IDs
 * (emotional-and-mental-support, communication-improvement,
 * travel-and-exploration) used elsewhere in the product (backend
 * _get_categories, the Flutter app, web/app marketplace) must have their
 * own metadata entry here, not silently fall through to the "other"/General
 * fallback via `categoryMetadata[category] || categoryMetadata.other`.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const CATEGORY_FILE = new URL('../app/apps/utils/category.ts', import.meta.url);
const source = readFileSync(CATEGORY_FILE, 'utf8');

const KNOWN_CATEGORY_IDS = [
  'emotional-and-mental-support',
  'communication-improvement',
  'travel-and-exploration',
];

describe('apps category metadata (static checker)', () => {
  for (const id of KNOWN_CATEGORY_IDS) {
    it(`has its own metadata entry for '${id}'`, () => {
      assert.match(source, new RegExp(`'${id}':\\s*{`));
    });
  }

  it('still falls back to the "other" entry for unrecognized ids', () => {
    assert.match(source, /categoryMetadata\[category\] \|\| categoryMetadata\.other/);
  });
});
