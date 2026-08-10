import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  BridgePayloadStream,
  BridgeStreamOpenRequest,
  BridgeStreamPort,
  ChatMessage,
  RecordId,
} from "@omi-core/contracts";
import {
  IncrementalChatGenerationParser,
  observeChatGeneration,
  type ChatGenerationObservationEvent,
} from "@omi-core/adapters-platform";
import { ManualEnv } from "../fakes.js";

function assistant(id: string, text: string): ChatMessage {
  return {
    id: id as RecordId,
    text,
    sender: "ai",
    type: "text",
    createdAt: 1,
    updatedAt: 2,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:canonical",
    messageSource: "desktop_chat",
    rating: null,
    reported: false,
    generationOutcome: "completed",
    revision: "revision-1",
    attachments: [],
  };
}

function event(id: string, kind: string, data: string): string {
  return `event: ${kind}\nid: ${id}\ndata: ${data}\n\n`;
}

test("incremental SSE survives every byte boundary, multiline data, and UTF-8 splits", () => {
  // red-proof: replace decoder.decode(chunk, {stream:true}) with a fresh
  // non-streaming decode. The split emoji throws or becomes replacement text.
  const terminal = { kind: "done", message: assistant("assistant-byte-split", "hé🙂 done") };
  const transcript = [
    event("opaque-snapshot", "snapshot", '{"kind":"snapshot","text":""}'),
    [
      "event: delta",
      "id: opaque-delta-1",
      'data: {"kind":',
      'data: "delta","text":"hé🙂"}',
      "",
      "",
    ].join("\n"),
    event("opaque-delta-2", "delta", '{"kind":"delta","text":" live"}'),
    event("opaque-terminal", "done", JSON.stringify(terminal)),
  ].join("");
  const bytes = new TextEncoder().encode(transcript);
  const parser = new IncrementalChatGenerationParser();
  const parsed = [];
  for (const byte of bytes) parsed.push(...parser.push(Uint8Array.of(byte)));
  parsed.push(...parser.finish());

  assert.deepEqual(
    parsed.map(({ id, frame }) => ({
      id,
      kind: frame.kind,
      ...(frame.kind === "snapshot" || frame.kind === "delta" ? { text: frame.text } : {}),
    })),
    [
      { id: "opaque-snapshot", kind: "snapshot", text: "" },
      { id: "opaque-delta-1", kind: "delta", text: "hé🙂" },
      { id: "opaque-delta-2", kind: "delta", text: " live" },
      { id: "opaque-terminal", kind: "done" },
    ],
  );
});

class ScriptedStream implements BridgePayloadStream {
  cancelled = false;

  constructor(
    readonly id: string,
    readonly channel: string,
    private readonly chunks: readonly string[],
  ) {}

  async *[Symbol.asyncIterator](): AsyncIterator<string> {
    for (const chunk of this.chunks) {
      if (this.cancelled) return;
      yield chunk;
    }
  }

  cancel(): void {
    this.cancelled = true;
  }
}

class ScriptedStreamPort implements BridgeStreamPort {
  readonly opens: BridgeStreamOpenRequest[] = [];
  readonly streams: ScriptedStream[] = [];

  constructor(private readonly scripts: readonly (readonly string[])[]) {}

  open(request: BridgeStreamOpenRequest): BridgePayloadStream {
    const script = this.scripts[this.opens.length];
    if (script === undefined) throw new Error("unexpected extra stream open");
    this.opens.push(request);
    const stream = new ScriptedStream(`script-${this.opens.length}`, request.channel, script);
    this.streams.push(stream);
    return stream;
  }
}

