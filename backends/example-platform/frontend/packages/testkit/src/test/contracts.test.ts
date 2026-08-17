import assert from "node:assert/strict";
import { test } from "node:test";
import { parseRecordId } from "@omi-core/contracts";
import { degrade } from "@omi-core/kernel";
import { generateSlug, WORDLIST } from "@omi-core/kernel";
import { ManualEnv } from "../fakes.js";

test("id grammar: slugs and legacy UUIDs accepted, junk rejected (ADR-006 rollout rule)", () => {
  assert.equal(parseRecordId("flying-dragon-vibrant")?.kind, "slug");
  assert.equal(parseRecordId("2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111")?.kind, "legacy-uuid");
  assert.equal(parseRecordId("Flying-Dragon")?.kind, "legacy-opaque", "not a slug, but a valid server-opaque id");
  assert.equal(parseRecordId("a1b2C3dEf4")?.kind, "legacy-opaque", "Firestore-style ids accepted");
  assert.equal(parseRecordId("ab"), null, "too short for any form");
  assert.equal(parseRecordId("../../etc/passwd"), null);
});

test("wordlist curation: every word individually produces valid slugs", () => {
  for (const w of WORDLIST) assert.match(w, /^[a-z]{2,12}$/, `bad word in list: ${w}`);
  const env = new ManualEnv();
  for (let i = 0; i < 100; i++) {
    const slug = generateSlug(() => env.random());
    assert.ok(parseRecordId(slug), `generated slug failed own grammar: ${slug}`);
  }
});

test("degrade(): the fallback value cannot exist without its telemetry event", () => {
  const events: unknown[] = [];
  const sink = { record: (e: unknown) => void events.push(e) };
  const v = degrade(sink, { path: "test.fallback", from: "primary", to: "cache", at: 1 }, 42);
  assert.equal(v.value, 42);
  assert.equal(events.length, 1, "constructing Degraded emitted exactly one event");
});
