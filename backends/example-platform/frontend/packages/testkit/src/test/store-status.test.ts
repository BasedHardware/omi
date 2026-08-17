import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import { PlatformTasksStore, RefreshTracker, type StoreStatus } from "@omi-core/domain";
import { Outbox, type PendingOp } from "@omi-core/sync";
import { readRatifiedCorpus } from "../ratified-fixtures.js";
import { ManualEnv, MemoryStore } from "../fakes.js";

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

interface TasksCorpusRow {
  readonly wireCase: string;
  readonly page: unknown;
}

const pageFor = (wireCase: string): Record<string, unknown> => {
  const rows = readRatifiedCorpus("tasks-read-conformance") as readonly TasksCorpusRow[];
  const row = rows.find((entry) => entry.wireCase === wireCase);
  assert.ok(row, `corpus row ${wireCase} is missing`);
  return structuredClone(row.page) as Record<string, unknown>;
};

const ok = (page: unknown): HttpResponse => ({ status: 200, json: page, text: JSON.stringify(page) });

class Scripted implements HttpClient {
  constructor(private readonly queue: HttpResponse[]) {}
  async request(): Promise<HttpResponse> {
    const next = this.queue.shift();
    if (!next) throw new Error("unscripted request");
    return next;
  }
}

const withEpoch = (page: Record<string, unknown>, epoch: number): Record<string, unknown> => {
  page["accountEpoch"] = epoch;
  return page;
};

test("platform tasks expose truthful refresh and queue phases", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const empty = withEpoch(pageFor("absence:query_gap"), 7);
  const http = new Scripted([ok(empty)]);
  const store = await PlatformTasksStore.open(disk.openBridge("status-tasks"), env, http);
  const notifications: StoreStatus[] = [];
  store.subscribe(() => notifications.push(store.status()));

  assert.deepEqual(refresh(store.status()), { phase: "initial-loading", hasSavedData: false });

  const firstRefresh = store.refresh();
  assert.equal(refresh(store.status()).phase, "initial-loading", "first refresh is still loading before its await settles");
  await firstRefresh;
  assert.deepEqual(refresh(store.status()), { phase: "ready", hasSavedData: false });
  assert.equal(notifications.length, 2, "refresh notifies at begin and end");

  const failed = new Scripted([{ status: 503, json: null }]);
  const failedStore = await PlatformTasksStore.open(disk.openBridge("status-tasks-fail"), env, failed);
  await failedStore.refresh();
  assert.deepEqual(refresh(failedStore.status()), { phase: "unavailable", hasSavedData: false });
});

test("reopened platform tasks carry durable items before their first refresh", async () => {
  const disk = new MemoryStore();
  const firstEnv = new ManualEnv();
  const page = pageFor("window:complete_terminal");
  const firstHttp = new Scripted([ok(page)]);
  const first = await PlatformTasksStore.open(disk.openBridge("status-reopen"), firstEnv, firstHttp);
  await first.refresh();
  assert.equal((await first.list()).length, 1);

  const reopenedEnv = new ManualEnv();
  const reopenedHttp = new Scripted([{ status: 503, json: null }]);
  const reopened = await PlatformTasksStore.open(disk.openBridge("status-reopen"), reopenedEnv, reopenedHttp);
  // red-proof: remove the cached-items seed of RefreshTracker and the
  // reopened store reports no saved data despite the durable row above.
  assert.deepEqual(refresh(reopened.status()), { phase: "initial-loading", hasSavedData: true });

  const refreshPromise = reopened.refresh();
  assert.deepEqual(refresh(reopened.status()), { phase: "refreshing", hasSavedData: true });
  await refreshPromise;
  assert.deepEqual(refresh(reopened.status()), { phase: "saved-but-refresh-failed", hasSavedData: true });
  assert.equal((await reopened.list()).length, 1);
});

test("pending overlays do not masquerade as durable saved data", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const empty = withEpoch(pageFor("absence:query_gap"), 7);
  const http = new Scripted([
    ok(empty),
    { status: 503, json: null },
    { status: 503, json: null },
  ]);
  const store = await PlatformTasksStore.open(disk.openBridge("status-pending-only"), env, http);
  await store.refresh();
  await store.create("pending only");
  assert.equal((await store.list()).length, 1);
  // red-proof: use list() (which applies pending overlays) for hasSavedData and
  // this failed refresh is incorrectly shown as saved-but-refresh-failed.
  await store.refresh();
  assert.deepEqual(refresh(store.status()), { phase: "unavailable", hasSavedData: false });
  assert.equal((await store.list()).length, 1, "the pending overlay remains visible");
});
