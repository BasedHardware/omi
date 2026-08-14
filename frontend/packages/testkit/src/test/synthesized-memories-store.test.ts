/**
 * The platform generation's read store.
 *
 * The load-bearing tests here are about what SURVIVES and what does not:
 * cached items survive a reopen so an offline cold start still shows
 * something; the recall claim does NOT, because coverage is a statement about
 * the server at the moment it was made.
 *
 * Hermetic: MemoryStore + ManualEnv + scripted responses. No network, no clock.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse, StorageBridge } from "@omi-core/contracts";
import { SynthesizedMemoriesStore } from "@omi-core/domain";
import { ManualEnv, MemoryStore } from "../fakes.js";

const DECLARED = "frontier-v1:declared";
const STM = "frontier-v1:included";

function completeness(status: "complete" | "degraded"): unknown {
  return {
    version: "recall-completeness-v1",
    status,
    reasons: status === "complete" ? [] : ["projection_stale"],
    frontiers: {
      declaredFrontier: DECLARED,
      newestSearchedAcceptedFrontier: DECLARED,
      missingAcceptedFrontierReason: null,
      newestSearchedStmFrontier: STM,
      missingStmFrontierReason: null,
    },
  };
}

function page(opts: {
  texts: readonly string[];
  more?: string | null;
  status?: "complete" | "degraded";
}): unknown {
  const cursor = opts.more ?? null;
  return {
    contractVersion: "1.0.0",
    items: opts.texts.map((text, i) => ({ id: `retrieval-node-v1:${text}-${i}`, text })),
    window:
      cursor === null
        ? { status: "complete", complete: true, hasMore: false, nextCursor: null }
        : { status: "more", complete: false, hasMore: true, nextCursor: cursor },
    completeness: completeness(opts.status ?? "complete"),
    absence: null,
  };
}

function ok(body: unknown): HttpResponse {
  return { status: 200, json: body, text: JSON.stringify(body) };
}

class Scripted implements HttpClient {
  readonly paths: string[] = [];
  constructor(private readonly queue: HttpResponse[]) {}
  async request(_m: string, path: string): Promise<HttpResponse> {
    this.paths.push(path);
    return this.queue.shift() ?? { status: 503, json: null };
  }
}

/** A fresh device disk. Reopening a bridge off the SAME disk is an app relaunch. */
function newDisk(): MemoryStore {
  return new MemoryStore();
}

function launch(disk: MemoryStore): StorageBridge {
  return disk.openBridge("uid-fe-core");
}

test("a fresh store is UNKNOWN before it has read anything", async () => {
  const store = await SynthesizedMemoriesStore.open(launch(newDisk()), new ManualEnv(), new Scripted([]));
  assert.deepEqual(store.recall(), { kind: "unknown" });
  assert.deepEqual(await store.list(), []);
  assert.equal(store.hasMore(), false);
  assert.equal(store.status().queue.phase, "idle", "a read model reports an idle queue, not an absent one");
  assert.equal(store.status().queue.pendingCount, 0);
});

test("cached items survive a reopen but the completeness claim does NOT", async () => {
  // red-proof: persist `recallState` alongside the items in `refresh()` and
  // restore it in `open()`. The reopened store then reports
  // `{ kind: "known", complete: true }` from a cold start, telling the user
  // "that is everything" about a set this process has never looked at.
  // APPLIED 2026-08-08: observed
  //   AssertionError: a persisted coverage claim is not evidence about today
  //   'known' !== 'unknown'
  const disk = newDisk();
  const env = new ManualEnv();

  const first = await SynthesizedMemoriesStore.open(
    launch(disk),
    env,
    new Scripted([ok(page({ texts: ["alpha", "beta"] }))]),
  );
  await first.refresh();
  const loaded = await first.list();
  assert.deepEqual(loaded.map((i) => i.text), ["alpha", "beta"]);
  assert.equal(first.recall().kind, "known");

  // Reopen against a transport that answers nothing — a cold, offline start.
  const reopened = await SynthesizedMemoriesStore.open(launch(disk), env, new Scripted([]));
  assert.deepEqual(
    (await reopened.list()).map((i) => i.text),
    ["alpha", "beta"],
    "the cache still serves, which is the whole point of persisting it",
  );
  assert.equal(reopened.status().refresh.hasSavedData, true);
  assert.equal(
    reopened.recall().kind,
    "unknown",
    "a persisted coverage claim is not evidence about today",
  );
});

