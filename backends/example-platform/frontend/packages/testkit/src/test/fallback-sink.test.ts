/**
 * COORD-degradation-is-unobservable: the port is `FallbackSink.record()`
 * (already existed); these tests are for the three things the ruling
 * required BOUND to it — the in-memory adapter reachable from `Env`, the
 * on-disk adapter's durability and cap, and dead-letter backward
 * compatibility for records written before `payload` existed.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { deadLetterPayload, type DeadLetter } from "@omi-core/contracts";
import { degrade } from "@omi-core/kernel";
import { openOnDiskFallbackSink, readOnDiskFallbackRecords, Outbox, type PendingOp } from "@omi-core/sync";
import { ManualEnv, MemoryStore, ScriptedTransport } from "../fakes.js";

/** Drain the microtask queue — `record()`'s append-then-maybe-truncate chain
 * is fire-and-forget from the caller's side, same as every DurableLog write
 * this codebase does not make the caller await. */
async function drainMicrotasks(): Promise<void> {
  for (let i = 0; i < 50; i++) await Promise.resolve();
}

test("the test sink comes from Env: degrade() through env.fallbackSink is inspectable — 'degraded exactly once, reason X'", () => {
  const env = new ManualEnv();
  const degraded = degrade(
    env.fallbackSink,
    { path: "listen.decode.unknown-frame", from: "server", to: "dropped", at: env.now() },
    "fallback-value",
  );
  assert.equal(degraded.value, "fallback-value");
  assert.equal(env.fallbackSink.records.length, 1, "degraded exactly once");
  assert.equal(env.fallbackSink.records[0]!.path, "listen.decode.unknown-frame", "reason X is inspectable");
});

test("teardown is structural: a fresh ManualEnv gets a fresh sink, nothing to forget to clean up", () => {
  const envA = new ManualEnv();
  degrade(envA.fallbackSink, { path: "a.fallback", from: "x", to: "y", at: 0 }, 1);
  const envB = new ManualEnv();
  assert.equal(envA.fallbackSink.records.length, 1);
  assert.equal(envB.fallbackSink.records.length, 0, "a new Env is a new sink — no leakage from the prior test's env");
});

test("on-disk adapter: fallback records survive a simulated relaunch (COORD-degradation-is-unobservable: 'still there in the morning')", async () => {
  const store = new MemoryStore();
  const bridge1 = store.openBridge("user-a");
  const sink1 = await openOnDiskFallbackSink(bridge1);
  sink1.record({ path: "sync.outbox.dead-letter", from: "outbox", to: "dead-letter", detail: "oversize", at: 1 });
  sink1.record({ path: "sync.outbox.auth-paused", from: "outbox", to: "auth-paused", detail: "token expired", at: 2 });
  // Give the fire-and-forget appends inside `record()` a turn to land before
  // "relaunching" — `record()` is synchronous by contract; durability is not
  // instantaneous, same as every other DurableLog write in this codebase.
  await drainMicrotasks();

  // "Relaunch": a fresh bridge handle over the SAME underlying store, exactly
  // how `MemoryStore.openBridge` models an app restart elsewhere in this test
  // suite (see outbox.test.ts's "offline write survives app restart").
  const bridge2 = store.openBridge("user-a");
  const recovered = await readOnDiskFallbackRecords(bridge2);
  assert.equal(recovered.length, 2, "both records are still there after relaunch");
  assert.deepEqual(
    recovered.map((r) => r.path),
    ["sync.outbox.dead-letter", "sync.outbox.auth-paused"],
    "append order preserved",
  );
  // red-proof: comment out the `void log.append(...)` line in
  // openOnDiskFallbackSink's record() (make it a pure in-memory no-op) —
  // this assertion fails because `recovered.length` is 0: nothing survived
  // the fresh bridge handle.
});

