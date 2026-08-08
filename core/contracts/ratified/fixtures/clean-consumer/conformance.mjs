import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { hasSafeSynthesizedPage } from "@omi-core/ratified-contracts/projections/synthesized";

const path = new URL("./node_modules/@omi-core/ratified-contracts/fixtures/page-conformance.json", import.meta.url);
const fixture = JSON.parse(await readFile(path, "utf8"));
for (const row of fixture) assert.equal(hasSafeSynthesizedPage(row.page), row.safe, row.name);