test("disconnect reconnects after the exact opaque id without duplicate events", async () => {
  const done = { kind: "done", message: assistant("assistant-reconnect", "Recovered answer") };
  const port = new ScriptedStreamPort([
    [
      event("event-snapshot-1", "snapshot", '{"kind":"snapshot","text":""}') +
      event("event-delta-1", "delta", '{"kind":"delta","text":"Recovered"}'),
    ],
    [
      event("event-delta-1", "delta", '{"kind":"delta","text":"duplicate"}') +
      event("event-snapshot-2", "snapshot", '{"kind":"snapshot","text":"Recovered"}') +
      event("event-delta-2", "delta", '{"kind":"delta","text":" answer"}') +
      event("event-terminal", "done", JSON.stringify(done)),
    ],
  ]);
  const env = new ManualEnv();
  const observation = observeChatGeneration(port, "generation/reconnect", env);
  const observed: ChatGenerationObservationEvent[] = [];
  const consume = (async () => {
    for await (const item of observation.events) observed.push(item);
  })();
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
  await env.advance(250);
  await consume;

  assert.deepEqual(port.opens, [
    {
      channel: "chat-generation-events",
      params: '{"generationId":"generation/reconnect"}',
      initialCredit: 4,
    },
    {
      channel: "chat-generation-events",
      params: '{"generationId":"generation/reconnect","lastEventId":"event-delta-1"}',
      initialCredit: 4,
    },
  ]);
  assert.deepEqual(
    observed.map((item) => item.kind === "terminal"
      ? { kind: item.kind, id: item.id, terminal: item.terminal.kind }
      : item),
    [
      { kind: "snapshot", id: "event-snapshot-1", text: "" },
      { kind: "delta", id: "event-delta-1", text: "Recovered" },
      { kind: "snapshot", id: "event-snapshot-2", text: "Recovered" },
      { kind: "delta", id: "event-delta-2", text: " answer" },
      { kind: "terminal", id: "event-terminal", terminal: "done" },
    ],
  );
  assert.equal(port.streams[1]?.cancelled, true, "terminal promptly closes the bridge stream");
});

test("missing snapshot and malformed SSE expose an error instead of advisory text", async () => {
  const port = new ScriptedStreamPort([
    [event("event-delta", "delta", '{"kind":"delta","text":"must not render"}')],
  ]);
  const observation = observeChatGeneration(port, "generation-invalid", new ManualEnv());
  const observed = [];
  for await (const item of observation.events) observed.push(item);
  assert.equal(observed.length, 1);
  assert.equal(observed[0]?.kind, "error");
  assert.match(observed[0]?.kind === "error" ? observed[0].failure : "", /leading snapshot/);
  assert.equal(port.streams[0]?.cancelled, true);
});

test("clean EOF waits on injected bounded backoff and preserves the exact cursor", async () => {
  const scripts = Array.from({ length: 51 }, () => [
    event("event-snapshot", "snapshot", '{"kind":"snapshot","text":"Saved"}'),
  ]);
  const port = new ScriptedStreamPort(scripts);
  const env = new ManualEnv();
  const delayed: number[] = [];
  const originalDelay = env.delay.bind(env);
  env.delay = (ms, fn) => {
    delayed.push(ms);
    return originalDelay(ms, fn);
  };
  const observation = observeChatGeneration(port, "generation-backoff", env);
  const iterator = observation.events[Symbol.asyncIterator]();
  assert.deepEqual(await iterator.next(), {
    value: { kind: "snapshot", id: "event-snapshot", text: "Saved" },
    done: false,
  });

  let settled = false;
  const terminal = iterator.next().then((value) => {
    settled = true;
    return value;
  });
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
  assert.equal(port.opens.length, 1, "clean EOF cannot spin open in microtasks");
  assert.deepEqual(delayed, [250], "the first reconnect delay is nonzero and injected");
  assert.equal(settled, false);

  for (const delay of [250, 500, 1_000, 2_000, 4_000]) {
    await env.advance(delay);
  }
  const result = await terminal;
  assert.equal(result.done, false);
  assert.equal(result.value?.kind, "error");
  assert.match(result.value?.kind === "error" ? result.value.failure : "", /reconnect limit/);
  assert.equal(port.opens.length, 6, "initial open plus five retries is the hard bound");
  assert.deepEqual(delayed, [250, 500, 1_000, 2_000, 4_000]);
  for (const request of port.opens.slice(1)) {
    assert.equal(
      request.params,
      '{"generationId":"generation-backoff","lastEventId":"event-snapshot"}',
    );
  }
});
