/**
 * ChatMessagesStore + platform chat adapter: ADR-005 write contract on the
 * wire, 409 identity-conflict dead-lettering, payload-hash idempotency,
 * keyed rating patches, and incomplete-snapshot honesty.
 *
 * Hermetic: ManualEnv + MemoryStore + ScriptedHttp only.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { ChatMessage, RecordId } from "@omi-core/contracts";
import {
  ChatMessagesStore,
  chatMessagePayloadHash,
  chatMessagesCodec,
} from "@omi-core/domain";
import { ManualEnv, MemoryStore, ScriptedHttp } from "../fakes.js";

function wireMessage(
  id: string,
  text: string,
  extras: Partial<{
    sender: string;
    rating: number | null;
    reported: boolean;
    journalRevision: number;
    payloadHash: string;
  }> = {},
): Record<string, unknown> {
  return {
    id,
    text,
    sender: extras.sender ?? "human",
    type: "text",
    createdAt: 1_704_067_200_000,
    updatedAt: 1_704_067_200_000,
    journalRevision: extras.journalRevision ?? 1,
    payloadHash:
      extras.payloadHash ??
      chatMessagePayloadHash({
        text,
        sender: extras.sender ?? "human",
        appId: null,
        sessionId: null,
        metadata: null,
        messageSource: "desktop_chat",
        attachmentIds: [],
      }),
    messageSource: "desktop_chat",
    rating: extras.rating === undefined ? null : extras.rating,
    reported: extras.reported ?? false,
    generationOutcome: extras.sender === "ai" ? "completed" : null,
    appId: null,
    chatSessionId: null,
    revision: `revision-${id}`,
    attachments: [],
  };
}

function historyEnvelope(
  messages: readonly Record<string, unknown>[],
  olderCursor: string | null = null,
): Record<string, unknown> {
  return {
    messages,
    page: { olderCursor, hasOlder: olderCursor !== null },
    capabilities: {
      maxAttachmentsPerMessage: 4,
      maxAttachmentBytes: 50_000_000,
      allowedAttachmentMimeTypes: ["application/pdf"],
    },
  };
}

function successfulSend(id: string, text: string): { status: number; json: null; text: string } {
  const human = wireMessage(id, text);
  const assistant = wireMessage(`assistant-${id}`, "Canonical answer", { sender: "ai" });
  return {
    status: 201,
    json: null,
    text: [
      "event: accepted",
      "id: event-accepted",
      `data: ${JSON.stringify({ kind: "accepted", message: human, generation: { id: `generation-${id}` } })}`,
      "",
      "event: done",
      "id: event-done",
      `data: ${JSON.stringify({ kind: "done", message: assistant })}`,
      "",
      "",
    ].join("\n"),
  };
}

test("409 identity conflict dead-letters and is never retried", async () => {
  // red-proof: in packages/adapters-platform/src/chat.ts create branch, replace
  // the `res.status === 409` foldIdentityConflict return with
  // `{ ok: false, failure: { kind: "retryable", detail: "409" } }` — the
  // outbox then retries and POST count grows past 1 / dead letter stays empty.
  // APPLIED 2026-08-08: observed
  //   AssertionError: exactly one attempt — 409 must never retry
  //   5 !== 1
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 409, json: { detail: "client_message_id payload conflict" } });
  await store.send("conflicting payload");
  await env.advance(700_000); // past every backoff step

  const posts = http.calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 1, "exactly one attempt — 409 must never retry");
  const dead = await store.deadLetters();
  assert.equal(dead.length, 1, "identity conflict is user-visible (dead)");
  assert.equal(dead[0]!.failure.kind, "permanent");
  assert.equal(dead[0]!.failure.reason, "conflict");
  assert.match(dead[0]!.summary, /^Send chat:/, "dead letter retains the send summary");
  assert.equal(store.pendingCount(), 0, "op left the pending queue");
});

test("403 forbidden is a permanent chat send outcome, never an auth pause", async () => {
  // red-proof: delegate Chat 403 to the shared classifyStatus taxonomy. The
  // outbox pauses with one pending op and creates no user-visible dead letter.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  http.respond({
    status: 403,
    json: { error: { code: "forbidden", retryable: false } },
  });
  await store.send("not allowed in this authorization context");
  await env.advance(10);

  assert.equal(store.pendingCount(), 0, "forbidden send is terminal and leaves the queue");
  assert.equal(store.status().queue.phase, "idle", "403 must not pause Chat for reauthentication");
  const dead = await store.deadLetters();
  assert.equal(dead.length, 1, "the permanent forbidden outcome remains user-visible");
  assert.equal(dead[0]?.failure.kind, "permanent");
});

test("the same op replayed produces the same payload hash and does not duplicate a message", async () => {
  // red-proof: rebuild attachmentIds instead of replaying the journaled op.
  // The whole-body equality and derived hash equality below both fail.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  await store.send("hello once", ["attachment-1"]);
  const localId = (await store.list())[0]!.id;
  // First attempt fails retryably so the SAME pending op is resent.
  http.respond({ status: 503, json: null });
  http.respond(successfulSend(localId, "hello once"));
  await env.advance(10_000); // first send (503) + backoff + retry (200)

  const posts = http.calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 2, "retryable failure causes a second send of the same op");
  assert.deepEqual(posts[0]!.body, posts[1]!.body, "retry replays the exact authored operation");
  const body1 = posts[0]!.body as Extract<import("@omi-core/contracts").ChatMessageOp, { op: "create" }>;
  const body2 = posts[1]!.body as Extract<import("@omi-core/contracts").ChatMessageOp, { op: "create" }>;
  const hash1 = chatMessagePayloadHash({
    text: body1.text,
    sender: body1.sender,
    appId: body1.appId ?? null,
    sessionId: body1.chatSessionId ?? null,
    metadata: body1.metadata ?? null,
    messageSource: body1.messageSource ?? "desktop_chat",
    attachmentIds: body1.attachmentIds,
  });
  const hash2 = chatMessagePayloadHash({
    text: body2.text,
    sender: body2.sender,
    appId: body2.appId ?? null,
    sessionId: body2.chatSessionId ?? null,
    metadata: body2.metadata ?? null,
    messageSource: body2.messageSource ?? "desktop_chat",
    attachmentIds: body2.attachmentIds,
  });
  assert.equal(hash1, hash2, "identical create payload must hash identically across retries");
  assert.match(hash1, /^sha256:[a-f0-9]{64}$/);

  assert.equal(body1.id, body2.id, "client message id is stable across retries");
  assert.equal(body1.id, localId, "wire id IS the local record id");
  assert.deepEqual(body1.attachmentIds, ["attachment-1"]);

  assert.equal(body1.journalRevision, body2.journalRevision, "journal revision is durable");

  // Content, not row count: one local identity, one text — replay must not mint a second row.
  const rows = await store.list();
  assert.equal(rows.map((r) => r.id).join(","), localId);
  assert.equal(rows.map((r) => r.text).join(","), "hello once");
});

test("the adapter never invents an unratified rating route", async () => {
  // red-proof: restore the provisional per-message PATCH. A PATCH appears in
  // the call log and the dead-letter assertion fails.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  const id = "amber-fox-ridge" as RecordId;
  http.respond({
    status: 200,
    json: historyEnvelope([wireMessage(id, "keep this text", { sender: "ai", reported: true })]),
  });
  http.respond({
    status: 200,
    json: historyEnvelope([wireMessage(id, "keep this text", { sender: "ai", reported: true })]),
  });
  await store.refresh();

  await store.rate(id, 1);
  await env.advance(10);
  assert.equal(http.calls.some((call) => call.method === "PATCH"), false);
  const dead = await store.deadLetters();
  assert.equal(dead.length, 1);
  assert.match(dead[0]!.failure.detail, /does not define patch/);
});

test("reconcile never deletes a local row against a complete:false snapshot", async () => {
  // red-proof: in packages/adapters-platform/src/chat.ts
  // `fetchChatMessageIdSnapshot`, change `complete: false` to `complete: true`.
  // Refresh then deletes the local-only row and this assertion fails on the
  // surviving id content.
  // APPLIED 2026-08-08: observed
  //   AssertionError: incomplete snapshot must never delete a local row
  //   expected true actual false
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  await store.send("local only survivor");
  const localId = (await store.list())[0]!.id;
  http.respond(successfulSend(localId, "local only survivor"));
  await env.advance(10);

  // Server page omits our message — complete:false must not delete it.
  http.respond({
    status: 200,
    json: historyEnvelope([wireMessage("other-server-msg", "someone else")]),
  });
  http.respond({
    status: 200,
    json: historyEnvelope([wireMessage("other-server-msg", "someone else")]),
  });
  await store.refresh();

  const rows = await store.list();
  const byId = new Map(rows.map((r) => [r.id, r]));
  assert.ok(byId.has(localId), "incomplete snapshot must never delete a local row");
  assert.equal(byId.get(localId)!.text, "local only survivor", "local content survives incomplete reconcile");
  assert.equal(byId.get("other-server-msg" as RecordId)?.text, "someone else", "server rows still upsert");
});

test("junk or non-200 reconcile body yields null snapshot — never an empty complete wipe", async () => {
  // red-proof: in fetchChatMessageReconcilePage, change the junk-body null
  // return to `{ messages: [], nextCursor: null, hasMore: false }` AND set
  // snapshot `complete: true` — refresh then wipes local rows.
  // APPLIED: paired with the complete:false red-proof above.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  await store.send("must survive junk snapshot");
  const localId = (await store.list())[0]!.id;
  http.respond(successfulSend(localId, "must survive junk snapshot"));
  await env.advance(10);

  http.respond({ status: 200, json: { unexpected: true } }); // rows fetch junk → null
  http.respond({ status: 200, json: null }); // snapshot path junk → null
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.map((r) => r.id).join(","), localId);
  assert.equal(rows[0]!.text, "must survive junk snapshot");
});

test("ratified create envelope carries the full authored operation", async () => {
  // red-proof: translate the ratified body back to snake_case or omit the
  // attachment list. The assertions below fail.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  await store.send("wire contract", ["attachment-1"]);
  const localId = (await store.list())[0]!.id;
  http.respond(successfulSend(localId, "wire contract"));
  await env.advance(10);

  const body = http.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
  assert.equal(body["id"], localId);
  assert.equal(body["journalRevision"], 1);
  assert.deepEqual(body["attachmentIds"], ["attachment-1"]);
  assert.equal(body["client_message_id"], undefined);
  assert.equal(body["client_message_payload_hash"], undefined);
  assert.equal(body["sender"], "human");
  assert.equal(body["text"], "wire contract");
});

test("codec keyed patch: rating-only overlay preserves text and reported", () => {
  // Companion to the store-level rating test — pins the codec mechanism itself.
  // red-proof: same setdefault mutation as the store rating test.
  const seeded: ChatMessage = {
    id: "x" as RecordId,
    text: "keep",
    sender: "ai",
    type: "text",
    createdAt: 1,
    updatedAt: 1,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:abc",
    messageSource: "desktop_chat",
    rating: null,
    reported: true,
    generationOutcome: "completed",
    attachments: [],
    revision: null,
  };
  const next = chatMessagesCodec.applyOp(
    JSON.stringify({ op: "patch", opId: "o", id: "x", at: 2, patch: { rating: -1 } }),
    seeded,
  );
  assert.ok(next);
  assert.equal(next.text, "keep");
  assert.equal(next.reported, true);
  assert.equal(next.rating, -1);
});
