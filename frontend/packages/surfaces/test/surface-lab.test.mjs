import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("surface lab is an explicit backend-free production fixture entry", async () => {
  const [entry, lab, pkg] = await Promise.all([
    read("src/production/main.tsx"),
    read("src/lab/main.tsx"),
    read("package.json"),
  ]);

  assert.match(entry, /query\.get\("lab"\) === "1"/);
  assert.match(entry, /import\("\.\.\/lab\/main\.js"\)/);
  assert.match(lab, /FIXTURE_STATES as MEMORY_STATES/);
  assert.match(lab, /CONVERSATION_FIXTURE_STATES/);
  assert.match(lab, /FIXTURE_STATES as TASK_STATES/);
  assert.match(lab, /new URLSearchParams\(\{ qa: surface\.id, state, platform, locale, \.\.\.\(polish \? \{ polish: "1" \} : \{\}\) \}\)/);
  assert.match(lab, /const MATRIX_SURFACES:[\s\S]+POLISH_EVIDENCE_STATES\.settings/);
  assert.match(lab, /const SURFACE_CATALOG = MATRIX_MODE \? MATRIX_SURFACES : SURFACES/);
  assert.doesNotMatch(lab, /bridgeHttpClient|openWebStorageBridge|fetch\(/);
  assert.match(pkg, /"dev:lab": "vite --port 4650 --open '\/\?lab=1'"/);

  // red-proof: routing the lab through bridge mode or replacing fixtureHref's
  // qa/state pair with route-only navigation makes this self-contained gate fail.
});

test("surface lab offers isolated mobile, desktop, and paired review", async () => {
  const lab = await read("src/lab/main.tsx");
  assert.match(lab, /type PreviewMode = "mobile" \| "desktop" \| "compare"/);
  assert.match(lab, /390 × 844/);
  assert.match(lab, /mode !== "desktop"/);
  assert.match(lab, /mode !== "mobile"/);
});
