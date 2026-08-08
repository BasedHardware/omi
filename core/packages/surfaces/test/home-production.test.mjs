import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("home search reads loaded projections without claiming backend completeness", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  assert.match(source, /type SearchProjection<T>/);
  assert.match(source, /list\(\): Promise<T\[\]>/);
  assert.match(source, /subscribe\(listener: \(\) => void\)/);
  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /memorySource\.list\(\)/);
  assert.match(source, /conversationSource\.list\(\)/);
  assert.doesNotMatch(source, /taskSource|Task\b/);
  assert.doesNotMatch(source, /refresh\(|fetch\(|search\(|complete:\s*true|backend/i);
  // red-proof: adding refresh/search/fetch or a completeness assertion makes
  // Home cease to be a filter over the already-loaded projections.
});

test("home search is a merged chronological spine, clearable, and keyboard focusable", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  const styles = await read("src/production/home.css");
  assert.match(source, /autoFocus/);
  assert.match(source, /event\.metaKey \|\| event\.ctrlKey/);
  assert.match(source, /event\.key\.toLocaleLowerCase\(\) !== "k"/);
  assert.match(source, /searchRef\.current\?\.focus\(\)/);
  assert.match(source, /common\.clearSearch/);
  assert.match(source, /common\.noResults/);
  assert.match(source, /home-result-spine/);
  assert.match(source, /kind: "memory"/);
  assert.match(source, /kind: "conversation"/);
  assert.doesNotMatch(source, /kind: "task"/);
  assert.match(source, /sort\(\(left, right\) => right\.timestamp - left\.timestamp\)/);
  assert.match(source, /home-kind-filter/);
  assert.match(source, /\["all", "conversation", "memory"\]/);
  assert.match(source, /aria-disabled="true" disabled>\{t\(locale, "nav\.rewind"\)\}/);
  assert.match(source, /home\.loadedCount/);
  assert.match(source, /home\.matchCount/);
  assert.match(styles, /grid-template-rows:\s*auto 12px minmax\(0,1fr\)/);
  assert.match(styles, /height:\s*64px/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  // red-proof: removing the controlled clear path, Cmd-K focus, or a result
  // spine/filter fails this interaction-and-hierarchy guard.
});

test("home does not fabricate ask, chat, send, or mutation affordances", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  assert.doesNotMatch(source, /store\.create|store\.patch|store\.delete|\b(?:ask|chat|send)\b/i);
  assert.match(source, /href=\{conversationHref\(row\.value\.id\)\}/);
  assert.doesNotMatch(source, /href=\{.*memory|href=\{.*task/i);
  // red-proof: adding an Ask button or clickable memory/task destination would
  // claim behavior the current loaded projections do not provide.
});
