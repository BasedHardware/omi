/**
 * CLIENT-side consumer of the write-ops corpus of record (rule 15).
 *
 * The corpus at `core/contracts/ratified/fixtures/write-ops-conformance.json`
 * is read, not re-authored. That distinction is the whole rule: the spikes
 * that designed this wire hand-authored their counterpart's payloads, which
 * tests the author's memory of the wire rather than the wire, and the memo
 * that recorded them says so outright — "the spikes themselves would not
 * satisfy rule 15".
 *
 * The SERVER-side consumer of the same file is
 * `platform/contract-tests/ratified-contracts.test.ts`, which reads it out of
 * the installed tarball. Two sides, one file, joined by the vendored
 * `sourceDigest`. Neither side can move the wire without the other's test
 * changing colour.
 *
 * The single most important row here is the stale-epoch one. It shares HTTP
 * 409 with `conflict` by design, and a client that branches on status alone
 * reports a straggler to its user as a failed edit that conflicted. That is a
 * false statement about a person's own content, and it is what B2 forbids.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { classifyWriteOpsResponse, buildWriteOpEnvelope, isControlUnavailable } from "@omi-core/adapters-platform";
import type { HttpResponse, WriteFailure } from "@omi-core/contracts";

import { readRatifiedCorpus, readRatifiedWriteOpsSchema } from "../ratified-fixtures.js";

interface WriteOpsCase {
  readonly name: string;
  readonly wireOutcome: string;
  readonly path: string;
  readonly requestBody: string;
  readonly envelopeAccepted: boolean;
  readonly response: { readonly status: number; readonly body: string };
  readonly clientFailure: Partial<WriteFailure> | null;
}

const corpus = readRatifiedCorpus("write-ops-conformance") as readonly WriteOpsCase[];

const asResponse = (row: WriteOpsCase): HttpResponse => ({
  status: row.response.status,
  json: JSON.parse(row.response.body) as unknown,
  text: row.response.body,
});

test("the corpus is loaded and non-empty", () => {
  // A missing or emptied corpus must never read as a pass — every assertion
  // below is inside a loop, and an empty loop is green.
  assert.ok(corpus.length >= 16, `write-ops corpus has ${corpus.length} rows`);
});

test("every corpus row classifies to exactly the failure the corpus declares", () => {
  // red-proof: in `classifyWriteOpsResponse`, delete the `case "stale_epoch"`
  // arm so the straggler falls through to `classifyStatus`. It then classifies
  // as permanent/conflict and this test goes red on that row.
  // APPLIED AND OBSERVED RED.
  let checked = 0;
  for (const row of corpus) {
    const actual = classifyWriteOpsResponse(asResponse(row), "corpus");
    if (row.clientFailure === null) {
      assert.equal(actual, null, `${row.name}: a 200 must not classify as a failure`);
      checked += 1;
      continue;
    }
    assert.ok(actual, `${row.name}: expected a classified failure`);
    assert.equal(actual.kind, row.clientFailure.kind, `${row.name}: kind`);
    if (row.clientFailure.kind === "permanent") {
      assert.equal(
        (actual as Extract<WriteFailure, { kind: "permanent" }>).reason,
        (row.clientFailure as Extract<WriteFailure, { kind: "permanent" }>).reason,
        `${row.name}: reason`,
      );
    }
    checked += 1;
  }
  // Producer-side count vs consumer-side observation: the number of rows the
  // corpus declares and the number this test actually classified must agree.
  // A `continue` that silently skipped a class would otherwise be invisible.
  assert.equal(checked, corpus.length);
});

test("a straggler is never reported to the user as a conflict or as gone", () => {
  // red-proof: same mutation as above; this row is the one that turns red
  // first and is asserted on its own so the failure names the defect.
  // APPLIED AND OBSERVED RED.
  const staleRows = corpus.filter((row) => row.wireOutcome === "stale_epoch");
  assert.ok(staleRows.length >= 1, "the corpus must carry a stale-epoch row");
  for (const row of staleRows) {
    const actual = classifyWriteOpsResponse(asResponse(row), "corpus");
    assert.deepEqual(actual, { kind: "permanent", reason: "stale_epoch", detail: "corpus" }, row.name);
  }
  // And the neighbouring 409s must NOT collapse into it.
  for (const row of corpus.filter((r) => r.wireOutcome === "conflict")) {
    const actual = classifyWriteOpsResponse(asResponse(row), "corpus") as Extract<WriteFailure, { kind: "permanent" }>;
    assert.equal(actual.reason, "conflict", row.name);
  }
});

test("the corpus covers every outcome the schema of record declares", () => {
  // red-proof: remove the stale_epoch row from the corpus JSON and this goes
  // red. APPLIED AND OBSERVED RED. This duplicates the mechanical check in
  // `scripts/check-wire-conformance.mjs` on purpose: that script proves the
  // corpus covers the schema, this proves the SUITE saw the coverage. A
  // registry row nobody executes is the failure rule 15 exists to catch.
  const declared = readRatifiedWriteOpsSchema().outcomes.map((row) => row.outcome);
  const covered = new Set(corpus.map((row) => row.wireOutcome));
  for (const outcome of declared) {
    assert.ok(covered.has(outcome), `no corpus row exercises the "${outcome}" outcome`);
  }
});

test("an op with no journaled write_id cannot be sent, and is never minted at send time", () => {
  // red-proof: make `buildWriteOpEnvelope` mint a fallback id when `writeId`
  // is undefined and this goes red. APPLIED AND OBSERVED RED.
  //
  // B1's failure mode is silent: a send-time mint yields a different id on
  // every replay, the server's registry never recognises the retry, and a
  // crash-replayed op applies twice. Nothing about that is visible from either
  // side at runtime, so it is pinned structurally here instead.
  const op = { op: "patch", record_id: "task-9f21", patch: { done: true } } as const;
  const built = buildWriteOpEnvelope({ domain: "tasks", op }, 7);
  assert.equal(built.ok, false);
  assert.deepEqual(built.ok === false ? built.failure : null, { reason: "no-journaled-write-id" });

  const withId = buildWriteOpEnvelope({ domain: "tasks", writeId: "a".repeat(64), op }, 7);
  assert.equal(withId.ok, true);
  assert.equal(withId.ok === true ? withId.path : null, "/v1/tasks/ops");
  assert.equal(withId.ok === true ? withId.envelope.write_id : null, "a".repeat(64));

  // The client-private word slug can never become the wire key, even by
  // accident: it does not satisfy the grammar.
  const slug = buildWriteOpEnvelope({ domain: "tasks", writeId: "edit-task-9f21-set-done", op }, 7);
  assert.equal(slug.ok, false);
  assert.deepEqual(slug.ok === false ? slug.failure : null, { reason: "malformed-write-id" });

  // Memories is read-only by ratified design; the adapter refuses rather than
  // letting the server be the only thing that says no.
  const readOnly = buildWriteOpEnvelope({ domain: "memories", writeId: "b".repeat(64), op }, 7);
  assert.equal(readOnly.ok, false);
});

test("no word slug appears anywhere in a serialized envelope", () => {
  // backend:RISK-015, asserted over the bytes rather than over the type.
  for (const row of corpus.filter((r) => r.envelopeAccepted)) {
    const parsed = JSON.parse(row.requestBody) as { write_id: string };
    assert.match(parsed.write_id, /^[0-9a-f]{64}$/, row.name);
    assert.ok(!row.requestBody.includes("opId"), `${row.name}: opId must stay client-private`);
    assert.ok(!row.requestBody.includes("op_id"), `${row.name}: opId must stay client-private`);
  }
});

test("control_unavailable keeps the op queued AND tells the binding to refresh control state", () => {
  // COORD-fable-rulings-wave2 W1. Two assertions, because the taxonomy answer
  // alone is not the whole obligation: `retryable` is right (never a dead
  // letter), and it is also indistinguishable from a plain 503, which after a
  // rollback means retrying in place against a platform that can never accept.
  //
  // red-proof: make `isControlUnavailable` return false unconditionally and this
  // goes red. APPLIED AND OBSERVED RED.
  // red-proof: classify control_unavailable as permanent/stale_epoch — the
  // collapse the ruling names as the expensive one — and the first assertion
  // goes red. APPLIED AND OBSERVED RED.
  const rows = corpus.filter((row) => row.wireOutcome === "control_unavailable");
  assert.ok(rows.length >= 1, "the corpus must carry a control_unavailable row");
  for (const row of rows) {
    const response = asResponse(row);
    assert.deepEqual(classifyWriteOpsResponse(response, "corpus"), { kind: "retryable", detail: "corpus" }, row.name);
    assert.equal(isControlUnavailable(response), true, row.name);
  }
  // And nothing else on this wire may read as control-unavailable — most
  // importantly not stale_epoch, which the client dead-letters permanently.
  for (const row of corpus.filter((entry) => entry.wireOutcome !== "control_unavailable")) {
    assert.equal(isControlUnavailable(asResponse(row)), false, row.name);
  }
});
