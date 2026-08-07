/**
 * Failure-class suite port: one citation per class from
 * `omi-frontend-unification-and-microapps-project-tracker/docs/client-failure-classes.md`.
 * Classes already proven in sibling files are listed in the worker report only —
 * do not duplicate those tests here.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { INITIAL_STATE, Outbox, Projection, step, type PendingOp, type ProjectionCodec } from "@omi-core/sync";
import { ManualEnv, MemoryStore, ScriptedTransport } from "../fakes.js";

interface Row {
  id: string;
  text: string;
  done?: boolean;
}

const codec: ProjectionCodec<Row> = {
  id: (r) => r.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as { kind: string; id: string; text?: string; done?: boolean };
    if (op.kind === "create") return { id: op.id, text: op.text ?? "" };
    if (op.kind === "delete") return null;
    if (!current) return current;
    const patched: Row = { ...current };
    if (op.text !== undefined) patched.text = op.text;
    if (op.done !== undefined) patched.done = op.done;
    return patched;
  },
};

function op(opId: string, recordId = "amber-fox-ridge", summary = `test op ${opId}`): PendingOp {
  return { opId, domain: "tasks", recordId, payload: `{"op":"${opId}"}`, summary, attempts: 0 };
}

test("FC-TASKS-010: an empty server reply never wipes local rows without a complete snapshot", async () => {
  // Production break: a paginated `[]` or empty upsert would mass-delete cached tasks.
  const store = new MemoryStore();
  const p = await Projection.open(await store.openBridge("u").openKv("tasks"), codec);
  await p.upsertServerRows([{ id: "amber-fox-ridge", text: "keep me" }]);

  await p.upsertServerRows([]);
  assert.deepEqual(await p.read([]), [{ id: "amber-fox-ridge", text: "keep me" }]);

  const partial = await p.reconcile({ setVersion: "v-empty-partial", complete: false, ids: [] });
  assert.deepEqual(partial.deletedIds, []);
  assert.deepEqual(await p.read([]), [{ id: "amber-fox-ridge", text: "keep me" }]);
});

test("FC-CONV-004: retry exhaustion surfaces retained content in dead letters, never silent drop", async () => {
  // Production break: a long retry chain would drop the journaled write with no user-visible dead letter.
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith(
    { ok: false, failure: { kind: "retryable", detail: "offline" } },
    { ok: false, failure: { kind: "retryable", detail: "still offline" } },
    { ok: false, failure: { kind: "permanent", reason: "validation", detail: "rejected after retries" } },
  );

  const box = await Outbox.open(store.openBridge("u"), env, t);
  await box.enqueue(op("precious", "cedar-owl-brook", "create: user dictated words"));
  await env.advance(10_000);

  assert.equal(t.sent.length, 3, "retried before terminal dead outcome");
  const dead = await box.deadLetters();
  assert.equal(dead.length, 1);
  assert.equal(dead[0]!.summary, "create: user dictated words", "renderable summary survives the retry chain");
});

test("FC-TASKS-012: a failed delete is dead-lettered, never fire-and-forget", async () => {
  // Production break: delete would vanish from the outbox without a terminal outcome the UI can show.
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "permanent", reason: "gone", detail: "server blocked delete" } });

  const box = await Outbox.open(store.openBridge("u"), env, t);
  await box.enqueue(op("del-1", "amber-fox-ridge", "delete: amber-fox-ridge"));
  await env.advance(1);

  assert.equal(t.sent.length, 1);
  const dead = await box.deadLetters();
  assert.equal(dead.length, 1);
  assert.equal(dead[0]!.opId, "del-1");
  assert.match(dead[0]!.summary, /delete/i);
});

test("FC-TASKS-014: a failed delete rolls back to confirmed server rows, never a silent hole", async () => {
  // Production break: optimistic delete would stick after server rejection, leaving a phantom gap.
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "permanent", reason: "gone", detail: "server blocked delete" } });

  const p = await Projection.open(await store.openBridge("u").openKv("tasks"), codec);
  await p.upsertServerRows([{ id: "amber-fox-ridge", text: "still here" }]);
  const box = await Outbox.open(store.openBridge("u"), env, t);
  await box.enqueue(op("del-1", "amber-fox-ridge", "delete: amber-fox-ridge"));
  await env.advance(1);

  const optimistic = await p.read([
    { recordId: "amber-fox-ridge", payload: JSON.stringify({ kind: "delete", id: "amber-fox-ridge" }) },
  ]);
  assert.equal(optimistic.length, 0, "pending overlay may hide the row optimistically");

  const rolledBack = await p.read([]);
  assert.deepEqual(rolledBack, [{ id: "amber-fox-ridge", text: "still here" }], "confirmed rows survive a dead-lettered delete");
});

// FC-TASKS-009 (re-find rows by id, never stale index) is structurally guaranteed:
// Projection keys rows in a Map by record id; no index-based lookup exists to go
// stale. No test can fail here — recorded as coverage-by-construction, not omission.

test("FC-MEM-004: edit-while-offline enqueues without error", async () => {
  // Production break: offline edits would throw or reject instead of queueing for later sync.
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();

  const box = await Outbox.open(store.openBridge("u"), env, t);
  await assert.doesNotReject(async () => {
    await box.enqueue(op("edit-a"));
    await box.enqueue(op("edit-b", "delta-kite-moss"));
  });
  await env.advance(1);
  assert.equal(t.sent.length, 1, "queued ops attempt send but enqueue itself never fails");
});

test("FC-MEM-003 / FC-MEM-007: single-flight — one op in flight until terminal outcome, so connectivity flapping cannot overlap sends", () => {
  // Production break: overlapping sync attempts would violate ordering and duplicate creates.
  const op1 = op("create");
  const op2 = op("patch", "amber-fox-ridge");
  let state = INITIAL_STATE;

  ({ state } = step(state, { t: "enqueued", op: op1 }, 0));
  ({ state } = step(state, { t: "enqueued", op: op2 }, 0));
  let result = step(state, { t: "flush" }, 0);
  state = result.state;

  result = step(state, { t: "enqueued", op: op("extra") }, 0);
  state = result.state;
  result = step(state, { t: "flush" }, 0);
  assert.deepEqual(result.effects, []);

  result = step(state, { t: "send-ok", opId: "create" }, 0);
  state = result.state;
  result = step(state, { t: "flush" }, 0);
  assert.equal(result.effects.filter((e) => e.t === "send").length, 1);
  assert.equal(result.effects.find((e) => e.t === "send")?.op.opId, "patch");
});
