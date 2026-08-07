/**
 * Adapter conformance: the legacy backend's quirks are absorbed HERE, with
 * the exact status→taxonomy mapping and the documented gaps (server-assigned
 * create ids; unpaginated complete snapshots with initialize side effect; 204
 * delete; split ordering authority) proven under test.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { FolderOp } from "@omi-core/contracts";
import {
  fetchFolderIdSnapshot,
  foldersTransport,
  sendFolderOp,
  wireToFolder,
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

test("status classification is total and terminal-correct (shared helper, not reinvented)", () => {
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
  const op: FolderOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as FolderOp["id"],
    at: 1,
    patch: { name: "Work" },
  };
  await sendFolderOp(http, op);
  assert.deepEqual(http.calls[0]!.body, { name: "Work" }, "no description/color/icon/order defaults smuggled in");
});

test("keyed patch: explicit null description clears on the wire", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: FolderOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as FolderOp["id"],
    at: 1,
    patch: { description: null },
  };
  await sendFolderOp(http, op);
  assert.deepEqual(http.calls[0]!.body, { description: null });
});

test("create: server-assigned id is surfaced as an alias, not silently adopted", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: { id: "srv-folder-42" } });
  const aliases: Array<[string, string]> = [];
  const transport = foldersTransport(http, (local, server) => aliases.push([local, server]));
  const domainOp: FolderOp = {
    op: "create",
    opId: "o1",
    id: "amber-fox-ridge" as FolderOp["id"],
    at: 1,
    name: "Work",
  };
  const result = await transport.send({
    opId: "o1",
    domain: "folders",
    recordId: "amber-fox-ridge",
    payload: JSON.stringify(domainOp),
    summary: "create: Work",
    attempts: 0,
  });
  assert.ok(result.ok);
  assert.deepEqual(aliases, [["amber-fox-ridge", "srv-folder-42"]]);
});

test("id snapshot is complete and synthesizes a stable set version (unpaginated list)", async () => {
  const http = new ScriptedHttp();
  http.respond(
    { status: 200, json: [{ id: "b" }, { id: "a" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }, { id: "c" }] },
  );
  const s1 = await fetchFolderIdSnapshot(http);
  const s2 = await fetchFolderIdSnapshot(http);
  const s3 = await fetchFolderIdSnapshot(http);
  assert.ok(s1 && s2 && s3);
  assert.equal(s1.complete, true, "GET /v1/folders is unpaginated — the snapshot is honestly complete");
  assert.equal(s1.setVersion, s2.setVersion, "order-independent");
  assert.notEqual(s1.setVersion, s3.setVersion, "content-sensitive");
});

test("delete succeeds on 204 with no body (folders wire shape)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 204, json: null });
  const result = await sendFolderOp(http, { op: "delete", opId: "o1", id: "amber-fox-ridge" as FolderOp["id"], at: 1 });
  assert.ok(result.ok, "204 no-body delete must be terminal success");
});

test("delete of an already-gone record is success (idempotent replay-safety)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 404, json: null });
  const result = await sendFolderOp(http, { op: "delete", opId: "o1", id: "amber-fox-ridge" as FolderOp["id"], at: 1 });
  assert.ok(result.ok, "replaying a delete after a crash must not dead-letter");
});

test("delete of a system folder is permanent validation, never retryable", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 400, json: { detail: "Cannot delete system folder" } });
  const result = await sendFolderOp(http, { op: "delete", opId: "o1", id: "system-other" as FolderOp["id"], at: 1 });
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.failure.kind, "permanent");
    assert.equal(result.failure.reason, "validation");
  }
});

test("create past folder limit is permanent validation, never retryable", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 400, json: { detail: "Maximum folder limit reached (50 custom folders)" } });
  const result = await sendFolderOp(http, {
    op: "create",
    opId: "o1",
    id: "amber-fox-ridge" as FolderOp["id"],
    at: 1,
    name: "One too many",
  });
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.failure.kind, "permanent");
    assert.equal(result.failure.reason, "validation");
  }
});

test("wire rows parse legacy UUID ids and reject junk", () => {
  const good = wireToFolder({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    name: "Work",
    color: "#6B7280",
    icon: "folder",
    created_at: "2024-01-01T00:00:00.000Z",
    updated_at: "2024-01-01T00:00:00.000Z",
    is_system: false,
    is_default: false,
  });
  assert.ok(good);
  assert.equal(wireToFolder({ id: "<script>", name: "x" }), null);
});

test("wire rows preserve isSystem and isDefault without smuggling defaults onto custom folders", () => {
  const system = wireToFolder({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    name: "Other",
    is_system: true,
    is_default: true,
  });
  assert.ok(system);
  assert.equal(system.isSystem, true);
  assert.equal(system.isDefault, true);

  const custom = wireToFolder({
    id: "amber-fox-ridge",
    name: "Work",
    is_system: false,
    is_default: false,
  });
  assert.ok(custom);
  assert.equal(custom.isSystem, false, "absent/false must not default to true");
  assert.equal(custom.isDefault, false);
});
