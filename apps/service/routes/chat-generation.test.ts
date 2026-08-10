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
} from "../app-facing";
import {
  createChatGenerationSupervisor,
  type ChatGenerationSupervisor,
} from "../chat/generation-supervisor";
import {
  createEmptyChatGenerationContextSource,
} from "../chat/generation-context";
import {
  createScriptedChatGenerationSource,
  type ChatGenerationSource,
} from "../chat/generation-source";
import type { ChatGenerationFrame } from "../stores/chat-generation-events-store";
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
    expect(await Promise.all(replays.map((response) => response.text()))).toHaveLength(8);
    db.close();
  });

  test("terminal SSE frame is byte-equal to the canonical history message", async () => {
    const { db, local } = boot();
    const response = await post(local, create("terminal-canonical"));
    expect(response.status).toBe(201);
    expect(response.headers.get("content-type")).toContain("text/event-stream");

    const frames = parseSse(await response.text());
    expect(frames.map((frame) => frame.event)).toEqual([
      "accepted", "snapshot", "delta", "delta", "done",
    ]);
    const terminal = frames.at(-1)?.data;
    expect(terminal?.kind).toBe("done");
    const canonical = (await history(local)).find((message) => message.sender === "ai");
    if (terminal?.kind !== "done" || canonical === undefined) throw new TypeError("missing terminal");
    expect(JSON.stringify(terminal.message)).toBe(JSON.stringify(canonical));
    db.close();
  });

  test("cancellation retains a durable partial and replay is idempotent", async () => {
    const source = createScriptedChatGenerationSource([
      { delayMs: 2, text: "retained partial" },
      { delayMs: 100, text: " must not arrive" },
    ]);
    const { db, local } = boot(createInMemoryLocalServiceStores(), source);
    const admitted = await post(local, create("cancel-partial"));
    const reader = admitted.body!.getReader();
    const throughDelta = await readUntil(reader, "delta");
    const accepted = parseSse(throughDelta).find((frame) => frame.event === "accepted")!;
    if (accepted.data.kind !== "accepted") throw new TypeError("missing admission");

    const cancelled = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}`,
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
    expect(JSON.stringify(canonical)).toBe(JSON.stringify(terminal.message));

    const repeated = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    expect(repeated.status).toBe(204);
    const replay = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}/events`,
      { headers: auth(local.devToken) },
    );
    const replayFrames = parseSse(await replay.text());
    expect(replayFrames).toHaveLength(1);
    expect(replayFrames[0]?.data).toEqual(terminal);
    const replayAtTerminal = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}/events`,
      { headers: { ...auth(local.devToken), "last-event-id": terminalFrames.at(-1)!.id } },
    );
    expect(parseSse(await replayAtTerminal.text())[0]?.data).toEqual(terminal);
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
    const admitted = await post(local, create("duplicate-cancel"));
    const reader = admitted.body!.getReader();
    const throughDelta = await readUntil(reader, "delta");
    const accepted = parseSse(throughDelta).find((frame) => frame.event === "accepted");
    if (accepted?.data.kind !== "accepted") throw new TypeError("missing admission");
    const path = `/v1/chat-generations/${accepted.data.generation.id}`;

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
    expect(stores.chatEvents.readLifecycle(ACCOUNT, accepted.data.generation.id)?.state)
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
    const admitted = await post(local, create("cancel-rejection"));
    const reader = admitted.body!.getReader();
    const throughDelta = await readUntil(reader, "delta");
    const accepted = parseSse(throughDelta).find((frame) => frame.event === "accepted");
    if (accepted?.data.kind !== "accepted") throw new TypeError("missing admission");

    const cancelled = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}`,
      { method: "DELETE", headers: auth(local.devToken) },
    );
    const frames = parseSse(await readRemaining(reader, throughDelta));

    expect(cancelled.status).toBe(202);
    expect(cancelCalls).toBe(1);
    expect(frames.at(-1)?.event).toBe("cancelled");
    expect(stores.chatEvents.readLifecycle(ACCOUNT, accepted.data.generation.id)?.state)
      .toBe("terminal");
    db.close();
  });

  test("reconnect starts with a current snapshot and Last-Event-ID replays strictly after", async () => {
    const hanging: ChatGenerationSource = Object.freeze({
      start(input) {
        queueMicrotask(() => input.onDelta("current partial"));
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local } = boot(createInMemoryLocalServiceStores(), hanging, "chat-reconnect-proof");
    const admitted = await post(local, create("reconnect"));
    const reader = admitted.body!.getReader();
    const initial = parseSse(await readUntil(reader, "delta"));
    const accepted = initial.find((frame) => frame.event === "accepted")!;
    const snapshot = initial.find((frame) => frame.event === "snapshot")!;
    if (accepted.data.kind !== "accepted") throw new TypeError("missing admission");
    await reader.cancel();

    const fresh = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}/events`,
      { headers: auth(local.devToken) },
    );
    const freshReader = fresh.body!.getReader();
    const freshText = await readUntil(freshReader, "snapshot");
    const freshSnapshot = parseSse(freshText)[0];
    expect(freshSnapshot?.data).toEqual({ kind: "snapshot", text: "current partial" });
    await freshReader.cancel();

    const afterAccepted = await local.app.request(
      `/v1/chat-generations/${accepted.data.generation.id}/events`,
      { headers: { ...auth(local.devToken), "last-event-id": accepted.id } },
    );
    const replayReader = afterAccepted.body!.getReader();
    const replayText = await readUntil(replayReader, "delta");
    expect(parseSse(replayText).map((frame) => frame.event)).toEqual(["snapshot", "delta"]);
    expect(parseSse(replayText)[0]?.id).toBe(snapshot.id);
    await replayReader.cancel();
    db.close();
  });

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
        const reader = admitted.body!.getReader();
        const beforeCrash = parseSse(await readUntil(reader, "delta"));
        const accepted = beforeCrash.find((frame) => frame.event === "accepted")!;
        if (accepted.data.kind !== "accepted") throw new TypeError("missing admission");
        generationId = accepted.data.generation.id;
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
        expect(starts).toBe(0);
        expect((await history(local)).map((entry) => entry.sender)).toEqual(["human"]);
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
    const firstFrames = parseSse(await first.text());
    const replay = await post(local, request);
    const replayFrames = parseSse(await replay.text());

    expect(first.status).toBe(201);
    expect(replay.status).toBe(200);
    expect(replayFrames).toEqual(firstFrames);
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
    const response = await post(local, create("disconnect"));
    const reader = response.body!.getReader();
    await readUntil(reader, "delta");
    await reader.cancel();
    await new Promise((resolve) => setTimeout(resolve, 40));

    const messages = await history(local);
    expect(messages.map((message) => message.sender)).toEqual(["human", "ai"]);
    expect(messages.at(-1)?.text).toBe("streamed after disconnect");
    db.close();
  });
});
