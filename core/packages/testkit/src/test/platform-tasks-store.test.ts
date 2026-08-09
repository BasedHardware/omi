/**
 * The platform generation's task read STORE, and the parked flip.
 *
 * Two things are pinned here, and the second is the one a future reader will be
 * glad of:
 *
 *  1. The store's honesty rules — coverage never restored from cache, coverage
 *     dropped on a failed read, a narrower cache discarded wholesale.
 *  2. THAT `openTasks()` IS STILL LEGACY. Fable pre-ruled the flip PARKED for
 *     this run (R7) and said it stays legacy at wake REGARDLESS of what the
 *     fixture evidence shows. A ruling that lives only in a document is a ruling
 *     the next lane can undo by accident at 4am; this test makes undoing it a
 *     red suite and a deliberate act.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import { PlatformTasksStore } from "@omi-core/domain";
import { readRatifiedCorpus } from "../ratified-fixtures.js";
import { ManualEnv, MemoryStore } from "../fakes.js";

interface TasksCorpusRow {
  readonly wireCase: string;
  readonly safe: boolean;
  readonly page: unknown;
}

const pageFor = (wireCase: string): unknown => {
  const rows = readRatifiedCorpus("tasks-read-conformance") as readonly TasksCorpusRow[];
  const row = rows.find((entry) => entry.wireCase === wireCase);
  assert.ok(row, `corpus row ${wireCase} is missing`);
  return structuredClone(row.page);
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

const env = new ManualEnv();
/** A fresh bridge over the SAME disk = a relaunch of the same app. */
const disk = (): MemoryStore => new MemoryStore();

test("coverage is unknown until an honest page is read, and is never restored from cache", async () => {
  // The rule matters more for tasks than for memories: a page can be
  // `incomplete` for `pending_writes` — an op the write path applied that this
  // projection has not caught up with — so a restored `complete` could hide the
  // user's own most recent edit and report the set as whole.
  //
  // red-proof: restore `coverageState` from the cache in `open()` -> red here.
  // APPLIED AND OBSERVED RED.
  const store = disk();
  const first = await PlatformTasksStore.open(
    store.openBridge("u1"), env, new Scripted([ok(pageFor("window:complete_terminal"))]));
  assert.equal(first.coverage().kind, "unknown", "a store with no read has no coverage claim");
  await first.refresh();
  assert.equal(first.coverage().kind, "known");

  // Reopen over the SAME bridge: the items come back, the claim does not.
  const reopened = await PlatformTasksStore.open(store.openBridge("u1"), env, new Scripted([]));
  assert.equal((await reopened.list()).length, 1, "cached items must survive a reopen");
  assert.equal(reopened.coverage().kind, "unknown", "a persisted coverage claim is not evidence about today");
});

test("a failed read drops the coverage claim but keeps the cached items", async () => {
  // Never leave a stale `complete` on screen. The items are still real; the
  // claim about how much of the set they are is not.
  //
  // red-proof: leave `coverageState` untouched on the non-page branch of
  // `refresh` -> red here. APPLIED AND OBSERVED RED.
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, new Scripted([
    ok(pageFor("window:complete_terminal")),
    { status: 503, json: null },
  ]));
  await store.refresh();
  assert.equal(store.coverage().kind, "known");
  await store.refresh();
  assert.equal(store.coverage().kind, "unknown");
  assert.equal((await store.list()).length, 1, "a failed refresh must not blank the list");
});

test("a cache missing any of the thirteen is discarded wholesale, not partially trusted", async () => {
  // A narrower row rendered beside a full one is exactly the visible difference
  // D2's parity exists to prevent, so a cache that cannot produce the full
  // record class is dropped rather than salvaged.
  //
  // red-proof: check only `id` in readCachedItems -> red here.
  // APPLIED AND OBSERVED RED.
  const bridge = disk().openBridge("u1");
  const kv = await bridge.openKv("platform-tasks");
  await kv.set("items", JSON.stringify([{ id: "task1_x", description: "narrow row" }]));
  const store = await PlatformTasksStore.open(bridge, env, new Scripted([]));
  assert.deepEqual(await store.list(), [], "a narrower cached row must not reach a surface");
  assert.equal(store.coverage().kind, "unknown");
});

test("loadMore appends and keeps the FIRST occurrence of a repeated id", async () => {
  // Deliberately the opposite answer from `walkPlatformTaskPages`, which refuses
  // a duplicate-bearing walk outright. A walk's product is a SET and a set
  // licenses deleting local rows, so an unreliable one must produce no answer.
  // Nothing is deleted here — this is incremental display — and refusing to
  // render would lose a user their working list over a server hiccup.
  const first = pageFor("window:more_continuation") as { items: { id: string }[] };
  const second = pageFor("window:complete_terminal") as { items: { id: string }[] };
  // Same id on both pages: the broken-keyset case.
  second.items[0]!.id = first.items[0]!.id;
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, new Scripted([ok(first), ok(second)]));
  await store.refresh();
  assert.equal(store.hasMore(), true);
  await store.loadMore();
  assert.equal((await store.list()).length, 1, "a repeated id must not double a row");
  assert.equal(store.hasMore(), false);
});

// THE FLIP PIN IS NOT HERE, and that is a real constraint rather than an
// omission. `createPlatformProductionStoreFactory` lives in
// `@omi-core/surfaces`, which compiles to a Vite bundle and has no unit-test
// seam of its own — the same reason its own header gives for why the generation
// SELECTOR lives in `@omi-core/domain` instead. Adding a testkit dependency on
// it to reach one function would drag a bundle into the unit suite.
//
// So R7's parked flip is pinned by `core/scripts/check-openTasks-parked.mjs`,
// which is a STATIC TRIPWIRE and is labelled as one there. It is weaker than a
// behavioural assertion and it is the strongest thing available at this seam.
