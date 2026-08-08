import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const governedFiles = [
  "src/projections/synthesized.ts",
  "fixtures/clean-consumer/consumer.ts",
];
const markers = [
  "domain-pending(DIV-DOMCORE-001)",
  "domain-pending(DIV-DOMCORE-008)",
];

for (const relative of governedFiles) {
  const lines = readFileSync(resolve(root, relative), "utf8").split("\n");
  for (const [index, line] of lines.entries()) {
    if (!line.includes("SynthesizedMemory")) continue;
    const adjacent = lines.slice(Math.max(0, index - 3), index).join("\n");
    for (const marker of markers) {
      assert.ok(adjacent.includes(marker), `${relative}:${index + 1} lacks adjacent // ${marker}`);
    }
  }
}

const forbidden = ["conversations", "FEAT-CONV-012"];
for (const relative of governedFiles) {
  const source = readFileSync(resolve(root, relative), "utf8");
  for (const term of forbidden) assert.ok(!source.includes(term), `${relative} crossed forbidden open surface ${term}`);
}

const boundary = readFileSync(resolve(root, "scripts/package-boundary.mjs"), "utf8");
assert.match(boundary, /domain-pending\(DIV-DOMCORE-003\)[\s\S]{0,160}legacy editable Memory/);
assert.match(boundary, /domain-pending\(DIV-DOMCORE-005\)[\s\S]{0,180}ConversationMemory/);
assert.ok(boundary.includes("FEAT-CONV-012"), "package boundary must hard-stop the open conversation feature");

const readme = readFileSync(resolve(root, "README.md"), "utf8");
for (const marker of [
  "domain-pending(DIV-DOMCORE-001)",
  "domain-pending(DIV-DOMCORE-008)",
  "domain-pending(DIV-DOMCORE-003)",
  "domain-pending(DIV-DOMCORE-005)",
]) {
  assert.ok(readme.includes(`// ${marker}`), `README.md lacks visible // ${marker}`);
}

console.log(`domain markers OK: ${governedFiles.length} files`);
