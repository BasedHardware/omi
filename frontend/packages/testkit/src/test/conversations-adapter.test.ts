/**
 * Adapter conformance: the legacy backend's quirks are absorbed HERE, with
 * the documented gaps (no create; synthetic and possibly-incomplete /
 * status-filtered set versions; non-atomic multi-field patch across
 * query-param and body endpoints; explicit cascade=false on delete) proven
 * under test.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { ConversationOp } from "@omi-core/contracts";
import {
  conversationsTransport,
  fetchConversationIdSnapshot,
  sendConversationOp,
  wireToConversation,
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
  assert.equal(classifyStatus({ status: 402, json: null }, "x").kind, "permanent", "locked conversation → entitlement");
  assert.equal(classifyStatus({ status: 503, json: null }, "x").kind, "retryable");
  const odd = classifyStatus({ status: 418, json: null }, "x");
  assert.ok(odd.kind === "retryable" && odd.unclassified, "unknown statuses are a telemetered taxonomy gap, never a guess");
});

test("keyed patch: absent keys never reach the wire (issue-draft-02 class)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: ConversationOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
    patch: { starred: true },
  };
  await sendConversationOp(http, op);
  assert.equal(http.calls.length, 1, "only the touched field issues a request");
  assert.equal(http.calls[0]!.method, "PATCH");
  assert.ok(http.calls[0]!.path.endsWith("/amber-fox-ridge/starred?starred=true"));
  assert.equal(http.calls[0]!.body, undefined, "no title/visibility/folderId defaults smuggled in");
});

test("multi-field patch fans out to query-param and body endpoints in a fixed order", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} }, { status: 200, json: {} }, { status: 200, json: {} }, { status: 200, json: {} });
  const op: ConversationOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
    patch: {
      title: "standup notes",
      starred: false,
      visibility: "public",
      folderId: "folder-1",
    },
  };
  const result = await sendConversationOp(http, op);
  assert.ok(result.ok);
  assert.equal(http.calls.length, 4, "one legacy request per touched field — conversations has no combined PATCH");
  assert.equal(http.calls[0]!.method, "PATCH");
  assert.ok(http.calls[0]!.path.endsWith("/amber-fox-ridge/title?title=standup%20notes"));
  assert.equal(http.calls[0]!.body, undefined, "title is a query param, not a JSON body");
  assert.ok(http.calls[1]!.path.endsWith("/amber-fox-ridge/starred?starred=false"));
  assert.equal(http.calls[1]!.body, undefined);
  assert.ok(http.calls[2]!.path.endsWith("/amber-fox-ridge/visibility?value=public"));
  assert.equal(http.calls[2]!.body, undefined);
  assert.ok(http.calls[3]!.path.endsWith("/amber-fox-ridge/folder"));
  assert.deepEqual(http.calls[3]!.body, { folder_id: "folder-1" }, "folderId is the sole JSON-body patch step");
});

test("multi-field patch stops at the first failure (no server-side transaction to fall back on)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 422, json: null }, { status: 200, json: {} });
  const op: ConversationOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
    patch: { title: "bad", starred: true },
  };
  const result = await sendConversationOp(http, op);
  assert.equal(result.ok, false);
  assert.equal(http.calls.length, 1, "the starred request never fires once title failed");
});

test("query-param patches never send a JSON body; folderId null clears via body", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} }, { status: 200, json: {} });
  await sendConversationOp(http, {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
    patch: { visibility: "shared", folderId: null },
  });
  assert.ok(http.calls[0]!.path.endsWith("/amber-fox-ridge/visibility?value=shared"));
  assert.equal(http.calls[0]!.body, undefined);
  assert.ok(http.calls[1]!.path.endsWith("/amber-fox-ridge/folder"));
  assert.deepEqual(http.calls[1]!.body, { folder_id: null }, "explicit null is a clear, not an absent key");
});

test("delete sends cascade=false explicitly and treats already-gone as success", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 404, json: null });
  const result = await sendConversationOp(http, {
    op: "delete",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
  });
  assert.ok(result.ok, "replaying a delete after a crash must not dead-letter");
  assert.equal(http.calls[0]!.method, "DELETE");
  assert.ok(http.calls[0]!.path.includes("amber-fox-ridge"));
  assert.ok(http.calls[0]!.path.endsWith("?cascade=false"), "cascade pinned to today's runtime default");
});

test("id snapshot synthesizes a stable set version and is honest about incompleteness", async () => {
  const http = new ScriptedHttp();
  http.respond(
    { status: 200, json: [{ id: "b" }, { id: "a" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }, { id: "c" }] },
  );
  const s1 = await fetchConversationIdSnapshot(http, 500);
  const s2 = await fetchConversationIdSnapshot(http, 500);
  const s3 = await fetchConversationIdSnapshot(http, 500);
  assert.ok(s1 && s2 && s3);
  assert.equal(
    s1.complete,
    false,
    "architect ruling 2026-08-07: the list endpoint filters by default statuses, so even a short page may NEVER claim completeness — reconcile would delete the filtered-out (in_progress/merging/failed) conversations locally",
  );
  assert.equal(s1.setVersion, s2.setVersion, "order-independent");
  assert.notEqual(s1.setVersion, s3.setVersion, "content-sensitive");
  assert.equal(http.calls[0]!.method, "GET");
  assert.ok(http.calls[0]!.path.includes("limit=500"));
  assert.ok(http.calls[0]!.path.includes("offset=0"));

  const http2 = new ScriptedHttp();
  http2.respond({ status: 200, json: [{ id: "a" }, { id: "b" }] });
  const full = await fetchConversationIdSnapshot(http2, 2);
  assert.ok(full);
  assert.equal(full.complete, false, "a full page never claims completeness — there is no ids-only endpoint to confirm it");
});

test("transport send round-trips a patch op (no create path exists for this domain)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const aliases: Array<[string, string]> = [];
  const transport = conversationsTransport(http, (local, server) => aliases.push([local, server]));
  const domainOp: ConversationOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as ConversationOp["id"],
    at: 1,
    patch: { starred: true },
  };
  const result = await transport.send({
    opId: "o1",
    domain: "conversations",
    recordId: "amber-fox-ridge",
    payload: JSON.stringify(domainOp),
    summary: "patch: starred",
    attempts: 0,
  });
  assert.ok(result.ok);
  assert.deepEqual(aliases, [], "no create → alias hook never fires");
});

test("wire rows parse legacy UUID ids and reject junk", () => {
  const good = wireToConversation({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    structured: { title: "t", overview: "o" },
    visibility: "private",
  });
  assert.ok(good);
  assert.equal(good.title, "t");
  assert.equal(good.overview, "o");
  assert.equal(wireToConversation({ id: "<script>", structured: { title: "t" } }), null);
});

test("wire rows never collapse starred/discarded/isLocked defaults or shared visibility", () => {
  const bare = wireToConversation({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    structured: {},
  });
  assert.ok(bare);
  assert.equal(bare.starred, false, "absent starred is false, not smuggled true");
  assert.equal(bare.discarded, false);
  assert.equal(bare.isLocked, false);
  assert.equal(bare.folderId, null, "absent folder_id stays null — not a default folder id");
  assert.equal(bare.visibility, "private");

  const shared = wireToConversation({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    structured: {},
    visibility: "shared",
    starred: true,
    discarded: true,
    is_locked: true,
    folder_id: "f1",
  });
  assert.ok(shared);
  assert.equal(shared.visibility, "shared", "shared is a real third visibility, not collapsed to private/public");
  assert.equal(shared.starred, true);
  assert.equal(shared.discarded, true);
  assert.equal(shared.isLocked, true);
  assert.equal(shared.folderId, "f1");
});

test("wire rows pull title/overview from structured — top-level title is ignored", () => {
  const row = wireToConversation({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    title: "WRONG",
    structured: { title: "correct", overview: "from structured" },
  });
  assert.ok(row);
  assert.equal(row.title, "correct");
  assert.equal(row.overview, "from structured");
});
