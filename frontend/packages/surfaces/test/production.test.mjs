import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("production entry gates fixtures and marks the explicit host platform", async () => {
  const source = await read("src/production/main.tsx");
  assert.match(source, /query\.get\("qa"\) === "memories"/);
  assert.match(source, /dataset\["platform"\]/);
  assert.match(source, /dataset\["theme"\]/);
  assert.match(source, /OMI_PRODUCTION_READY/);
  // red-proof: removing the qa=memories guard would make arbitrary URL state
  // values enter the synthetic fixture path in a production shell.
  assert.doesNotMatch(source, /const fixtureValue = query\.get\("state"\);/);
});

test("desktop-only Rewind stays out of mobile captured tabs", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  const mobileTabs = source.match(/<div className="nav-mobile">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(source, /nav\.rewind/);
  assert.match(source, /desktop-library-segment/);
  assert.doesNotMatch(mobileTabs, /nav\.rewind/);
  assert.match(mobileTabs, /nav\.conversations/);
  assert.match(mobileTabs, /nav\.tasks/);
  // red-proof: adding Rewind to nav-mobile violates the binding's desktop-only rule.
});

test("memory cards keep locked and provenance behavior honest", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /splitProvenance\(memory\.content\)/);
  assert.match(source, /locked\.body/);
  assert.match(source, /await store\.discardDeadLetter\(letter\.opId\)/);
  assert.match(source, /memory\.locked \? \(/);
  assert.match(source, /store\.patch\(memory\.id, \{ visibility: targetVisibility \}\)/);
  assert.match(source, /store\.delete\(memory\.id\)/);
  const lockedBranch = source.match(/\{memory\.locked \? \(([\s\S]*?)\) : editing/)?.[1] ?? "";
  assert.doesNotMatch(lockedBranch, /store\.patch\(memory\.id, \{ content/);
  assert.doesNotMatch(source, /provenance-prefix/);
  assert.match(source, /<p className="memory-content">\{visibleText\}<\/p>/);
  assert.doesNotMatch(source, /failure\.detail/);
  assert.doesNotMatch(source, /setReview/);
  assert.doesNotMatch(source, /memories\.(accept|reject)/);
  assert.doesNotMatch(source, /t\("en"/);
  // red-proof: rendering failure.detail or the provenance prefix in the body
  // would expose backend/debug text or duplicate the source label.
});

test("fixture matrix covers the truthful production states", async () => {
  const source = await read("src/production/memory-fixtures.ts");
  for (const state of ["loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "locked", "long"]) {
    assert.match(source, new RegExp(`\\"${state}\\"`));
  }
  assert.match(source, /FIXED_NOW = Date\.UTC/);
  // red-proof: replacing fixed fixture time with Date.now() makes screenshot
  // evidence drift between runs and invalidates visual comparisons.
});

test("i18n hardcoded-copy guard walks nested JSX text and expressions", async () => {
  const source = await read("../../scripts/check-i18n-parity.mjs");
  assert.match(source, /ts\.isJsxText\(node\)/);
  assert.match(source, /ts\.isJsxExpression\(node\)/);
  assert.match(source, /visitAst\(sourceFile\)/);
  // red-proof: a checker that only scans top-level JSX would miss a literal
  // nested under a wrapper and let visible English copy ship untranslated.
});

test("fixture ids are parsed RecordIds and platform CSS is attribute-driven", async () => {
  const fixtures = await read("src/production/memory-fixtures.ts");
  const styles = await read("src/production/styles.css");
  assert.match(fixtures, /parseRecordId/);
  assert.doesNotMatch(fixtures, /memory-001|memory-002/);
  assert.match(styles, /html\[data-platform="desktop"\]/);
  assert.match(styles, /html\[data-platform="mobile"\]/);
  assert.doesNotMatch(styles, /html\[data-platform="desktop"\].*memory-grid[^\n]*repeat\(/);
  assert.doesNotMatch(styles, /@media\s*\(min-width/);
  // red-proof: replacing an attribute selector with a width media override
  // would silently make a requested mobile QA fixture render desktop chrome.
});
