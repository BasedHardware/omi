import { describe, expect, test } from "bun:test";

import { parseChatGenerationEventStream } from "@omi-core/adapters-platform";

import {
  CHAT_GENERATION_SSE_HEARTBEAT,
  CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS,
  openLiveGenerationSse,
} from "../src/generation-sse";
import type { GenerationEvent } from "../src/wire";

const snapshot = (id: string, text: string): GenerationEvent => ({
  id,
  kind: "snapshot",
  text,
});

const delta = (id: string, text: string): GenerationEvent => ({
  id,
  kind: "delta",
  text,
});

const done = (id: string): GenerationEvent => ({
  id,
  kind: "done",
  message: {
    id: "assistant-1",
    text: "done",
    sender: "ai",
    type: "text",
    createdAt: 1,
    updatedAt: 1,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "hash",
    messageSource: "omi",
    rating: null,
    reported: false,
    revision: null,
    attachments: [],
    generationOutcome: "completed",
  },
});

const encode = (event: GenerationEvent): string => {
  const { id: _id, ...frame } = event;
  return `event: ${event.kind}\nid: ${event.id}\ndata: ${JSON.stringify(
    frame
  )}\n\n`;
};

const isTerminal = (event: GenerationEvent): boolean =>
  event.kind === "done" ||
  event.kind === "failed" ||
  event.kind === "cancelled";

const readUntil = async (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  predicate: (text: string) => boolean,
  timeoutMs: number
): Promise<string> => {
  const decoder = new TextDecoder();
  let text = "";
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(0, deadline - Date.now());
    const result = await Promise.race([
      reader.read(),
      new Promise<{ done: true; value: undefined }>((resolve) => {
        setTimeout(() => {
          resolve({ done: true, value: undefined });
        }, remaining);
      }),
    ]);
    if (result.value !== undefined) {
      text += decoder.decode(result.value);
      if (predicate(text)) return text;
    }
    if (result.done && result.value === undefined && Date.now() >= deadline) {
      break;
    }
  }
  return text;
};

describe("live generation SSE heartbeats", () => {
  test("idle cadence matches production comment heartbeats", () => {
    expect(CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS).toBe(5_000);
    expect(CHAT_GENERATION_SSE_HEARTBEAT).toBe(": heartbeat\n\n");
  });

  test("idle live streams emit comment heartbeats without advancing replay cursors", async () => {
    const stream = openLiveGenerationSse(
      encode,
      [snapshot("event-1", "hello")],
      () => () => {},
      isTerminal,
      20
    );
    const reader = stream.getReader();
    const body = await readUntil(
      reader,
      (text) => text.includes(": heartbeat"),
      200
    );
    await reader.cancel();

    expect(body).toContain("event: snapshot\nid: event-1\n");
    expect(body).toContain(": heartbeat\n\n");
    expect(parseChatGenerationEventStream(body)).toEqual([
      { kind: "snapshot", text: "hello" },
    ]);
  });

  test("activity resets the idle heartbeat timer", async () => {
    let emit: (event: GenerationEvent) => void = () => {};
    const stream = openLiveGenerationSse(
      encode,
      [snapshot("event-1", "hello")],
      (listener) => {
        emit = listener;
        return () => {
          emit = () => {};
        };
      },
      isTerminal,
      40
    );
    const reader = stream.getReader();
    const burst = await readUntil(
      reader,
      (text) => text.includes("event: snapshot"),
      100
    );
    expect(burst).toContain("event: snapshot");

    let ordinal = 0;
    emit(delta(`delta-${ordinal}`, "+"));
    const activity = setInterval(() => {
      ordinal += 1;
      emit(delta(`delta-${ordinal}`, "+"));
    }, 10);
    const duringActivity = await readUntil(
      reader,
      (text) => text.includes(": heartbeat"),
      90
    );
    clearInterval(activity);

    expect(duringActivity).not.toContain(": heartbeat");

    const idle = await readUntil(
      reader,
      (text) => text.includes(": heartbeat"),
      200
    );
    await reader.cancel();
    expect(idle).toContain(": heartbeat\n\n");
  });

  test("a terminal event stops heartbeats and closes the live stream", async () => {
    let emit: (event: GenerationEvent) => void = () => {};
    const stream = openLiveGenerationSse(
      encode,
      [snapshot("event-1", "hello")],
      (listener) => {
        emit = listener;
        return () => {
          emit = () => {};
        };
      },
      isTerminal,
      20
    );
    const reader = stream.getReader();
    await readUntil(reader, (text) => text.includes("event: snapshot"), 100);
    emit(done("event-done"));
    const body = await readUntil(
      reader,
      (text) => text.includes("event: done"),
      100
    );
    const rest = await readUntil(reader, () => false, 80);
    await reader.cancel();

    expect(body).toContain("event: done\nid: event-done\n");
    expect(`${body}${rest}`).not.toContain(": heartbeat");
  });
});
