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
