/**
 * Adapter conformance: the legacy backend's quirks are absorbed HERE, with
 * the exact status→taxonomy mapping and the documented gaps (server-
 * assigned, content-hashed create ids; synthetic and possibly-incomplete
 * set versions; non-atomic multi-field patch) proven under test.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { MemoryOp } from "@omi-core/contracts";
import {
  classifyStatus,
  fetchMemoryIdSnapshot,
  memoriesTransport,
  sendMemoryOp,
  wireToMemory,
  type HttpClient,
  type HttpResponse,
} from "@omi-core/adapters-legacy";

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
  const op: MemoryOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as MemoryOp["id"],
    at: 1,
    patch: { visibility: "public" },
  };
  await sendMemoryOp(http, op);
  assert.equal(http.calls.length, 1, "only the touched field issues a request");
  assert.deepEqual(http.calls[0]!.body, { value: "public" }, "no content/userReview defaults smuggled in");
  assert.equal(http.calls[0]!.path, "/v3/memories/amber-fox-ridge/visibility");
});

test("multi-field patch fans out to the legacy per-field endpoints in a fixed order", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} }, { status: 200, json: {} });
  const op: MemoryOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as MemoryOp["id"],
    at: 1,
    patch: { content: "new text", visibility: "private" },
  };
  const result = await sendMemoryOp(http, op);
  assert.ok(result.ok);
  assert.equal(http.calls.length, 2, "one legacy request per touched field — memories has no combined PATCH");
  assert.equal(http.calls[0]!.path, "/v3/memories/amber-fox-ridge");
  assert.deepEqual(http.calls[0]!.body, { value: "new text" });
  assert.equal(http.calls[1]!.path, "/v3/memories/amber-fox-ridge/visibility");
  assert.deepEqual(http.calls[1]!.body, { value: "private" });
});

test("multi-field patch stops at the first failure (no server-side transaction to fall back on)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 422, json: null }, { status: 200, json: {} });
  const op: MemoryOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as MemoryOp["id"],
    at: 1,
    patch: { content: "new text", visibility: "private" },
  };
  const result = await sendMemoryOp(http, op);
  assert.equal(result.ok, false);
  assert.equal(http.calls.length, 1, "the visibility request never fires once content failed");
});

test("userReview patch is a query-param POST, not a JSON PATCH body", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: {} });
  const op: MemoryOp = {
    op: "patch",
    opId: "o1",
    id: "amber-fox-ridge" as MemoryOp["id"],
    at: 1,
    patch: { userReview: true },
  };
  await sendMemoryOp(http, op);
  assert.equal(http.calls[0]!.method, "POST");
  assert.equal(http.calls[0]!.path, "/v3/memories/amber-fox-ridge/review?value=true");
  assert.equal(http.calls[0]!.body, undefined, "no JSON body — the legacy review endpoint reads a query param");
});

test("create: server-assigned id is surfaced as an alias, not silently adopted", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: { id: "content-hash-123" } });
  const aliases: Array<[string, string]> = [];
  const transport = memoriesTransport(http, (local, server) => aliases.push([local, server]));
  const domainOp: MemoryOp = {
    op: "create",
    opId: "o1",
    id: "amber-fox-ridge" as MemoryOp["id"],
    at: 1,
    content: "the user lives in Denver",
  };
  const result = await transport.send({
    opId: "o1",
    domain: "memories",
    recordId: "amber-fox-ridge",
    payload: JSON.stringify(domainOp),
    summary: "create: the user lives in Denver",
    attempts: 0,
  });
  assert.ok(result.ok);
  assert.deepEqual(aliases, [["amber-fox-ridge", "content-hash-123"]]);
});

test("id snapshot synthesizes a stable set version and is honest about incompleteness", async () => {
  const http = new ScriptedHttp();
  http.respond(
    { status: 200, json: [{ id: "b" }, { id: "a" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }] },
    { status: 200, json: [{ id: "a" }, { id: "b" }, { id: "c" }] },
  );
  const s1 = await fetchMemoryIdSnapshot(http, 500);
  const s2 = await fetchMemoryIdSnapshot(http, 500);
  const s3 = await fetchMemoryIdSnapshot(http, 500);
  assert.ok(s1 && s2 && s3);
  assert.equal(s1.complete, true, "a short page under the requested limit means nothing was left unread");
  assert.equal(s1.setVersion, s2.setVersion, "order-independent");
  assert.notEqual(s1.setVersion, s3.setVersion, "content-sensitive");

  const http2 = new ScriptedHttp();
  http2.respond({ status: 200, json: [{ id: "a" }, { id: "b" }] });
  const full = await fetchMemoryIdSnapshot(http2, 2);
  assert.ok(full);
  assert.equal(full.complete, false, "a full page never claims completeness — there is no ids-only endpoint to confirm it");
});

test("delete of an already-gone record is success (idempotent replay-safety)", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 404, json: null });
  const result = await sendMemoryOp(http, { op: "delete", opId: "o1", id: "amber-fox-ridge" as MemoryOp["id"], at: 1 });
  assert.ok(result.ok, "replaying a delete after a crash must not dead-letter");
});

test("wire rows parse legacy UUID ids and reject junk", () => {
  const good = wireToMemory({
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    content: "d",
    category: "interesting",
    visibility: "private",
  });
  assert.ok(good);
  assert.equal(wireToMemory({ id: "<script>", content: "d" }), null);
});

test("wire rows never smuggle canonical-only defaults onto a keyed field: userReview stays a real tri-state", () => {
  const noReview = wireToMemory({ id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111", content: "d", user_review: null });
  assert.ok(noReview);
  assert.equal(noReview.userReview, null, "never defaulted to false — null means genuinely unreviewed");

  const rejected = wireToMemory({ id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111", content: "d", user_review: false });
  assert.ok(rejected);
  assert.equal(rejected.userReview, false, "an explicit false verdict is preserved, not collapsed to null");
});