test("a failed refresh keeps the cached items but drops the recall claim", async () => {
  // red-proof: in the `outcome.kind !== "page"` branch of `refresh()`, remove
  // the `this.recallState = { kind: "unknown" }` line. A stale `complete` then
  // stays on screen across a failed refresh.
  // APPLIED 2026-08-08: observed  'known' !== 'unknown'
  const disk = newDisk();
  const env = new ManualEnv();
  const http = new Scripted([ok(page({ texts: ["alpha"] })), { status: 503, json: null }]);
  const store = await SynthesizedMemoriesStore.open(launch(disk), env, http);

  await store.refresh();
  assert.equal(store.recall().kind, "known");

  await store.refresh();
  assert.deepEqual((await store.list()).map((i) => i.text), ["alpha"], "offline reads keep serving");
  assert.equal(store.recall().kind, "unknown", "but we no longer claim to know the coverage");
  assert.equal(store.status().refresh.phase, "saved-but-refresh-failed");
  assert.equal(store.status().refresh.hasSavedData, true);
});

test("loadMore appends the next keyset page in server order and stops at the terminal one", async () => {
  // red-proof: change the append in `loadMore` to
  // `[...synthesizedMemoryItemsFromPage(outcome.page), ...this.items]`; the
  // asserted text sequence reverses. Asserting only `length === 3` would miss
  // it entirely — that is the decorative shape rule 14 names.
  // APPLIED 2026-08-08: observed
  //   [ 'gamma', 'alpha', 'beta' ] deepEqual [ 'alpha', 'beta', 'gamma' ]
  const http = new Scripted([
    ok(page({ texts: ["alpha", "beta"], more: "cursor-1" })),
    ok(page({ texts: ["gamma"] })),
  ]);
  const store = await SynthesizedMemoriesStore.open(launch(newDisk()), new ManualEnv(), http);

  await store.refresh();
  assert.equal(store.hasMore(), true);
  assert.deepEqual((await store.list()).map((i) => i.text), ["alpha", "beta"]);

  await store.loadMore();
  assert.deepEqual((await store.list()).map((i) => i.text), ["alpha", "beta", "gamma"]);
  assert.equal(store.hasMore(), false);

  // A further call is a no-op, so a surface may call it on every scroll event.
  await store.loadMore();
  assert.equal(http.paths.length, 2, "no request is issued without a cursor");
  assert.deepEqual(http.paths, [
    "/v1/memories?limit=100",
    "/v1/memories?limit=100&cursor=cursor-1",
  ]);
});

test("a degraded page is reported as degraded, not smoothed into complete", async () => {
  // red-proof: in the adapter's `synthesizedRecallStateFromPage`, set
  // `complete: page.window.complete`. This page's window terminated, so the
  // store would report complete:true for a projection the server called stale.
  // APPLIED 2026-08-08: observed  true !== false
  const store = await SynthesizedMemoriesStore.open(
    launch(newDisk()),
    new ManualEnv(),
    new Scripted([ok(page({ texts: ["alpha"], status: "degraded" }))]),
  );
  await store.refresh();
  const recall = store.recall();
  assert.equal(recall.kind, "known");
  if (recall.kind !== "known") return;
  assert.equal(recall.status, "degraded");
  assert.equal(recall.complete, false);
  assert.deepEqual(recall.reasons, ["projection_stale"]);
});

test("a corrupt cache is treated as no cache, never salvaged row by row", async () => {
  // red-proof: change `readCachedItems` to `continue` past a bad row instead of
  // returning []. The store then shows the one good row out of a damaged blob
  // — items on screen that no server ever sent as a set.
  // APPLIED 2026-08-08: observed  1 !== 0
  const disk = newDisk();
  const bridge = launch(disk);
  const kv = await bridge.openKv("synthesized-memories");
  await kv.set("items", JSON.stringify([{ id: "retrieval-node-v1:good", text: "good" }, { id: 7 }]));

  const store = await SynthesizedMemoriesStore.open(launch(disk), new ManualEnv(), new Scripted([]));
  assert.deepEqual(await store.list(), [], "a partially readable cache is not a cache");
  assert.equal(store.status().refresh.hasSavedData, false);
  assert.deepEqual(store.recall(), { kind: "unknown" });

  for (const junk of ["not json", "null", '"a string"', "{}", "[3]"]) {
    await kv.set("items", junk);
    const s = await SynthesizedMemoriesStore.open(launch(disk), new ManualEnv(), new Scripted([]));
    assert.deepEqual(await s.list(), [], `cache ${junk} must not load`);
  }
});

test("subscribers are notified on refresh so a surface re-renders", async () => {
  const store = await SynthesizedMemoriesStore.open(
    launch(newDisk()),
    new ManualEnv(),
    new Scripted([ok(page({ texts: ["alpha"] }))]),
  );
  let notifications = 0;
  const unsubscribe = store.subscribe(() => {
    notifications += 1;
  });
  await store.refresh();
  assert.ok(notifications >= 2, "at least the refresh start and its completion");
  unsubscribe();
  const before = notifications;
  await store.refresh();
  assert.equal(notifications, before, "an unsubscribed listener stops being called");
});
