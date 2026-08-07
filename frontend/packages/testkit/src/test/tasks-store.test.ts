/**
 * TasksStore integration: the full loop a surface exercises — optimistic
 * create, alias absorption of the legacy server-assigned id, refresh rekey,
 * wire-id resolution on patch, and durable offline reads across restart.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { TasksStore } from "@omi-core/domain";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

test("create → alias → refresh → patch resolves wire id → offline restart", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();

  const store = await TasksStore.open(disk.openBridge("user-a"), env, http);
  http.respond({ status: 200, json: { id: "srv-1" } }); // legacy create assigns its own id

  await store.create("ship the exemplar");
  let rows = await store.list();
  assert.equal(rows.length, 1, "optimistic row renders before any network");
  const localId = rows[0]!.id;
  assert.match(localId, /^[a-z]+(-[a-z]+)+$/, "local identity is a slug");
  assert.equal(store.pendingCount(), 1);

  await env.advance(10);
  assert.equal(store.pendingCount(), 0, "create confirmed");

  // Server truth comes back under the SERVER id; refresh rekeys to local.
  http.respond(
    { status: 200, json: { action_items: [{ id: "srv-1", description: "ship the exemplar", completed: false }] } },
  );
  http.respond({ status: 200, json: null }); // ids endpoint junk body -> snapshot null, no reconcile
  await store.refresh();
  rows = await store.list();
  assert.equal(rows.length, 1, "no duplicate: server row rekeyed onto the local slug");
  assert.equal(rows[0]!.id, localId);

  // Patch goes out under the WIRE id.
  http.respond({ status: 200, json: {} });
  await store.patch(localId, { completed: true });
  await env.advance(10);
  const patchCall = http.calls.at(-1)!;
  assert.equal(patchCall.method, "PATCH");
  assert.ok(patchCall.path.endsWith("/srv-1"), `patch hit the server id, got ${patchCall.path}`);
  assert.deepEqual(patchCall.body, { completed: true }, "keyed patch, no smuggled defaults");

  // Kill the app; relaunch offline (no responses scripted).
  const store2 = await TasksStore.open(disk.openBridge("user-a"), env, new ScriptedHttp());
  const offline = await store2.list();
  assert.equal(offline.length, 1, "cold offline launch shows synced rows (ADR-004 D1)");
  assert.equal(offline[0]!.id, localId);
});

test("reconcile with aliased snapshot ids never deletes the local row", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await TasksStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: { id: "srv-9" } });
  await store.create("keep me");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  http.respond({ status: 200, json: { action_items: [{ id: "srv-9", description: "keep me" }] } });
  http.respond({ status: 200, json: { ids: ["srv-9"] } }); // complete snapshot in server ids
  await store.refresh();
  const rows = await store.list();
  assert.equal(rows.length, 1, "alias-mapped reconcile kept the row");
  assert.equal(rows[0]!.id, localId);
});
