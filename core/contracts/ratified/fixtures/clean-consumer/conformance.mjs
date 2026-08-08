import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  hasHonestPageWindow,
  hasHonestRecallCompleteness,
  hasSafeSynthesizedPage,
} from "@omi-core/ratified-contracts/projections/synthesized";
import { hasSafeRecallTrace } from "@omi-core/ratified-contracts/recall/trace";

const fixtureRoot = new URL("./node_modules/@omi-core/ratified-contracts/fixtures/", import.meta.url);
for (const row of await fixture("page-conformance.json")) {
  assert.equal(hasSafeSynthesizedPage(row.page), row.safe, row.name);
}
for (const row of await fixture("read-page-windows.json")) {
  assert.equal(hasHonestPageWindow(row.window), row.honest, row.name);
}
for (const row of await fixture("recall-completeness.json")) {
  assert.equal(hasHonestRecallCompleteness(row.page), row.honest, row.name);
}
for (const row of await fixture("recall-trace.json")) {
  assert.equal(hasSafeRecallTrace(row.trace), row.safe, row.name);
}

async function fixture(name) {
  return JSON.parse(await readFile(new URL(name, fixtureRoot), "utf8"));
}
