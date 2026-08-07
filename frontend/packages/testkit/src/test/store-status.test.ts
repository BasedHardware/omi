import assert from "node:assert/strict";
import { test } from "node:test";
import { MemoriesStore, RefreshTracker, TasksStore, type StoreStatus } from "@omi-core/domain";
import { Outbox, type PendingOp } from "@omi-core/sync";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

function refresh(status: StoreStatus): StoreStatus["refresh"] {
  return status.refresh;
}

test("the refresh tracker fences an older overlapping completion", () => {
  const tracker = new RefreshTracker();
  const older = tracker.begin();
  const newer = tracker.begin();

  // red-proof: remove the generation check in RefreshTracker.complete and the
  // older completion overwrites the newer ready state with unavailable.
  assert.equal(tracker.complete(newer, true, true), true);
  assert.equal(tracker.complete(older, false, false), false);
  assert.deepEqual(tracker.snapshot(), { phase: "ready", hasSavedData: true });
});

test("the refresh tracker serializes an older in-flight application before newer data", async () => {
  const tracker = new RefreshTracker();
  const older = tracker.begin();
  let releaseOlder!: () => void;
  let olderStarted!: () => void;
  const olderHeld = new Promise<void>((resolve) => {
    releaseOlder = resolve;
  });
  const started = new Promise<void>((resolve) => {
    olderStarted = resolve;
  });
  let appliedVersion = 0;
  const olderApply = tracker.applyIfCurrent(older, async () => {
    olderStarted();
    await olderHeld;
    appliedVersion = 1;
  });
  await started;

  const newer = tracker.begin();
  const newerApply = tracker.applyIfCurrent(newer, async () => {
    appliedVersion = 2;
  });
  releaseOlder();
  // red-proof: remove the applicationTail predecessor gate and the newer
  // application completes first, allowing stale older data to finish last.
  assert.deepEqual(await Promise.all([olderApply, newerApply]), [true, true]);
  assert.equal(appliedVersion, 2);
});

test("the queue snapshot exposes the in-flight sending phase", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  let resolveSend: ((result: { ok: true }) => void) | null = null;
  const box = await Outbox.open(disk.openBridge("status-sending"), env, {
    send: () => new Promise<{ ok: true }>((resolve) => {
      resolveSend = resolve;
    }),
  }, "tasks");
  const op: PendingOp = {
    opId: "status-op",
    domain: "tasks",
    recordId: "amber-fox-ridge",
    payload: "{}",
    summary: "status test",
    attempts: 0,
  };
  await box.enqueue(op);
  await env.advance(0);
  // red-proof: remove the inFlight branch in Outbox.queueStatus and this
  // content assertion reports queued while the transport is still pending.
  assert.deepEqual(box.queueStatus(), { phase: "sending", pendingCount: 1 });
  resolveSend!({ ok: true });
  await env.advance(0);
  assert.deepEqual(box.queueStatus(), { phase: "idle", pendingCount: 0 });
});

test("tasks expose truthful refresh and queue phases", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await TasksStore.open(disk.openBridge("status-tasks"), env, http);
  const notifications: StoreStatus[] = [];
  store.subscribe(() => notifications.push(store.status()));

  assert.deepEqual(refresh(store.status()), { phase: "initial-loading", hasSavedData: false });

  http.respond({ status: 200, json: { action_items: [] } }, { status: 200, json: { ids: [] } });
  const firstRefresh = store.refresh();
  assert.equal(refresh(store.status()).phase, "initial-loading", "first refresh is still loading before its await settles");
  await firstRefresh;
  assert.deepEqual(refresh(store.status()), { phase: "ready", hasSavedData: false });
  assert.equal(notifications.length, 2, "refresh notifies at begin and end");

  http.respond({ status: 503, json: null }, { status: 503, json: null });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "unavailable", hasSavedData: false });

  http.respond(
    { status: 200, json: { action_items: [{ id: "amber-fox-ridge", description: "saved" }] } },
    { status: 200, json: { ids: ["amber-fox-ridge"] } },
  );
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "ready", hasSavedData: true });

  http.respond({ status: 503, json: null }, { status: 503, json: null });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "saved-but-refresh-failed", hasSavedData: true });
  assert.equal((await store.list()).length, 1, "failed refresh keeps the saved row");

  await store.create("queued task");
  await env.advance(1);
  assert.deepEqual(store.status().queue, { phase: "retrying", pendingCount: 1 });
});

