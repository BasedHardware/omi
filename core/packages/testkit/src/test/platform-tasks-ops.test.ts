/**
 * THE PLATFORM TASKS WRITE CLIENT, end to end on the client side.
 *
 * Every test here drives the REAL outbox, the REAL stamp source and the REAL
 * op-sender over a scripted HTTP boundary — no re-implementation of envelope
 * building or response classification, because a test that re-types the wire
 * tests the author's memory of it.
 *
 * The sharpest assertion in the file is the last group's: after a stale-epoch
 * refusal, **that write id never leaves the client again, through any path**.
 * David's signed copy asks the person to re-apply the edit themselves, and the
 * mechanism underneath is that the dead envelope carries a superseded epoch
 * which the fence refuses forever. A "Try again" affordance — or a replay the
 * journal forgot to tombstone — would resubmit it and fail silently for as long
 * as anyone kept pressing. That is what these tests are here to make loud.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createDevAccountEpochProvider,
  createPlatformWriteStamps,
  platformTasksTransport,
  taskOpToWriteOp,
} from "@omi-core/adapters-platform";
import { parseRecordId, type HttpResponse, type RecordId, type TaskOp } from "@omi-core/contracts";
import { WRITE_ID_PATTERN, WRITE_AVAILABILITY, WRITE_ERRORS, WRITE_REFUSALS } from "@omi-core/ratified-contracts/write/ops";
import { Outbox, WriteStampUnavailableError, type PendingOp } from "@omi-core/sync";

import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

const RECORD: RecordId = parseRecordId("flying-dragon-vibrant")!.id;

function patchOp(opId: string, description = "buy milk"): PendingOp {
  const domainOp: TaskOp = { op: "patch", opId, id: RECORD, at: 1_000, patch: { description } };
  return {
    opId,
    domain: "tasks",
    recordId: RECORD,
    payload: JSON.stringify(domainOp),
    summary: `Edit task ${RECORD}: description`,
    attempts: 0,
  };
}

/** Distinct 32-byte reads, so two ops can never collide by accident. */
function countingEntropy(start = 1): () => Uint8Array {
  let n = start;
  return () => new Uint8Array(32).fill(n++ & 0xff);
}

const body = (text: string, status: number): HttpResponse => ({ status, json: JSON.parse(text) as unknown, text });

const accepted = (revision: string | null): HttpResponse =>
  body(JSON.stringify({ applied: { record_id: RECORD, revision }, idempotent: false }), 200);

const staleEpoch = (): HttpResponse => body(WRITE_REFUSALS.stale_epoch.body, WRITE_REFUSALS.stale_epoch.status);

interface Harness {
  readonly store: MemoryStore;
  readonly env: ManualEnv;
  readonly http: ScriptedHttp;
  readonly controlRefreshes: string[];
  open(epoch: number | null, entropyStart?: number): Promise<Outbox>;
}

function harness(): Harness {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const controlRefreshes: string[] = [];
  const transport = platformTasksTransport({
    http,
    onControlUnavailable: (op) => controlRefreshes.push(op.opId),
  });
  return {
    store,
    env,
    http,
    controlRefreshes,
    open: (epoch, entropyStart = 1) =>
      Outbox.open(
        store.openBridge("user-a"),
        env,
        transport,
        "tasks",
        createPlatformWriteStamps({
          entropy: countingEntropy(entropyStart),
          epochs: createDevAccountEpochProvider(epoch),
        }),
      ),
  };
}

const posts = (h: Harness): { path: string; envelope: Record<string, unknown> }[] =>
  h.http.calls
    .filter((call) => call.method === "POST")
    .map((call) => ({ path: call.path, envelope: call.body as Record<string, unknown> }));

/* ── B1: minted at enqueue, journaled with the op, never at send ─────────── */

