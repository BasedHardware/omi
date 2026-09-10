/**
 * STATIC CHECKER (not behavioral coverage) for the public marketplace category map.
 * Run: npm test  (from web/frontend)
 *
 * category.ts imports lucide-react components, so node:test cannot import it
 * directly. This asserts the source-level contract behind the regression: every
 * category id the backend can assign to a published app must have its own
 * metadata entry, so getCategoryMetadata() only falls back to the General
 * entry for the real `other` category and genuinely unknown ids. Before the
 * fix, three known ids (communication-improvement, emotional-and-mental-support,
 * travel-and-exploration) were missing and rendered as duplicate "General"
 * sections on /apps.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const SOURCE = new URL('../app/apps/utils/category.ts', import.meta.url);
const source = readFileSync(SOURCE, 'utf8');

// Source of truth for category ids: the backend's base category → master
// category map. Every key there can be assigned to a published app, so every
// key must resolve to its own marketplace metadata (not the General fallback).
const BACKEND_APPS = new URL('../../../../backend/utils/apps.py', import.meta.url);
const backendSource = readFileSync(BACKEND_APPS, 'utf8');

function backendCategoryIds() {
  const block = backendSource.match(
    /^_BASE_CATEGORY_MAPPING: Dict\[str, str\] = \{\n([\s\S]*?)^\}/m,
  );
  assert.ok(block, 'could not find _BASE_CATEGORY_MAPPING in backend/utils/apps.py');
  const ids = [...block[1].matchAll(/^\s+'([a-z0-9-]+)': '/gm)].map((m) => m[1]);
  assert.ok(ids.length >= 10, `unexpectedly few backend category ids: ${ids.length}`);
  return ids;
}

// `other` is the General fallback itself and is checked separately below.
const REQUIRED_CATEGORY_IDS = backendCategoryIds().filter((id) => id !== 'other');

// Added by this fix; existing entries keep their historical hues (ratchet is no-increase).
const NEW_CATEGORY_IDS = [
  'communication-improvement',
  'emotional-and-mental-support',
  'travel-and-exploration',
];

function entryFor(id) {
  // Matches either a quoted or bare object key at the top level of categoryMetadata.
  const pattern = new RegExp(`^  '?${id}'?: \\{\\n([\\s\\S]*?)^  \\},$`, 'm');
  const match = source.match(pattern);
  return match ? match[1] : null;
}

function field(entry, name) {
  const match = entry.match(new RegExp(`^\\s+${name}: '([^']*)',$`, 'm'));
  return match ? match[1] : null;
}

describe('marketplace categoryMetadata (static checker)', () => {
  for (const id of REQUIRED_CATEGORY_IDS) {
    it(`has a dedicated entry for ${id}`, () => {
      const entry = entryFor(id);
      assert.ok(entry, `categoryMetadata is missing an entry for '${id}'`);
      assert.equal(field(entry, 'id'), id);
      assert.notEqual(field(entry, 'displayName'), 'General');
      assert.notEqual(field(entry, 'description'), 'Other useful applications');
      assert.match(entry, /^\s+icon: [A-Z][A-Za-z0-9]*,$/m);
    });
  }

  it('keeps the General entry as the fallback for `other` and unknown ids', () => {
    assert.ok(
      backendCategoryIds().includes('other'),
      'backend map should still define other',
    );
    const other = entryFor('other');
    assert.ok(other);
    assert.equal(field(other, 'displayName'), 'General');
    assert.match(
      source,
      /return categoryMetadata\[category\] \|\| categoryMetadata\.other;/,
    );
  });

  it('does not add purple accents to the new entries (INV-UI-1 ratchet)', () => {
    for (const id of NEW_CATEGORY_IDS) {
      assert.doesNotMatch(
        entryFor(id),
        /purple|violet|fuchsia/,
        `${id} uses a purple hue`,
      );
    }
  });
});
