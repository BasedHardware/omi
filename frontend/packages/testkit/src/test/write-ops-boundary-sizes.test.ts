/**
 * Adversarial boundary / size corpus against the shipped write-ops wire
 * validators. Does not restate the conformance corpus — it pins the exact
 * edges of `RECORD_ID_PATTERN`, `WRITE_ID_PATTERN`, `REVISION_PATTERN`,
 * `account_epoch` safe-integer + canonical-form rules, envelope code-unit
 * budget, and `mintWriteId` entropy length.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_WRITE_ENVELOPE_JSON_CODE_UNITS,
  WRITE_ID_ENTROPY_BYTES,
  WRITE_ID_PATTERN,
  isTrustedWriteOpEnvelope,
  mintWriteId,
  parseWriteId,
  parseWriteOpEnvelopeJson,
} from "@omi-core/ratified-contracts/write/ops";

const VALID_WRITE_ID = "a".repeat(64);
const VALID_REVISION = "b".repeat(64);

/** Compact patch envelope; `accountEpochRaw` is spliced as a JSON number literal. */
function patchEnvelope(opts: {
  readonly writeId?: string;
  readonly accountEpochRaw?: string;
  readonly recordId?: string;
  readonly baseRevision?: string;
  readonly patchValue?: string;
}): string {
  const writeId = opts.writeId ?? VALID_WRITE_ID;
  const accountEpochRaw = opts.accountEpochRaw ?? "0";
  const recordId = opts.recordId ?? "x";
  const patchValue = opts.patchValue ?? "v";
  const base =
    opts.baseRevision === undefined
      ? ""
      : `,"base_revision":${JSON.stringify(opts.baseRevision)}`;
  return (
    `{"write_id":${JSON.stringify(writeId)},"account_epoch":${accountEpochRaw},` +
    `"domain":"tasks","op":{"op":"patch","record_id":${JSON.stringify(recordId)},` +
    `"patch":{"p":${JSON.stringify(patchValue)}}${base}}}`
  );
}

test("record_id length and printable-ASCII boundaries on patch", () => {
  // Boundary: RECORD_ID_PATTERN /^[\x21-\x7e]{1,256}$/ — exactly 1 char (accept).
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "x" })), null);

  // Boundary: exactly 256 chars (accept).
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "r".repeat(256) })), null);

  // Boundary: exactly 257 chars (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "r".repeat(257) })), null);

  // Boundary: empty string (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "" })), null);

  // Boundary: space (\x20) is below the printable-ASCII floor (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: " " })), null);

  // Boundary: newline is outside \x21-\x7e (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "\n" })), null);

  // Boundary: DEL (\x7f) is above the printable-ASCII ceiling (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ recordId: "\x7f" })), null);
});

test("write_id length, case, and all-zero structural acceptance", () => {
  // Boundary: 63 lowercase hex chars — too short (reject).
  assert.equal(parseWriteId("a".repeat(63)), null);
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ writeId: "a".repeat(63) })), null);

  // Boundary: 65 lowercase hex chars — too long (reject).
  assert.equal(parseWriteId("a".repeat(65)), null);
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ writeId: "a".repeat(65) })), null);

  // Boundary: 64 hex with one uppercase — pattern is lowercase-only (reject).
  const mixedCase = "A" + "a".repeat(63);
  assert.equal(mixedCase.length, 64);
  assert.equal(parseWriteId(mixedCase), null);
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ writeId: mixedCase })), null);
  assert.ok(!WRITE_ID_PATTERN.test(mixedCase));

  // Boundary: 64 hex all zero — structurally valid; parser must not add an
  // entropy / non-zero check on top of the grammar (accept).
  const allZero = "0".repeat(64);
  assert.equal(parseWriteId(allZero), allZero);
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ writeId: allZero })), null);
});