test("the write id is minted at enqueue, journaled, and put on the wire unchanged", async () => {
  const h = harness();
  h.http.respond(accepted("a".repeat(64)));
  const box = await h.open(7);
  await box.enqueue(patchOp("op-1"));
  await h.env.advance(1);

  const journaled = box.pendingOps();
  assert.equal(journaled.length, 0, "the op confirmed and left the queue");

  const sent = posts(h);
  assert.equal(sent.length, 1);
  assert.equal(sent[0]!.path, "/v1/tasks/ops");
  assert.match(String(sent[0]!.envelope["write_id"]), WRITE_ID_PATTERN);
  assert.equal(sent[0]!.envelope["account_epoch"], 7, "the epoch the op was CREATED under");
  assert.equal(sent[0]!.envelope["domain"], "tasks");
  // red-proof: in outbox.ts `stamp()`, return `op` unchanged instead of the
  // stamped copy. The envelope then has no write_id, the sender reports the op
  // unsendable, and no POST is made at all — this assertion fails.
  // RED-PROOF PENDING.
});

test("two ops never share a write id, and a replay after restart reuses its own", async () => {
  const h = harness();
  const box = await h.open(7);
  await box.enqueue(patchOp("op-1", "first"));
  await box.enqueue(patchOp("op-2", "second"));
  // Nothing responds yet: both stay queued, so we can read the journal's ids
  // off the wire on the retries below rather than from a private field.
  h.http.respond(accepted(null), accepted(null));
  await h.env.advance(700_000);

  const ids = posts(h).map((p) => String(p.envelope["write_id"]));
  assert.equal(ids.length, 2);
  assert.notEqual(ids[0], ids[1], "independent entropy per op — never derived from opId");

  // App restart on the same disk. The journal replays, and B1's whole point is
  // that the replay carries the SAME id so the registry recognises it.
  const h2 = harness();
  const box2 = await h2.open(7);
  await box2.enqueue(patchOp("op-3", "third"));
  const restarted = await h2.open(7, 99);
  h2.http.respond(accepted(null), accepted(null));
  await h2.env.advance(700_000);
  const replayIds = posts(h2).map((p) => String(p.envelope["write_id"]));
  assert.ok(replayIds.length >= 2, "the op was sent before and after the restart");
  assert.equal(new Set(replayIds).size, 1, "a replay reuses the journaled write id");
  void restarted;
  // red-proof: make `enqueue` re-stamp an already-stamped op (drop the
  // `op.writeId ??` guard) — replays still pass, because a replay does not go
  // through enqueue. Mint inside `sendPlatformTaskOp` instead and this fails
  // with two distinct ids. RED-PROOF PENDING.
});

test("an op that cannot be stamped is never journaled and never acknowledged", async () => {
  const h = harness();
  const box = await h.open(null); // no epoch known yet
  await assert.rejects(() => box.enqueue(patchOp("op-1")), WriteStampUnavailableError);
  assert.equal(box.pendingOps().length, 0, "nothing pending");

  // The durability protocol is journal-then-acknowledge; a refused stamp must
  // leave nothing behind, or a later launch would replay an op the user was
  // told had failed.
  const reopened = await h.open(9);
  assert.equal(reopened.pendingOps().length, 0, "nothing was journaled");
  // red-proof: move the `stamp()` call in enqueue to AFTER `log.append` — the
  // reopened outbox then replays an unstamped op and this fails.
  // RED-PROOF PENDING.
});

/* ── W1: control_unavailable is retryable, never a dead letter ───────────── */

test("control_unavailable refreshes control state, keeps the op, and never dead-letters it", async () => {
  const h = harness();
  h.http.respond(
    body(WRITE_AVAILABILITY.control_unavailable.body, WRITE_AVAILABILITY.control_unavailable.status),
    accepted(null),
  );
  const box = await h.open(7);
  await box.enqueue(patchOp("op-1"));
  await h.env.advance(1);

  assert.deepEqual(h.controlRefreshes, ["op-1"], "the control binding was told, by name");
  assert.deepEqual(await box.deadLetters(), [], "W1: never a dead letter");
  assert.equal(box.pendingOps().length, 1, "the op is still queued");

  await h.env.advance(700_000);
  assert.deepEqual(await box.deadLetters(), [], "still not a dead letter after every backoff step");
  assert.equal(box.pendingOps().length, 0, "it drained once the server could decide");
  // red-proof: map `control_unavailable` onto stale_epoch's permanent arm in
  // sendPlatformTaskOp (return the stale_epoch failure for a 503). The op is
  // then dead-lettered on the first response and both dead-letter assertions
  // fail. RED-PROOF PENDING.
});