test("reopened tasks carry durable projection evidence before their first refresh", async () => {
  const disk = new MemoryStore();
  const firstEnv = new ManualEnv();
  const firstHttp = new ScriptedHttp();
  const first = await TasksStore.open(disk.openBridge("status-reopen"), firstEnv, firstHttp);

  firstHttp.respond(
    { status: 200, json: { action_items: [{ id: "amber-fox-ridge", description: "saved" }] } },
    { status: 200, json: { ids: ["amber-fox-ridge"] } },
  );
  await first.refresh();

  const reopenedEnv = new ManualEnv();
  const reopenedHttp = new ScriptedHttp();
  const reopened = await TasksStore.open(disk.openBridge("status-reopen"), reopenedEnv, reopenedHttp);
  // red-proof: remove the projection read used to seed RefreshTracker and the
  // reopened store reports no saved data despite the durable row above.
  assert.deepEqual(refresh(reopened.status()), { phase: "initial-loading", hasSavedData: true });

  reopenedHttp.respond({ status: 503, json: null }, { status: 503, json: null });
  const refreshPromise = reopened.refresh();
  assert.deepEqual(refresh(reopened.status()), { phase: "refreshing", hasSavedData: true });
  await refreshPromise;
  assert.deepEqual(refresh(reopened.status()), { phase: "saved-but-refresh-failed", hasSavedData: true });
  assert.equal((await reopened.list()).length, 1);
});

test("pending overlays do not masquerade as durable saved data", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await TasksStore.open(disk.openBridge("status-pending-only"), env, http);

  await store.create("pending only");
  assert.equal((await store.list()).length, 1);
  // red-proof: use list() (which applies pending overlays) for hasSavedData and
  // this failed refresh is incorrectly shown as saved-but-refresh-failed.
  http.respond({ status: 503, json: null }, { status: 503, json: null });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "unavailable", hasSavedData: false });
  assert.equal((await store.list()).length, 1, "the pending overlay remains visible");
});

test("memories expose truthful refresh and auth queue phases", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await MemoriesStore.open(disk.openBridge("status-memories"), env, http);

  assert.deepEqual(refresh(store.status()), { phase: "initial-loading", hasSavedData: false });

  http.respond({ status: 200, json: [] }, { status: 200, json: [] });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "ready", hasSavedData: false });

  http.respond({ status: 503, json: null }, { status: 503, json: null });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "unavailable", hasSavedData: false });

  http.respond(
    { status: 200, json: [{ id: "amber-fox-ridge", content: "saved", visibility: "private" }] },
    { status: 200, json: [{ id: "amber-fox-ridge" }] },
  );
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "ready", hasSavedData: true });

  http.respond({ status: 503, json: null }, { status: 503, json: null });
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "saved-but-refresh-failed", hasSavedData: true });
  assert.equal((await store.list()).length, 1, "failed refresh keeps the saved memory");

  const authDisk = new MemoryStore();
  const authEnv = new ManualEnv();
  const authHttp = new ScriptedHttp();
  const authStore = await MemoriesStore.open(authDisk.openBridge("status-auth"), authEnv, authHttp);
  authHttp.respond({ status: 401, json: null });
  await authStore.create("needs auth");
  await authEnv.advance(1);
  assert.deepEqual(authStore.status().queue, { phase: "needs-auth", pendingCount: 1 });

  authStore.onAuthRestored();
  assert.deepEqual(authStore.status().queue, { phase: "queued", pendingCount: 1 });
  authHttp.respond({ status: 200, json: { id: "srv-auth" } });
  await authEnv.advance(1);
  assert.deepEqual(authStore.status().queue, { phase: "idle", pendingCount: 0 });
});
