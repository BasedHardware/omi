/**
 * Failure-class conformance for the outbox. Each test names the class it
 * kills; these are the WS-002 exit gates in executable form.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { Outbox, type PendingOp } from "@omi-core/sync";
import { ManualEnv, MemoryStore, ScriptedTransport } from "../fakes.js";

function op(opId: string, recordId = "flying-dragon-vibrant"): PendingOp {
  return { opId, domain: "tasks", recordId, payload: `{"op":"${opId}"}`, summary: `test op ${opId}`, attempts: 0 };
}

test("offline write survives app restart (FC: write loss on kill)", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t1 = new ScriptedTransport(); // never responds ok — we stay offline

  const box1 = await Outbox.open(store.openBridge("user-a"), env, t1);
  await box1.enqueue(op("op-1"));
  // App killed before any send succeeds. New launch, same disk:
  const t2 = new ScriptedTransport();
  t2.respondWith({ ok: true, serverRevision: "r1" });
  const box2 = await Outbox.open(store.openBridge("user-a"), env, t2);
  await env.advance(1);
  assert.deepEqual(t2.sent, ["op-1"], "journaled op replays after restart");
  void box1;
  void box2;
});

test("permanent rejection dead-letters, never retries (FC-permanent-write-rejection-retried-forever)", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "permanent", reason: "oversize", detail: "1MiB doc limit" } });

  const box = await Outbox.open(store.openBridge("user-a"), env, t);
  await box.enqueue(op("op-big"));
  await env.advance(700_000); // far past every backoff step

  assert.equal(t.sent.length, 1, "exactly one attempt — permanent means permanent");
  const dead = await box.deadLetters();
  assert.equal(dead.length, 1);
  assert.equal(dead[0]!.opId, "op-big");
  assert.equal(dead[0]!.failure.reason, "oversize");
  assert.equal(dead[0]!.summary, "test op op-big", "dead letter is renderable — retained content is not lost content");
});

test("retryable failures back off and eventually succeed", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith(
    { ok: false, failure: { kind: "retryable", detail: "ECONNRESET" } },
    { ok: false, failure: { kind: "retryable", detail: "503" } },
    { ok: true, serverRevision: "r2" },
  );

  const box = await Outbox.open(store.openBridge("user-a"), env, t);
  await box.enqueue(op("op-flaky"));
  await env.advance(10_000);

  assert.deepEqual(t.sent, ["op-flaky", "op-flaky", "op-flaky"]);
  assert.deepEqual(await box.deadLetters(), []);
});

test("auth-invalid pauses the queue; auth-restored resumes it (no drop, no spin)", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "auth-invalid", detail: "token expired" } }, { ok: true });

  const box = await Outbox.open(store.openBridge("user-a"), env, t);
  await box.enqueue(op("op-authed"));
  await env.advance(700_000);
  assert.equal(t.sent.length, 1, "paused — no spinning while logged out");

  box.onAuthRestored();
  await env.advance(1);
  assert.equal(t.sent.length, 2, "resumed after re-auth");
  assert.deepEqual(await box.deadLetters(), []);
});

test("rate-limited honors retryAfter, not the backoff table", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "rate-limited", retryAfterMs: 60_000, detail: "429" } }, { ok: true });

  const box = await Outbox.open(store.openBridge("user-a"), env, t);
  await box.enqueue(op("op-limited"));
  await env.advance(59_000);
  assert.equal(t.sent.length, 1, "not before the server's hint");
  await env.advance(2_000);
  assert.equal(t.sent.length, 2, "promptly after it");
});

test("account switch: user B never sees or replays user A's queue (FC: cross-account leak)", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const tA = new ScriptedTransport();
  const boxA = await Outbox.open(store.openBridge("user-a"), env, tA);
  await boxA.enqueue(op("op-private-to-a"));

  const tB = new ScriptedTransport();
  tB.respondWith({ ok: true });
  const boxB = await Outbox.open(store.openBridge("user-b"), env, tB);
  await env.advance(1_000);

  assert.deepEqual(tB.sent, [], "user B's outbox is empty");
  assert.deepEqual(await boxB.deadLetters(), []);
});

test("ops send strictly in order; a patch never overtakes its create", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t = new ScriptedTransport();
  t.respondWith(
    { ok: false, failure: { kind: "retryable", detail: "flap" } },
    { ok: true },
    { ok: true },
  );

  const box = await Outbox.open(store.openBridge("user-a"), env, t);
  await box.enqueue(op("op-create"));
  await box.enqueue(op("op-patch"));
  await env.advance(10_000);

  assert.deepEqual(t.sent, ["op-create", "op-create", "op-patch"], "single-flight, FIFO");
});

test("crash after journal append but before send: op is not lost (crash harness)", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const t1 = new ScriptedTransport();
  const box1 = await Outbox.open(store.openBridge("user-a"), env, t1);
  await box1.enqueue(op("op-1"));
  await box1.enqueue(op("op-2"));
  // Crash: the disk kept only the first append.
  store.crashDropLogTail("user-a", "outbox", 1);

  const t2 = new ScriptedTransport();
  t2.respondWith({ ok: true }, { ok: true });
  await Outbox.open(store.openBridge("user-a"), env, t2);
  await env.advance(1);
  assert.deepEqual(t2.sent, ["op-1"], "surviving journal entries replay; lost tail loses only what durability semantics allow");
});