/* ── B2: 409 is two outcomes, and the client must not confuse them ───────── */

test("a stale-epoch 409 is permanent/stale_epoch; a conflict 409 stays conflict", async () => {
  const h = harness();
  h.http.respond(staleEpoch());
  const box = await h.open(3);
  await box.enqueue(patchOp("op-stale"));
  await h.env.advance(700_000);
  const dead = await box.deadLetters();
  assert.equal(dead.length, 1);
  assert.equal(dead[0]!.failure.reason, "stale_epoch", "never `conflict`, never `gone` — B2");

  const h2 = harness();
  h2.http.respond(body(WRITE_ERRORS.conflict.body, WRITE_ERRORS.conflict.status));
  const box2 = await h2.open(3);
  await box2.enqueue(patchOp("op-conflict"));
  await h2.env.advance(700_000);
  const dead2 = await box2.deadLetters();
  assert.equal(dead2.length, 1);
  assert.equal(dead2[0]!.failure.reason, "conflict", "a real precondition failure is still a conflict");
  // red-proof: delete the `case "stale_epoch"` arm from
  // classifyWriteOpsResponse — the straggler falls through to classifyStatus,
  // 409 becomes permanent/conflict, and the first assertion fails while the
  // second still passes. RED-PROOF PENDING.
});

test("a write refusal with no raw body is an unclassified gap, never a guessed conflict", async () => {
  const h = harness();
  // A binding that supplies only pre-parsed json. Two outcome classes share
  // 409 and are distinguished by BYTES, so there is nothing here to read.
  h.http.respond({ status: 409, json: { error: "stale_epoch", refusal_outcome: "stale_epoch" } });
  const box = await h.open(3);
  await box.enqueue(patchOp("op-1"));
  await h.env.advance(1);

  assert.deepEqual(await box.deadLetters(), [], "no dead letter on a guess");
  assert.equal(box.pendingOps().length, 1, "the op is kept");
  const gaps = h.env.fallbackSink.records.filter((r) => r.path === "sync.outbox.unclassified-failure");
  assert.equal(gaps.length, 1, "the binding defect is visible, not silent");
  assert.match(gaps[0]!.detail ?? "", /carried no raw body/);
  // red-proof: delete the `response.text === undefined` guard in
  // sendPlatformTaskOp. classifyWriteOpsResponse then falls through to
  // classifyStatus, the 409 becomes permanent/conflict, and the op is
  // dead-lettered — telling a person their edit lost a race that never
  // happened. Both the dead-letter and the gap assertions fail.
  // RED-PROOF PENDING.
});

/* ── THE PIN: a dead envelope is never resubmitted, by any path ──────────── */