test("on-disk adapter: size cap drops the oldest records, not the newest", async () => {
  const store = new MemoryStore();
  const bridge = store.openBridge("user-a");
  const cap = 3;
  const sink = await openOnDiskFallbackSink(bridge, cap);
  for (let i = 0; i < 7; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    // Let each append (and its cap check) resolve before the next, so the
    // cap is enforced incrementally rather than racing — this test is about
    // the *bound*, not about concurrent-append ordering.
    await drainMicrotasks();
  }
  const recovered = await readOnDiskFallbackRecords(bridge);
  assert.ok(recovered.length <= cap, `capped ledger must never exceed ${cap} entries, got ${recovered.length}`);
  assert.equal(recovered.at(-1)?.path, "test.record.6", "the newest record always survives the cap");
  assert.ok(
    !recovered.some((r) => r.path === "test.record.0"),
    "the oldest record is the one the cap drops",
  );
  // red-proof: change the cap check in openOnDiskFallbackSink from `size >
  // cap` to `false` (disable truncation) — this assertion fails because
  // `recovered.length` grows past `cap` and `test.record.0` is still present.
});

test("on-disk adapter: cap=1 keeps only the newest record", async () => {
  const store = new MemoryStore();
  const bridge = store.openBridge("user-a");
  const cap = 1;
  const sink = await openOnDiskFallbackSink(bridge, cap);
  for (let i = 0; i < 4; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    await drainMicrotasks();
  }
  const recovered = await readOnDiskFallbackRecords(bridge);
  assert.equal(recovered.length, 1, "cap=1 must leave exactly one record");
  assert.equal(recovered[0]!.path, "test.record.3", "the sole survivor is always the newest");
  // red-proof: change the cap check from `size > cap` to `size > cap + 1` —
  // the second append no longer truncates, so more than one record survives
  // and the newest-only claim fails.
});

test("on-disk adapter: exactly at the cap does not truncate", async () => {
  const store = new MemoryStore();
  const bridge = store.openBridge("user-a");
  const cap = 5;
  const sink = await openOnDiskFallbackSink(bridge, cap);
  for (let i = 0; i < cap; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    await drainMicrotasks();
  }
  const recovered = await readOnDiskFallbackRecords(bridge);
  assert.equal(recovered.length, cap, "filling exactly to the cap must not drop any records");
  assert.deepEqual(
    recovered.map((r) => r.path),
    ["test.record.0", "test.record.1", "test.record.2", "test.record.3", "test.record.4"],
    "all five records survive in append order when size never exceeds cap",
  );
  // red-proof: change the cap check from `size > cap` to `size >= cap` and the
  // truncate offset from `lsn - cap` to `lsn - (cap - 1)` — the 5th append
  // then truncates and drops the oldest, so `recovered.length` is 4 not 5.
});

test("on-disk adapter: one over the cap drops exactly the single oldest", async () => {
  const store = new MemoryStore();
  const bridge = store.openBridge("user-a");
  const cap = 5;
  const sink = await openOnDiskFallbackSink(bridge, cap);
  for (let i = 0; i < cap + 1; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    await drainMicrotasks();
  }
  const recovered = await readOnDiskFallbackRecords(bridge);
  assert.equal(recovered.length, cap, "one over the cap must leave exactly `cap` records");
  assert.ok(!recovered.some((r) => r.path === "test.record.0"), "the single dropped record is the oldest");
  assert.ok(
    recovered.some((r) => r.path === "test.record.1"),
    "the second-oldest must survive — only one record is dropped",
  );
  assert.equal(recovered.at(-1)?.path, "test.record.5", "the newest record survives");
  // red-proof: change the truncate offset from `lsn - cap` to `lsn - (cap - 1)` —
  // the single overage then drops two oldest instead of one, so length is 4
  // and `test.record.1` is missing too.
});

