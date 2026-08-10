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
  ChatAdmissionEnvelope,
  ChatAttachment,
  ChatCompletedAssistantMessage,
  ChatGenerationFrame,
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
  admitChatMessageOp,
  cancelChatGeneration,
  fetchChatMessageReconcilePage,
  parseChatGenerationEventStream,
  platformChatGenerationEventsPath,
  platformChatGenerationPath,
  wireToChatHistoryEnvelope,
  wireToChatGenerationFrame,
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

  const admissionAi: ChatAdmissionEnvelope = {
    // @ts-expect-error admission envelopes carry a canonical human message only
    message: completed,
    generation: { id: "generation-01" },
  };
  const acceptedFrame: ChatGenerationFrame = {
    // @ts-expect-error admission is JSON and accepted is not a generation frame
    kind: "accepted",
  };
  // @ts-expect-error done frames carry a completed canonical assistant message only
  const doneHuman: ChatTerminalFrame = { kind: "done", message: human };
  // @ts-expect-error cancelled frames require generationOutcome=cancelled
  const cancelledCompleted: ChatTerminalFrame = { kind: "cancelled", message: completed };
  // @ts-expect-error an AI message cannot carry the human-only null outcome
  const aiWithoutTerminalOutcome: ChatMessage = { ...completed, generationOutcome: null };
  // @ts-expect-error hasOlder=true requires an opaque older cursor
  const missingOlderCursor: ChatHistoryPageWire = { hasOlder: true, olderCursor: null };

  assert.equal(admissionAi.message.sender, "ai");
  assert.equal(acceptedFrame.kind, "accepted");
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

test("JSON admission is finite and never opens or consumes generation SSE", async () => {
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
  const http = new ScriptedHttp();
  http.respond({
    status: 201,
    json: { message: human, generation: { id: "generation-01" } },
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
  const sent = await admitChatMessageOp(http, op);
  assert.equal(sent.ok, true);
  if (!sent.ok) return;
  assert.equal(sent.admission.message.id, human.id);
  assert.equal(sent.admission.generation.id, "generation-01");
  assert.deepEqual(http.calls[0], { method: "POST", path: "/v1/chat-messages", body: op });
  assert.equal(http.calls.length, 1, "POST admission cannot consume or wait on SSE");

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

test("accepted is rejected from generation SSE while duplicate ids apply each frame once", () => {
  const human = canonicalMessage("client-message-no-accepted", "human", "Question");
  const assistant = canonicalMessage("assistant-message-no-accepted", "ai", "Snapshot plus delta");
  assert.equal(
    wireToChatGenerationFrame({
      kind: "accepted",
      message: human,
      generation: { id: "generation-no-accepted" },
    }),
    null,
    "accepted belongs only to the JSON admission envelope",
  );

  const parsed = parseChatGenerationEventStream([
    "event: snapshot",
    "id: event-snapshot",
    `data: ${JSON.stringify({ kind: "snapshot", text: "Snapshot" })}`,
    "",
    "event: snapshot",
    "id: event-snapshot",
    `data: ${JSON.stringify({ kind: "snapshot", text: "duplicated snapshot" })}`,
    "",
    "event: delta",
    "id: event-delta",
    `data: ${JSON.stringify({ kind: "delta", text: " plus delta" })}`,
    "",
    "event: delta",
    "id: event-delta",
    `data: ${JSON.stringify({ kind: "delta", text: " duplicated delta" })}`,
    "",
    "event: done",
    "id: event-done",
    `data: ${JSON.stringify({ kind: "done", message: assistant })}`,
    "",
    "event: done",
    "id: event-done",
    `data: ${JSON.stringify({ kind: "done", message: assistant })}`,
    "",
    "",
  ].join("\n"));

  assert.deepEqual(
    parsed?.map((frame) => frame.kind === "snapshot" || frame.kind === "delta"
      ? { kind: frame.kind, text: frame.text }
      : { kind: frame.kind }),
    [
      { kind: "snapshot", text: "Snapshot" },
      { kind: "delta", text: " plus delta" },
      { kind: "done" },
    ],
  );
});

test("an exact replay admission reuses identities without coupling POST to observation", async () => {
  const human = canonicalMessage("client-message-replay", "human", "Same send");
  const http = new ScriptedHttp();
  http.respond({
    status: 200,
    json: { message: human, generation: { id: "generation-replay" } },
  });
  const op: Extract<ChatMessageOp, { op: "create" }> = {
    op: "create",
    opId: "outbox-op-replay",
    id: human.id,
    at: human.createdAt,
    text: human.text,
    sender: "human",
    journalRevision: human.journalRevision,
    attachmentIds: [],
  };

  const result = await admitChatMessageOp(http, op);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.admission.message.id, human.id);
  assert.equal(result.admission.generation.id, "generation-replay");
  assert.deepEqual(http.calls.map((call) => ({ method: call.method, path: call.path })), [
    { method: "POST", path: "/v1/chat-messages" },
  ]);
});

test("malformed or forbidden admission fails before any observer can open", async () => {
  const human = canonicalMessage("client-message-terminal-guard", "human", "Question");
  const op: Extract<ChatMessageOp, { op: "create" }> = {
    op: "create",
    opId: "outbox-op-terminal-guard",
    id: human.id,
    at: human.createdAt,
    text: human.text,
    sender: "human",
    journalRevision: human.journalRevision,
    attachmentIds: [],
  };
  const malformedHttp = new ScriptedHttp();
  malformedHttp.respond({ status: 201, json: { generation: { id: "missing-human" } } });
  const malformed = await admitChatMessageOp(malformedHttp, op);
  assert.equal(malformed.ok, false);
  if (!malformed.ok) assert.match(malformed.failure.detail, /malformed JSON admission/);

  const forbiddenHttp = new ScriptedHttp();
  forbiddenHttp.respond({
    status: 403,
    json: { error: { code: "forbidden", retryable: false } },
  });
  const forbidden = await admitChatMessageOp(forbiddenHttp, op);
  assert.equal(forbidden.ok, false);
  if (!forbidden.ok) assert.equal(forbidden.failure.kind, "permanent");
});
