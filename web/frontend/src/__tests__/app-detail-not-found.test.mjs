/**
 * STATIC CHECKER (not behavioral coverage) for the public app detail page.
 * Run: npm test  (from web/frontend)
 *
 * The page is a Next.js server component, so it cannot be imported by node:test.
 * This asserts the source-level contract that produced the regression: an unknown
 * app id must signal a 404 via notFound(), never throw a bare Error (which Next
 * renders as HTTP 500). Behavioral proof lives in the PR: a running server
 * returned 500 before the fix and 404 after, for the same missing app id.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const PAGE = new URL('../app/apps/[id]/page.tsx', import.meta.url);
const source = readFileSync(PAGE, 'utf8');

describe('apps/[id] missing app handling (static checker)', () => {
  it('signals a 404 through notFound()', () => {
    assert.match(source, /from 'next\/navigation'/);
    assert.match(source, /notFound\(\)/);
  });

  it('never throws a bare Error for a missing app', () => {
    assert.doesNotMatch(source, /throw new Error\('App not found'\)/);
  });
});