test("on-disk adapter: cap keeps holding across a second round of appends", async () => {
  const store = new MemoryStore();
  const bridge = store.openBridge("user-a");
  const cap = 3;
  const sink = await openOnDiskFallbackSink(bridge, cap);
  for (let i = 0; i < 5; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    await drainMicrotasks();
  }
  const afterFirst = await readOnDiskFallbackRecords(bridge);
  assert.equal(afterFirst.length, cap, "first wave must already be capped");
  assert.deepEqual(
    afterFirst.map((r) => r.path),
    ["test.record.2", "test.record.3", "test.record.4"],
  );

  for (let i = 5; i < 8; i++) {
    sink.record({ path: `test.record.${i}`, from: "x", to: "y", at: i });
    await drainMicrotasks();
  }
  const afterSecond = await readOnDiskFallbackRecords(bridge);
  assert.equal(afterSecond.length, cap, "second wave must still be capped — not only the first truncation");
  assert.deepEqual(
    afterSecond.map((r) => r.path),
    ["test.record.5", "test.record.6", "test.record.7"],
    "after the second round, only the newest `cap` records remain",
  );
  assert.ok(
    !afterSecond.some((r) => r.path === "test.record.2"),
    "records that survived the first truncation are still subject to later ones",
  );
  // red-proof: change the truncate offset from `lsn - cap` to `size - cap`
  // (tracked count instead of latest LSN) — after the first truncation,
  // surviving entries have LSNs well above `size - cap`, so later truncations
  // stop removing the oldest and the second-round cap fails.
});

function opWithPayload(opId: string, payload: string): PendingOp {
  return { opId, domain: "tasks", recordId: "flying-dragon-vibrant", payload, summary: `test op ${opId}`, attempts: 0 };
}

test("old-shape dead letters (written before `payload` existed) replay without throwing", async () => {
  const store = new MemoryStore();
  const env = new ManualEnv();
  const bridge = store.openBridge("user-a");

  // Seed the dead-letter KV directly in the PRE-payload shape — this is what
  // a real device's journal looks like if it dead-lettered an op before this
  // change shipped. `deadLetters()` must read it back without throwing.
  const oldShapeLetter = {
    opId: "old-op",
    recordId: "flying-dragon-vibrant",
    domain: "tasks",
    summary: "old-shape dead letter, no payload field",
    failure: { kind: "permanent", reason: "validation", detail: "pre-existing" },
    deadAt: 1,
  };
  const kv = await bridge.openKv("outbox-meta-tasks");
  await kv.set("dead-letters", JSON.stringify([oldShapeLetter]));

  const box = await Outbox.open(bridge, env, new ScriptedTransport(), "tasks");
  // The call itself is the assertion: a reader that crashed on the old shape
  // would throw here and fail the test with an uncaught exception, rather
  // than reaching the assertions below.
  const dead = await box.deadLetters();
  assert.equal(dead.length, 1);
  assert.equal(dead[0]!.opId, "old-op");
  assert.equal(dead[0]!.payload, undefined, "genuinely absent, not fabricated");
  assert.equal(deadLetterPayload(dead[0]!), null, "safe accessor reports 'unavailable', does not throw");

  // A NEW dead letter, journaled after this change, sits right next to the
  // old-shape one and DOES carry a reconstructable payload.
  const t = new ScriptedTransport();
  t.respondWith({ ok: false, failure: { kind: "permanent", reason: "oversize", detail: "too big" } });
  const boxLive = await Outbox.open(store.openBridge("user-a"), env, t, "tasks");
  await boxLive.enqueue(opWithPayload("new-op", `{"op":"patch","id":"flying-dragon-vibrant","patch":{"content":"hello"}}`));
  await env.advance(1);
  const both = await boxLive.deadLetters();
  assert.equal(both.length, 2, "old-shape and new-shape dead letters coexist in the same journal");
  const fresh = both.find((d) => d.opId === "new-op")!;
  assert.deepEqual(deadLetterPayload(fresh), { op: "patch", id: "flying-dragon-vibrant", patch: { content: "hello" } });
});

test("deadLetterPayload() never throws, even on malformed payload", () => {
  const malformed: DeadLetter = {
    opId: "x",
    recordId: "flying-dragon-vibrant",
    domain: "tasks",
    summary: "s",
    payload: "{not json",
    failure: { kind: "permanent", reason: "validation", detail: "d" },
    deadAt: 0,
  };
  assert.doesNotThrow(() => deadLetterPayload(malformed));
  assert.equal(deadLetterPayload(malformed), null);
  // red-proof: remove the try/catch inside deadLetterPayload() (keep only the
  // `payload === undefined` guard) — this test then throws a SyntaxError
  // instead of returning null, proving the try/catch (not just the
  // undefined guard) is load-bearing for malformed-but-present payloads.
});
