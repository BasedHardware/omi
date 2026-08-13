// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type LocalServiceStores,
} from "../app-facing";
import {
  createChatGenerationSupervisor,
  type ChatGenerationSupervisor,
} from "../chat/generation-supervisor";
import {
  createEmptyChatGenerationContextSource,
  createDeterministicChatGenerationContextSource,
  type ChatGenerationContextPacket,
  type ChatGenerationContextSource,
} from "../chat/generation-context";
import {
  createGatewayChatGenerationSource,
  createScriptedChatGenerationSource,
  type ChatGenerationScheduler,
  type ChatGenerationSource,
} from "../chat/generation-source";
import type { ChatGenerationLivenessPolicy } from "../chat/generation-supervisor";
import {
  boundedChatGenerationPollDelay,
  normalizeChatGenerationStreamPolicy,
  type ChatGenerationStreamPolicy,
} from "./chat-messages";
import type { ChatGenerationFrame } from "../stores/chat-generation-events-store";
import type { ChatGenerationEventsStore } from "../stores/chat-generation-events-store";
import type { ChatGenerationRetentionPolicy } from "../stores/chat-generation-events-store";
import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
  type AgentRunEventStore,
} from "../chat/agent-run-events";
import type { ChatGenerationFinalization } from "../stores/chat-generation-finalization";
import { createInMemoryChatGenerationFinalization } from "../stores/chat-generation-finalization";
import type { ChatMessageRecord } from "../stores/chat-messages-store";
import { createSqliteLocalServiceStores } from "../../../drivers/sqlite/service-stores";

const ACCOUNT = "chat-generation-account";
const auth = (token: string): HeadersInit => ({ authorization: `Bearer ${token}` });
const create = (id: string, text = "Tell me something useful") => ({
  op: "create",
  opId: `op-${id}`,
  id,
  at: 1_786_352_400_000,
  text,
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
});

const boot = (
  stores = createInMemoryLocalServiceStores(),
  generationSource: ChatGenerationSource = createScriptedChatGenerationSource([
    { delayMs: 2, text: "Useful " },
    { delayMs: 3, text: "answer." },
  ]),
  devSecretLabel = "chat-generation-proof",
  generationContext: ChatGenerationContextSource = createEmptyChatGenerationContextSource(),
  generationStreamPolicy?: ChatGenerationStreamPolicy,
  generationStreamScheduler?: ChatGenerationScheduler,
  generationLiveness?: ChatGenerationLivenessPolicy,
  generationRetentionPolicy?: ChatGenerationRetentionPolicy,
  agentRunEvents?: AgentRunEventStore,
  chatSupervisor?: ChatGenerationSupervisor,
) => {
  const db = new Database(":memory:");
  const local = createLocalDevService({
    db,
    stores,
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel,
    generationSource,
    generationContext,
    generationStreamPolicy,
    generationStreamScheduler,
    generationLiveness,
    generationRetentionPolicy,
    agentRunEvents,
    chatSupervisor,
  });
  return { db, local, stores };
};

const post = (local: ReturnType<typeof createLocalDevService>, body: unknown): Promise<Response> =>
  Promise.resolve(local.app.request("/v1/chat-messages", {
    method: "POST",
    headers: { ...auth(local.devToken), "content-type": "application/json" },
    body: JSON.stringify(body),
  }));

interface ChatAdmissionBody {
  readonly message: ChatMessageRecord & { readonly generationOutcome: null };
  readonly generation: { readonly id: string };
}

type ChatWireMessage = ChatMessageRecord & {
  readonly generationOutcome: "completed" | "cancelled" | null;
};

const readAdmission = async (response: Response): Promise<ChatAdmissionBody> =>
  await response.json() as ChatAdmissionBody;

const generationEvents = (
  local: ReturnType<typeof createLocalDevService>,
  generationId: string,
  lastEventId?: string,
): Promise<Response> => Promise.resolve(local.app.request(
  `/v1/chat-generations/${generationId}/events`,
  {
    headers: {
      ...auth(local.devToken),
      ...(lastEventId === undefined ? {} : { "last-event-id": lastEventId }),
    },
  },
));

const agentEvents = (
  local: ReturnType<typeof createLocalDevService>,
  generationId: string,
  lastEventId?: string,
): Promise<Response> => Promise.resolve(local.app.request(
  `/v1/chat-generations/${generationId}/agent-events`,
  {
    headers: {
      ...auth(local.devToken),
      ...(lastEventId === undefined ? {} : { "last-event-id": lastEventId }),
    },
  },
));

const admitAndOpen = async (
  local: ReturnType<typeof createLocalDevService>,
  body: unknown,
): Promise<{
  readonly admissionResponse: Response;
  readonly admission: ChatAdmissionBody;
  readonly eventsResponse: Response;
}> => {
  const admissionResponse = await post(local, body);
  const admission = await readAdmission(admissionResponse);
  const eventsResponse = await generationEvents(local, admission.generation.id);
  return { admissionResponse, admission, eventsResponse };
};

interface ParsedSseFrame {
  readonly event: string;
  readonly id: string;
  readonly data: ChatGenerationFrame;
}

const parseSse = (text: string): readonly ParsedSseFrame[] => Object.freeze(text
  .split("\n\n")
  .filter((block) => block.trim().length > 0)
  .map((block) => {
    const lines = block.split("\n");
    const event = lines.find((line) => line.startsWith("event: "))?.slice(7);
    const id = lines.find((line) => line.startsWith("id: "))?.slice(4);
    const data = lines.find((line) => line.startsWith("data: "))?.slice(6);
    if (event === undefined || id === undefined || data === undefined) {
      throw new TypeError(`invalid SSE frame: ${block}`);
    }
    return Object.freeze({ event, id, data: JSON.parse(data) as ChatGenerationFrame });
  }));

const readUntil = async (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  event: string,
  initial = "",
): Promise<string> => {
  const decoder = new TextDecoder();
  let text = initial;
  while (!parseSse(text).some((frame) => frame.event === event)) {
    const chunk = await reader.read();
    if (chunk.done) break;
    text += decoder.decode(chunk.value, { stream: true });
  }
  return text;
};

const readRemaining = async (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  initial: string,
): Promise<string> => {
  const decoder = new TextDecoder();
  let text = initial;
  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) return text + decoder.decode();
    text += decoder.decode(chunk.value, { stream: true });
  }
};

const readOutcomeWithin = async (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  milliseconds: number,
): Promise<Readonly<{ kind: "read"; done: boolean } | { kind: "timeout" }>> => {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const outcome = await Promise.race([
    reader.read().then((result) => ({ kind: "read" as const, done: result.done })),
    new Promise<{ kind: "timeout" }>((resolve) => {
      timer = setTimeout(() => resolve({ kind: "timeout" }), milliseconds);
    }),
  ]);
  if (timer !== null) clearTimeout(timer);
  return outcome;
};

const waitForTerminalLifecycle = async (
  events: ChatGenerationEventsStore,
  generationId: string,
  milliseconds: number,
): Promise<"terminal" | "timeout"> => {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    if (events.readLifecycle(ACCOUNT, generationId)?.state === "terminal") return "terminal";
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  return "timeout";
};

const history = async (local: ReturnType<typeof createLocalDevService>): Promise<ChatMessageRecord[]> => {
  const response = await local.app.request("/v1/chat-messages?limit=100", {
    headers: auth(local.devToken),
  });
  expect(response.status).toBe(200);
  return (await response.json() as { messages: ChatMessageRecord[] }).messages;
};