test("after a stale-epoch dead letter, that write id never leaves the client again", async () => {
  const h = harness();
  h.http.respond(staleEpoch());
  const box = await h.open(3);
  await box.enqueue(patchOp("op-stale"));
  await h.env.advance(1);

  const firstSend = posts(h);
  assert.equal(firstSend.length, 1);
  const deadWriteId = String(firstSend[0]!.envelope["write_id"]);
  assert.match(deadWriteId, WRITE_ID_PATTERN);

  const dead = await box.deadLetters();
  assert.equal(dead.length, 1, "the refusal produced a dead letter");
  assert.equal(dead[0]!.failure.reason, "stale_epoch");
  assert.equal(
    dead[0]!.payload,
    patchOp("op-stale").payload,
    'the full serialized op is retained — "your edit is saved below" is a promise about this',
  );

  // Everything a surface, a shell, or a restart can do to this outbox. If any
  // of it resubmits the dead envelope, the person is told to re-apply an edit
  // while the client quietly retries one that can never be accepted.
  h.http.respond(accepted(null), accepted(null), accepted(null));
  await h.env.advance(700_000); // every backoff step
  box.onAuthRestored(); // re-auth, the one event that un-pauses a queue
  await h.env.advance(700_000);
  await box.discardDeadLetter("op-stale"); // the only affordance the surface offers
  await h.env.advance(700_000);
  const relaunched = await h.open(9); // app restart, journal replay, newer epoch
  await h.env.advance(700_000);

  const everySend = posts(h);
  assert.equal(
    everySend.filter((p) => p.envelope["write_id"] === deadWriteId).length,
    1,
    "the dead envelope was sent exactly once, ever",
  );
  assert.equal(everySend.length, 1, "and nothing else was sent either");
  assert.equal(relaunched.pendingOps().length, 0, "the tombstone survived the restart");
  // red-proof: in outbox.ts's `interpret`, skip the tombstone append for a
  // `dead` outcome (append it only when the outcome is confirmed). The relaunch
  // then replays the dead op and resends the identical envelope, so the
  // exactly-once assertion fails with 2. RED-PROOF PENDING.
});

/* ── the codec, and what it deliberately does not carry ─────────────────── */

test("the wire op carries the record and the keyed patch, and never the client-private opId", () => {
  const created = taskOpToWriteOp({
    op: "create",
    opId: "quiet-otter-lucid",
    id: RECORD,
    at: 5,
    description: "buy milk",
    source: "user",
  });
  assert.deepEqual(created, { op: "create", record_id: RECORD, content: { description: "buy milk", source: "user" } });

  const patched = taskOpToWriteOp({ op: "patch", opId: "quiet-otter-lucid", id: RECORD, at: 5, patch: { completed: true } });
  assert.deepEqual(patched, { op: "patch", record_id: RECORD, patch: { completed: true } });

  // Absent key means "leave unchanged" — the domain contract's core guarantee,
  // and it survives only if the mapping never fills a field list.
  assert.deepEqual(Object.keys((patched as { patch: Record<string, unknown> }).patch), ["completed"]);

  assert.deepEqual(taskOpToWriteOp({ op: "delete", opId: "x", id: RECORD, at: 5 }), {
    op: "delete",
    record_id: RECORD,
  });
  assert.equal(taskOpToWriteOp({ op: "patch", opId: "x", id: "" as unknown as RecordId, at: 5, patch: {} }), null);
  for (const built of [created, patched]) {
    assert.ok(built !== null && !JSON.stringify(built).includes("quiet-otter-lucid"), "opId never crosses the wire");
  }
  // red-proof: spread `...domainOp` into the create branch instead of naming
  // the fields — `opId` and `at` reach the bag and the last assertion fails.
  // RED-PROOF PENDING.
});

test("the epoch provider ignores regressions and junk, so a reorder cannot manufacture stragglers", () => {
  const epochs = createDevAccountEpochProvider(null);
  assert.equal(epochs.currentAccountEpoch(), null, "unknown is a value, not zero");
  assert.equal(epochs.observeAccountEpoch(4), true);
  assert.equal(epochs.observeAccountEpoch(3), false, "epochs advance; a regression is dropped");
  assert.equal(epochs.currentAccountEpoch(), 4);
  assert.equal(epochs.observeAccountEpoch(5), true);
  assert.equal(epochs.currentAccountEpoch(), 5);
  for (const junk of [-1, 1.5, "6", null, undefined, Number.NaN, Number.MAX_SAFE_INTEGER + 2]) {
    assert.equal(epochs.observeAccountEpoch(junk), false, `rejects ${String(junk)}`);
  }
  assert.equal(epochs.currentAccountEpoch(), 5);
  // red-proof: drop the `value < epoch` guard — observing 3 after 4 then wins,
  // the client stamps ops with an epoch the server has moved past, and every
  // one of them comes back a straggler. RED-PROOF PENDING.
});
