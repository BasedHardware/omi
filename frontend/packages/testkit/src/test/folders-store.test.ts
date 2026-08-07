/**
 * FoldersStore integration: optimistic create, alias absorption of the legacy
 * server-assigned id, keyed patch, delete, and junk-snapshot honesty.
 *
 * Lives here rather than under domain/src because the exemplar pair's store
 * tests do (tasks-store.test.ts, memories-store.test.ts): testkit already
 * depends on domain, so hosting them here needs no test runner in the domain
 * package and no domain->testkit devDependency cycle.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { RecordId } from "@omi-core/contracts";
import { ConversationsStore, FoldersStore, MemoriesStore, TasksStore } from "@omi-core/domain";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

const wireFolder = (id: string, name: string) => ({
  id,
  name,
  color: "#6B7280",
  icon: "folder",
  created_at: "2024-01-01T00:00:00.000Z",
  updated_at: "2024-01-01T00:00:00.000Z",
  is_system: false,
  is_default: false,
});

/**
 * Regression: foldersTransport originally took only onServerAssignedId, with no
 * resolveWireId hook, so once the legacy server assigned its own create id a
 * later patch/delete went out under the LOCAL SLUG — an id the server has never
 * heard of, so every post-create edit 404'd forever. This is the assertion
 * tasks-store.test.ts has always carried; folders could not until the adapter
 * grew the third parameter.
 */
test("after an alias is recorded, patch and delete go out under the WIRE id", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await FoldersStore.open(disk.openBridge("user-a"), env, http);

  http.respond({ status: 200, json: { id: "srv-77" } }); // legacy create assigns its own id
  await store.create("Work");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;
  assert.match(localId, /^[a-z]+(-[a-z]+)+$/, "local identity stays a slug");
  assert.notEqual(localId, "srv-77", "the server id is aliased, not adopted");

  http.respond({ status: 200, json: {} });
  await store.patch(localId, { name: "Personal" });
  await env.advance(10);
  const patchCall = http.calls.find((c) => c.method === "PATCH")!;
  assert.ok(patchCall.path.endsWith("/srv-77"), `patch must hit the server id, got ${patchCall.path}`);

  http.respond({ status: 204, json: null });
  await store.delete(localId);
  await env.advance(10);
  const delCall = http.calls.find((c) => c.method === "DELETE")!;
  assert.ok(delCall.path.endsWith("/srv-77"), `delete must hit the server id, got ${delCall.path}`);
});

test("create-offline-then-confirm folds server-assigned id into alias map", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();

  const store = await FoldersStore.open(disk.openBridge("user-a"), env, http);
  http.respond({ status: 200, json: { id: "srv-1" } });

  await store.create("Work");
  let rows = await store.list();
  assert.equal(rows.length, 1, "optimistic row renders before any network");
  const localId = rows[0]!.id;
  assert.match(localId, /^[a-z]+(-[a-z]+)+$/, "local identity is a slug");
  assert.equal(store.pendingCount(), 1);

  await env.advance(10);
  assert.equal(store.pendingCount(), 0, "create confirmed");

  // The server row carries a DISTINGUISHABLE name on purpose. Row-count alone
  // cannot prove rekeying here: reconcile runs right after (folders snapshots
  // are complete-capable) and would delete a stray server-id row anyway, so a
  // broken rekey would still leave exactly one row. Only the server's own field
  // value landing on the LOCAL slug proves the server row was merged onto the
  // local identity rather than silently dropped.
  http.respond({ status: 200, json: [wireFolder("srv-1", "Work (server copy)")] });
  http.respond({ status: 200, json: [wireFolder("srv-1", "Work (server copy)")] });
  await store.refresh();
  rows = await store.list();
  assert.equal(rows.length, 1, "no duplicate: server row rekeyed onto the local slug");
  assert.equal(rows[0]!.id, localId, "identity stays the local slug");
  assert.equal(rows[0]!.name, "Work (server copy)", "server truth was merged onto the local slug, not discarded");
});

test("patch applies keyed rename optimistically", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await FoldersStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: [wireFolder("amber-fox-ridge", "Work")] });
  http.respond({ status: 200, json: [{ id: "amber-fox-ridge" }] });
  await store.refresh();

  http.respond({ status: 200, json: {} });
  await store.patch("amber-fox-ridge" as RecordId, { name: "Personal" });
  const rows = await store.list();
  assert.equal(rows[0]!.name, "Personal", "optimistic overlay shows the rename before confirm");

  await env.advance(10);
  const patchCall = http.calls.find((c) => c.method === "PATCH")!;
  assert.deepEqual(patchCall.body, { name: "Personal" }, "keyed patch, no smuggled defaults");
});

