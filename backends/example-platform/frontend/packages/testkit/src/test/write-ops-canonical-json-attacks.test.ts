/**
 * Adversarial corpus against the canonical-JSON parsing layer that backs
 * `parseWriteOpEnvelopeJson`.
 *
 * The mechanism under test is `parseCanonicalJson`: `JSON.parse(raw)`, then
 * re-serialize via `detachJsonData`/`JSON.stringify`, and require the result to
 * be BYTE-IDENTICAL to the original `raw`. Anything that fails that round trip
 * is rejected before the write-op predicate runs. These cases hand-write the
 * raw JSON text a hostile or buggy client could send — never `JSON.stringify`
 * of an object, which is canonical by construction.
 *
 * Known-good starting envelope shape is the accepted `patch` + `base_revision`
 * row from `write-ops-conformance.json` ("patch with a base_revision
 * precondition accepted"). That fixture is not modified here.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { parseWriteOpEnvelopeJson } from "@omi-core/ratified-contracts/write/ops";

/** First write_id from the known-good patch envelope. */
const WRITE_ID_A = "e11889ad5e74748964b84c271bd3b7bc6170d4a5816eb7e33f701a2cabe77a4c";
/** A different valid 64-hex id used only in the duplicate-key attack. */
const WRITE_ID_B = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const BASE_REVISION = "219a4807d8970548f0af5a687bb16d444d7090c74e203b37e072baae95a5f022";

/**
 * Exact requestBody from the conformance row
 * "patch with a base_revision precondition accepted".
 */
const KNOWN_GOOD_PATCH =
  `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","op":{"op":"patch","record_id":"task-9f21","patch":{"done":true},"base_revision":"${BASE_REVISION}"}}`;

const NESTED_OP = `{"op":"patch","record_id":"task-9f21","patch":{"done":true},"base_revision":"${BASE_REVISION}"}`;

test("sanity: known-good patch envelope is accepted", () => {
  assert.notEqual(parseWriteOpEnvelopeJson(KNOWN_GOOD_PATCH), null);
});

test("duplicate top-level write_id with different values is rejected", () => {
  // red-proof: if the round-trip check were removed, JSON.parse would keep only
  // WRITE_ID_B and the predicate would accept the envelope.
  const raw =
    `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","op":${NESTED_OP},"write_id":"${WRITE_ID_B}"}`;
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("duplicate top-level key with identical values is still rejected", () => {
  // Sharpest duplicate case: both copies agree, so a semantic "the value used
  // is right" check would wrongly accept. Rejection is structural (byte
  // round-trip), not semantic — JSON.parse keeps one occurrence, re-serialize
  // is shorter than raw.
  const raw =
    `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","domain":"tasks","op":${NESTED_OP}}`;
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("duplicate nested key inside op.patch is rejected", () => {
  const raw =
    `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","op":{"op":"patch","record_id":"task-9f21","patch":{"done":true,"done":false},"base_revision":"${BASE_REVISION}"}}`;
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("top-level key reordering without duplicates is accepted", () => {
  // Non-obvious property of the mechanism: the round trip requires raw to equal
  // ITS OWN canonical re-serialization of JSON.parse(raw), not a globally
  // sorted key order. JSON.parse preserves insertion order; JSON.stringify
  // emits that same order. hasExactKeys sorts before comparing, so key order
  // is not a semantic constraint either. Reordering (unlike duplication or
  // whitespace) is therefore safe — pin this so nobody "fixes" acceptance of
  // valid reordered input by accident.
  const reordered =
    `{"op":${NESTED_OP},"domain":"tasks","write_id":"${WRITE_ID_A}","account_epoch":7}`;
  const parsed = parseWriteOpEnvelopeJson(reordered);
  assert.notEqual(parsed, null);
  assert.equal(parsed?.write_id, WRITE_ID_A);
  assert.equal(parsed?.domain, "tasks");
  assert.equal(parsed?.account_epoch, 7);
  assert.equal(parsed?.op.op, "patch");
});

test("extra space after a colon is rejected", () => {
  const raw = KNOWN_GOOD_PATCH.replace(`"account_epoch":7`, `"account_epoch": 7`);
  assert.notEqual(raw, KNOWN_GOOD_PATCH);
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("extra space after a comma is rejected", () => {
  const raw = KNOWN_GOOD_PATCH.replace(`"account_epoch":7,`, `"account_epoch":7, `);
  assert.notEqual(raw, KNOWN_GOOD_PATCH);
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("trailing newline after the closing brace is rejected", () => {
  assert.equal(parseWriteOpEnvelopeJson(`${KNOWN_GOOD_PATCH}\n`), null);
});

test("leading whitespace before the opening brace is rejected", () => {
  assert.equal(parseWriteOpEnvelopeJson(` ${KNOWN_GOOD_PATCH}`), null);
});

test("byte-order mark before the opening brace is rejected", () => {
  assert.equal(parseWriteOpEnvelopeJson(`\uFEFF${KNOWN_GOOD_PATCH}`), null);
});

test("account_epoch +7 returns null rather than throwing", () => {
  const raw =
    `{"write_id":"${WRITE_ID_A}","account_epoch":+7,"domain":"tasks","op":${NESTED_OP}}`;
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("account_epoch 07 (invalid JSON) returns null rather than throwing", () => {
  // JSON.parse itself throws on a leading-zero integer; the boundary must catch
  // and return null, not leak an uncaught exception.
  const raw =
    `{"write_id":"${WRITE_ID_A}","account_epoch":07,"domain":"tasks","op":${NESTED_OP}}`;
  assert.equal(parseWriteOpEnvelopeJson(raw), null);
});

test("unicode-escaped ASCII in record_id fails round-trip; literal form is accepted", () => {
  // JSON.stringify prefers the literal form for printable ASCII, so \\u0041
  // ("A") does not round-trip even though the decoded string is identical.
  const escaped =
    `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","op":{"op":"patch","record_id":"task-\\u0041","patch":{"done":true},"base_revision":"${BASE_REVISION}"}}`;
  const literal =
    `{"write_id":"${WRITE_ID_A}","account_epoch":7,"domain":"tasks","op":{"op":"patch","record_id":"task-A","patch":{"done":true},"base_revision":"${BASE_REVISION}"}}`;
  assert.equal(parseWriteOpEnvelopeJson(escaped), null);
  const accepted = parseWriteOpEnvelopeJson(literal);
  assert.notEqual(accepted, null);
  assert.equal(accepted?.op.record_id, "task-A");
});
