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
