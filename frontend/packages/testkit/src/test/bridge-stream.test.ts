import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  BRIDGE_STREAM_MESSAGE_CHANNEL,
  BRIDGE_STREAM_SINK_FUNCTION,
  type StreamFromShellWire,
  type StreamToShellWire,
} from "@omi-core/contracts";
import {
  BridgeStreamProtocolError,
  bridgeStreamPort,
  isBridgeStreamAvailable,
} from "@omi-core/bridge-web";

const host = globalThis as unknown as Record<string, unknown>;

afterEach(() => {
  Reflect.deleteProperty(host, BRIDGE_STREAM_MESSAGE_CHANNEL);
  Reflect.deleteProperty(host, BRIDGE_STREAM_SINK_FUNCTION);
});

function installHost(): {
  sent: StreamToShellWire[];
  emit(frame: StreamFromShellWire | string): void;
} {
  const sent: StreamToShellWire[] = [];
  host[BRIDGE_STREAM_MESSAGE_CHANNEL] = {
    postMessage(raw: string): void {
      sent.push(JSON.parse(raw) as StreamToShellWire);
    },
  };
  return {
    sent,
    emit(frame) {
      const sink = host[BRIDGE_STREAM_SINK_FUNCTION] as (raw: string) => void;
      sink(typeof frame === "string" ? frame : JSON.stringify(frame));
    },
  };
}

test("finite credit opens on the real host wire and consumption grants exactly one", async () => {
  // red-proof: remove Session.grantOne() from next()/accept(). The final
  // host-wire assertion contains only open instead of open,grant.
  const wire = installHost();
  assert.equal(isBridgeStreamAvailable(), true);
  const stream = bridgeStreamPort().open({
    channel: "chat-generation-events",
    params: JSON.stringify({ generationId: "generation-opaque" }),
    initialCredit: 2,
  });
  assert.deepEqual(wire.sent, [{
    t: "open",
    id: stream.id,
    channel: "chat-generation-events",
    params: '{"generationId":"generation-opaque"}',
    credit: 2,
  }]);

  wire.emit({ t: "data", id: stream.id, channel: stream.channel, payload: "first" });
  assert.deepEqual(await stream[Symbol.asyncIterator]().next(), { value: "first", done: false });
  assert.deepEqual(wire.sent[1], {
    t: "grant",
    id: stream.id,
    channel: stream.channel,
    credit: 1,
  });
});

test("zero credit is rejected before open and over-credit fails only its stream", async () => {
  // red-proof: delete the credit===0 guard in Session.accept(). The isolated
  // stream yields "overrun" instead of rejecting with credit-overrun.
  const wire = installHost();
  const port = bridgeStreamPort();
  assert.throws(
    () => port.open({ channel: "a", params: "{}", initialCredit: 0 }),
    /initial-credit-must-be-positive/,
  );
  assert.equal(wire.sent.length, 0);

  const overrun = port.open({ channel: "a", params: "{}", initialCredit: 1 });
  const isolated = port.open({ channel: "b", params: "{}", initialCredit: 1 });
  wire.emit({ t: "data", id: overrun.id, channel: "a", payload: "within-credit" });
  wire.emit({ t: "data", id: overrun.id, channel: "a", payload: "overrun" });
  await assert.rejects(overrun[Symbol.asyncIterator]().next(), (error: unknown) => {
    assert.ok(error instanceof BridgeStreamProtocolError);
    assert.equal(error.violation, "credit-overrun");
    return true;
  });
  wire.emit({ t: "data", id: isolated.id, channel: "b", payload: "uncontaminated" });
  assert.equal((await isolated[Symbol.asyncIterator]().next()).value, "uncontaminated");
  assert.ok(wire.sent.some((frame) =>
    frame.t === "cancel" && frame.id === overrun.id && frame.reason === "credit-overrun"));
});

test("malformed, wrong-id, and mismatched-channel frames never settle another stream", async () => {
  const wire = installHost();
  const port = bridgeStreamPort();
  const malformed = port.open({ channel: "a", params: "{}", initialCredit: 1 });
  const safe = port.open({ channel: "b", params: "{}", initialCredit: 1 });

  wire.emit(JSON.stringify({ t: "data", id: malformed.id, channel: "a", payload: 7 }));
  await assert.rejects(malformed[Symbol.asyncIterator]().next(), /malformed-frame/);
  wire.emit({ t: "data", id: "unknown-stream", channel: "b", payload: "wrong id" });
  wire.emit({ t: "data", id: safe.id, channel: "a", payload: "wrong channel" });
  await assert.rejects(safe[Symbol.asyncIterator]().next(), /mismatched-channel/);

  const untouched = port.open({ channel: "c", params: "{}", initialCredit: 1 });
  wire.emit({ t: "data", id: untouched.id, channel: "c", payload: "right stream" });
  assert.equal((await untouched[Symbol.asyncIterator]().next()).value, "right stream");
});

test("cancel is prompt and duplicate terminal or late data is dropped", async () => {
  // red-proof: move Session.retire()/settled until a shell terminal arrives.
  // The late payload below becomes observable instead of the immediate done.
  const wire = installHost();
  const stream = bridgeStreamPort().open({ channel: "chat", params: "{}", initialCredit: 1 });
  const iterator = stream[Symbol.asyncIterator]();
  const pending = iterator.next();
  stream.cancel("user-stop");
  assert.deepEqual(await pending, { value: undefined, done: true });
  assert.deepEqual(wire.sent.at(-1), {
    t: "cancel",
    id: stream.id,
    channel: "chat",
    reason: "user-stop",
  });
  wire.emit({ t: "data", id: stream.id, channel: "chat", payload: "late" });
  wire.emit({ t: "end", id: stream.id, channel: "chat" });
  wire.emit({ t: "error", id: stream.id, channel: "chat", failure: "duplicate terminal" });
  assert.deepEqual(await iterator.next(), { value: undefined, done: true });
});

test("shell error is the sole terminal and cannot contaminate a sibling", async () => {
  const wire = installHost();
  const port = bridgeStreamPort();
  const failed = port.open({ channel: "a", params: "{}", initialCredit: 1 });
  const sibling = port.open({ channel: "b", params: "{}", initialCredit: 1 });
  wire.emit({ t: "error", id: failed.id, channel: "a", failure: "offline" });
  await assert.rejects(failed[Symbol.asyncIterator]().next(), /shell error: offline/);
  wire.emit({ t: "data", id: sibling.id, channel: "b", payload: "still live" });
  assert.equal((await sibling[Symbol.asyncIterator]().next()).value, "still live");
});