test("base_revision length and case boundaries on patch", () => {
  // Boundary: exactly 64 lowercase hex (accept).
  assert.notEqual(
    parseWriteOpEnvelopeJson(patchEnvelope({ baseRevision: VALID_REVISION })),
    null,
  );

  // Boundary: 64 hex with one uppercase (reject).
  assert.equal(
    parseWriteOpEnvelopeJson(patchEnvelope({ baseRevision: "A" + "b".repeat(63) })),
    null,
  );

  // Boundary: 63 chars — too short (reject).
  assert.equal(
    parseWriteOpEnvelopeJson(patchEnvelope({ baseRevision: "b".repeat(63) })),
    null,
  );

  // Boundary: 65 chars — too long (reject).
  assert.equal(
    parseWriteOpEnvelopeJson(patchEnvelope({ baseRevision: "b".repeat(65) })),
    null,
  );
});

test("account_epoch numeric and canonical-form boundaries", () => {
  // Boundary: 0 is the inclusive floor (accept).
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "0" })), null);

  // Boundary: -1 is below the floor (reject) — also covered by the conformance
  // corpus; pinned here so this file stands alone.
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "-1" })), null);

  // Boundary: Number.MAX_SAFE_INTEGER (9007199254740991) — still a safe integer (accept).
  assert.equal(Number.MAX_SAFE_INTEGER, 9007199254740991);
  assert.notEqual(
    parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "9007199254740991" })),
    null,
  );

  // Boundary: MAX_SAFE_INTEGER+1 (9007199254740992) — no longer a safe integer (reject).
  assert.equal(
    parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "9007199254740992" })),
    null,
  );

  // Boundary: non-integer float (reject).
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "7.5" })), null);

  // Boundary: JSON literal `7.0`. JSON.parse yields the number 7, but
  // JSON.stringify(7) is `"7"`, not `"7.0"`. parseCanonicalJson requires the
  // request body to equal that compact round-trip, so the non-canonical
  // spelling is refused even though 7.0 === 7 numerically.
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "7.0" })), null);
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "7" })), null);

  // Boundary: JSON literal `1e2`. Parses to 100; stringifies as `"100"`. Same
  // canonical-form refusal as `7.0` — scientific notation is not the wire form.
  assert.equal(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "1e2" })), null);
  assert.notEqual(parseWriteOpEnvelopeJson(patchEnvelope({ accountEpochRaw: "100" })), null);
});

test("envelope JSON code-unit budget at MAX_WRITE_ENVELOPE_JSON_CODE_UNITS", () => {
  // Boundary: one padded string in the patch field-bag so `.length` controls
  // the serialized size precisely (no multi-key loops).
  const prefix =
    `{"write_id":${JSON.stringify(VALID_WRITE_ID)},"account_epoch":0,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"x","patch":{"p":"`;
  const suffix = '"}}}';
  const padLength = MAX_WRITE_ENVELOPE_JSON_CODE_UNITS - prefix.length - suffix.length;
  assert.ok(padLength > 0, "fixture overhead must leave room for a pad");

  // Boundary: serialized length exactly at the limit (accept).
  const atLimit = prefix + "a".repeat(padLength) + suffix;
  assert.equal(atLimit.length, MAX_WRITE_ENVELOPE_JSON_CODE_UNITS);
  const accepted = parseWriteOpEnvelopeJson(atLimit);
  assert.notEqual(accepted, null);
  assert.equal(isTrustedWriteOpEnvelope(accepted), true);

  // Boundary: one code unit over the limit (reject).
  const overByOne = prefix + "a".repeat(padLength + 1) + suffix;
  assert.equal(overByOne.length, MAX_WRITE_ENVELOPE_JSON_CODE_UNITS + 1);
  assert.equal(parseWriteOpEnvelopeJson(overByOne), null);
});

test("mintWriteId entropy length and hex mapping boundaries", () => {
  assert.equal(WRITE_ID_ENTROPY_BYTES, 32);

  // Boundary: 32 zero bytes → 64-char all-zero write id (sibling convention).
  assert.equal(mintWriteId(new Uint8Array(32)), "00".repeat(32));

  // Boundary: wrong entropy length returns null (does not silently shrink/grow).
  assert.equal(mintWriteId(new Uint8Array(31)), null);
  assert.equal(mintWriteId(new Uint8Array(33)), null);

  // Boundary: every byte 255 → lowercase "f" × 64.
  assert.equal(mintWriteId(new Uint8Array(32).fill(255)), "f".repeat(64));
});
