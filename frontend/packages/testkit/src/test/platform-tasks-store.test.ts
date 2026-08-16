/**
 * The platform generation's task store.
 *
 * Two things are pinned here:
 *
 *  1. The store's honesty rules — coverage never restored from cache, coverage
 *     dropped on a failed read, a narrower cache discarded wholesale.
 *  2. Writes use the ratified ops envelope (`POST /v1/tasks/ops`) with
 *     `write_id` idempotency and the account epoch observed from the read.
 *     Completeness stays the server's envelope. Opaque read handles without a
 *     write id are refused rather than upserted.
 *
 * Live Tasks open this store by name (`openPlatformTasks()`). The retired
 * `openTasks()` factory port and R7 (`check-openTasks-parked.mjs`) are gone
 * with the legacy generation.
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
  readonly calls: { method: string; path: string; body?: unknown }[] = [];
  constructor(private readonly queue: HttpResponse[]) {}
  async request(method: string, path: string, body?: unknown): Promise<HttpResponse> {
    this.calls.push(body === undefined ? { method, path } : { method, path, body });
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

test("create/edit/complete go through POST /v1/tasks/ops with write_id, and completeness stays the server's", async () => {
  // red-proof: send create to /v1/action-items instead of /v1/tasks/ops, or
  // derive complete from items.length. APPLIED AND OBSERVED RED.
  const empty = pageFor("absence:query_gap") as Record<string, unknown>;
  empty["accountEpoch"] = 7;
  const revision = "a".repeat(64);
  const opaqueId = "task1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const afterCreate = pageFor("window:complete_terminal") as {
    items: Array<Record<string, unknown>>;
    completeness: { status: string };
    accountEpoch?: number;
  };
  afterCreate.accountEpoch = 7;
  afterCreate.items[0] = {
    ...afterCreate.items[0]!,
    id: opaqueId,
    description: "round-trip task",
    completed: false,
    revision,
  };

  const http = new Scripted([
    ok(empty),
    {
      status: 200,
      json: { applied: { record_id: "placeholder", revision }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "placeholder", revision }, idempotent: false }),
    },
    ok(afterCreate),
    {
      status: 200,
      json: { applied: { record_id: "placeholder", revision: "b".repeat(64) }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "placeholder", revision: "b".repeat(64) }, idempotent: false }),
    },
    {
      status: 200,
      json: { applied: { record_id: "placeholder", revision: "c".repeat(64) }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "placeholder", revision: "c".repeat(64) }, idempotent: false }),
    },
  ]);
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, http);
  await store.refresh();
  const coverage = store.coverage();
  assert.equal(coverage.kind, "known");
  assert.equal(coverage.kind === "known" && coverage.complete, true, "complete is the server's envelope");

  await store.create("round-trip task");
  await env.advance(10);
  const created = await store.list();
  assert.equal(created.length, 1);
  assert.equal(created[0]!.description, "round-trip task");
  const localId = created[0]!.id;
  assert.match(localId, /^[a-z]+(-[a-z]+)+$/);

  const createCall = http.calls.find((call) => call.method === "POST");
  assert.equal(createCall?.path, "/v1/tasks/ops");
  const createEnvelope = createCall?.body as { write_id?: string; account_epoch?: number; domain?: string; op?: { op?: string; record_id?: string } };
  assert.match(String(createEnvelope.write_id), /^[0-9a-f]{64}$/);
  assert.equal(createEnvelope.account_epoch, 7);
  assert.equal(createEnvelope.domain, "tasks");
  assert.equal(createEnvelope.op?.op, "create");
  assert.equal(createEnvelope.op?.record_id, localId);

  await store.refresh();
  const afterRefresh = await store.list();
  assert.equal(afterRefresh.length, 1);
  assert.equal(afterRefresh[0]!.id, localId, "opaque read handle rekeys onto the write id");

  await store.patch(localId, { description: "round-trip edited" });
  await env.advance(10);
  assert.equal((await store.list())[0]!.description, "round-trip edited");

  await store.patch(localId, { completed: true });
  await env.advance(10);
  assert.equal((await store.list())[0]!.completed, true);

  const patches = http.calls.filter((call) => call.method === "POST").slice(1);
  assert.equal(patches.length, 2);
  for (const call of patches) {
    assert.equal(call.path, "/v1/tasks/ops");
    const envelope = call.body as { op?: { op?: string; record_id?: string; patch?: Record<string, unknown> } };
    assert.equal(envelope.op?.op, "patch");
    assert.equal(envelope.op?.record_id, localId, "patch uses the write id, not the opaque handle");
  }
  assert.equal((patches[0]!.body as { op: { patch: { description: string } } }).op.patch.description, "round-trip edited");
  assert.equal((patches[1]!.body as { op: { patch: { completed: boolean } } }).op.patch.completed, true);
});

test("create refuses to journal when the read has not observed an account epoch", async () => {
  // red-proof: a live demo stack omits accountEpoch until control cutover;
  // inventing epoch 0 here would stamp a generation the fence cannot catch.
  const page = pageFor("window:complete_terminal");
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, new Scripted([ok(page)]));
  await store.refresh();
  await assert.rejects(() => store.create("no epoch"), /account-epoch/);
});

test("a second create with the same normalized description does not enqueue while the first is open", async () => {
  // write_id is minted, not derived from content (B1). Same write_id with a
  // different fingerprint is write_id_reuse. Double-tap protection is this
  // coalesce, not a content-keyed registry row.
  const empty = pageFor("absence:query_gap") as Record<string, unknown>;
  empty["accountEpoch"] = 7;
  const revision = "d".repeat(64);
  const http = new Scripted([
    ok(empty),
    {
      status: 200,
      json: { applied: { record_id: "placeholder", revision }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "placeholder", revision }, idempotent: false }),
    },
  ]);
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, http);
  await store.refresh();
  await Promise.all([
    store.create("  Buy   Milk "),
    store.create("buy milk"),
  ]);
  await env.advance(10);
  const listed = await store.list();
  assert.equal(listed.length, 1);
  assert.equal(listed[0]!.description, "  Buy   Milk ");
  assert.equal(http.calls.filter((call) => call.method === "POST").length, 1);
  await store.create("BUY MILK");
  assert.equal((await store.list()).length, 1);
  assert.equal(http.calls.filter((call) => call.method === "POST").length, 1);
});

test("the same description may create again after the open row is completed", async () => {
  const empty = pageFor("absence:query_gap") as Record<string, unknown>;
  empty["accountEpoch"] = 7;
  const http = new Scripted([
    ok(empty),
    {
      status: 200,
      json: { applied: { record_id: "a", revision: "e".repeat(64) }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "a", revision: "e".repeat(64) }, idempotent: false }),
    },
    {
      status: 200,
      json: { applied: { record_id: "a", revision: "f".repeat(64) }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "a", revision: "f".repeat(64) }, idempotent: false }),
    },
    {
      status: 200,
      json: { applied: { record_id: "b", revision: "g".repeat(64) }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "b", revision: "g".repeat(64) }, idempotent: false }),
    },
  ]);
  const store = await PlatformTasksStore.open(disk().openBridge("u1"), env, http);
  await store.refresh();
  await store.create("Buy milk");
  await env.advance(10);
  const firstId = (await store.list())[0]!.id;
  await store.patch(firstId, { completed: true });
  await env.advance(10);
  await store.create("Buy milk");
  await env.advance(10);
  const listed = await store.list();
  assert.equal(listed.filter((row) => row.description === "Buy milk").length, 2);
  assert.equal(http.calls.filter((call) => call.method === "POST").length, 3);
});

test("a patch against a bare opaque read handle is refused rather than upserted", async () => {
  // red-proof: send the HMAC handle as record_id. The write door upserts a
  // second row. APPLIED AND OBSERVED RED.
  const page = pageFor("window:complete_terminal") as { items: { id: string }[] };
  const store = await PlatformTasksStore.open(
    disk().openBridge("u1"),
    env,
    new Scripted([ok(page)]),
  );
  await store.refresh();
  const opaqueId = (await store.list())[0]!.id;
  await assert.rejects(
    () => store.patch(opaqueId, { completed: true }),
    /opaque read handle has no write id/,
  );
});
