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

test("conversation rows keep a compact, accessible reference shape", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  const styles = await read("src/production/conversations.css");
  assert.match(source, /className="conversation-avatar" aria-hidden=\{true\}/);
  assert.match(source, /className=\{`conversation-star\$\{conversation\.starred/);
  assert.match(source, /aria-label=\{conversation\.starred \? t\(locale, "conversations\.unstar"\) : t\(locale, "conversations\.star"\)\}/);
  assert.match(styles, /grid-template-columns:\s*var\(--min-tap-target\) minmax\(0, 1fr\) var\(--min-tap-target\)/);
  assert.match(styles, /html\[data-platform="desktop"\] \.conversation-row/);
  assert.match(styles, /html\[data-platform="mobile"\] \.conversation-summary/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  // red-proof: replacing the attribute-driven platform layouts with a viewport
  // media query or a literal color breaks deterministic host-selected QA.
});

test("detail metadata precedes summary and title editing is keyboard-complete", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  const metadata = source.indexOf('className="conversation-detail-meta"');
  const summary = source.indexOf('className="conversation-summary"');
  assert.ok(metadata >= 0 && summary > metadata);
  assert.match(source, /autoFocus/);
  assert.match(source, /event\.key === "Enter"/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /aria-labelledby="conversation-summary-heading"/);
  assert.match(source, /\{canPatch && <div className="conversation-detail-actions">/);
  // red-proof: moving the summary above the scan metadata or dropping Escape
  // strands keyboard users in the title editor and makes this test fail.
});

test("conversation failures use product copy rather than backend summaries", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  // `dead.body` is now chosen by `deadLetterView`, which returns it for every
  // permanent reason except the stale-epoch one David signed copy for. The
  // check that matters is unchanged: product copy, never server text.
  assert.match(source, /t\(locale, view\.messageKey\)/);
  assert.doesNotMatch(source, /letter\.summary|view\.summary|failure\.detail/);
  // red-proof: rendering the adapter summary would leak backend wording into
  // localized product chrome and make screenshots dependent on server text.
});
