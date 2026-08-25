import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PAGE = new URL("../app/apps/[id]/page.tsx", import.meta.url);
const source = readFileSync(PAGE, "utf8");

describe("apps/[id] JSON-LD sink (static checker)", () => {
  it("escapes HTML-special characters on the structured-data payload", () => {
    assert.match(source, /export function generateStructuredData/);
    assert.ok(source.includes(".replace(/</g"));
    assert.ok(source.includes(".replace(/>/g"));
    assert.ok(source.includes(".replace(/&/g"));
  });
});
