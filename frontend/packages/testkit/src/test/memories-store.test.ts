/**
 * MemoriesStore integration: the full loop a surface exercises — optimistic
 * create, alias absorption of the legacy server-assigned id, refresh rekey,
 * wire-id resolution on patch, and durable offline reads across restart.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { MemoriesStore, TasksStore } from "@omi-core/domain";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

test("create → alias → refresh → patch resolves wire id → offline restart", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();

  const store = await MemoriesStore.open(disk.openBridge("user-a"), env, http);
  http.respond({ status: 200, json: { id: "srv-1" } }); // legacy create assigns its own id

  await store.create("the user lives in Denver");
  let rows = await store.list();
  assert.equal(rows.length, 1, "optimistic row renders before any network");
  const localId = rows[0]!.id;
  assert.match(localId, /^[a-z]+(-[a-z]+)+$/, "local identity is a slug");
  assert.equal(store.pendingCount(), 1);

  await env.advance(10);
  assert.equal(store.pendingCount(), 0, "create confirmed");

  // Server truth comes back under the SERVER id; refresh rekeys to local.
  http.respond({
    status: 200,
    json: [{ id: "srv-1", content: "the user lives in Denver", visibility: "private", category: "interesting" }],
  });
  http.respond({ status: 200, json: null }); // list endpoint junk body on snapshot path -> null, no reconcile
  await store.refresh();
  rows = await store.list();
  assert.equal(rows.length, 1, "no duplicate: server row rekeyed onto the local slug");
  assert.equal(rows[0]!.id, localId);

  // Patch goes out under the WIRE id.
  http.respond({ status: 200, json: {} });
  await store.patch(localId, { visibility: "public" });
  await env.advance(10);
  const patchCall = http.calls.at(-1)!;
  assert.equal(patchCall.method, "PATCH");
  assert.ok(patchCall.path.endsWith("/srv-1/visibility"), `patch hit the server id, got ${patchCall.path}`);
  assert.deepEqual(patchCall.body, { value: "public" }, "keyed patch, no smuggled defaults");

  // Kill the app; relaunch offline (no responses scripted).
  const store2 = await MemoriesStore.open(disk.openBridge("user-a"), env, new ScriptedHttp());
  const offline = await store2.list();
  assert.equal(offline.length, 1, "cold offline launch shows synced rows (ADR-004 D1)");
  assert.equal(offline[0]!.id, localId);
});

test("reconcile with aliased snapshot ids never deletes the local row", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await MemoriesStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: { id: "srv-9" } });
  await store.create("keep me");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  http.respond({ status: 200, json: [{ id: "srv-9", content: "keep me", visibility: "private" }] });
  http.respond({ status: 200, json: [{ id: "srv-9" }] });
  await store.refresh();
  const rows = await store.list();
  assert.equal(rows.length, 1, "alias-mapped reconcile kept the row");
  assert.equal(rows[0]!.id, localId);
});

/**
 * Regression (rule 12): `GET /v3/memories` hides user-rejected and
 * invalidated memories, and applies that filter AFTER the page limit — so a
 * row missing from the list is NOT evidence the row is gone. While
 * `fetchMemoryIdSnapshot` claimed `complete: true` on a short page, the very
 * next refresh deleted every filtered-out memory from the local projection.
 */
test("a memory the filtered list endpoint hides is never deleted locally", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await MemoriesStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: { id: "srv-hidden" } });
  await store.create("the user rejected this one");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  // Server list comes back short AND without our row (the filter dropped it).
  http.respond({ status: 200, json: [] });
  http.respond({ status: 200, json: [] });
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.length, 1, "a short filtered page must never drive a reconcile delete");
  assert.equal(rows[0]!.id, localId);
});

/**
 * Regression: memories is the first domain to be co-hosted with tasks on one
 * bridge (the dev harness does exactly this, and every real shell will too).
 * While `Outbox` hardcoded the journal name "outbox", both stores shared one
 * log: on the next launch each replayed the OTHER domain's pending ops through
 * its own transport — a queued task create would be POSTed to `/v3/memories`,
 * and a queued memory would land on `/v1/action-items`.
 */
test("two domains on one bridge never replay each other's queued ops", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const bridge = disk.openBridge("user-a");

  const tasks = await TasksStore.open(bridge, env, new ScriptedHttp());
  await MemoriesStore.open(bridge, env, new ScriptedHttp());

  // Queue a task offline (unscripted ScriptedHttp 500s -> stays pending).
  await tasks.create("ship the exemplar");
  await env.advance(10);
  assert.equal(tasks.pendingCount(), 1, "the task op is queued, not confirmed");

  // Relaunch both stores over the same durable storage.
  const bridge2 = disk.openBridge("user-a");
  const memoriesHttp = new ScriptedHttp();
  const tasks2 = await TasksStore.open(bridge2, env, new ScriptedHttp());
  const memories2 = await MemoriesStore.open(bridge2, env, memoriesHttp);
  await env.advance(10);

  assert.equal(tasks2.pendingCount(), 1, "the task op replays into its own outbox");
  assert.equal(memories2.pendingCount(), 0, "the memories outbox never adopts a task op");
  assert.deepEqual(await memories2.list(), [], "no task op leaks into the memories projection overlay");
  assert.deepEqual(
    memoriesHttp.calls.filter((c) => c.method !== "GET"),
    [],
    "the memories transport never sent another domain's op",
  );
});

/**
 * Regression (D4): the legacy list handler serializes a locked memory with a
 * TRUNCATED body (`content[:70] + '...'`) behind a paid-plan gate. That
 * truncation used to land in the projection as ordinary content, and the
 * surface's commit-on-blur textarea would PATCH it back — permanently
 * destroying the real content. The store is the single mutation owner, so the
 * refusal lives there: no surface mistake can reach the wire.
 */
test("a locked memory's truncated content can never be patched back", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await MemoriesStore.open(disk.openBridge("u"), env, http);

  // Server truth: a locked memory, arriving already truncated.
  const truncated = "the user has a long and detailed memory about their tra...";
  http.respond({ status: 200, json: [{ id: "srv-locked", content: truncated, is_locked: true }] });
  http.respond({ status: 200, json: [] });
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.locked, true, "the is_locked wire signal reaches the contract");
  assert.equal(rows[0]!.content, truncated);

  await assert.rejects(
    () => store.patch(rows[0]!.id, { content: "edited by a surface that forgot to gate" }),
    /locked memory/,
    "a content patch on a locked row is refused, not queued",
  );
  assert.equal(store.pendingCount(), 0, "no op was enqueued");
  assert.deepEqual(
    http.calls.filter((c) => c.method === "PATCH"),
    [],
    "the truncation never reached the wire",
  );

  // The lock is specific to content: server-owned fields stay patchable.
  await store.patch(rows[0]!.id, { visibility: "public" });
  assert.equal(store.pendingCount(), 1, "a non-content patch on a locked row is still allowed");
});

test("an unlocked memory has locked=false and stays editable", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await MemoriesStore.open(disk.openBridge("u"), env, http);

  // `is_locked` absent entirely — the common case, and it must read as unlocked.
  http.respond({ status: 200, json: [{ id: "srv-open", content: "fully readable" }] });
  http.respond({ status: 200, json: [] });
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows[0]!.locked, false, "absent is_locked defaults to unlocked");
  await store.patch(rows[0]!.id, { content: "edited freely" });
  assert.equal(store.pendingCount(), 1);
});
