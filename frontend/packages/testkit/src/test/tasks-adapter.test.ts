/**
 * Adapter conformance: the legacy backend's quirks are absorbed HERE, with
 * the exact status→taxonomy mapping and the two documented gaps (server-
 * assigned create ids; synthetic set versions) proven under test.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { TaskOp } from "@omi-core/contracts";
import {
  fetchIdSnapshot,
  fetchTasks,
  sendTaskOp,
  tasksTransport,
  wireToTask,
} from "@omi-core/adapters-legacy";
import { classifyStatus } from "@omi-core/kernel";
import { type HttpClient, type HttpResponse } from "@omi-core/contracts";

class ScriptedHttp implements HttpClient {
  public readonly calls: { method: string; path: string; body?: unknown }[] = [];
  private script: HttpResponse[] = [];

  respond(...responses: HttpResponse[]): void {
    this.script.push(...responses);
  }

  async request(method: "GET" | "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<HttpResponse> {
    this.calls.push(body === undefined ? { method, path } : { method, path, body });
    return this.script.shift() ?? { status: 500, json: null };
  }
}

test("status classification is total and terminal-correct", () => {
  assert.equal(classifyStatus({ status: 401, json: null }, "x").kind, "auth-invalid");
  assert.equal(classifyStatus({ status: 429, json: null, retryAfterMs: 5 }, "x").kind, "rate-limited");
  assert.equal(classifyStatus({ status: 422, json: null }, "x").kind, "permanent");
  assert.equal(classifyStatus({ status: 409, json: null }, "x").kind, "permanent");
  assert.equal(classifyStatus({ status: 503, json: null }, "x").kind, "retryable");
  const odd = classifyStatus({ status: 418, json: null }, "x");
  assert.ok(odd.kind === "retryable" && odd.unclassified, "unknown statuses are a telemetered taxonomy gap, never a guess");
});

test("keyed patch: absent keys never reach the wire (issue-draft-02 class)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: TaskOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as TaskOp["id"],
    at: 1,
    patch: { completed: true },
  };
  await sendTaskOp(http, op);
  assert.deepEqual(http.calls[0]!.body, { completed: true }, "no owner/source/sort_order defaults smuggled in");
});

test("create: server-assigned id is surfaced as an alias, not silently adopted", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: { id: "srv-123" } });
  const aliases: Array<[string, string]> = [];
  const transport = tasksTransport(http, (local, server) => aliases.push([local, server]));
  const domainOp: TaskOp = {
    op: "create",
    opId: "o1",
    id: "amber-fox-ridge" as TaskOp["id"],
    at: 1,
    description: "ship it",
    source: "user",
  };
  const result = await transport.send({
    opId: "o1",
    domain: "tasks",
    recordId: "amber-fox-ridge",
    payload: JSON.stringify(domainOp),
    summary: "create: ship it",
    attempts: 0,
  });
  assert.ok(result.ok);
  assert.deepEqual(aliases, [["amber-fox-ridge", "srv-123"]]);
});

test("id snapshot synthesizes a stable set version (reconcile idempotence)", async () => {
  const http = new ScriptedHttp();
  http.respond(
    { status: 200, json: { ids: ["b", "a"] } },
    { status: 200, json: { ids: ["a", "b"] } },
    { status: 200, json: { ids: ["a", "b", "c"] } },
  );
  const s1 = await fetchIdSnapshot(http);
  const s2 = await fetchIdSnapshot(http);
  const s3 = await fetchIdSnapshot(http);
  assert.ok(s1 && s2 && s3);
  assert.equal(s1.complete, true, "the ids endpoint returns the whole set — snapshot is honest");
  assert.equal(s1.setVersion, s2.setVersion, "order-independent");
  assert.notEqual(s1.setVersion, s3.setVersion, "content-sensitive");
});

test("delete of an already-gone record is success (idempotent replay-safety)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 404, json: null });
  const result = await sendTaskOp(http, { op: "delete", opId: "o1", id: "amber-fox-ridge" as TaskOp["id"], at: 1 });
  assert.ok(result.ok, "replaying a delete after a crash must not dead-letter");
});

test("wire rows parse legacy UUID ids and reject junk", () => {
  const good = wireToTask({ id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111", description: "d", completed: false });
  assert.ok(good);
  assert.equal(wireToTask({ id: "<script>", description: "d" }), null);
});

test("multi-field patch is one combined PATCH with every touched key and no untouched ones", async () => {
  // red-proof: in wirePatch, drop the `if (p.owner !== undefined)` / sortOrder /
  // indentLevel arms (or emit one request per field like memories) — then either
  // calls.length > 1 or the single body is missing owner/sort_order/indent_level.
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: TaskOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as TaskOp["id"],
    at: 1,
    patch: {
      description: "renamed",
      owner: "uid-1",
      sortOrder: 3,
      indentLevel: 1,
    },
  };
  const result = await sendTaskOp(http, op);
  assert.ok(result.ok);
  assert.equal(http.calls.length, 1, "tasks has one combined PATCH — not one request per field");
  assert.equal(http.calls[0]!.method, "PATCH");
  assert.equal(http.calls[0]!.path, "/v1/action-items/amber-fox-ridge");
  assert.deepEqual(
    http.calls[0]!.body,
    { description: "renamed", owner: "uid-1", sort_order: 3, indent_level: 1 },
    "touched keys present; completed/due_at absent — never defaulted onto the wire",
  );
});

test("dueAt explicit null clears on the wire as due_at: null", async () => {
  // red-proof: in wirePatch, change `p.dueAt === null ? null` to omit the key
  // (or to `undefined`) when dueAt is null — body then lacks due_at entirely.
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: TaskOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as TaskOp["id"],
    at: 1,
    patch: { dueAt: null },
  };
  await sendTaskOp(http, op);
  assert.deepEqual(http.calls[0]!.body, { due_at: null }, "clearing a due date must send explicit null, not omit the key");
});

test("dueAt absent from the patch sends no due_at key at all", async () => {
  // red-proof: in wirePatch, change `if (p.dueAt !== undefined)` to always
  // assign `body["due_at"] = null` (or drop the undefined guard) — then a
  // completed-only patch grows a due_at key on the wire.
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: TaskOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as TaskOp["id"],
    at: 1,
    patch: { completed: true },
  };
  await sendTaskOp(http, op);
  assert.deepEqual(http.calls[0]!.body, { completed: true });
  assert.ok(!Object.prototype.hasOwnProperty.call(http.calls[0]!.body, "due_at"), "untouched dueAt must not appear on the wire");
});

test("fetchIdSnapshot: body missing ids key returns null, not a bogus snapshot", async () => {
  // red-proof: in fetchIdSnapshot, change `!Array.isArray(body.ids)` to treat
  // missing ids as `[]` (e.g. `body.ids ?? []`) — then {} becomes a complete empty snapshot.
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  assert.equal(await fetchIdSnapshot(http), null, "rule 12: junk body never becomes a snapshot");
});

test("fetchIdSnapshot: null json body returns null, not a bogus snapshot", async () => {
  // red-proof: in fetchIdSnapshot, drop the `!body ||` guard so null json is
  // cast and read — then null becomes a thrown error or a synthetic empty set.
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: null });
  assert.equal(await fetchIdSnapshot(http), null, "rule 12: junk body never becomes a snapshot");
});

test("fetchTasks: mixed well-formed and junk rows keep only the well-formed one", async () => {
  // red-proof: in fetchTasks, push raw rows without wireToTask (or treat a null
  // wireToTask result as fatal / include the junk) — then the list grows a second
  // entry or the call returns null instead of the single good Task.
  const http = new ScriptedHttp();
  http.respond({
    status: 200,
    json: {
      action_items: [
        { id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111", description: "keep me", completed: false },
        { description: "no id field" },
        { id: 42, description: "non-string id" },
      ],
    },
  });
  const tasks = await fetchTasks(http);
  assert.ok(tasks);
  assert.equal(tasks.length, 1, "junk rows are silently dropped, not fatal");
  assert.equal(tasks[0]!.id, "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111");
  assert.equal(tasks[0]!.description, "keep me");
});
