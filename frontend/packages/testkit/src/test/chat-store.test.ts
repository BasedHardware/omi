/**
 * ChatMessagesStore + platform chat adapter: ADR-005 write contract on the
 * wire, 409 identity-conflict dead-lettering, payload-hash idempotency,
 * keyed rating patches, and incomplete-snapshot honesty.
 *
 * Hermetic: ManualEnv + MemoryStore + ScriptedHttp only.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  BridgePayloadStream,
  BridgeStreamOpenRequest,
  BridgeStreamPort,
  ChatMessage,
  HttpResponse,
  RecordId,
} from "@omi-core/contracts";
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

function successfulSend(id: string, text: string): readonly [HttpResponse] {
  const human = wireMessage(id, text);
  return [
    {
      status: 201,
      json: { message: human, generation: { id: `generation-${id}` } },
    },
  ];
}

function failedGenerationSend(id: string, text: string): readonly [HttpResponse] {
  const human = wireMessage(id, text);
  return [
    {
      status: 201,
      json: { message: human, generation: { id: `generation-${id}` } },
    },
  ];
}

function sseEvent(id: string, kind: string, value: unknown): string {
  return `event: ${kind}\nid: ${id}\ndata: ${JSON.stringify(value)}\n\n`;
}

function successfulGeneration(id: string): string {
  return (
    sseEvent("event-snapshot", "snapshot", { kind: "snapshot", text: "" }) +
    sseEvent("event-done", "done", {
      kind: "done",
      message: wireMessage(`assistant-${id}`, "Canonical answer", { sender: "ai" }),
    })
  );
}

function failedGeneration(): string {
  return (
    sseEvent("event-snapshot", "snapshot", { kind: "snapshot", text: "" }) +
    sseEvent("event-failed", "failed", {
      kind: "failed",
      error: { code: "provider_down", retryable: true },
    })
  );
}

function emptyCancelledGeneration(): string {
  return (
    sseEvent("event-snapshot", "snapshot", { kind: "snapshot", text: "" }) +
    sseEvent("event-cancelled", "cancelled", { kind: "cancelled", message: null })
  );
}

function agentRunEvent(
  generationId: string,
  eventId: string,
  sequence: number,
  kind: string,
  safeSummary: string,
  details: Readonly<Record<string, unknown>>,
): string {
  return sseEvent(eventId, kind, {
    runId: generationId,
    attemptId: "attempt-one",
    eventId,
    sequence,
    createdAt: 1_786_442_400_000 + sequence,
    kind,
    safeSummary,
    details,
  });
}

class StoreTestStream implements BridgePayloadStream {
  cancelled = false;

  constructor(
    readonly id: string,
    readonly channel: string,
    private readonly chunks: readonly string[],
    private readonly hangs: boolean,
  ) {}

  async *[Symbol.asyncIterator](): AsyncIterator<string> {
    for (const chunk of this.chunks) {
      if (this.cancelled) return;
      yield chunk;
    }
    if (this.hangs && !this.cancelled) await new Promise<void>(() => undefined);
  }

  cancel(): void {
    this.cancelled = true;
  }
}

class StoreTestStreamPort implements BridgeStreamPort {
  readonly opens: BridgeStreamOpenRequest[] = [];
  readonly streams: StoreTestStream[] = [];

  constructor(
    private readonly scripts: readonly { chunks: readonly string[]; hangs?: boolean }[],
  ) {}

  open(request: BridgeStreamOpenRequest): BridgePayloadStream {
    const script = this.scripts[this.opens.length];
    if (script === undefined) throw new Error("unexpected stream open");
    this.opens.push(request);
    const stream = new StoreTestStream(
      `store-stream-${this.opens.length}`,
      request.channel,
      script.chunks,
      script.hangs ?? false,
    );
    this.streams.push(stream);
    return stream;
  }
}

async function drainMicrotasks(): Promise<void> {
  for (let index = 0; index < 12; index += 1) await Promise.resolve();
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

test("POST admission drains the durable outbox while generation remains hanging", async () => {
  // red-proof: await observeChatGeneration from chatMessagesTransport before
  // returning admission. pendingCount stays 1 instead of reaching 0 while the
  // scripted generation remains open after two live deltas.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const streamPort = new StoreTestStreamPort([{
    chunks: [
      sseEvent("event-snapshot", "snapshot", { kind: "snapshot", text: "" }) +
      sseEvent("event-delta-1", "delta", { kind: "delta", text: "Live" }) +
      sseEvent("event-delta-2", "delta", { kind: "delta", text: " answer" }),
    ],
    hangs: true,
  }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streamPort);

  await store.send("show this immediately");
  const clientMessageId = (await store.list())[0]!.id;
  http.respond({
    status: 201,
    json: {
      message: wireMessage(clientMessageId, "show this immediately"),
      generation: { id: "generation-hanging" },
    },
  });
  await env.advance(10);
  await drainMicrotasks();

  assert.equal(store.pendingCount(), 0, "durable POST is acknowledged before generation terminal");
  assert.deepEqual(
    http.calls.map((call) => ({ method: call.method, path: call.path })),
    [{ method: "POST", path: "/v1/chat-messages" }],
    "observation neither replays POST nor asks bounded HttpClient for SSE",
  );
  assert.deepEqual(
    (await store.list()).map((message) => ({ id: message.id, sender: message.sender, text: message.text })),
    [{ id: clientMessageId, sender: "human", text: "show this immediately" }],
    "canonical admitted human row is durable while assistant remains advisory",
  );
  assert.deepEqual(store.activeGenerations(), [{
    generationId: "generation-hanging",
    clientMessageId,
    text: "Live answer",
    lastEventId: "event-delta-2",
    observationState: "streaming",
    failure: null,
  }]);
});

test("an admitted generation without a native stream fails explicitly and stays failed after reopen", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const store = await ChatMessagesStore.open(disk.openBridge("unsupported-stream"), env, http);

  await store.send("keep an unsupported stream honest");
  const clientMessageId = (await store.list())[0]!.id;
  http.respond(...successfulSend(clientMessageId, "keep an unsupported stream honest"));
  await env.advance(10);
  await drainMicrotasks();

  assert.deepEqual(store.activeGenerations(), [{
    generationId: `generation-${clientMessageId}`,
    clientMessageId,
    text: "",
    lastEventId: null,
    observationState: "failed",
    failure: "stream-unavailable",
  }], "missing native streaming support is terminal-looking, never a false active spinner");

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("unsupported-stream"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    reopened.activeGenerations(),
    store.activeGenerations(),
    "the bounded unsupported-stream state remains explicit across restart",
  );
});

test("two concurrent generation terminals append independently and survive reopen", async () => {
  const disk = new MemoryStore();
  const store = await ChatMessagesStore.open(
    disk.openBridge("concurrent-terminals"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  const terminalWriter = store as unknown as {
    recordGenerationTerminal(
      generationId: string,
      clientMessageId: RecordId,
      terminal: { kind: "failed"; error: { code: string; retryable: boolean } },
    ): Promise<void>;
  };

  await Promise.all([
    terminalWriter.recordGenerationTerminal(
      "generation-concurrent-one",
      "message-concurrent-one" as RecordId,
      { kind: "failed", error: { code: "provider_down", retryable: true } },
    ),
    terminalWriter.recordGenerationTerminal(
      "generation-concurrent-two",
      "message-concurrent-two" as RecordId,
      { kind: "failed", error: { code: "context_unavailable", retryable: false } },
    ),
  ]);

  const expected = [
    {
      generationId: "generation-concurrent-one",
      clientMessageId: "message-concurrent-one",
      terminal: { kind: "failed", error: { code: "provider_down", retryable: true } },
    },
    {
      generationId: "generation-concurrent-two",
      clientMessageId: "message-concurrent-two",
      terminal: { kind: "failed", error: { code: "context_unavailable", retryable: false } },
    },
  ];
  assert.deepEqual(await store.generationDeliveries(), expected);

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("concurrent-terminals"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    await reopened.generationDeliveries(),
    expected,
    "append-only per-generation records prevent whole-value lost updates across reopen",
  );
});

test("append-only terminal records retain the legacy whole-value snapshot during migration", async () => {
  const disk = new MemoryStore();
  const bridge = disk.openBridge("terminal-migration");
  const legacyKv = await bridge.openKv("chat-generation-deliveries");
  const legacy = {
    generationId: "generation-legacy",
    clientMessageId: "message-legacy",
    terminal: { kind: "failed", error: { code: "legacy_failure", retryable: false } },
  };
  await legacyKv.set("generation-deliveries", JSON.stringify([legacy]));
  const store = await ChatMessagesStore.open(bridge, new ManualEnv(), new ScriptedHttp());
  const terminalWriter = store as unknown as {
    recordGenerationTerminal(
      generationId: string,
      clientMessageId: RecordId,
      terminal: { kind: "failed"; error: { code: string; retryable: boolean } },
    ): Promise<void>;
  };
  await terminalWriter.recordGenerationTerminal(
    "generation-log",
    "message-log" as RecordId,
    { kind: "failed", error: { code: "new_failure", retryable: true } },
  );

  assert.deepEqual(await store.generationDeliveries(), [
    legacy,
    {
      generationId: "generation-log",
      clientMessageId: "message-log",
      terminal: { kind: "failed", error: { code: "new_failure", retryable: true } },
    },
  ]);
});

test("privacy-reduced agent activity persists in an append-only log and restores by generation", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const scripts: { chunks: readonly string[]; hangs?: boolean }[] = [];
  const streams = new StoreTestStreamPort(scripts);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("show agent activity");
  const clientMessageId = (await store.list())[0]!.id;
  const generationId = `generation-${clientMessageId}`;
  scripts.push(
    { chunks: [successfulGeneration(clientMessageId)] },
    { chunks: [
      agentRunEvent(generationId, "opaque-accepted", 1, "run_accepted", "Run accepted", {
        admissionId: "opaque-admission",
      }) +
      agentRunEvent(generationId, "opaque-capability", 2, "capability_receipt", "Local scripted adapter declared", {
        tier: "deterministic-scripted", adapter: "local-scripted", deterministic: true,
      }) +
      agentRunEvent(generationId, "opaque-terminal", 3, "terminal", "Run complete", {
        terminalOutcome: "completed", terminalCode: "completed", retryable: false, recoveryAction: null,
      }),
    ] },
  );
  http.respond(...successfulSend(clientMessageId, "show agent activity"));
  await env.advance(10);
  await drainMicrotasks();

  const timelines = store.agentRunTimelines();
  assert.equal(timelines.length, 1);
  assert.equal(timelines[0]?.observationState, "complete");
  assert.deepEqual(timelines[0]?.events.map((event) => event.kind), [
    "run_accepted", "capability_receipt", "terminal",
  ]);
  assert.doesNotMatch(
    JSON.stringify(timelines[0]?.events),
    /opaque-accepted|opaque-admission|opaque-capability|opaque-terminal|attempt-one/,
    "opaque transport and run identities never enter the UI event model",
  );

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("u"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    reopened.agentRunTimelines(),
    timelines,
    "safe timeline events restore from the append-only log without a whole-value rewrite",
  );
});

test("agent activity restore rejects partial, cursor-reused, and client-rebound timelines", async () => {
  const disk = new MemoryStore();
  const bridge = disk.openBridge("corrupt-agent-runs");
  const log = await bridge.openLog("chat-agent-run-events");
  const accepted = (sequence: number) => ({
    sequence,
    createdAt: 1_786_442_400_000 + sequence,
    kind: "run_accepted",
    safeSummary: "Run accepted",
    details: {},
  });
  const status = (sequence: number) => ({
    sequence,
    createdAt: 1_786_442_400_000 + sequence,
    kind: "status",
    safeSummary: "Generating",
    details: { status: "generating", progressPct: 50 },
  });
  const append = async (
    generationId: string,
    clientMessageId: string,
    eventId: string,
    event: Readonly<Record<string, unknown>>,
  ) => log.append(JSON.stringify({ generationId, clientMessageId, eventId, event }));

  await append("generation-valid", "message-valid", "event-valid-1", accepted(1));
  await append("generation-valid", "message-valid", "event-valid-2", status(2));
  await append("generation-reused", "message-reused", "event-same", accepted(1));
  await append("generation-reused", "message-reused", "event-same", status(2));
  await append("generation-rebound", "message-original", "event-rebound-1", accepted(1));
  await append("generation-rebound", "message-other", "event-rebound-2", status(2));
  await append("generation-partial", "message-partial", "event-partial-2", status(2));
  await append("generation-malformed", "message-malformed", "event-malformed-1", accepted(1));
  await append("generation-malformed", "message-malformed", "event-malformed-2", {
    ...status(2),
    safeSummary: "rawArguments: hidden",
  });

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("corrupt-agent-runs"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    reopened.agentRunTimelines().map((timeline) => ({
      generationId: timeline.generationId,
      clientMessageId: timeline.clientMessageId,
      eventKinds: timeline.events.map((event) => event.kind),
      lastEventId: timeline.lastEventId,
    })),
    [{
      generationId: "generation-valid",
      clientMessageId: "message-valid",
      eventKinds: ["run_accepted", "status"],
      lastEventId: "event-valid-2",
    }],
    "only one-client, unique-cursor, run-accepted-first timelines may reach the UI",
  );
});

test("observer failure durably leaves a non-streaming failed generation state", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const streams = new StoreTestStreamPort([{
    chunks: [sseEvent("event-delta", "delta", { kind: "delta", text: "unsafe" })],
  }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("keep observer failure honest");
  const clientMessageId = (await store.list())[0]!.id;
  http.respond(...successfulSend(clientMessageId, "keep observer failure honest"));
  await env.advance(10);
  await drainMicrotasks();

  assert.deepEqual(store.activeGenerations(), [{
    generationId: `generation-${clientMessageId}`,
    clientMessageId,
    text: "",
    lastEventId: null,
    observationState: "failed",
    failure: "observation-failed",
  }]);
  const reopened = await ChatMessagesStore.open(
    disk.openBridge("u"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    reopened.activeGenerations(),
    store.activeGenerations(),
    "observer failure remains terminal-looking after restart instead of resuming as streaming",
  );
});

test("an admitted human send and a failed assistant generation remain two visible store facts", async () => {
  // red-proof: omit generation-terminal delivery from chatMessagesTransport.
  // The outbox still confirms the human row and drains, but the store has no
  // generationDeliveries surface on which to expose provider_down/retryable.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const streams = new StoreTestStreamPort([{ chunks: [failedGeneration()] }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("answer even during an outage");
  const clientMessageId = (await store.list())[0]!.id;
  http.respond(...failedGenerationSend(clientMessageId, "answer even during an outage"));
  await env.advance(10);
  await drainMicrotasks();

  assert.equal(store.pendingCount(), 0, "the admitted human operation is honestly confirmed");
  assert.deepEqual(
    (await store.list()).map((message) => ({ sender: message.sender, text: message.text })),
    [{ sender: "human", text: "answer even during an outage" }],
    "the confirmed human message remains in the thread",
  );

  const observed = store as unknown as {
    generationDeliveries?: () => Promise<readonly {
      generationId: string;
      clientMessageId: string;
      terminal: { kind: string; error?: { code: string; retryable: boolean } };
    }[]>;
  };
  assert.equal(
    typeof observed.generationDeliveries,
    "function",
    "the store must expose the assistant generation outcome separately from admission",
  );
  const expectedDeliveries = [{
    generationId: `generation-${clientMessageId}`,
    clientMessageId,
    terminal: { kind: "failed", error: { code: "provider_down", retryable: true } },
  }];
  assert.deepEqual(await observed.generationDeliveries!(), expectedDeliveries);

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("u"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(
    await reopened.generationDeliveries(),
    expectedDeliveries,
    "the failed assistant outcome remains visible after app restart",
  );
});

test("empty cancellation is durable terminal state and never a fabricated assistant record", async () => {
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const streams = new StoreTestStreamPort([{ chunks: [emptyCancelledGeneration()] }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("stop before there is assistant content");
  const clientMessageId = (await store.list())[0]!.id;
  http.respond(...successfulSend(clientMessageId, "stop before there is assistant content"));
  await env.advance(10);
  await drainMicrotasks();

  assert.deepEqual(
    (await store.list()).map(({ sender, text, generationOutcome }) => ({ sender, text, generationOutcome })),
    [{ sender: "human", text: "stop before there is assistant content", generationOutcome: null }],
    "null cancellation leaves the admitted human and creates no empty assistant row",
  );
  assert.deepEqual(await store.generationDeliveries(), [{
    generationId: `generation-${clientMessageId}`,
    clientMessageId,
    terminal: { kind: "cancelled", message: null },
  }]);
  assert.deepEqual(store.activeGenerations(), []);

  const reopened = await ChatMessagesStore.open(
    disk.openBridge("u"),
    new ManualEnv(),
    new ScriptedHttp(),
  );
  assert.deepEqual(await reopened.generationDeliveries(), await store.generationDeliveries());
  assert.equal((await reopened.list()).filter((message) => message.sender === "ai").length, 0);
});

test("the same op replayed produces the same payload hash and does not duplicate a message", async () => {
  // red-proof: rebuild attachmentIds instead of replaying the journaled op.
  // The whole-body equality and derived hash equality below both fail.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const streams = new StoreTestStreamPort([{ chunks: [successfulGeneration("amber-planet-cedar")] }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("hello once", ["attachment-1"]);
  const localId = (await store.list())[0]!.id;
  // First attempt fails retryably so the SAME pending op is resent.
  http.respond({ status: 503, json: null });
  http.respond(...successfulSend(localId, "hello once"));
  await env.advance(10_000); // first send (503) + backoff + retry (200)
  await drainMicrotasks();

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

  // Content, not row count: one human identity and one canonical assistant —
  // replay must not mint a second copy of either side of the turn.
  const rows = await store.list();
  assert.deepEqual(
    rows.map((row) => ({ id: row.id, sender: row.sender, text: row.text })),
    [
      { id: localId, sender: "human", text: "hello once" },
      { id: `assistant-${localId}`, sender: "ai", text: "Canonical answer" },
    ],
  );
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
  http.respond(...successfulSend(localId, "local only survivor"));
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
  const streams = new StoreTestStreamPort([{ chunks: [successfulGeneration("amber-planet-cedar")] }]);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("must survive junk snapshot");
  const localId = (await store.list())[0]!.id;
  http.respond(...successfulSend(localId, "must survive junk snapshot"));
  await env.advance(10);
  await drainMicrotasks();

  http.respond({ status: 200, json: { unexpected: true } }); // rows fetch junk → null
  http.respond({ status: 200, json: null }); // snapshot path junk → null
  await store.refresh();

  const rows = await store.list();
  const byId = new Map(rows.map((row) => [row.id, row]));
  assert.equal(byId.get(localId)?.text, "must survive junk snapshot");
  assert.equal(
    byId.get(`assistant-${localId}` as RecordId)?.text,
    "Canonical answer",
    "the terminal assistant delivery survives an unrelated malformed refresh",
  );
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
  http.respond(...successfulSend(localId, "wire contract"));
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

test("pending approval Allow posts resolution without leaking approval ids", async () => {
  // red-proof: ProductionChatStore used to duck-type resolveApproval onto
  // ChatMessagesStore and silently no-op. Allow must POST the generation's
  // pending approval without putting approvalId on the UI timeline.
  const disk = new MemoryStore();
  const env = new ManualEnv();
  const http = new ScriptedHttp();
  const scripts: { chunks: readonly string[]; hangs?: boolean }[] = [];
  const streams = new StoreTestStreamPort(scripts);
  const store = await ChatMessagesStore.open(disk.openBridge("u"), env, http, streams);

  await store.send("need a scoped write");
  const clientMessageId = (await store.list())[0]!.id;
  const generationId = `generation-${clientMessageId}`;
  scripts.push(
    { chunks: [successfulGeneration(clientMessageId)] },
    { chunks: [
      agentRunEvent(generationId, "opaque-accepted", 1, "run_accepted", "Run accepted", {
        admissionId: "opaque-admission",
      }) +
      agentRunEvent(generationId, "opaque-approval", 2, "approval_requested", "Approval requested for a scoped write", {
        approvalId: "approval:call:write",
        callId: "call:write",
        reason: "A scoped approval is required.",
        expiresAt: 1_786_442_460_002,
      }),
    ], hangs: true },
  );
  http.respond(...successfulSend(clientMessageId, "need a scoped write"));
  await env.advance(10);
  await drainMicrotasks();
  for (let index = 0; index < 20 && store.agentRunTimelines()[0]?.events.length !== 2; index += 1) {
    await drainMicrotasks();
  }

  const timeline = store.agentRunTimelines()[0];
  assert.equal(timeline?.events.map((event) => event.kind).join(","), "run_accepted,approval_requested");
  assert.doesNotMatch(
    JSON.stringify(timeline?.events),
    /approval:call:write|call:write|opaque-approval/,
    "approval and call identities never enter the UI event model",
  );

  http.respond({
    status: 200,
    json: { outcome: { kind: "completed", summary: "Scoped write recorded." } },
  });
  await store.resolveApproval("approved");
  const approvalPosts = http.calls.filter((call) =>
    call.method === "POST" && String(call.path).includes("agent-approvals"));
  assert.equal(approvalPosts.length, 1);
  assert.deepEqual(approvalPosts[0], {
    method: "POST",
    path: `/v1/chat-generations/${encodeURIComponent(generationId)}/agent-approvals`,
    body: { resolution: "approved" },
  });
  assert.equal("approvalId" in (approvalPosts[0]?.body as object), false);
});
