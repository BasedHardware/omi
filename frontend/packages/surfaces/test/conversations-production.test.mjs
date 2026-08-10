import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("conversation discovery uses only available title, overview, star, and folder data", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  assert.match(source, /<ProductionSearchField/);
  assert.match(source, /conversations\.filterSavedPlaceholder/);
  assert.match(source, /`\$\{row\.title\} \$\{row\.overview\}`/);
  assert.match(source, /filter === "starred" \? rows\.filter/);
  assert.match(source, /row\.folderId !== folderId/);
  assert.match(source, /folders\.filter\(\(folder\) => !folder\.isSystem\)/);
  assert.doesNotMatch(source, /participant|speaker|transcript|store\.create/i);
  // red-proof: searching or filtering a fabricated participant/transcript field
  // makes this fail; these fields are absent from the ratified list contract.
});

test("conversation parity labels fixture days without consulting the wall clock", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  assert.match(source, /CONVERSATION_FIXED_NOW/);
  assert.match(source, /deterministic && new Date\(value\)/);
  assert.match(source, /return t\(locale, "tasks\.today"\)/);
  assert.doesNotMatch(source, /Date\.now\(\)/);
  // red-proof: replacing CONVERSATION_FIXED_NOW with Date.now() makes the
  // Today group drift across screenshot runs and fails this guard.
});

test("conversation rows use host-selected CSS without literal colors", async () => {
  const styles = await read("src/production/conversations.css");
  assert.match(styles, /grid-template-columns:\s*var\(--min-tap-target\) minmax\(0, 1fr\) var\(--min-tap-target\)/);
  assert.match(styles, /html\[data-platform="desktop"\] \.conversation-row/);
  assert.match(styles, /html\[data-platform="mobile"\] \.conversation-summary/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  // STRUCTURAL CSS ASSERTION: jsdom cannot observe host-selected layout or
  // semantic-token usage. Replacing the attribute-driven platform layouts with a viewport
  // media query or a literal color breaks deterministic host-selected QA.
});
