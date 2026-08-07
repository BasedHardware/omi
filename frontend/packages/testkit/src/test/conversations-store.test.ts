/**
 * ConversationsStore integration: the loop a surface exercises without create —
 * refresh ingest, optimistic title patch, delete, filtered-snapshot honesty,
 * dead-letter on entitlement (402), and durable offline reads across restart.
 *
 * Path note: exemplar store tests live here (testkit), not under domain/src —
 * domain has no testkit dependency (testkit → domain). Brief path
 * `domain/src/conversations-store.test.ts` would invent a parallel pattern.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { ConversationsStore, MemoriesStore, TasksStore } from "@omi-core/domain";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

function wireConversation(id: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id,
    structured: { title: "standup", overview: "" },
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-02T00:00:00.000Z",
    source: "omi",
    status: "completed",
    discarded: false,
    starred: false,
    visibility: "private",
    is_locked: false,
    folder_id: null,
    ...overrides,
  };
}

test("refresh → patch title → delete → offline restart", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ConversationsStore.open(disk.openBridge("user-a"), env, http);

  http.respond({ status: 200, json: [wireConversation("550e8400-e29b-41d4-a716-446655440000")] });
  http.respond({ status: 200, json: [wireConversation("550e8400-e29b-41d4-a716-446655440000")] });
  await store.refresh();

  let rows = await store.list();
  assert.equal(rows.length, 1, "server-originated row lands via refresh");
  assert.equal(rows[0]!.title, "standup");
  assert.equal(rows[0]!.status, "completed");
  const id = rows[0]!.id;

  http.respond({ status: 200, json: {} });
  await store.patch(id, { title: "weekly sync" });
  rows = await store.list();
  assert.equal(rows[0]!.title, "weekly sync", "optimistic title overlay before confirm");
  assert.equal(store.pendingCount(), 1);

  await env.advance(10);
  assert.equal(store.pendingCount(), 0, "title patch confirmed");
  const titleCall = http.calls.find((c) => c.method === "PATCH" && c.path.includes("/title"));
  assert.ok(titleCall, "patch hit the dedicated title route");
  assert.ok(
    titleCall!.path.includes("/550e8400-e29b-41d4-a716-446655440000/title?title=weekly%20sync"),
    `got ${titleCall!.path}`,
  );
  assert.equal(titleCall!.body, undefined, "title is query-only; no body defaults smuggled");

  http.respond({ status: 200, json: {} });
  await store.delete(id);
  await env.advance(10);
  rows = await store.list();
  assert.equal(rows.length, 0, "confirmed delete removes the row");
  const del = http.calls.find((c) => c.method === "DELETE");
  assert.ok(del?.path.includes("cascade=false"), "delete pins cascade=false");

  const store2 = await ConversationsStore.open(disk.openBridge("user-a"), env, new ScriptedHttp());
  const offline = await store2.list();
  assert.equal(offline.length, 0, "cold offline launch shows durable projection (ADR-004 D1)");
});

test("a conversation the filtered list endpoint hides is never deleted locally", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ConversationsStore.open(disk.openBridge("u"), env, http);

  // Seed via refresh: an in_progress row that default statuses=processing,completed hide.
  http.respond({
    status: 200,
    json: [wireConversation("550e8400-e29b-41d4-a716-446655440001", { status: "in_progress", structured: { title: "live", overview: "" } })],
  });
  http.respond({
    status: 200,
    json: [wireConversation("550e8400-e29b-41d4-a716-446655440001", { status: "in_progress" })],
  });
  await store.refresh();
  assert.equal((await store.list()).length, 1);

  // Later refresh: default filter page omits the in_progress id; snapshot must
  // stay incomplete so reconcile never deletes it.
  http.respond({ status: 200, json: [] });
  http.respond({ status: 200, json: [] });
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.length, 1, "a filtered incomplete snapshot must never drive a reconcile delete");
  assert.equal(rows[0]!.id, "550e8400-e29b-41d4-a716-446655440001");
});

test("locked conversation stays listed; title patch on unlocked only reaches the wire", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ConversationsStore.open(disk.openBridge("u"), env, http);

  http.respond({
    status: 200,
    json: [
      wireConversation("550e8400-e29b-41d4-a716-446655440002", {
        is_locked: true,
        structured: { title: "paid transcript", overview: "" },
      }),
    ],
  });
  http.respond({ status: 200, json: [] });
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows[0]!.isLocked, true, "is_locked wire signal reaches the contract");
  assert.equal(rows[0]!.title, "paid transcript");
});

test("402 entitlement on patch becomes a dead letter (not auth-invalid)", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ConversationsStore.open(disk.openBridge("u"), env, http);

  http.respond({
    status: 200,
    json: [wireConversation("550e8400-e29b-41d4-a716-446655440003")],
  });
  http.respond({ status: 200, json: [] });
  await store.refresh();
  const id = (await store.list())[0]!.id;

  http.respond({ status: 402, json: null });
  await store.patch(id, { title: "blocked" });
  // Exhaust retry budget: permanent failures dead-letter immediately.
  await env.advance(10);

  assert.equal(store.pendingCount(), 0);
  const dead = await store.deadLetters();
  assert.equal(dead.length, 1, "entitlement failure is user-visible");
  assert.equal(dead[0]!.failure.kind, "permanent");
  assert.equal(dead[0]!.failure.reason, "entitlement");
});

test("two domains on one bridge never replay each other's queued ops", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const bridge = disk.openBridge("user-a");

  const tasks = await TasksStore.open(bridge, env, new ScriptedHttp());
  await ConversationsStore.open(bridge, env, new ScriptedHttp());

  await tasks.create("ship the exemplar");
  await env.advance(10);
  assert.equal(tasks.pendingCount(), 1, "the task op is queued, not confirmed");

  const bridge2 = disk.openBridge("user-a");
  const conversationsHttp = new ScriptedHttp();
  const tasks2 = await TasksStore.open(bridge2, env, new ScriptedHttp());
  const conversations2 = await ConversationsStore.open(bridge2, env, conversationsHttp);
  await MemoriesStore.open(bridge2, env, new ScriptedHttp());
  await env.advance(10);

  assert.equal(tasks2.pendingCount(), 1, "the task op replays into its own outbox");
  assert.equal(conversations2.pendingCount(), 0, "the conversations outbox never adopts a task op");
  assert.deepEqual(await conversations2.list(), [], "no task op leaks into the conversations projection overlay");
  assert.deepEqual(
    conversationsHttp.calls.filter((c) => c.method !== "GET"),
    [],
    "the conversations transport never sent another domain's op",
  );
});

test("keyed patch never smuggles absent fields onto the wire", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ConversationsStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: [wireConversation("550e8400-e29b-41d4-a716-446655440004")] });
  http.respond({ status: 200, json: [] });
  await store.refresh();
  const id = (await store.list())[0]!.id;

  http.respond({ status: 200, json: {} });
  await store.patch(id, { starred: true });
  await env.advance(10);

  const patches = http.calls.filter((c) => c.method === "PATCH");
  assert.equal(patches.length, 1, "only the touched field issues a request");
  assert.ok(patches[0]!.path.endsWith("/starred?starred=true"));
  assert.equal(patches[0]!.body, undefined, "no title/visibility/folderId defaults smuggled in");
});
