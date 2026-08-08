import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("memory provenance stays metadata while long-content checks only the body", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  const presentation = await read("src/production/memory-presentation.ts");
  assert.match(presentation, /\[a-z0-9_-\]\{1,80\}/);
  assert.match(source, /const isLong = body\.length > 240/);
  assert.match(source, /<header className="memory-card-header">/);
  assert.match(source, /<span className="memory-provenance">\{provenance \?\? memory\.category\}<\/span>/);
  assert.doesNotMatch(source, /\{letter\.summary\}|failure\.detail/);
  // red-proof: rendering the full stored string in metadata or using its total
  // length would bring slug noise back into the body and misclassify long keys.
});

test("create and edit affordances are keyboard-safe and contract-bounded", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /aria-expanded=\{composerOpen\}/);
  assert.match(source, /<form className="memory-create"/);
  assert.match(source, /onSubmit=\{\(event\) => \{ event\.preventDefault\(\); void add\(\); \}\}/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /event\.metaKey \|\| event\.ctrlKey/);
  assert.match(source, /confirm\(t\(locale, "memories\.deleteConfirm"\)\)/);
  assert.doesNotMatch(source, /store\.(search|setScope|open)/);
  // red-proof: removing submit handling strands keyboard users; adding search
  // or scope calls would claim semantics absent from the Memory store contract.
});

test("shared chrome exposes platform hierarchy without fake destinations", async () => {
  const source = await read("src/production/ProductionChrome.tsx");
  const styles = await read("src/production/styles.css");
  assert.match(source, /aria-hidden="true" focusable="false"/);
  assert.match(source, /active === "conversations" \|\| active === "memories"/);
  assert.match(source, /href=\{href\("home"\)\}/);
  assert.match(source, /aria-current=\{active === "home" \? "page" : undefined\}/);
  assert.match(source, /<span aria-disabled="true"><ChromeIcon name="apps"/);
  assert.match(styles, /html\[data-platform="desktop"\].*production-nav:first-child/);
  assert.match(styles, /html\[data-platform="mobile"\].*production-nav:last-child/);
  assert.match(styles, /env\(safe-area-inset-bottom/);
  assert.match(styles, /focus-visible/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  // red-proof: Home is a supported query surface, while placeholder links stay
  // disabled; dropping the nested active rule leaves Memories with no mobile tab.
});