test("delete removes the folder optimistically", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await FoldersStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: [wireFolder("amber-fox-ridge", "Work")] });
  http.respond({ status: 200, json: [{ id: "amber-fox-ridge" }] });
  await store.refresh();

  http.respond({ status: 204, json: null });
  await store.delete("amber-fox-ridge" as RecordId);
  assert.equal((await store.list()).length, 0, "optimistic delete hides the row immediately");
  await env.advance(10);
  assert.equal(store.pendingCount(), 0, "delete confirmed");
});

test("junk snapshot body does not wipe local rows", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await FoldersStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: { id: "srv-9" } });
  await store.create("keep me");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  http.respond({ status: 200, json: [wireFolder("srv-9", "keep me")] });
  http.respond({ status: 200, json: null }); // junk body -> snapshot null, no reconcile
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.length, 1, "a junk snapshot must never drive reconcile deletes");
  assert.equal(rows[0]!.id, localId);
});

test("reconcile with aliased snapshot ids never deletes the local row", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await FoldersStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: { id: "srv-9" } });
  await store.create("keep me");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  http.respond({ status: 200, json: [wireFolder("srv-9", "keep me")] });
  http.respond({ status: 200, json: [wireFolder("srv-9", "keep me")] });
  await store.refresh();
  const rows = await store.list();
  assert.equal(rows.length, 1, "alias-mapped reconcile kept the row");
  assert.equal(rows[0]!.id, localId);
});

/**
 * The multi-store law, now for every domain: the dev harness (and every real
 * shell) opens all four stores off ONE bridge. Each must own a
 * domain-namespaced outbox journal, or on the next launch each store adopts the
 * others' queued ops and flushes them through the wrong transport. Narrower
 * pairwise versions of this live in the memories and conversations suites; this
 * is the one that fails when domain N+1 forgets to namespace.
 */
test("all four domains co-hosted on one bridge keep their queues separate", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const bridge = disk.openBridge("user-a");

  const tasks = await TasksStore.open(bridge, env, new ScriptedHttp());
  const memories = await MemoriesStore.open(bridge, env, new ScriptedHttp());
  const folders = await FoldersStore.open(bridge, env, new ScriptedHttp());
  const conversations = await ConversationsStore.open(bridge, env, new ScriptedHttp());

  // One queued write per domain; unscripted ScriptedHttp 500s, so all stay pending.
  await tasks.create("ship the exemplar");
  await memories.create("the user lives in Denver");
  await folders.create("Work");
  await conversations.delete("550e8400-e29b-41d4-a716-446655440009" as RecordId);
  await env.advance(10);

  for (const [name, count] of [
    ["tasks", tasks.pendingCount()],
    ["memories", memories.pendingCount()],
    ["folders", folders.pendingCount()],
    ["conversations", conversations.pendingCount()],
  ] as const) {
    assert.equal(count, 1, `${name} owns exactly its own queued op, not the other three`);
  }

  // Relaunch all four over the same durable storage.
  const bridge2 = disk.openBridge("user-a");
  const https = {
    tasks: new ScriptedHttp(),
    memories: new ScriptedHttp(),
    folders: new ScriptedHttp(),
    conversations: new ScriptedHttp(),
  };
  const tasks2 = await TasksStore.open(bridge2, env, https.tasks);
  const memories2 = await MemoriesStore.open(bridge2, env, https.memories);
  const folders2 = await FoldersStore.open(bridge2, env, https.folders);
  const conversations2 = await ConversationsStore.open(bridge2, env, https.conversations);
  await env.advance(10);

  assert.equal(tasks2.pendingCount(), 1, "each op replays into its own outbox only");
  assert.equal(memories2.pendingCount(), 1);
  assert.equal(folders2.pendingCount(), 1);
  assert.equal(conversations2.pendingCount(), 1);

  // No projection cross-contamination: each store overlays only its own op.
  assert.equal((await tasks2.list()).length, 1);
  assert.equal((await memories2.list()).length, 1);
  assert.equal((await folders2.list()).length, 1);
  assert.deepEqual(await conversations2.list(), [], "a delete op on an absent row overlays to nothing");

  // Every request each transport made must belong to that transport's domain.
  const wrote = (h: ScriptedHttp): string[] => h.calls.filter((c) => c.method !== "GET").map((c) => c.path);
  for (const p of wrote(https.tasks)) assert.match(p, /action-items/, `tasks transport sent ${p}`);
  for (const p of wrote(https.memories)) assert.match(p, /memories/, `memories transport sent ${p}`);
  for (const p of wrote(https.folders)) assert.match(p, /folders/, `folders transport sent ${p}`);
  for (const p of wrote(https.conversations)) assert.match(p, /conversations/, `conversations transport sent ${p}`);
});
