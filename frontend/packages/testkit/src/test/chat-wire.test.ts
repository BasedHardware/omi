/**
 * Ratified Chat wire red-proofs.
 *
 * The fixtures below are copied from the vendored wire proposal plus David's
 * attachment/cancellation ratification. They intentionally exercise the real
 * adapter rather than a second request builder.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import type {
  ChatAcceptedFrame,
  ChatAttachment,
  ChatCompletedAssistantMessage,
  ChatHistoryPageWire,
  ChatHumanMessage,
  ChatMessage,
  ChatMessageOp,
  ChatTerminalFrame,
  RecordId,
} from "@omi-core/contracts";
import {
  PLATFORM_CHAT_ATTACHMENTS_PATH,
  PLATFORM_CHAT_MESSAGES_PATH,
  cancelChatGeneration,
  fetchChatMessageReconcilePage,
  sendChatMessageOp,
  platformChatGenerationEventsPath,
  platformChatGenerationPath,
  wireToChatHistoryEnvelope,
  wireToChatMessage,
} from "@omi-core/adapters-platform";
import { chatMessagePayloadHash } from "@omi-core/kernel";
import { ScriptedHttp } from "../fakes.js";

function canonicalMessage(
  id: string,
  sender: "human",
  text: string,
  attachments?: readonly ChatAttachment[],
): ChatHumanMessage;
function canonicalMessage(
  id: string,
  sender: "ai",
  text: string,
  attachments?: readonly ChatAttachment[],
): ChatCompletedAssistantMessage;
function canonicalMessage(
  id: string,
  sender: "human" | "ai",
  text: string,
  attachments: readonly ChatAttachment[] = [],
): ChatMessage {
  const fields = {
    id: id as RecordId,
    text,
    type: "text" as const,
    createdAt: 1_786_352_400_000,
    updatedAt: 1_786_352_400_000,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:fixture",
    messageSource: "desktop_chat",
    rating: null,
    reported: false,
    revision: `revision-${id}`,
    attachments,
  };
  return sender === "human"
    ? { ...fields, sender, generationOutcome: null }
    : { ...fields, sender, generationOutcome: "completed" };
}

test("attachment metadata survives absent content and round-trips", () => {
  // red-proof: make ChatAttachment.contentReference required to be a string,
  // or make any durable metadata field optional. The null fixture or the
  // negative compiler assertion below then fails compilation.
  const expired: ChatAttachment = {
    id: "attachment-opaque-01",
    displayName: "handoff.pdf",
    mediaType: "application/pdf",
    sizeBytes: 12_345,
    contentReference: null,
  };
  const message = canonicalMessage("client-message-01", "human", "Read this", [expired]);
  const roundTripped = wireToChatMessage(JSON.parse(JSON.stringify(message)));
  assert.deepEqual(roundTripped?.attachments, [expired]);

  // @ts-expect-error durable displayName/mediaType/sizeBytes metadata is mandatory
  const missingDurableMetadata: ChatAttachment = {
    id: "attachment-opaque-02",
    contentReference: null,
  };
  assert.equal(missingDurableMetadata.contentReference, null);
});

test("an empty attachment content reference rejects the containing message", () => {
  // red-proof: permit `contentReference === ""` in wireToChatAttachment. The
  // malformed row below is accepted as a third semantic state beside an opaque
  // reference and null.
  const message = canonicalMessage("client-message-empty-reference", "human", "Read this", [
    {
      id: "attachment-opaque-01",
      displayName: "handoff.pdf",
      mediaType: "application/pdf",
      sizeBytes: 12_345,
      contentReference: "",
    },
  ]);

  assert.equal(
    wireToChatMessage(message),
    null,
    "empty is neither an opaque content reference nor the ratified null expiry state",
  );
});

test("a history page with duplicate message ids is rejected intact", () => {
  // red-proof: change the duplicate branch in wireToChatHistoryEnvelope back
  // to `continue`. The malformed two-row page is silently accepted as one row.
  const duplicate = canonicalMessage("amber-fox-ridge", "human", "First copy");
  const envelope = {
    messages: [duplicate, { ...duplicate, text: "Conflicting duplicate" }],
    page: { olderCursor: null, hasOlder: false },
    capabilities: {
      maxAttachmentsPerMessage: 4,
      maxAttachmentBytes: 50_000_000,
      allowedAttachmentMimeTypes: ["application/pdf"],
    },
  };

  assert.equal(
    wireToChatHistoryEnvelope(envelope),
    null,
    "duplicate-free keyset history is a page invariant, not a lossy dedupe request",
  );
});

test("cancelled and completed terminals are distinct and cancellation retains the partial", () => {
  // red-proof: remove the cancelled arm or make its message nullable. This
  // construction or the retained-partial read stops compiling.
  const partial = {
    ...canonicalMessage("assistant-partial-01", "ai", "The retained partial"),
    generationOutcome: "cancelled" as const,
  };
  const cancelled: ChatTerminalFrame = { kind: "cancelled", message: partial };
  const completed: ChatTerminalFrame = {
    kind: "done",
    message: canonicalMessage("assistant-complete-01", "ai", "The complete answer"),
  };
  assert.notEqual(cancelled.kind, completed.kind);
  assert.equal(cancelled.message.text, "The retained partial");
});

test("exported chat types exclude illegal message, terminal, and page states", () => {
  const human = canonicalMessage("human-contract-state", "human", "Question");
  const completed = canonicalMessage("assistant-contract-state", "ai", "Answer");

  const acceptedAi: ChatAcceptedFrame = {
    kind: "accepted",
    // @ts-expect-error accepted frames carry a canonical human message only
    message: completed,
    generation: { id: "generation-01" },
  };
  // @ts-expect-error done frames carry a completed canonical assistant message only
  const doneHuman: ChatTerminalFrame = { kind: "done", message: human };
  // @ts-expect-error cancelled frames require generationOutcome=cancelled
  const cancelledCompleted: ChatTerminalFrame = { kind: "cancelled", message: completed };
  // @ts-expect-error an AI message cannot carry the human-only null outcome
  const aiWithoutTerminalOutcome: ChatMessage = { ...completed, generationOutcome: null };
  // @ts-expect-error hasOlder=true requires an opaque older cursor
  const missingOlderCursor: ChatHistoryPageWire = { hasOlder: true, olderCursor: null };

  assert.equal(acceptedAi.message.sender, "ai");
  assert.equal(doneHuman.kind, "done");
  assert.equal(cancelledCompleted.kind, "cancelled");
  assert.equal(aiWithoutTerminalOutcome.generationOutcome, null);
  assert.equal(missingOlderCursor.olderCursor, null);
});

test("idempotent send payload hash covers the ordered attachment id list", () => {
  // red-proof: omit attachmentIds from the canonical payload. The mutation
  // below then hashes identically and fails the final assertion.
  const payload = {
    text: "Read these",
    sender: "human",
    appId: null,
    sessionId: null,
    metadata: null,
    messageSource: "desktop_chat",
    attachmentIds: ["attachment-opaque-01", "attachment-opaque-02"],
  } as const;
  const id = "client-message-01";
  const replay = { id, hash: chatMessagePayloadHash(payload) };
  const sameReplay = { id, hash: chatMessagePayloadHash({ ...payload }) };
  const mutated = {
    id,
    hash: chatMessagePayloadHash({ ...payload, attachmentIds: ["attachment-opaque-02"] }),
  };
  assert.deepEqual(replay, sameReplay);
  assert.notEqual(replay.hash, mutated.hash);
});

test("adapter emits the ratified paths, envelope, keyset cursor, and canonical terminal", async () => {
  // red-proof: restore either provisional /v1/chat/messages path, translate
  // the create body to legacy snake_case, use cursor=, or treat the final delta
  // as done. The path/body/cursor/terminal assertions below fail respectively.
  const source = readFileSync(
    new URL("../../../adapters-platform/src/chat.ts", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(source, /\/v1\/chat\/messages(?:\/reconcile)?/);
  assert.equal(PLATFORM_CHAT_MESSAGES_PATH, "/v1/chat-messages");
  assert.equal(PLATFORM_CHAT_ATTACHMENTS_PATH, "/v1/chat-attachments");
  assert.equal(platformChatGenerationPath("generation/01"), "/v1/chat-generations/generation%2F01");
  assert.equal(
    platformChatGenerationEventsPath("generation/01"),
    "/v1/chat-generations/generation%2F01/events",
  );

  const human = canonicalMessage("client-message-01", "human", "Read this");
  const assistant = canonicalMessage("assistant-message-01", "ai", "Complete canonical answer");
  const http = new ScriptedHttp();
  http.respond({
    status: 201,
    json: null,
    text: [
      "event: accepted",
      "id: event-01",
      `data: ${JSON.stringify({ kind: "accepted", message: human, generation: { id: "generation-01" } })}`,
      "",
      "event: delta",
      "id: event-02",
      `data: ${JSON.stringify({ kind: "delta", text: "Complete canonical" })}`,
      "",
      "event: done",
      "id: event-03",
      `data: ${JSON.stringify({ kind: "done", message: assistant })}`,
      "",
      "",
    ].join("\n"),
  });

  const op: Extract<ChatMessageOp, { op: "create" }> = {
    op: "create",
    opId: "outbox-op-01",
    id: "client-message-01" as RecordId,
    at: 1_786_352_400_000,
    text: "Read this",
    sender: "human",
    journalRevision: 1,
    type: "text",
    appId: null,
    chatSessionId: null,
    messageSource: "desktop_chat",
    metadata: null,
    attachmentIds: ["attachment-opaque-01"],
  };
  const sent = await sendChatMessageOp(http, op);
  assert.equal(sent.ok, true);
  if (!sent.ok) return;
  assert.equal(sent.terminal.kind, "done");
  if (sent.terminal.kind !== "done") return;
  assert.equal(sent.terminal.message.text, "Complete canonical answer");
  assert.deepEqual(http.calls[0], { method: "POST", path: "/v1/chat-messages", body: op });

  http.respond({
    status: 200,
    json: {
      messages: [human],
      page: { olderCursor: "older-opaque-02", hasOlder: true },
      capabilities: {
        maxAttachmentsPerMessage: 4,
        maxAttachmentBytes: 50_000_000,
        allowedAttachmentMimeTypes: ["application/pdf"],
      },
    },
  });
  const page = await fetchChatMessageReconcilePage(http, {
    limit: 2,
    cursor: "older-opaque-01",
  });
  assert.equal(page?.nextCursor, "older-opaque-02");
  assert.equal(page?.hasMore, true);
  assert.equal(
    http.calls[1]?.path,
    "/v1/chat-messages?limit=2&olderCursor=older-opaque-01",
  );

  http.respond({
    status: 202,
    json: { cancellation: { state: "accepted" } },
  });
  assert.deepEqual(await cancelChatGeneration(http, "generation/01"), {
    ok: true,
    state: "accepted",
  });
  assert.deepEqual(http.calls[2], {
    method: "DELETE",
    path: "/v1/chat-generations/generation%2F01",
  });
});

test("a disconnected initiating stream reconnects by generation and Last-Event-ID", async () => {
  // red-proof: remove the reconnect branch from sendChatMessageOp. The call
  // either cannot accept the reconnect transport or returns malformed success
  // without issuing the ratified GET carrying the last observed event cursor.
  const human = canonicalMessage("client-message-reconnect", "human", "Keep going");
  const assistant = canonicalMessage("assistant-message-reconnect", "ai", "Recovered answer");
  const http = new ScriptedHttp();
  http.respond({
    status: 201,
    json: null,
    text: [
      "event: accepted",
      "id: event-accepted",
      `data: ${JSON.stringify({ kind: "accepted", message: human, generation: { id: "generation-reconnect" } })}`,
      "",
      "event: delta",
      "id: event-delta",
      `data: ${JSON.stringify({ kind: "delta", text: "Recovered" })}`,
      "",
      "",
    ].join("\n"),
  });
  const requests: Array<{
    method: "GET";
    path: string;
    headers: { "Last-Event-ID": string };
  }> = [];
  const reconnect = {
    async request(request: (typeof requests)[number]) {
      requests.push(request);
      return {
        status: 200,
        json: null,
        text: [
          "event: snapshot",
          "id: event-snapshot",
          `data: ${JSON.stringify({ kind: "snapshot", text: "Recovered" })}`,
          "",
          "event: done",
          "id: event-done",
          `data: ${JSON.stringify({ kind: "done", message: assistant })}`,
          "",
          "",
        ].join("\n"),
      };
    },
  };
  const op: Extract<ChatMessageOp, { op: "create" }> = {
    op: "create",
    opId: "outbox-op-reconnect",
    id: "client-message-reconnect" as RecordId,
    at: 1_786_352_400_000,
    text: "Keep going",
    sender: "human",
    journalRevision: 1,
    attachmentIds: [],
  };

  const sent = await sendChatMessageOp(http, op, reconnect);
  assert.equal(sent.ok, true);
  if (!sent.ok) return;
  assert.equal(sent.terminal.kind, "done");
  assert.deepEqual(requests, [{
    method: "GET",
    path: "/v1/chat-generations/generation-reconnect/events",
    headers: { "Last-Event-ID": "event-delta" },
  }]);
});
