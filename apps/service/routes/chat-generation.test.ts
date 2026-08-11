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
  type ChatGenerationContextSource,
} from "../chat/generation-context";
import {
  createScriptedChatGenerationSource,
  type ChatGenerationSource,
} from "../chat/generation-source";
import type { ChatGenerationFrame } from "../stores/chat-generation-events-store";
import type { ChatGenerationEventsStore } from "../stores/chat-generation-events-store";
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

  test("cancellation before context or provider start retains one empty cancelled assistant", async () => {
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
    expect(frames[0]?.data).toMatchObject({
      kind: "cancelled",
      message: { sender: "ai", text: "", generationOutcome: "cancelled" },
    });
    if (frames[0]?.data.kind !== "cancelled") throw new TypeError("missing cancellation");
    const canonical = (await history(local)).find((message) => message.sender === "ai");
    expect(JSON.stringify(canonical)).toBe(JSON.stringify(frames[0].data.message));
    expect(starts).toBe(0);
    expect(stores.chatEvents.listAfter(ACCOUNT, admission.generation.id, null)?.map(
      (event) => event.frame.kind,
    )).toEqual(["accepted", "snapshot", "cancelled"]);
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
        const local = createLocalDevService({
          db,
          stores: createSqliteLocalServiceStores(db),
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
        expect(frames[0]?.data).toMatchObject({
          kind: "cancelled",
          message: { sender: "ai", text: "", generationOutcome: "cancelled" },
        });
        expect(starts).toBe(0);
        expect((await history(local)).map((entry) => [
          entry.sender,
          entry.text,
          (entry as ChatWireMessage).generationOutcome,
        ])).toEqual([
          ["human", "cancel after restart", null],
          ["ai", "", "cancelled"],
        ]);
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
      });
      const first = supervisor(firstStores, source((input) => { firstCallbacks = input; }));
      const second = supervisor(secondStores, source((input) => { secondCallbacks = input; }));
      first.onAdmitted({ accountId: ACCOUNT, stored: admitted.stored, acceptedEvent: admitted.acceptedEvent });
      second.onAdmitted({ accountId: ACCOUNT, stored: admitted.stored, acceptedEvent: admitted.acceptedEvent });
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
});