describe("ratified chat generation wire red proofs", () => {
  test("SSE policy rejects zero-delay polling to prevent busy spins", () => {
    expect(() => normalizeChatGenerationStreamPolicy({
      pollIntervalMs: 0,
      heartbeatIntervalMs: 0,
      maxBatchEvents: 1,
      maxBufferedEvents: 1,
      backpressurePollIntervalMs: 1,
    })).toThrow("invalid Chat generation stream policy");
    expect(normalizeChatGenerationStreamPolicy({
      pollIntervalMs: 1,
      heartbeatIntervalMs: 0,
      maxBatchEvents: 1,
      maxBufferedEvents: 1,
      backpressurePollIntervalMs: 1,
    }).pollIntervalMs).toBe(1);
    expect([0, 5, 25].map((now) => boundedChatGenerationPollDelay(5, now, 0, false))).toEqual([5, 1, 1]);
  });

  test("same-process concurrent replay re-drives a dispatch throw exactly once", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement(ACCOUNT, {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 2,
      limitReached: false,
      upgradeAvailable: true,
    });
    let sourceStarts = 0;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        sourceStarts += 1;
        queueMicrotask(() => {
          input.onDelta("Recovered answer.");
          input.onComplete();
        });
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const delegate = createChatGenerationSupervisor({
      source,
      context: createEmptyChatGenerationContextSource(),
      messages: stores.chatMessages,
      events: stores.chatEvents,
      finalization: stores.chatFinalization,
      attachments: stores.chatAttachments,
      nowEpochMilliseconds: () => 1_786_352_400_100,
      assistantMessageId: (_accountId, generationId) => `assistant-${generationId}`,
      eventId: (_accountId, generationId, kind, sequence) =>
        `event-${generationId}-${kind}-${sequence}`,
      revision: (_accountId, messageId, payloadHash) => `revision-${messageId}-${payloadHash}`,
    });
    let dispatchAttempts = 0;
    const supervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted(input): void {
        dispatchAttempts += 1;
        if (dispatchAttempts === 1) throw new Error("injected dispatch crash");
        delegate.onAdmitted(input);
      },
      cancel: delegate.cancel,
      recoverInterrupted: delegate.recoverInterrupted,
    });
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-dispatch-replay-proof",
      generationSource: source,
      generationContext: createEmptyChatGenerationContextSource(),
      chatSupervisor: supervisor,
    });
    const request = create("dispatch-retry");

    const first = await post(local, request);
    expect(first.status).toBe(503);
    expect(await first.json()).toEqual({
      error: { code: "service_unavailable", retryable: true, action: "retry" },
    });

    const replays = await Promise.all(Array.from({ length: 8 }, () => post(local, request)));
    expect(replays.map((response) => response.status)).toEqual(Array(8).fill(200));
    await new Promise((resolve) => setTimeout(resolve, 10));
    const human = stores.chatMessages.readMessage(ACCOUNT, "dispatch-retry")!;
    const eventKinds = stores.chatEvents.listAfter(
      ACCOUNT,
      human.generationId!,
      null,
    )!.map((event) => event.frame.kind);
    expect(eventKinds).toEqual(["accepted", "snapshot", "delta", "done"]);
    const lifecycle = stores.chatEvents.listUnterminated();
    expect(lifecycle).toEqual([]);
    expect(sourceStarts).toBe(1);
    expect(dispatchAttempts).toBe(9);
    expect((await history(local)).map((message) => [message.sender, message.text])).toEqual([
      ["human", "Tell me something useful"],
      ["ai", "Recovered answer."],
    ]);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
    const replayBodies = await Promise.all(replays.map((response) => response.text()));
    expect(new Set(replayBodies).size).toBe(1);
    db.close();
  });

  test("POST is finite JSON and GET terminal is byte-equal to canonical history", async () => {
    const { db, local } = boot();
    const { admissionResponse, admission, eventsResponse } = await admitAndOpen(
      local,
      create("terminal-canonical"),
    );
    expect(admissionResponse.status).toBe(201);
    expect(admissionResponse.headers.get("content-type")).toContain("application/json");
    expect(eventsResponse.headers.get("content-type")).toContain("text/event-stream");
    expect(admission.message).toMatchObject({
      id: "terminal-canonical",
      sender: "human",
      text: "Tell me something useful",
      generationOutcome: null,
    });

    const frames = parseSse(await eventsResponse.text());
    expect(frames.map((frame) => frame.event)).toEqual([
      "snapshot", "delta", "delta", "done",
    ]);
    expect(frames.some((frame) => frame.event === "accepted")).toBe(false);
    const terminal = frames.at(-1)?.data;
    expect(terminal?.kind).toBe("done");
    const canonical = (await history(local)).find((message) => message.sender === "ai");
    if (terminal?.kind !== "done" || canonical === undefined) throw new TypeError("missing terminal");
    expect((terminal.message as ChatWireMessage).generationOutcome).toBe("completed");
    expect((canonical as ChatWireMessage).generationOutcome).toBe("completed");
    expect(JSON.stringify(terminal.message)).toBe(JSON.stringify(canonical));

    const reopened = await generationEvents(local, admission.generation.id);
    const reopenedFrames = parseSse(await reopened.text());
    expect(reopenedFrames).toHaveLength(1);
    expect(reopenedFrames[0]?.data).toEqual(terminal);
    const healed = await generationEvents(
      local,
      admission.generation.id,
      reopenedFrames[0]!.id,
    );
    expect(parseSse(await healed.text())[0]?.data).toEqual(terminal);
    db.close();
  });

  test("POST returns finite JSON before a hanging provider completes", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start() {
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      hanging,
      "chat-finite-admission-proof",
    );
    const outcome = await Promise.race([
      post(local, create("finite-before-provider")).then(async (admitted) => ({
        kind: "response" as const,
        status: admitted.status,
        contentType: admitted.headers.get("content-type"),
        text: await admitted.text(),
      })),
      new Promise<{ readonly kind: "timeout" }>((resolve) => {
        setTimeout(() => resolve({ kind: "timeout" }), 100);
      }),
    ]);

    expect(outcome.kind).toBe("response");
    if (outcome.kind !== "response") throw new TypeError("POST waited for provider completion");
    expect(outcome.status).toBe(201);
    expect(outcome.contentType).toContain("application/json");
    const admission = JSON.parse(outcome.text) as ChatAdmissionBody;
    expect(admission.message).toMatchObject({
      id: "finite-before-provider",
      sender: "human",
    });
    expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("active");
    db.close();
  });

  test("provider receives a structured context packet while SSE/history remain canonical", async () => {
    let received: ChatGenerationContextPacket | null = null;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        received = input.context;
        queueMicrotask(() => {
          input.onDelta("context-backed answer");
          input.onComplete();
        });
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const context = createDeterministicChatGenerationContextSource({
      candidates: [{
        sourceKind: "memory",
        sourceId: "memory:first",
        claimId: "claim:first",
        evidenceId: "evidence:first",
        ownerAccountId: ACCOUNT,
        sourceHash: `sha256:${"c".repeat(64)}`,
        capturedAt: 1,
        expiresAt: null,
        redactedPreview: "safe context evidence",
        tokenEstimate: 3,
        inclusionReason: "retrieve_harness_evidence",
        policyDecision: "included",
        priority: 1,
        conflictKey: null,
      }],
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), source, "chat-context-packet-proof", context);
    const { admission, eventsResponse } = await admitAndOpen(local, create("structured-context"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event))).toHaveLength(1);
    expect(frames.at(-1)?.data.kind).toBe("done");
    expect(received).not.toBeNull();
    expect(received).toMatchObject({
      ownerAccountId: ACCOUNT,
      generationId: admission.generation.id,
      schemaVersion: "v1",
      traceVersion: "v1",
    });
    expect(received?.items.map((item) => item.evidenceId)).toEqual(["evidence:first"]);
    const rows = await history(local);
    expect(rows.filter((row) => row.sender === "ai").map((row) => row.text)).toEqual(["context-backed answer"]);
    db.close();
  });

  test("GET projects internal accepted records out of every generation stream", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start() {
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      hanging,
      "chat-internal-admission-projection-proof",
    );
    const admitted = await post(local, create("project-internal-admission"));
    const admission = await readAdmission(admitted);
    const stream = await generationEvents(local, admission.generation.id);
    const reader = stream.body!.getReader();
    const initial = await readUntil(reader, "snapshot");
    const append = (eventId: string, frame: ChatGenerationFrame): void => {
      expect(stores.chatEvents.append({
        accountId: ACCOUNT,
        generationId: admission.generation.id,
        eventId,
        createdAt: 1_786_352_400_200,
        frame,
      }).kind).toBe("appended");
    };
    append("event-internal-accepted-after-snapshot", {
      kind: "accepted",
      message: admission.message,
      generation: { id: admission.generation.id },
    });
    append("event-external-delta-after-internal", { kind: "delta", text: "visible" });
    append("event-external-failed-after-internal", {
      kind: "failed",
      error: { code: "proof_terminal", retryable: false },
    });

    const frames = parseSse(await readRemaining(reader, initial));
    expect(frames.map((frame) => frame.event)).toEqual(["snapshot", "delta", "failed"]);
    expect(frames.some((frame) => frame.event === "accepted")).toBe(false);
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)?.map(
      (event) => event.frame.kind,
    )).toEqual(["accepted", "snapshot", "accepted", "delta", "failed"]);
    db.close();
  });

  test("a synchronous terminal callback cancels the run returned afterward exactly once", async () => {
    let cancelCalls = 0;
    const synchronous: ChatGenerationSource = Object.freeze({
      start(input) {
        input.onDelta("synchronous answer");
        input.onComplete();
        return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      synchronous,
      "chat-synchronous-terminal-proof",
    );

    const { admissionResponse, admission, eventsResponse } = await admitAndOpen(
      local,
      create("synchronous-terminal"),
    );
    const frames = parseSse(await eventsResponse.text());

    expect(admissionResponse.status).toBe(201);
    expect(frames.map((frame) => frame.event)).toEqual(["done"]);
    expect(cancelCalls).toBe(1);
    expect(stores.chatEvents.listUnterminated()).toEqual([]);
    expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("terminal");
    expect((await history(local)).map((entry) => [entry.sender, entry.text])).toEqual([
      ["human", "Tell me something useful"],
      ["ai", "synchronous answer"],
    ]);
    db.close();
  });

  test("cancellation retains a durable partial and replay is idempotent", async () => {
    const source = createScriptedChatGenerationSource([
      { delayMs: 2, text: "retained partial" },
      { delayMs: 100, text: " must not arrive" },
    ]);
    const { db, local } = boot(createInMemoryLocalServiceStores(), source);
    const { admission, eventsResponse } = await admitAndOpen(local, create("cancel-partial"));
    const reader = eventsResponse.body!.getReader();
    const throughDelta = await readUntil(reader, "delta");

    const cancelled = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    expect(cancelled.status).toBe(202);
    expect(await cancelled.json()).toEqual({ cancellation: { state: "accepted" } });
    const terminalFrames = parseSse(await readRemaining(reader, throughDelta));
    const terminal = terminalFrames.at(-1)?.data;
    expect(terminal?.kind).toBe("cancelled");
    if (terminal?.kind !== "cancelled" || terminal.message === null) {
      throw new TypeError("missing retained cancellation partial");
    }
    expect(terminal.message.text).toBe("retained partial");
    const canonical = (await history(local)).find((message) => message.sender === "ai");
    expect((terminal.message as ChatWireMessage).generationOutcome).toBe("cancelled");
    expect((canonical as ChatWireMessage | undefined)?.generationOutcome).toBe("cancelled");
    expect(JSON.stringify(canonical)).toBe(JSON.stringify(terminal.message));

    const repeated = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    expect(repeated.status).toBe(204);
    const replay = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}/events`,
      { headers: auth(local.devToken) },
    );
    const replayFrames = parseSse(await replay.text());
    expect(replayFrames).toHaveLength(1);
    expect(replayFrames[0]?.data).toEqual(terminal);
    const replayAtTerminal = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}/events`,
      { headers: { ...auth(local.devToken), "last-event-id": terminalFrames.at(-1)!.id } },
    );
    expect(parseSse(await replayAtTerminal.text())[0]?.data).toEqual(terminal);
    db.close();
  });

  test("cancellation before context or provider start retains no assistant content", async () => {
    let releaseContext: ((value: readonly string[]) => void) | null = null;
    const context: ChatGenerationContextSource = Object.freeze({
      load: (): Promise<readonly string[]> => new Promise((resolve) => {
        releaseContext = resolve;
      }),
    });
    let starts = 0;
    const source: ChatGenerationSource = Object.freeze({
      start() {
        starts += 1;
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const stores = createInMemoryLocalServiceStores();
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-cancel-before-start-proof",
      generationSource: source,
      generationContext: context,
    });
    const admitted = await post(local, create("cancel-before-start"));
    const admission = await readAdmission(admitted);
    const cancelled = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    expect(cancelled.status).toBe(202);
    if (releaseContext === null) throw new TypeError("generation context did not start loading");
    releaseContext(Object.freeze([]));
    await new Promise((resolve) => setTimeout(resolve, 0));

    const response = await generationEvents(local, admission.generation.id);
    const frames = parseSse(await response.text());
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toEqual({ kind: "cancelled", message: null });
    expect((await history(local)).map((message) => [
      message.sender,
      (message as ChatWireMessage).generationOutcome,
    ])).toEqual([["human", null]]);
    expect(starts).toBe(0);
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)?.map(
      (event) => event.frame.kind,
    )).toEqual(["accepted", "snapshot", "cancelled"]);
    db.close();
  });

  test("memory-context failure degrades explicitly and does not make Chat unavailable", async () => {
    let observedCredential: string | null = null;
    const context: ChatGenerationContextSource = Object.freeze({
      async load(input) {
        observedCredential = input.bearerToken;
        // Memory-read unavailability is represented by the context source
        // (later: MemoryRouteReadPort composition). A generic throw still
        // fails Chat as generation_context_failed; this source fail-opens.
        return Object.freeze([]);
      },
    });
    let sourceContext: unknown = null;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        sourceContext = input.context;
        queueMicrotask(() => {
          input.onDelta("Useful without memory.");
          input.onComplete();
        });
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const stores = createInMemoryLocalServiceStores();
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-memory-context-failure-proof",
      generationSource: source,
      generationContext: context,
    });
    const admitted = await readAdmission(await post(local, create("context-failure")));
    expect(await waitForTerminalLifecycle(stores.chatEvents, admitted.generation.id, 100))
      .toBe("terminal");
    expect(observedCredential).toBe(local.devToken);
    expect(sourceContext).toMatchObject({
      ownerAccountId: ACCOUNT,
      generationId: admitted.generation.id,
      schemaVersion: "v1",
      items: [],
    });
    expect(JSON.stringify(sourceContext)).not.toContain(local.devToken);
    expect((await history(local)).at(-1)?.text).toBe("Useful without memory.");
    db.close();
  });

  test("duplicate DELETE has one provider-cancellation owner and one canonical terminal", async () => {
    let cancelCalls = 0;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("retained"));
        return Object.freeze({
          cancel(): void {
            cancelCalls += 1;
          },
        });
      },
    });
    const { db, local, stores } = boot(createInMemoryLocalServiceStores(), source);
    const { admission, eventsResponse } = await admitAndOpen(local, create("duplicate-cancel"));
    const reader = eventsResponse.body!.getReader();
    const throughDelta = await readUntil(reader, "snapshot");
    const path = `/v1/chat-generations/${admission.generation.id}`;

    const firstDelete = local.app.request(path, { method: "DELETE", headers: auth(local.devToken) });
    const secondDelete = local.app.request(path, { method: "DELETE", headers: auth(local.devToken) });
    const deletes = await Promise.all([firstDelete, secondDelete]);
    const completed = parseSse(await readRemaining(reader, throughDelta));
    const terminalKinds = completed
      .map((frame) => frame.event)
      .filter((kind) => ["done", "failed", "cancelled"].includes(kind));

    expect(deletes.map((response) => response.status)).toEqual([202, 202]);
    expect(cancelCalls).toBe(1);
    expect(terminalKinds).toEqual(["cancelled"]);
    expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("terminal");
    expect((await history(local)).map((entry) => [entry.sender, entry.text])).toEqual([
      ["human", "Tell me something useful"],
      ["ai", "retained"],
    ]);
    db.close();
  });

  test("provider cancellation exceptions are contained and the stream still terminalizes", async () => {
    let cancelCalls = 0;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("before rejection"));
        return Object.freeze({
          cancel(): void {
            cancelCalls += 1;
            throw new Error("provider rejects cancellation");
          },
        });
      },
    });
    const { db, local, stores } = boot(createInMemoryLocalServiceStores(), source);
    const { admission, eventsResponse } = await admitAndOpen(local, create("cancel-rejection"));
    const reader = eventsResponse.body!.getReader();
    const throughDelta = await readUntil(reader, "snapshot");

    const cancelled = await local.app.request(
      `/v1/chat-generations/${admission.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    const frames = parseSse(await readRemaining(reader, throughDelta));

    expect(cancelled.status).toBe(202);
    expect(cancelCalls).toBe(1);
    expect(frames.at(-1)?.event).toBe("cancelled");
    expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("terminal");
    db.close();
  });

  test("a provider callback storage exception becomes one failed terminal without escaping", async () => {
    const base = createInMemoryLocalServiceStores();
    let injected = true;
    const throwingEvents: ChatGenerationEventsStore = Object.freeze({
      append(input) {
        if (input.frame.kind === "delta" && injected) {
          injected = false;
          throw new Error("injected delta append failure");
        }
        return base.chatEvents.append(input);
      },
      listAfter: base.chatEvents.listAfter,
      readLifecycle: base.chatEvents.readLifecycle,
      listUnterminated: base.chatEvents.listUnterminated,
      requestCancellation: base.chatEvents.requestCancellation,
      reset: base.chatEvents.reset,
    });
    const stores: LocalServiceStores = Object.freeze({ ...base, chatEvents: throwingEvents });
    let callbackError: string | null = null;
    let cancelCalls = 0;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => {
          try {
            input.onDelta("must not remain active");
            input.onComplete();
            input.onError(new Error("late provider error"));
          } catch (error) {
            callbackError = error instanceof Error ? error.message : String(error);
          }
        });
        return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
      },
    });
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-callback-storage-proof",
      generationSource: source,
    });
    const { admission, eventsResponse } = await admitAndOpen(
      local,
      create("callback-storage-failure"),
    );
    const reader = eventsResponse.body!.getReader();
    const initial = await readUntil(reader, "snapshot");
    const lifecycle = await waitForTerminalLifecycle(
      throwingEvents,
      admission.generation.id,
      100,
    );
    if (lifecycle === "timeout") await reader.cancel();

    expect(lifecycle).toBe("terminal");
    expect(callbackError).toBeNull();
    const events = base.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)!;
    expect(events.map((event) => event.frame.kind)).toEqual(["accepted", "snapshot", "failed"]);
    expect(events.filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind)))
      .toHaveLength(1);
    expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
    expect(cancelCalls).toBe(1);
    if (lifecycle === "terminal") {
      const completed = parseSse(await readRemaining(reader, initial));
      expect(completed.at(-1)?.data).toEqual({
        kind: "failed",
        error: { code: "generation_interrupted", retryable: true },
      });
      expect(Object.hasOwn(completed.at(-1)?.data ?? {}, "message")).toBe(false);
      expect(Object.hasOwn(completed.at(-1)?.data ?? {}, "generationOutcome")).toBe(false);
    }
    db.close();
  });

  test("a non-string provider delta fails closed without persisting object text", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => {
          input.onDelta({ forged: true } as unknown as string);
          input.onComplete();
        });
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), source, "chat-delta-type-proof");
    const { admission, eventsResponse } = await admitAndOpen(local, create("delta-object"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.at(-1)?.data).toEqual({ kind: "failed", error: { code: "generation_provider_failed", retryable: true } });
    expect(frames.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event))).toHaveLength(1);
    expect(JSON.stringify(await history(local))).not.toContain("forged");
    expect((local as unknown as { writePath: { chatEvents: ChatGenerationEventsStore } }).writePath.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)
      ?.map((event) => event.frame.kind)).toEqual(["accepted", "snapshot", "failed"]);
    db.close();
  });

  test("provider, context, and attachment failures stay failed through SSE, history, and replay", async () => {
    const cases = [
      {
        name: "provider",
        code: "generation_provider_failed",
        source: Object.freeze({
          start(input: Parameters<ChatGenerationSource["start"]>[0]) {
            queueMicrotask(() => input.onError({
              code: "generation_provider_failed",
              retryable: false,
            }));
            return Object.freeze({ cancel: (): void => {} });
          },
        }),
        context: createEmptyChatGenerationContextSource(),
        attachmentFailure: false,
      },
      {
        name: "provider-getter",
        code: "generation_provider_failed",
        source: Object.freeze({
          start(input: Parameters<ChatGenerationSource["start"]>[0]) {
            const malformed = Object.defineProperties({}, {
              code: { get: (): never => { throw new Error("code getter escaped"); } },
              retryable: { get: (): never => { throw new Error("retryable getter escaped"); } },
            });
            queueMicrotask(() => input.onError(malformed));
            return Object.freeze({ cancel: (): void => {} });
          },
        }),
        context: createEmptyChatGenerationContextSource(),
        attachmentFailure: false,
      },
      {
        name: "provider-proxy",
        code: "generation_provider_failed",
        source: Object.freeze({
          start(input: Parameters<ChatGenerationSource["start"]>[0]) {
            const malformed = new Proxy(
              { code: "generation_provider_failed", retryable: false },
              { getOwnPropertyDescriptor: (): never => { throw new Error("proxy escaped"); } },
            );
            queueMicrotask(() => input.onError(malformed));
            return Object.freeze({ cancel: (): void => {} });
          },
        }),
        context: createEmptyChatGenerationContextSource(),
        attachmentFailure: false,
      },
      {
        name: "provider-forged-proxy",
        code: "generation_provider_failed",
        source: Object.freeze({
          start(input: Parameters<ChatGenerationSource["start"]>[0]) {
            let trapCalls = 0;
            const malformed = new Proxy(
              { code: "generation_provider_failed", retryable: true },
              {
                get: (): never => {
                  trapCalls += 1;
                  throw new Error("proxy getter escaped");
                },
                getOwnPropertyDescriptor: (): PropertyDescriptor | undefined => {
                  trapCalls += 1;
                  return { value: "generation_timeout", writable: true, enumerable: true, configurable: true };
                },
              },
            );
            queueMicrotask(() => {
              input.onError(malformed);
              expect(trapCalls).toBe(0);
            });
            return Object.freeze({ cancel: (): void => {} });
          },
        }),
        context: createEmptyChatGenerationContextSource(),
        attachmentFailure: false,
      },
      {
        name: "context",
        code: "generation_context_failed",
        source: Object.freeze({
          start() {
            throw new Error("provider must not start after context failure");
          },
        }),
        context: Object.freeze({
          async load(): Promise<readonly string[]> {
            throw new Error("injected context failure");
          },
        }),
        attachmentFailure: false,
      },
      {
        name: "attachment",
        code: "generation_attachment_failed",
        source: Object.freeze({
          start() {
            throw new Error("provider must not start after attachment failure");
          },
        }),
        context: createEmptyChatGenerationContextSource(),
        attachmentFailure: true,
      },
    ] as const;

    for (const scenario of cases) {
      const base = createInMemoryLocalServiceStores();
      const stores: LocalServiceStores = scenario.attachmentFailure === true
        ? Object.freeze({
            ...base,
            chatAttachments: Object.freeze({
              ...base.chatAttachments,
              loadForGeneration(): never {
                throw new Error("injected attachment failure");
              },
            }),
          })
        : base;
      const db = new Database(":memory:");
      const local = createLocalDevService({
        db,
        stores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: `chat-${scenario.name}-failure-projection-proof`,
        generationSource: scenario.source,
        generationContext: scenario.context,
      });
      const { admission } = await admitAndOpen(local, create(`projection-${scenario.name}`));
      const stream = await generationEvents(local, admission.generation.id);
      const frames = parseSse(await stream.text());
      const terminals = frames.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event));
      expect(terminals).toHaveLength(1);
      expect(terminals[0]?.event).toBe("failed");
      expect(terminals[0]?.data).toEqual({
        kind: "failed",
        error: {
          code: scenario.code,
          retryable: scenario.name === "provider" ? false : true,
        },
      });
      expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);

      const replay = parseSse(await (await generationEvents(local, admission.generation.id)).text());
      expect(replay.filter((frame) => frame.event === "failed")).toHaveLength(1);
      expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)!
        .filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind)))
        .toHaveLength(1);
      db.close();
    }
  });

  for (const [name, complete] of [
    ["synchronous", (input: Parameters<ChatGenerationSource["start"]>[0]): void => input.onComplete()],
    ["asynchronous", (input: Parameters<ChatGenerationSource["start"]>[0]): void => queueMicrotask(() => input.onComplete())],
    ["whitespace", (input: Parameters<ChatGenerationSource["start"]>[0]): void => {
      input.onDelta(" \n\t");
      input.onComplete();
    }],
  ] as const) {
    test(`${name} empty provider completion is failed without an assistant fallback`, async () => {
      const source: ChatGenerationSource = Object.freeze({
        start(input) {
          complete(input);
          return Object.freeze({ cancel: (): void => {} });
        },
      });
      const { db, local } = boot(createInMemoryLocalServiceStores(), source, `chat-empty-${name}-proof`);
      const { admission, eventsResponse } = await admitAndOpen(local, create(`empty-${name}`));
      const frames = parseSse(await eventsResponse.text());
      expect(frames.map((frame) => frame.event)).toEqual(["failed"]);
      expect(frames.at(-1)?.data).toEqual({
        kind: "failed",
        error: { code: "generation_provider_failed", retryable: true },
      });
      expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
      const replay = parseSse(await (await generationEvents(local, admission.generation.id)).text());
      expect(replay).toEqual([frames.at(-1)]);
      expect(frames.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event)))
        .toHaveLength(1);
      db.close();
    });
  }

  test("meaningful leading and trailing whitespace remains in a completed answer", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        input.onDelta(" answer ");
        input.onComplete();
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), source, "chat-whitespace-content-proof");
    const { admission, eventsResponse } = await admitAndOpen(local, create("whitespace-content"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.at(-1)?.event).toBe("done");
    const done = frames.at(-1)?.data;
    if (done?.kind !== "done") throw new TypeError("missing done frame");
    expect(done.message.text).toBe(" answer ");
    expect((await history(local)).map((entry) => [entry.sender, entry.text])).toEqual([
      ["human", "Tell me something useful"],
      ["ai", " answer "],
    ]);
    expect((await generationEvents(local, admission.generation.id)).status).toBe(200);
    db.close();
  });

  test("an out-of-band timeout cannot create a ghost terminal without admission", async () => {
    const stores = createInMemoryLocalServiceStores();
    const supervisor = createChatGenerationSupervisor({
      source: Object.freeze({
        start() {
          return Object.freeze({ cancel: (): void => {} });
        },
      }),
      context: createEmptyChatGenerationContextSource(),
      messages: stores.chatMessages,
      events: stores.chatEvents,
      finalization: stores.chatFinalization,
      attachments: stores.chatAttachments,
      nowEpochMilliseconds: () => 100,
      assistantMessageId: (_accountId, id) => `assistant-${id}`,
      eventId: (_accountId, id, kind, sequence) => `event-${id}-${kind}-${sequence}`,
      revision: (_accountId, id, hash) => `revision-${id}-${hash}`,
    });
    supervisor.timeout?.(ACCOUNT, "never-admitted");
    await Promise.resolve();
    expect(stores.chatEvents.listAfter(ACCOUNT, "never-admitted", null)).toEqual([]);
  });

  test("a durable terminalization failure stays active until recovery can append failed", async () => {
    const base = createInMemoryLocalServiceStores();
    let allowTerminal = false;
    const finalization: ChatGenerationFinalization = Object.freeze({
      finalize(input) {
        if (!allowTerminal) throw new Error("injected durable terminal failure");
        return base.chatFinalization.finalize(input);
      },
    });
    let cancelCalls = 0;
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => {
          input.onDelta("visible before terminal failure");
          input.onComplete();
        });
        return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
      },
    });
    const supervisor = createChatGenerationSupervisor({
      source,
      context: createEmptyChatGenerationContextSource(),
      messages: base.chatMessages,
      events: base.chatEvents,
      finalization,
      attachments: base.chatAttachments,
      nowEpochMilliseconds: () => 1_786_352_400_100,
      assistantMessageId: (_accountId, generationId) => `assistant-${generationId}`,
      eventId: (_accountId, generationId, kind, sequence) =>
        `event-${generationId}-${kind}-${sequence}`,
      revision: (_accountId, messageId, payloadHash) => `revision-${messageId}-${payloadHash}`,
    });
    const stores: LocalServiceStores = Object.freeze({
      ...base,
      chatFinalization: finalization,
    });
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-terminal-recovery-proof",
      generationSource: source,
      chatSupervisor: supervisor,
    });
    const { admission, eventsResponse } = await admitAndOpen(local, create("terminal-recovery"));
    const reader = eventsResponse.body!.getReader();
    const initial = await readUntil(reader, "snapshot");
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(base.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("active");
    expect(base.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)?.map(
      (event) => event.frame.kind,
    )).toEqual(["accepted", "snapshot", "delta"]);
    expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
    expect(cancelCalls).toBe(1);

    allowTerminal = true;
    supervisor.recoverInterrupted();
    expect(await waitForTerminalLifecycle(base.chatEvents, admission.generation.id, 100))
      .toBe("terminal");
    const completed = parseSse(await readRemaining(reader, initial));
    expect(completed.at(-1)?.event).toBe("failed");
    expect(completed.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event)))
      .toHaveLength(1);
    expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
    db.close();
  });

  for (const faultPoint of ["before", "after"] as const) {
    test(`in-memory finalization rolls back a ${faultPoint}-terminal-append failure`, async () => {
      const base = createInMemoryLocalServiceStores();
      base.settings.putEntitlement(ACCOUNT, {
        planLabel: "Metered",
        limitKey: "chat_messages",
        used: 0,
        limit: 2,
        limitReached: false,
        upgradeAvailable: true,
      });
      const crash = (): never => { throw new Error(`injected ${faultPoint} terminal crash`); };
      const finalization = createInMemoryChatGenerationFinalization(
        base.chatMessages,
        base.chatEvents,
        faultPoint === "before"
          ? { beforeTerminalAppend: crash }
          : { afterTerminalAppend: crash },
      );
      const stores: LocalServiceStores = Object.freeze({
        ...base,
        chatFinalization: finalization,
      });
      let cancelCalls = 0;
      const source: ChatGenerationSource = Object.freeze({
        start(input) {
          queueMicrotask(() => input.onComplete());
          return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
        },
      });
      const db = new Database(":memory:");
      const local = createLocalDevService({
        db,
        stores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: `chat-in-memory-${faultPoint}-terminal-proof`,
        generationSource: source,
      });
      const { admission, eventsResponse } = await admitAndOpen(
        local,
        create(`in-memory-${faultPoint}-terminal`),
      );
      const reader = eventsResponse.body!.getReader();
      const initial = await readUntil(reader, "snapshot");
      await new Promise((resolve) => setTimeout(resolve, 10));
      const lifecycle = base.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state;
      if (lifecycle !== "terminal") await reader.cancel();

      expect(lifecycle).toBe("active");
      expect(base.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)?.map(
        (event) => event.frame.kind,
      )).toEqual(["accepted", "snapshot"]);
      expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
      expect(base.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
      expect(cancelCalls).toBe(1);
      db.close();
    });
  }

  test("reconnect starts with a current snapshot and Last-Event-ID replays strictly after", async () => {
    let callbacks: Parameters<ChatGenerationSource["start"]>[0] | null = null;
    const hanging: ChatGenerationSource = Object.freeze({
      start(input) {
        callbacks = input;
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), hanging, "chat-reconnect-proof");
    const admissionResponse = await post(local, create("reconnect"));
    const admission = await readAdmission(admissionResponse);
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (callbacks === null) throw new TypeError("generation source did not start");
    const initialResponse = await generationEvents(local, admission.generation.id);
    const reader = initialResponse.body!.getReader();
    callbacks.onDelta("current partial");
    const initial = parseSse(await readUntil(reader, "delta"));
    const delta = initial.find((frame) => frame.event === "delta")!;
    expect(initial.map((frame) => frame.event)).toEqual(["snapshot", "delta"]);
    expect(initial.some((frame) => frame.event === "accepted")).toBe(false);
    await reader.cancel();

    callbacks.onDelta(" plus more");
    const fresh = await generationEvents(local, admission.generation.id);
    const freshReader = fresh.body!.getReader();
    const freshText = await readUntil(freshReader, "snapshot");
    const freshSnapshot = parseSse(freshText)[0];
    expect(freshSnapshot?.data).toEqual({ kind: "snapshot", text: "current partial plus more" });
    await freshReader.cancel();

    const continuation = await generationEvents(local, admission.generation.id, delta.id);
    const replayReader = continuation.body!.getReader();
    const replayText = await readUntil(replayReader, "snapshot");
    expect(parseSse(replayText).map((frame) => frame.event)).toEqual(["snapshot"]);
    expect(parseSse(replayText)[0]?.data).toEqual({
      kind: "snapshot",
      text: "current partial plus more",
    });
    await replayReader.cancel();
    db.close();
  });

  test("revoking the authenticated session promptly closes its existing SSE without cancellation", async () => {
    let cancelCalls = 0;
    const hanging: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("visible before revoke"));
        return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      hanging,
      "chat-stream-revocation-proof",
    );
    const { admission, eventsResponse } = await admitAndOpen(local, create("stream-revocation"));
    const reader = eventsResponse.body!.getReader();
    await readUntil(reader, "snapshot");

    const revoked = await local.app.request("/v1/session/current", {
      method: "DELETE",
      headers: auth(local.devToken),
    });
    const outcome = await readOutcomeWithin(reader, 100);
    if (outcome.kind === "timeout") await reader.cancel();

    expect(revoked.status).toBe(204);
    expect(outcome).toEqual({ kind: "read", done: true });
    expect(cancelCalls).toBe(0);
    expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
      .toBe("active");
    db.close();
  });

  for (const lifecycle of ["deletion_pending", "deleted"] as const) {
    test(`${lifecycle} promptly closes an existing SSE without cancelling generation`, async () => {
      let cancelCalls = 0;
      const hanging: ChatGenerationSource = Object.freeze({
        start(input) {
          queueMicrotask(() => input.onDelta(`visible before ${lifecycle}`));
          return Object.freeze({ cancel: (): void => { cancelCalls += 1; } });
        },
      });
      const stores = createInMemoryLocalServiceStores();
      const { db, local } = boot(stores, hanging, `chat-stream-${lifecycle}-proof`);
      const { admission, eventsResponse } = await admitAndOpen(
        local,
        create(`stream-${lifecycle}`),
      );
      const reader = eventsResponse.body!.getReader();
      await readUntil(reader, "snapshot");

      stores.accountLifecycle.setLifecycle(ACCOUNT, lifecycle);
      const outcome = await readOutcomeWithin(reader, 100);
      if (outcome.kind === "timeout") await reader.cancel();

      expect(outcome).toEqual({ kind: "read", done: true });
      expect(cancelCalls).toBe(0);
      expect(stores.chatEvents.readLifecycle(ACCOUNT, admission.generation.id)?.state)
        .toBe("active");
      db.close();
    });
  }

  test("an interrupted durable generation becomes an explicit failed terminal after restart", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-generation-crash-"));
    const path = join(directory, "service.sqlite");
    const hanging: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("visible before crash"));
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    try {
      let generationId = "";
      {
        const db = new Database(path);
        const local = createLocalDevService({
          db,
          stores: createSqliteLocalServiceStores(db),
          ownerAccountId: ACCOUNT,
          memoryCount: 0,
          accountTimezone: "UTC",
          devSecretLabel: "chat-generation-crash-proof",
          generationSource: hanging,
        });
        const admitted = await post(local, create("crash-mid-generation"));
        const admission = await readAdmission(admitted);
        generationId = admission.generation.id;
        const events = await generationEvents(local, generationId);
        const reader = events.body!.getReader();
        await readUntil(reader, "snapshot");
        await reader.cancel();
        db.close();
      }
      {
        const db = new Database(path);
        const local = createLocalDevService({
          db,
          stores: createSqliteLocalServiceStores(db),
          ownerAccountId: ACCOUNT,
          memoryCount: 0,
          accountTimezone: "UTC",
          devSecretLabel: "chat-generation-crash-proof",
        });
        const replay = await local.app.request(`/v1/chat-generations/${generationId}/events`, {
          headers: auth(local.devToken),
        });
        expect(replay.status).toBe(200);
        expect(parseSse(await replay.text()).map((frame) => frame.data)).toEqual([{
          kind: "failed",
          error: { code: "generation_interrupted", retryable: true },
        }]);
        expect((await history(local)).map((message) => message.sender)).toEqual(["human"]);
        db.close();
      }
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("durable agent timeline reconstructs and recovers one truthful terminal without replay side effects", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-agent-generation-recovery-"));
    const path = join(directory, "service.sqlite");
    const hanging: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("durable partial"));
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    let generationId = "";
    try {
      const firstDb = new Database(path);
      const first = createLocalDevService({
        db: firstDb,
        stores: createSqliteLocalServiceStores(firstDb),
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "agent-durable-recovery-proof",
        generationSource: hanging,
      });
      const admission = await readAdmission(await post(first, create("agent-durable-recovery")));
      generationId = admission.generation.id;
      await new Promise((resolve) => setTimeout(resolve, 10));
      firstDb.close();

      const secondDb = new Database(path);
      const secondStores = createSqliteLocalServiceStores(secondDb);
      const second = createLocalDevService({
        db: secondDb,
        stores: secondStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "agent-durable-recovery-proof",
      });
      const canonical = parseSse(await (await generationEvents(second, generationId)).text());
      expect(canonical.at(-1)?.data).toEqual({
        kind: "failed",
        error: { code: "generation_interrupted", retryable: true },
      });
      const timeline = secondStores.agentRunEvents!;
      const events = timeline.list(generationId);
      expect(events.filter((event) => event.kind === "terminal")).toHaveLength(1);
      expect(events.filter((event) => event.kind === "recovery")).toHaveLength(1);
      expect(events.at(-1)).toMatchObject({
        kind: "terminal",
        terminalOutcome: "failed",
        terminalCode: "generation_interrupted",
      });
      expect((await history(second)).map((entry) => entry.sender)).toEqual(["human"]);
      const replay = await agentEvents(second, generationId);
      expect((await replay.text())).toContain("event: terminal");
      const beforeReload = timeline.snapshot();
      secondDb.close();

      const thirdDb = new Database(path);
      const thirdStores = createSqliteLocalServiceStores(thirdDb);
      createLocalDevService({
        db: thirdDb,
        stores: thirdStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "agent-durable-recovery-proof",
      });
      expect(thirdStores.agentRunEvents!.snapshot()).toEqual(beforeReload);
      expect(thirdStores.chatEvents.listAfter(ACCOUNT, generationId, null)!
        .filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind))).toHaveLength(1);
      const foreignDb = new Database(path);
      const foreign = createLocalDevService({
        db: foreignDb,
        stores: createSqliteLocalServiceStores(foreignDb),
        ownerAccountId: "foreign-agent-owner",
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "agent-durable-foreign-proof",
      });
      expect((await agentEvents(foreign, generationId)).status).toBe(404);
      foreignDb.close();
      thirdDb.close();
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("restart owns a durable cancellation request without starting or double-cancelling a provider", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-cancellation-restart-"));
    const path = join(directory, "service.sqlite");
    try {
      {
        const db = new Database(path);
        const stores = createSqliteLocalServiceStores(db);
        const admitted = stores.chatAdmission.admit({
          accountId: ACCOUNT,
          message: {
            id: "restart-cancel-human",
            text: "cancel after restart",
            sender: "human",
            type: "text",
            createdAt: 100,
            updatedAt: 100,
            chatSessionId: null,
            appId: null,
            journalRevision: 1,
            payloadHash: "sha256:restart-cancel",
            messageSource: "desktop_chat",
            rating: null,
            reported: false,
            revision: "revision-restart-cancel",
          },
          generationId: "generation-restart-cancel",
          acceptedEventId: "event-restart-cancel-accepted",
          admittedAt: 100,
          attachmentIds: [],
        });
        expect(admitted.kind).toBe("created");
        expect(stores.chatEvents.requestCancellation(ACCOUNT, "generation-restart-cancel").kind)
          .toBe("accepted");
        db.close();
      }
      {
        let starts = 0;
        const db = new Database(path);
        const stores = createSqliteLocalServiceStores(db);
        const local = createLocalDevService({
          db,
          stores,
          ownerAccountId: ACCOUNT,
          memoryCount: 0,
          accountTimezone: "UTC",
          devSecretLabel: "chat-cancellation-restart-proof",
          generationSource: {
            start() {
              starts += 1;
              return Object.freeze({ cancel: (): void => {} });
            },
          },
        });
        const replay = await local.app.request(
          "/v1/chat-generations/generation-restart-cancel/events",
          { headers: auth(local.devToken) },
        );
        const frames = parseSse(await replay.text());
        expect(frames.map((frame) => frame.event)).toEqual(["cancelled"]);
        expect(frames[0]?.data).toEqual({ kind: "cancelled", message: null });
        expect(starts).toBe(0);
        expect((await history(local)).map((entry) => [
          entry.sender,
          entry.text,
          (entry as ChatWireMessage).generationOutcome,
        ])).toEqual([
          ["human", "cancel after restart", null],
        ]);
        const timeline = stores.agentRunEvents!.list("generation-restart-cancel");
        expect(timeline.filter((event) => event.kind === "recovery")).toHaveLength(1);
        expect(timeline.filter((event) => event.kind === "terminal")).toHaveLength(1);
        expect(timeline.at(-1)).toMatchObject({
          kind: "terminal",
          terminalOutcome: "cancelled",
          terminalCode: "cancelled",
        });
        expect((await local.app.request("/v1/chat-generations/generation-restart-cancel", {
          method: "DELETE",
          headers: auth(local.devToken),
        })).status).toBe(204);
        db.close();
      }
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("two SQLite supervisor compositions emit one terminal in a completion-cancel race", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-supervisor-race-"));
    const path = join(directory, "service.sqlite");
    const firstDb = new Database(path);
    const secondDb = new Database(path);
    try {
      const firstStores = createSqliteLocalServiceStores(firstDb);
      const secondStores = createSqliteLocalServiceStores(secondDb);
      const admitted = firstStores.chatAdmission.admit({
        accountId: ACCOUNT,
        message: {
          id: "race-human",
          text: "race",
          sender: "human",
          type: "text",
          createdAt: 100,
          updatedAt: 100,
          chatSessionId: null,
          appId: null,
          journalRevision: 1,
          payloadHash: "sha256:race-human",
          messageSource: "desktop_chat",
          rating: null,
          reported: false,
          revision: "revision-race-human",
        },
        generationId: "generation-race",
        acceptedEventId: "event-race-accepted",
        admittedAt: 100,
        attachmentIds: [],
      });
      if (admitted.kind !== "created") throw new TypeError("race admission failed");
      let firstCallbacks: Parameters<ChatGenerationSource["start"]>[0] | null = null;
      let secondCallbacks: Parameters<ChatGenerationSource["start"]>[0] | null = null;
      const agentRunEvents = createInMemoryAgentRunEventStore();
      const source = (capture: (input: Parameters<ChatGenerationSource["start"]>[0]) => void): ChatGenerationSource =>
        Object.freeze({
          start(input) {
            capture(input);
            return Object.freeze({ cancel: (): void => {} });
          },
        });
      const supervisor = (
        stores: ReturnType<typeof createSqliteLocalServiceStores>,
        generationSource: ChatGenerationSource,
      ) => createChatGenerationSupervisor({
        source: generationSource,
        context: createEmptyChatGenerationContextSource(),
        messages: stores.chatMessages,
        events: stores.chatEvents,
        finalization: stores.chatFinalization,
        attachments: stores.chatAttachments,
        nowEpochMilliseconds: () => 200,
        assistantMessageId: () => "assistant-race",
        eventId: (_accountId, _generationId, kind, sequence) => `event-race-${kind}-${sequence}`,
        revision: () => "revision-assistant-race",
        agentRunEvents,
      });
      const first = supervisor(firstStores, source((input) => { firstCallbacks = input; }));
      const second = supervisor(secondStores, source((input) => { secondCallbacks = input; }));
      first.onAdmitted({
        accountId: ACCOUNT,
        stored: admitted.stored,
        acceptedEvent: admitted.acceptedEvent,
        bearerToken: "header.payload.signature",
      });
      second.onAdmitted({
        accountId: ACCOUNT,
        stored: admitted.stored,
        acceptedEvent: admitted.acceptedEvent,
        bearerToken: "header.payload.signature",
      });
      await new Promise((resolve) => setTimeout(resolve, 0));
      if (firstCallbacks === null || secondCallbacks === null) throw new TypeError("sources did not start");
      firstCallbacks.onDelta("winner");
      expect(secondStores.chatEvents.requestCancellation(ACCOUNT, "generation-race").kind)
        .toBe("accepted");
      firstCallbacks.onComplete();
      second.cancel(ACCOUNT, "generation-race");
      await new Promise((resolve) => setTimeout(resolve, 0));

      const kinds = firstStores.chatEvents.listAfter(ACCOUNT, "generation-race", null)!
        .map((event) => event.frame.kind);
      expect(kinds.filter((kind) => ["done", "failed", "cancelled"].includes(kind)))
        .toEqual(["done"]);
      expect(firstStores.chatEvents.readLifecycle(ACCOUNT, "generation-race")?.state)
        .toBe("terminal");
      expect((await Promise.resolve(firstStores.chatMessages.listHistory(ACCOUNT, {
        limit: 10,
        snapshotSequence: firstStores.chatMessages.readSnapshotSequence(ACCOUNT),
        olderThan: null,
      }))).messages.map((entry) => [entry.sender, entry.text])).toEqual([
        ["human", "race"],
        ["ai", "winner"],
      ]);
      const agentTerminalEvents = agentRunEvents.list("generation-race")
        .filter((event) => event.kind === "terminal");
      expect(agentTerminalEvents).toHaveLength(1);
      expect(agentTerminalEvents[0]).toMatchObject({
        terminalOutcome: "completed",
        terminalCode: "completed",
        retryable: false,
      });
    } finally {
      secondDb.close();
      firstDb.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("send replay produces one generation, one assistant, and one quota decrement", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement(ACCOUNT, {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 2,
      limitReached: false,
      upgradeAvailable: true,
    });
    const { db, local } = boot(stores);
    const request = create("bill-once");

    const first = await post(local, request);
    const firstBody = await first.text();
    const replay = await post(local, request);
    const replayBody = await replay.text();

    expect(first.status).toBe(201);
    expect(replay.status).toBe(200);
    expect(replayBody).toBe(firstBody);
    const admission = JSON.parse(firstBody) as ChatAdmissionBody;
    expect(await waitForTerminalLifecycle(stores.chatEvents, admission.generation.id, 100))
      .toBe("terminal");
    expect((await history(local)).map((message) => message.sender)).toEqual(["human", "ai"]);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
    db.close();
  });

  test("disconnecting SSE does not cancel generation and history converges", async () => {
    const source = createScriptedChatGenerationSource([
      { delayMs: 2, text: "streamed " },
      { delayMs: 20, text: "after disconnect" },
    ]);
    const { db, local } = boot(createInMemoryLocalServiceStores(), source);
    const { eventsResponse } = await admitAndOpen(local, create("disconnect"));
    const reader = eventsResponse.body!.getReader();
    await readUntil(reader, "delta");
    await reader.cancel();
    await new Promise((resolve) => setTimeout(resolve, 40));

    const messages = await history(local);
    expect(messages.map((message) => message.sender)).toEqual(["human", "ai"]);
    expect(messages.at(-1)?.text).toBe("streamed after disconnect");
    db.close();
  });

  test("slow SSE consumers get bounded batches and reconnect from the last durable cursor", async () => {
    const source = createScriptedChatGenerationSource([
      { delayMs: 1, text: "one" },
      { delayMs: 1, text: "two" },
      { delayMs: 1, text: "three" },
      { delayMs: 1, text: "four" },
    ]);
    const { db, local } = boot(
      createInMemoryLocalServiceStores(),
      source,
      "chat-stream-backpressure-proof",
      createEmptyChatGenerationContextSource(),
      {
        pollIntervalMs: 1,
        heartbeatIntervalMs: 0,
        maxBatchEvents: 2,
        maxBufferedEvents: 2,
        backpressurePollIntervalMs: 2,
      },
    );
    const { admission } = await admitAndOpen(local, create("stream-backpressure"));
    const firstResponse = await generationEvents(local, admission.generation.id);
    const firstReader = firstResponse.body!.getReader();
    const firstChunk = await firstReader.read();
    expect(firstChunk.done).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, 20));
    const firstTail = await readRemaining(firstReader, new TextDecoder().decode(firstChunk.value));
    const firstFrames = parseSse(firstTail);
    expect(firstFrames.some((frame) => frame.event === "done")).toBe(false);
    const lastCursor = firstFrames.at(-1)?.id;
    expect(lastCursor).toBeDefined();

    const reconnect = await generationEvents(local, admission.generation.id, lastCursor);
    const reconnectFrames = parseSse(await reconnect.text());
    expect(reconnectFrames.at(-1)?.event).toBe("done");
    expect(firstFrames.some((frame) => frame.event === "delta")).toBe(true);
    db.close();
  });

  test("idle SSE streams emit bounded heartbeat comments without advancing replay cursors", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    const { db, local } = boot(
      createInMemoryLocalServiceStores(),
      hanging,
      "chat-stream-heartbeat-proof",
      createEmptyChatGenerationContextSource(),
      {
        pollIntervalMs: 1,
        heartbeatIntervalMs: 2,
        maxBatchEvents: 4,
        maxBufferedEvents: 8,
        backpressurePollIntervalMs: 2,
      },
    );
    const { admission } = await admitAndOpen(local, create("stream-heartbeat"));
    const response = await generationEvents(local, admission.generation.id);
    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toContain("event: snapshot");
    const heartbeat = await reader.read();
    expect(heartbeat.done).toBe(false);
    expect(new TextDecoder().decode(heartbeat.value)).toContain(": heartbeat");
    await reader.cancel();
    db.close();
  });

  test("scheduler cleanup faults stay inside the callback boundary and still fail once", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onComplete());
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const scheduler: ChatGenerationScheduler = Object.freeze({
      setTimeout(callback): symbol {
        queueMicrotask(callback);
        return Symbol("timer");
      },
      clearTimeout(): void {
        throw new Error("injected timer cleanup fault");
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      source,
      "chat-scheduler-cleanup-proof",
      createEmptyChatGenerationContextSource(),
      undefined,
      scheduler,
      {
        firstEventDeadlineMs: 10,
        maxRunDurationMs: 20,
        heartbeatIntervalMs: 0,
        cancelGraceMs: 0,
      },
    );
    const { admission, eventsResponse } = await admitAndOpen(local, create("scheduler-cleanup"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.at(-1)?.event).toBe("failed");
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)
      ?.filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind))).toHaveLength(1);
    expect((await history(local)).filter((message) => message.sender === "ai")).toHaveLength(0);
    db.close();
  });

  test("cancel-grace scheduler failure falls back to one cancelled terminal", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    const scheduler: ChatGenerationScheduler = Object.freeze({
      setTimeout(callback, delayMs): ReturnType<typeof setTimeout> {
        if (delayMs === 3) throw new Error("injected grace timer fault");
        return setTimeout(callback, delayMs);
      },
      clearTimeout(handle): void {
        clearTimeout(handle as ReturnType<typeof setTimeout>);
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      source,
      "chat-cancel-grace-scheduler-proof",
      createEmptyChatGenerationContextSource(),
      undefined,
      scheduler,
      { firstEventDeadlineMs: 10, maxRunDurationMs: 20, heartbeatIntervalMs: 0, cancelGraceMs: 3 },
    );
    const { admission, eventsResponse } = await admitAndOpen(local, create("cancel-grace-scheduler"));
    const response = await local.app.request(`/v1/chat-generations/${admission.generation.id}`, {
      method: "DELETE", headers: auth(local.devToken),
    });
    expect(response.status).toBe(202);
    expect(parseSse(await eventsResponse.text()).at(-1)?.event).toBe("cancelled");
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)
      ?.filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind))).toHaveLength(1);
    db.close();
  });

  test("heartbeat reschedule scheduler failure becomes one failed terminal", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    let heartbeatSchedules = 0;
    const scheduler: ChatGenerationScheduler = Object.freeze({
      setTimeout(callback, delayMs): ReturnType<typeof setTimeout> {
        if (delayMs === 2) {
          heartbeatSchedules += 1;
          if (heartbeatSchedules === 2) throw new Error("injected heartbeat reschedule fault");
        }
        return setTimeout(callback, delayMs);
      },
      clearTimeout(handle): void {
        clearTimeout(handle as ReturnType<typeof setTimeout>);
      },
    });
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      source,
      "chat-heartbeat-scheduler-proof",
      createEmptyChatGenerationContextSource(),
      undefined,
      scheduler,
      { firstEventDeadlineMs: 20, maxRunDurationMs: 50, heartbeatIntervalMs: 2, cancelGraceMs: 0 },
    );
    const { admission, eventsResponse } = await admitAndOpen(local, create("heartbeat-reschedule"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.at(-1)?.event).toBe("failed");
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)
      ?.filter((event) => ["done", "failed", "cancelled"].includes(event.frame.kind))).toHaveLength(1);
    db.close();
  });

  test("compacted replay cursors heal an older SSE cursor from the terminal", async () => {
    const { db, local, stores } = boot(
      createInMemoryLocalServiceStores(),
      undefined,
      "chat-retention-policy-proof",
      createEmptyChatGenerationContextSource(),
      undefined,
      undefined,
      undefined,
      { ttlMs: 86_400_000, maxDetailEvents: 128 },
    );
    const { admission, eventsResponse } = await admitAndOpen(local, create("retention-replay"));
    await eventsResponse.text();
    await (await generationEvents(local, admission.generation.id)).text();
    expect(stores.chatEvents.retentionMetadata!(ACCOUNT, admission.generation.id)).toMatchObject({ ttlMs: 86_400_000 });
    const all = stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)!;
    const oldCursor = all.find((event) => event.frame.kind === "snapshot")?.id;
    expect(oldCursor).toBeDefined();
    const compactNow = Math.max(...all.map((event) => event.createdAt)) + 100;
    const compacted = stores.chatEvents.compact!(ACCOUNT, admission.generation.id, compactNow, {
      ttlMs: 1,
      maxDetailEvents: 0,
    });
    expect(compacted?.metadata.replayCursor).toBe(all.findLast((event) =>
      ["done", "failed", "cancelled"].includes(event.frame.kind))?.id);
    const replay = await generationEvents(local, admission.generation.id, oldCursor);
    const frames = parseSse(await replay.text());
    expect(frames.at(-1)?.event).toBe("done");
    db.close();
  });

  test("app-facing composition applies bounded liveness defaults when omitted", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), hanging, "chat-default-liveness-proof");
    const { eventsResponse } = await admitAndOpen(local, create("default-liveness"));
    const frames = parseSse(await eventsResponse.text());
    expect(frames.at(-1)?.data).toEqual({ kind: "failed", error: { code: "generation_timeout", retryable: true } });
    db.close();
  });

  test("retention compaction stays dormant until an explicit policy is injected", async () => {
    const { db, local, stores } = boot();
    const { admission, eventsResponse } = await admitAndOpen(local, create("retention-policy-omitted"));
    await eventsResponse.text();
    await (await generationEvents(local, admission.generation.id)).text();
    expect(stores.chatEvents.retentionMetadata!(ACCOUNT, admission.generation.id)).toBeNull();
    db.close();
  });

  test("agent timeline transport projects reload-stable tool, approval, recovery, usage, and terminal events", async () => {
    const agentStore = createInMemoryAgentRunEventStore();
    const detachedSupervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), undefined, "agent-timeline-proof",
      createEmptyChatGenerationContextSource(), undefined, undefined, undefined, undefined, agentStore,
      detachedSupervisor);
    const admission = await post(local, create("agent-timeline"));
    const accepted = await readAdmission(admission);
    const runId = accepted.generation.id;
    const supervisor = createAgentRunEventSupervisor({
      events: agentStore,
      nowEpochMilliseconds: () => 1_786_352_400_000,
      eventId: (id, sequence, kind) => `${id}:event:${sequence}:${kind}`,
    });
    supervisor.accepted({ runId, attemptId: `${runId}:attempt:1`, admissionId: accepted.message.id });
    const hidden = agentStore.append({
      schemaVersion: 1,
      runId,
      attemptId: `${runId}:attempt:1`,
      eventId: `${runId}:event:2:internal-status`,
      sequence: 2,
      visibility: "internal",
      createdAt: 1_786_352_400_000,
      safeSummary: "internal raw args must stay hidden",
      kind: "status",
      status: "generating",
      progressPct: null,
    });
    expect(hidden.kind).toBe("appended");
    supervisor.capability({ runId, attemptId: `${runId}:attempt:1`, capabilityId: "capability:scripted",
      tier: "deterministic-scripted", adapter: "scripted-chat-generation", deterministic: true });
    supervisor.context({ runId, attemptId: `${runId}:attempt:1`, contextReceiptId: "context:one",
      sourceKind: "memory", sourceRef: "source:one", sourceHash: `sha256:${"a".repeat(64)}`,
      ownerRef: ACCOUNT, expiresAt: null, redactedPreview: "safe context", tokenEstimate: 3,
      inclusionReason: "selected", policyDecision: "included" });
    supervisor.toolRequest({ runId, attemptId: `${runId}:attempt:1`, callId: "call:one", toolName: "clock",
      timeoutMs: 1000, idempotencyKey: "idem:one" });
    supervisor.toolResult({ runId, attemptId: `${runId}:attempt:1`, callId: "call:one", toolName: "clock",
      resultSummary: "safe result", durationMs: 2, retryable: false });
    supervisor.toolRequest({ runId, attemptId: `${runId}:attempt:1`, callId: "call:two", toolName: "search",
      timeoutMs: 1000, idempotencyKey: "idem:two" });
    supervisor.approvalRequested({ runId, attemptId: `${runId}:attempt:1`, approvalId: "approval:two",
      callId: "call:two", reason: "needs approval", expiresAt: 1_786_352_401_000 });
    supervisor.approvalResolved({ runId, attemptId: `${runId}:attempt:1`, approvalId: "approval:two",
      callId: "call:two", resolution: "approved" });
    supervisor.usage({ runId, attemptId: `${runId}:attempt:1`, usageId: "usage:one", inputTokens: 3,
      outputTokens: 2, totalTokens: 5, durationMs: 4 });
    supervisor.recovery({ runId, attemptId: `${runId}:attempt:1`, recoveryId: "recovery:one", action: "reconnect",
      reason: "provider reconnect", fromAttemptId: `${runId}:attempt:1`, toAttemptId: `${runId}:attempt:2` });
    const terminal = supervisor.terminal({ runId, attemptId: `${runId}:attempt:2`, terminalOutcome: "completed",
      terminalCode: "completed", retryable: false, recoveryAction: null });
    const snapshot = agentStore.snapshot();
    const reloaded = createInMemoryAgentRunEventStore();
    reloaded.restore(snapshot);
    const timelineResponse = await agentEvents(local, runId);
    const body = await timelineResponse.text();
    expect(timelineResponse.status).toBe(200);
    expect(body).toContain("tool_request");
    expect(body).toContain("approval_requested");
    expect(body).toContain("context_receipt");
    expect(body).toContain("recovery");
    expect(body).toContain("usage");
    expect(body).toContain(terminal.eventId);
    expect(body).not.toContain("raw");
    // Exercise the route against the restored ledger, not only a detached
    // equality check: a process reload must preserve the same projection.
    agentStore.reset();
    agentStore.restore(snapshot);
    const replay = await agentEvents(local, runId, terminal.eventId);
    expect((await replay.text())).toContain(terminal.eventId);
    const unknownCursor = await agentEvents(local, runId, "missing:event");
    expect(unknownCursor.status).toBe(410);
    const foreign = await agentEvents(local, "generation:foreign");
    expect(foreign.status).toBe(404);
    expect(reloaded.list(runId)).toEqual(agentStore.list(runId));
    db.close();
  });

  test("real scripted generation emits a joined agent timeline that reloads and replays", async () => {
    const agentStore = createInMemoryAgentRunEventStore();
    const source = createScriptedChatGenerationSource([{
      delayMs: 1,
      text: "scripted answer",
      progressPct: 35,
      usage: {
        usageId: "usage-scripted",
        provider: "local",
        model: "deterministic",
        inputTokens: 2,
        outputTokens: 1,
        totalTokens: 3,
      },
    }]);
    const { db, local } = boot(createInMemoryLocalServiceStores(), source,
      "agent-real-scripted-proof", createEmptyChatGenerationContextSource(),
      undefined, undefined, undefined, undefined, agentStore);
    const admission = await readAdmission(await post(local, create("agent-real-scripted")));
    const generation = await generationEvents(local, admission.generation.id);
    expect((await generation.text())).toContain("event: done");
    const events = agentStore.list(admission.generation.id);
    expect(events.map((event) => event.kind)).toEqual([
      "run_accepted", "capability_receipt", "status", "status", "context_receipt", "status", "status", "usage", "terminal",
    ]);
    expect(events.find((event) => event.kind === "status" && event.progressPct === 35)).toBeDefined();
    expect(events.find((event) => event.kind === "usage" && event.usageId === "usage-scripted")).toBeDefined();
    expect(events.every((event) => event.runId === admission.generation.id)).toBe(true);
    expect(events.filter((event) => event.kind === "terminal")).toHaveLength(1);
    expect(events.some((event) => event.kind === "tool_request" || event.kind === "approval_requested")).toBe(false);
    const timeline = await agentEvents(local, admission.generation.id);
    const body = await timeline.text();
    expect(body).toContain(`id: ${events.at(-1)!.eventId}`);
    expect(body).toContain("event: terminal");

    const snapshot = agentStore.snapshot();
    const reloaded = createInMemoryAgentRunEventStore();
    reloaded.restore(snapshot);
    expect(reloaded.list(admission.generation.id)).toEqual(events);
    const replay = await agentEvents(local, admission.generation.id, events.at(-1)!.eventId);
    expect((await replay.text())).toContain("event: terminal");
    db.close();
  });

  test("gateway-backed app admission joins canonical and agent SSE through SQLite replay", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-gateway-generation-acceptance-"));
    const path = join(directory, "service.sqlite");
    const gatewayToken = "loopback-gateway-token-must-not-escape";
    const privateProviderField = "provider-private-value-must-not-escape";
    const rawProviderField = "raw-provider-value-must-not-escape";
    let gatewayRequest: Readonly<{
      authorization: string | null;
      caller: string | null;
      user: string | null;
      feature: string | null;
      body: Record<string, unknown>;
    }> | null = null;
    const gateway = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      async fetch(request) {
        gatewayRequest = Object.freeze({
          authorization: request.headers.get("authorization"),
          caller: request.headers.get("x-omi-service-caller"),
          user: request.headers.get("x-omi-user-uid"),
          feature: request.headers.get("x-omi-llm-feature"),
          body: await request.json() as Record<string, unknown>,
        });
        return new Response([
          `data: ${JSON.stringify({
            choices: [{ delta: { content: "Gateway-backed " } }],
            private: privateProviderField,
          })}\n\n`,
          `data: ${JSON.stringify({
            choices: [{ delta: { content: "answer." } }],
            raw: { value: rawProviderField },
            usage: { prompt_tokens: 11, completion_tokens: 2, total_tokens: 13 },
          })}\n\n`,
          "data: [DONE]\n\n",
        ].join(""), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      },
    });
    const context = createDeterministicChatGenerationContextSource({
      candidates: [{
        sourceKind: "memory",
        sourceId: "memory:gateway-acceptance",
        claimId: "claim:gateway-acceptance",
        evidenceId: "evidence:gateway-acceptance",
        ownerAccountId: ACCOUNT,
        sourceHash: `sha256:${"d".repeat(64)}`,
        capturedAt: 1,
        expiresAt: null,
        redactedPreview: "The user prefers concise action plans.",
        tokenEstimate: 6,
        inclusionReason: "authorized acceptance context",
        policyDecision: "included",
      }],
    });
    const source = createGatewayChatGenerationSource({
      gatewayUrl: `http://127.0.0.1:${gateway.port}`,
      laneId: "omi:auto:chat-agent",
      serviceToken: gatewayToken,
    });
    const publicBodies: string[] = [];

    try {
      const firstDb = new Database(path);
      const firstStores = createSqliteLocalServiceStores(firstDb);
      const first = createLocalDevService({
        db: firstDb,
        stores: firstStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "gateway-generation-acceptance-proof",
        generationSource: source,
        generationContext: context,
      });

      const admittedResponse = await post(first, create("gateway-joined-acceptance"));
      expect(admittedResponse.status).toBe(201);
      expect(admittedResponse.headers.get("content-type")).toContain("application/json");
      const admission = await readAdmission(admittedResponse);
      const generationId = admission.generation.id;
      const canonicalInitialBody = await (await generationEvents(first, generationId)).text();
      publicBodies.push(canonicalInitialBody);
      const canonicalInitial = parseSse(canonicalInitialBody);
      expect(canonicalInitial.filter((frame) => ["done", "failed", "cancelled"].includes(frame.event)))
        .toHaveLength(1);
      expect(canonicalInitial.at(-1)?.data).toMatchObject({
        kind: "done",
        message: { text: "Gateway-backed answer.", generationOutcome: "completed" },
      });

      const agentInitialBody = await (await agentEvents(first, generationId)).text();
      publicBodies.push(agentInitialBody);
      const agentInitial = agentInitialBody.split("\n\n")
        .filter((block) => block.trim().length > 0)
        .map((block) => JSON.parse(block.split("\n")
          .find((line) => line.startsWith("data: "))!.slice(6)) as Record<string, unknown>);
      expect(agentInitial.every((event) => event.runId === generationId)).toBe(true);
      expect(agentInitial).toContainEqual(expect.objectContaining({
        kind: "capability_receipt",
        details: {
          tier: "unknown",
          adapter: "omi-llm-gateway",
          deterministic: false,
        },
      }));
      expect(agentInitial).toContainEqual(expect.objectContaining({
        kind: "context_receipt",
        details: expect.objectContaining({
          sourceKind: "context-packet",
          policyDecision: "included",
          tokenEstimate: 6,
        }),
      }));
      expect(agentInitial).toContainEqual(expect.objectContaining({
        kind: "usage",
        details: expect.objectContaining({
          inputTokens: 11,
          outputTokens: 2,
          totalTokens: 13,
        }),
      }));
      expect(agentInitial.filter((event) => event.kind === "terminal")).toHaveLength(1);
      expect(agentInitial.at(-1)).toMatchObject({
        kind: "terminal",
        details: {
          terminalOutcome: "completed",
          terminalCode: "completed",
          retryable: false,
          recoveryAction: null,
        },
      });

      expect(gatewayRequest).toMatchObject({
        authorization: `Bearer ${gatewayToken}`,
        caller: "platform",
        user: ACCOUNT,
        feature: "rewrite_chat",
      });
      expect(gatewayRequest?.body).toMatchObject({
        model: "omi:auto:chat-agent",
        stream: true,
        stream_options: { include_usage: true },
      });
      expect(JSON.stringify(gatewayRequest?.body.messages)).toContain(
        "The user prefers concise action plans.",
      );

      const canonicalReplayBefore = await (await generationEvents(first, generationId)).text();
      const agentReplayBefore = await (await agentEvents(first, generationId)).text();
      const historyBefore = await history(first);
      const agentSnapshotBefore = firstStores.agentRunEvents!.snapshot();
      publicBodies.push(canonicalReplayBefore, agentReplayBefore, JSON.stringify(historyBefore));
      expect(parseSse(canonicalReplayBefore).filter((frame) =>
        ["done", "failed", "cancelled"].includes(frame.event))).toHaveLength(1);
      firstDb.close();

      const secondDb = new Database(path);
      const secondStores = createSqliteLocalServiceStores(secondDb);
      const second = createLocalDevService({
        db: secondDb,
        stores: secondStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "gateway-generation-acceptance-proof",
        generationSource: source,
        generationContext: context,
      });
      const canonicalReplayAfter = await (await generationEvents(second, generationId)).text();
      const agentReplayAfter = await (await agentEvents(second, generationId)).text();
      const historyAfter = await history(second);
      publicBodies.push(canonicalReplayAfter, agentReplayAfter, JSON.stringify(historyAfter));
      expect(canonicalReplayAfter).toBe(canonicalReplayBefore);
      expect(agentReplayAfter).toBe(agentReplayBefore);
      expect(historyAfter).toEqual(historyBefore);
      expect(secondStores.agentRunEvents!.snapshot()).toEqual(agentSnapshotBefore);
      expect(secondStores.agentRunEvents!.list(generationId)
        .filter((event) => event.kind === "terminal")).toHaveLength(1);
      secondDb.close();

      const publicProjection = publicBodies.join("\n");
      expect(publicProjection).not.toContain(gatewayToken);
      expect(publicProjection).not.toContain(privateProviderField);
      expect(publicProjection).not.toContain(rawProviderField);
      expect(publicProjection).not.toMatch(/"(?:private|raw|arguments|credentials?)"\s*:/u);
    } finally {
      gateway.stop(true);
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("real provider failure emits one failed agent terminal with no tool or approval claims", async () => {
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onError({ code: "generation_provider_failed", retryable: false }));
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const agentStore = createInMemoryAgentRunEventStore();
    const { db, local } = boot(createInMemoryLocalServiceStores(), source,
      "agent-real-failure-proof", createEmptyChatGenerationContextSource(),
      undefined, undefined, undefined, undefined, agentStore);
    const admission = await readAdmission(await post(local, create("agent-real-failure")));
    const generation = await generationEvents(local, admission.generation.id);
    expect((await generation.text())).toContain("event: failed");
    const events = agentStore.list(admission.generation.id);
    const terminal = events.at(-1);
    expect(events.every((event) => event.runId === admission.generation.id)).toBe(true);
    expect(events.filter((event) => event.kind === "terminal")).toHaveLength(1);
    expect(terminal).toMatchObject({
      kind: "terminal",
      terminalOutcome: "failed",
      terminalCode: "generation_provider_failed",
      retryable: false,
      recoveryAction: null,
    });
    expect(events.some((event) => event.kind === "tool_request" || event.kind === "approval_requested")).toBe(false);
    expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
    const replay = await agentEvents(local, admission.generation.id);
    expect((await replay.text())).toContain("event: terminal");
    db.close();
  });

  test("agent timeline refreshes projection for events appended after connect", async () => {
    const agentStore = createInMemoryAgentRunEventStore();
    const detachedSupervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), undefined,
      "agent-timeline-live-projection-proof", createEmptyChatGenerationContextSource(),
      undefined, undefined, undefined, undefined, agentStore, detachedSupervisor);
    const admission = await readAdmission(await post(local, create("agent-live-projection")));
    const runId = admission.generation.id;
    const attemptId = `${runId}:attempt:1`;
    const supervisor = createAgentRunEventSupervisor({
      events: agentStore,
      nowEpochMilliseconds: () => 1_786_352_400_000,
      eventId: (id, sequence, kind) => `${id}:event:${sequence}:${kind}`,
    });
    supervisor.accepted({ runId, attemptId, admissionId: admission.message.id });
    const response = await agentEvents(local, runId);
    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(first.done).toBe(false);
    expect(new TextDecoder().decode(first.value)).toContain("run_accepted");
    // These events are appended after connect. The stream must re-project the
    // durable ledger rather than consulting only its initial visible map.
    supervisor.status({ runId, attemptId, status: "generating", progressPct: 40 });
    supervisor.terminal({ runId, attemptId, terminalOutcome: "failed",
      terminalCode: "generation_provider_failed", retryable: true, recoveryAction: null });
    const body = await readRemaining(reader, new TextDecoder().decode(first.value));
    expect(body).toContain("event: status");
    expect(body).toContain("event: terminal");
    expect((body.match(/event: terminal/gu) ?? [])).toHaveLength(1);
    db.close();
  });

  test("corrupt durable agent state is a fixed replay-expired response, not a generic 500", async () => {
    const db = new Database(":memory:");
    const stores = createSqliteLocalServiceStores(db);
    const detachedSupervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "agent-timeline-corrupt-route-proof",
      generationSource: createScriptedChatGenerationSource([]),
      generationContext: createEmptyChatGenerationContextSource(),
      chatSupervisor: detachedSupervisor,
    });
    const admission = await readAdmission(await post(local, create("agent-corrupt-route")));
    const runId = admission.generation.id;
    const sidecar = createAgentRunEventSupervisor({
      events: stores.agentRunEvents!,
      nowEpochMilliseconds: () => 1_786_352_400_000,
      eventId: (id, sequence, kind) => `${id}:event:${sequence}:${kind}`,
    });
    sidecar.accepted({ runId, attemptId: `${runId}:attempt:1`, admissionId: admission.message.id });
    db.query("UPDATE service_agent_run_events SET event_json = ? WHERE run_id = ? AND sequence = ?")
      .run("{not-json", runId, 1);
    const response = await agentEvents(local, runId);
    expect(response.status).toBe(410);
    expect(response.status).not.toBe(500);
    db.close();
  });

  test("agent timeline closes a live reader after auth revocation on the next bounded poll", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    const agentStore = createInMemoryAgentRunEventStore();
    const detachedSupervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), hanging,
      "agent-timeline-auth-lease-proof", createEmptyChatGenerationContextSource(),
      undefined, undefined, undefined, undefined, agentStore, detachedSupervisor);
    const admission = await readAdmission(await post(local, create("agent-auth-lease")));
    const supervisor = createAgentRunEventSupervisor({
      events: agentStore,
      nowEpochMilliseconds: () => 1_786_352_400_000,
      eventId: (id, sequence, kind) => `${id}:event:${sequence}:${kind}`,
    });
    supervisor.accepted({ runId: admission.generation.id, attemptId: `${admission.generation.id}:attempt:1`,
      admissionId: admission.message.id });
    const response = await agentEvents(local, admission.generation.id);
    const reader = response.body!.getReader();
    const initial = await reader.read();
    expect(initial.done).toBe(false);
    expect(new TextDecoder().decode(initial.value)).toContain("run_accepted");

    const revoked = await local.app.request("/v1/session/current", {
      method: "DELETE",
      headers: auth(local.devToken),
    });
    const outcome = await readOutcomeWithin(reader, 100);
    if (outcome.kind === "timeout") await reader.cancel();
    expect(revoked.status).toBe(204);
    expect(outcome).toEqual({ kind: "read", done: true });
    db.close();
  });

  test("agent timeline slow readers use one positive-delay backpressure retry without spinning", async () => {
    const scheduled: number[] = [];
    const handles = new Set<object>();
    let clearCalls = 0;
    const scheduler: ChatGenerationScheduler = {
      setTimeout(callback, delayMs) {
        const handle = { callback };
        handles.add(handle);
        scheduled.push(delayMs);
        return handle;
      },
      clearTimeout(handle) {
        clearCalls += 1;
        if (typeof handle === "object" && handle !== null) handles.delete(handle as object);
        if (clearCalls === 1) throw new Error("injected clear failure");
      },
    };
    const hanging: ChatGenerationSource = Object.freeze({
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    const agentStore = createInMemoryAgentRunEventStore();
    const detachedSupervisor: ChatGenerationSupervisor = Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), hanging,
      "agent-timeline-backpressure-proof", createEmptyChatGenerationContextSource(),
      undefined, scheduler, undefined, undefined, agentStore, detachedSupervisor);
    const admission = await readAdmission(await post(local, create("agent-backpressure")));
    const runId = admission.generation.id;
    const attemptId = `${runId}:attempt:1`;
    const supervisor = createAgentRunEventSupervisor({
      events: agentStore,
      nowEpochMilliseconds: () => 1_786_352_400_000,
      eventId: (id, sequence, kind) => `${id}:event:${sequence}:${kind}`,
    });
    supervisor.accepted({ runId, attemptId, admissionId: admission.message.id });
    for (let index = 0; index < 20; index += 1) {
      supervisor.status({ runId, attemptId, status: "generating", progressPct: index });
    }
    const response = await agentEvents(local, runId);
    const reader = response.body!.getReader();
    // Do not read: desiredSize reaches zero after the first enqueue and must
    // defer rather than queueMicrotask-spin over the remaining events.
    await new Promise((resolve) => setTimeout(resolve, 0));
    const scheduledBefore = scheduled.length;
    expect(scheduledBefore).toBeGreaterThan(0);
    expect(scheduled.every((delay) => delay >= 1)).toBe(true);
    expect(scheduled).toContain(5);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(scheduled.length).toBe(scheduledBefore);
    await reader.cancel();
    expect(clearCalls).toBeGreaterThan(0);
    db.close();
  });
});
