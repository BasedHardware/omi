import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("memory presentation stays contract-bounded", async () => {
  // RETAINED-SOURCE-ASSERTION: raw-field and invented-state absence is a contract-shape restriction across all fixtures.
  const source = await read("src/production/MemoriesProduction.tsx");
  const presentation = await read("src/production/memory-presentation.ts");
  assert.match(presentation, /\[a-z0-9_-\]\{1,80\}/);
  assert.doesNotMatch(source, /\{letter\.summary\}|failure\.detail/);
  // STRUCTURAL CONTRACT ASSERTION: the presenter grammar and forbidden backend
  // fields are source-boundary facts; rendered provenance and length behavior
  // are covered in memories-rendering.test.mjs.
});

test("memory mutations stay within the ratified store contract", async () => {
  // RETAINED-SOURCE-ASSERTION: the allowed mutation vocabulary and forbidden review workflow are port-boundary facts.
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /confirm\(t\(locale, "memories\.deleteConfirm"\)\)/);
  assert.doesNotMatch(source, /store\.(search|setScope|open)/);
  // STRUCTURAL CONTRACT ASSERTION: adding search or scope calls would claim
  // semantics absent from the Memory store contract. Form behavior is rendered.
});

test("shared chrome uses host-selected CSS", async () => {
  // RETAINED-SOURCE-ASSERTION: jsdom cannot observe host-selected CSS branches or prove viewport-query absence.
  const styles = await read("src/production/styles.css");
  assert.match(styles, /html\[data-platform="desktop"\].*production-nav:first-child/);
  assert.match(styles, /html\[data-platform="mobile"\].*production-nav:last-child/);
  assert.match(styles, /env\(safe-area-inset-bottom/);
  assert.match(styles, /focus-visible/);
  // Host-selected layout remains attribute-driven; the shared accessibility
  // contract is allowed its two user-preference media queries.
  assert.doesNotMatch(styles, /@media\s*\((?!prefers-reduced-motion|prefers-reduced-transparency)/);
  // STRUCTURAL CSS ASSERTION: jsdom does not calculate these host-selected
  // platform layouts, safe-area rules, or focus-visible styles.
});
