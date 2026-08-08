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
    journal_revision: number;
    client_message_payload_hash: string;
  }> = {},
): Record<string, unknown> {
  return {
    id,
    text,
    sender: extras.sender ?? "human",
    type: "text",
    created_at: "2024-01-01T00:00:00.000Z",
    updated_at: "2024-01-01T00:00:00.000Z",
    journal_revision: extras.journal_revision ?? 1,
    client_message_payload_hash:
      extras.client_message_payload_hash ??
      chatMessagePayloadHash({
        text,
        sender: extras.sender ?? "human",
        appId: null,
        sessionId: null,
        metadata: null,
        messageSource: "desktop_chat",
      }),
    message_source: "desktop_chat",
    rating: extras.rating === undefined ? null : extras.rating,
    reported: extras.reported ?? false,
    app_id: null,
    chat_session_id: null,
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

test("the same op replayed produces the same payload hash and does not duplicate a message", async () => {
  // red-proof: in packages/adapters-platform/src/chat.ts create body, change
  // `client_message_payload_hash: payloadHash` to
  // `client_message_payload_hash: payloadHash + ":" + String(Math.random())`
  // — the two POST bodies then disagree on the hash field.
  // APPLIED 2026-08-08: observed
  //   AssertionError: identical create payload must hash identically across retries
  //   + 'sha256:…:0.219…' - 'sha256:…:0.441…'
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  // First attempt fails retryably so the SAME pending op is resent.
  http.respond({ status: 503, json: null });
  http.respond({ status: 200, json: {} });

  await store.send("hello once");
  const localId = (await store.list())[0]!.id;
  await env.advance(10_000); // first send (503) + backoff + retry (200)

  const posts = http.calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 2, "retryable failure causes a second send of the same op");
  const hash1 = (posts[0]!.body as { client_message_payload_hash: string }).client_message_payload_hash;
  const hash2 = (posts[1]!.body as { client_message_payload_hash: string }).client_message_payload_hash;
  assert.equal(hash1, hash2, "identical create payload must hash identically across retries");
  assert.match(hash1, /^sha256:[a-f0-9]{64}$/);

  const id1 = (posts[0]!.body as { client_message_id: string }).client_message_id;
  const id2 = (posts[1]!.body as { client_message_id: string }).client_message_id;
  assert.equal(id1, id2, "client_message_id is stable across retries");
  assert.equal(id1, localId, "wire client_message_id IS the local record id");

  const rev1 = (posts[0]!.body as { journal_revision: number }).journal_revision;
  const rev2 = (posts[1]!.body as { journal_revision: number }).journal_revision;
  assert.equal(rev1, rev2, "journal_revision is part of the durable op, not regenerated");

  // Content, not row count: one local identity, one text — replay must not mint a second row.
  const rows = await store.list();
  assert.equal(rows.map((r) => r.id).join(","), localId);
  assert.equal(rows.map((r) => r.text).join(","), "hello once");
});

test("a keyed rating patch leaves other fields untouched", async () => {
  // red-proof: in packages/domain/src/chat-codec.ts patch branch, replace the
  // keyed `if (p.rating !== undefined) next.rating = p.rating` with
  // setdefaults `next.rating = p.rating ?? null; next.text = ""; next.reported = false`
  // — fails with `absent keys must not clear text` ("" !== "keep this text").
  // APPLIED 2026-08-08: observed
  //   AssertionError: absent keys must not clear text
  //   + '' - 'keep this text'
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  const id = "amber-fox-ridge" as RecordId;
  http.respond({
    status: 200,
    json: {
      messages: [wireMessage(id, "keep this text", { sender: "ai", rating: null, reported: true })],
      next_cursor: null,
      has_more: false,
    },
  });
  http.respond({
    status: 200,
    json: {
      messages: [wireMessage(id, "keep this text", { sender: "ai", rating: null, reported: true })],
      next_cursor: null,
      has_more: false,
    },
  });
  await store.refresh();

  http.respond({ status: 200, json: { status: "ok" } });
  await store.rate(id, 1);
  const optimistic = await store.list();
  assert.equal(optimistic.length, 1);
  assert.equal(optimistic[0]!.text, "keep this text", "absent keys must not clear text");
  assert.equal(optimistic[0]!.reported, true, "absent keys must not clear reported");
  assert.equal(optimistic[0]!.rating, 1, "rating is the only field the patch may change");
  assert.equal(optimistic[0]!.sender, "ai");

  await env.advance(10);
  const patchCall = http.calls.find((c) => c.method === "PATCH")!;
  assert.deepEqual(patchCall.body, { rating: 1 }, "wire body is keyed — no smuggled defaults");
  assert.ok(
    patchCall.path.endsWith(`/${id}/rating`),
    `rating patch hits the rating endpoint, got ${patchCall.path}`,
  );
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

  http.respond({ status: 200, json: { id: "will-be-same" } });
  await store.send("local only survivor");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  // Server page omits our message — complete:false must not delete it.
  http.respond({
    status: 200,
    json: {
      messages: [wireMessage("other-server-msg", "someone else")],
      next_cursor: null,
      has_more: false,
    },
  });
  http.respond({
    status: 200,
    json: {
      messages: [wireMessage("other-server-msg", "someone else")],
      next_cursor: null,
      has_more: false,
    },
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

  http.respond({ status: 200, json: {} });
  await store.send("must survive junk snapshot");
  await env.advance(10);
  const localId = (await store.list())[0]!.id;

  http.respond({ status: 200, json: { unexpected: true } }); // rows fetch junk → null
  http.respond({ status: 200, json: null }); // snapshot path junk → null
  await store.refresh();

  const rows = await store.list();
  assert.equal(rows.map((r) => r.id).join(","), localId);
  assert.equal(rows[0]!.text, "must survive junk snapshot");
});

test("ADR-005 create wire shape carries client_message_id, journal_revision, and payload hash", async () => {
  // red-proof: omit `client_message_id` from the create body — assertion on
  // body.client_message_id fails.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http);

  http.respond({ status: 200, json: {} });
  await store.send("wire contract");
  const localId = (await store.list())[0]!.id;
  await env.advance(10);

  const body = http.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
  assert.equal(body["client_message_id"], localId);
  assert.equal(body["journal_revision"], 1);
  assert.equal(
    body["client_message_payload_hash"],
    chatMessagePayloadHash({
      text: "wire contract",
      sender: "human",
      appId: null,
      sessionId: null,
      metadata: null,
      messageSource: "desktop_chat",
    }),
  );
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
