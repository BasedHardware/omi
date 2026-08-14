/**
 * /listen protocol conformance — replays the prototype corpus through the
 * generated @omi-core/wire-listen decoder.
 *
 * Corpus ported from prototypes/listen-schema/conformance/corpus.json.
 * Hermetic: no network, no wall clock.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { isDegraded, type FallbackRecord, type FallbackSink } from "@omi-core/contracts";
import {
  LISTEN_CLIENT_MESSAGE_TYPES,
  LISTEN_CLOSE_CODES,
  LISTEN_HANDSHAKE_PARAM_DEFAULTS,
  LISTEN_HANDSHAKES,
  LISTEN_HEARTBEAT_TEXT,
  LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION,
  LISTEN_RESERVED_UNEMITTED_TYPES,
  LISTEN_SERVER_EVENT_TYPES,
  checkAll,
  createListenCaptureStreamPort,
  decode,
  decodeValue,
  indexByWireType,
  listenEntitlementPayloadFromEvent,
  listenReservedCloseEntitlementExhaustionInfo,
  shouldRetryAfterClose,
  unwrapDecoded,
  Validator,
  type DecodedListenFrame,
  type EntitlementEvent,
} from "@omi-core/wire-listen";
import { ManualEnv } from "../fakes.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_ROOT = join(HERE, "../../../..");
const require = createRequire(import.meta.url);
const schema = JSON.parse(
  readFileSync(join(CORE_ROOT, "contracts/wire/listen/listen-protocol.schema.json"), "utf8"),
) as {
  $defs: Record<string, Record<string, unknown>>;
  "x-omi-protocol": {
    non_envelope_frames: { id: string; direction: string }[];
    version_knob: { present: boolean };
    unemitted_model_classes: string[];
    invariants: { id: string; checkable: boolean; rule?: string }[];
    close_codes: { code: number }[];
    baseline: string;
    schema_version: string;
  };
};

const corpus = JSON.parse(readFileSync(require.resolve("@omi-core/wire-listen/fixtures/corpus.json"), "utf8")) as {
  scenarios: CorpusScenario[];
  client_messages: CorpusClientMessage[];
};

interface CorpusFrame {
  text?: string;
  json?: unknown;
  expect: string;
}

interface CorpusScenario {
  name: string;
  handshake: string;
  query?: string;
  invariants?: string[];
  violates?: string[];
  frames: CorpusFrame[];
  close?: number;
}

interface CorpusClientMessage {
  name: string;
  json: { type: string; [k: string]: unknown };
  valid: boolean;
  handshake_only?: string;
}

const proto = schema["x-omi-protocol"];
const validator = new Validator(schema);
const serverDefs = indexByWireType(schema, "server-event", "x-omi-event-type");
const clientDefs = indexByWireType(schema, "client-message", "x-omi-message-type");

class RecordingSink implements FallbackSink {
  readonly events: FallbackRecord[] = [];
  record(event: FallbackRecord): void {
    this.events.push(event);
  }
}

function frameText(frame: CorpusFrame): string {
  return "text" in frame && frame.text !== undefined ? frame.text : JSON.stringify(frame.json);
}

function tagOf(decoded: DecodedListenFrame): string {
  switch (decoded.kind) {
    case "event":
      return `event:${decoded.event.type}`;
    case "transcript_batch":
      return `transcript_batch:${decoded.segments.length}`;
    case "heartbeat":
      return "heartbeat";
    case "unknown_event":
      return `unknown_event:${decoded.type}`;
    case "invalid":
      return `invalid:${decoded.reason}`;
    default: {
      const _exhaustive: never = decoded;
      throw new Error(`unhandled kind ${JSON.stringify(_exhaustive)}`);
    }
  }
}

function replay(scenario: CorpusScenario) {
  const sink = new RecordingSink();
  const at = 1_000_000;
  const steps = scenario.frames.map((frame, index) => {
    const raw = frameText(frame);
    const result = decode(sink, at, raw);
    const decoded = unwrapDecoded(result);
    return { index, frame, raw, result, decoded };
  });
  return {
    steps,
    sink,
    close: scenario.close ?? null,
    query: scenario.query ?? "",
    handshake: scenario.handshake,
  };
}

// ------------------------------------------------- schema self-consistency

test("canonical server event enum has the 16 values from the requirements list", () => {
  assert.equal(LISTEN_SERVER_EVENT_TYPES.length, 16);
  assert.equal(new Set(LISTEN_SERVER_EVENT_TYPES).size, 16);
  const canonical = LISTEN_SERVER_EVENT_TYPES as readonly string[];
  assert.ok(!canonical.includes("auth_response"));
  assert.ok(!canonical.includes("entitlement"));
  assert.ok(serverDefs.has("auth_response"));
  assert.ok(serverDefs.has("entitlement"));
});

test("client->server enum has exactly the 4 session-scoped types", () => {
  assert.deepEqual([...LISTEN_CLIENT_MESSAGE_TYPES], [
    "image_chunk",
    "skip_question",
    "suggested_transcript",
    "speaker_assigned",
  ]);
  assert.ok(clientDefs.has("auth"));
  assert.ok(!(LISTEN_CLIENT_MESSAGE_TYPES as readonly string[]).includes("auth"));
});

test("exactly two non-envelope frames, both server->client", () => {
  assert.equal(proto.non_envelope_frames.length, 2);
  assert.deepEqual(
    proto.non_envelope_frames.map((f) => f.id),
    ["transcript_batch", "heartbeat"],
  );
  assert.equal(LISTEN_HEARTBEAT_TEXT, "ping");
});

test("close-code table: emitted 1xxx, reserved 4xxx (incl. entitlement 4020)", () => {
  for (const code of [1000, 1001, 1003, 1008, 1011]) {
    assert.equal(LISTEN_CLOSE_CODES[code]?.emittedByListen, true, `${code} should be emitted`);
  }
  for (const code of [4001, 4004, 4020]) {
    assert.equal(LISTEN_CLOSE_CODES[code]?.emittedByListen, false, `${code} is reserved/not emitted`);
  }
  assert.equal(LISTEN_CLOSE_CODES[4020]?.name, "entitlement_upgrade_required");
  assert.equal(shouldRetryAfterClose(1003), false);
  assert.equal(shouldRetryAfterClose(1008), false);
  assert.equal(shouldRetryAfterClose(1011), true);
  assert.equal(shouldRetryAfterClose(4020), false);
  assert.equal(shouldRetryAfterClose(1013), true);
});

test("two handshake variants with different param sets and no version knob", () => {
  assert.equal(LISTEN_HANDSHAKES.length, 2);
  const native = LISTEN_HANDSHAKES[0]!;
  const web = LISTEN_HANDSHAKES[1]!;
  assert.equal(native.path, "/v4/listen");
  assert.equal(native.params.length, 15);
  assert.equal(native.authMechanism, "dependency");
  assert.equal(web.path, "/v4/web/listen");
  assert.equal(web.params.length, 11);
  assert.equal(web.authMechanism, "first-frame");
  const nativeOnly = native.params.filter((p) => !(web.params as readonly string[]).includes(p));
  assert.deepEqual(nativeOnly, ["stt_service", "speaker_auto_assign", "create_speakers", "vad_gate"]);
  assert.equal(proto.version_knob.present, false);
});

test("every handshake param resolves to the one canonical param definition", () => {
  const canonical = Object.keys(LISTEN_HANDSHAKE_PARAM_DEFAULTS);
  for (const variant of LISTEN_HANDSHAKES) {
    for (const param of variant.params) {
      assert.ok(canonical.includes(param), `${param} missing from HandshakeParams`);
      const allowed = (
        schema.$defs["HandshakeParams"] as { properties: Record<string, { "x-omi-handshakes": string[] }> }
      ).properties[param]!["x-omi-handshakes"];
      assert.ok(allowed.includes(variant.id), `${param} not marked for handshake ${variant.id}`);
    }
  }
});

test("reserved-unemitted types include ping and entitlement", () => {
  assert.ok(LISTEN_RESERVED_UNEMITTED_TYPES.includes("ping"));
  assert.ok(LISTEN_RESERVED_UNEMITTED_TYPES.includes("entitlement"));
  assert.equal(proto.unemitted_model_classes.length, 5);
});

test("every schema invariant marked checkable has an executable rule", async () => {
  const { RULES } = await import("@omi-core/wire-listen");
  for (const inv of proto.invariants) {
    if (!inv.checkable) continue;
    assert.ok(inv.rule, `${inv.id} is marked checkable but names no rule`);
    assert.ok(RULES[inv.rule!], `${inv.id} names rule ${inv.rule} with no implementation`);
  }
});

// -------------------------------------------- corpus replay

for (const scenario of corpus.scenarios) {
  test(`decode: ${scenario.name}`, () => {
    const ctx = replay(scenario);
    for (const step of ctx.steps) {
      assert.equal(tagOf(step.decoded), step.frame.expect, `frame ${step.index} of ${scenario.name}`);
      // INV-LISTEN-006: unknown frames must be Degraded, never a bare unknown_event.
      if (step.decoded.kind === "unknown_event") {
        assert.ok(isDegraded(step.result), `unknown_event at ${scenario.name}#${step.index} must be Degraded`);
        assert.equal(step.result.fallback.path, "listen.decode.unknown-frame");
      } else {
        assert.ok(!isDegraded(step.result), `non-unknown frame must not be Degraded at ${scenario.name}#${step.index}`);
      }
    }
    for (const step of ctx.steps) {
      if (!("json" in step.frame)) continue;
      const sink = new RecordingSink();
      assert.equal(tagOf(unwrapDecoded(decodeValue(sink, 1, step.frame.json))), step.frame.expect);
    }
  });

  test(`schema validates: ${scenario.name}`, () => {
    const ctx = replay(scenario);
    for (const step of ctx.steps) {
      const { decoded } = step;
      const where = `${scenario.name} frame ${step.index}`;
      if (decoded.kind === "event") {
        const entry = serverDefs.get(decoded.event.type);
        assert.ok(entry, `${where}: no $def for ${decoded.event.type}`);
        const errors = validator.validate(entry.def, decoded.event, where);
        assert.deepEqual(errors, [], `${where}: ${errors.join("; ")}`);
      } else if (decoded.kind === "transcript_batch") {
        const batchDef = schema.$defs["TranscriptBatchFrame"];
        assert.ok(batchDef, "TranscriptBatchFrame $def missing");
        const errors = validator.validate(batchDef, decoded.segments, where);
        assert.deepEqual(errors, [], `${where}: ${errors.join("; ")}`);
      } else if (decoded.kind === "heartbeat") {
        const hbDef = schema.$defs["HeartbeatFrame"];
        assert.ok(hbDef, "HeartbeatFrame $def missing");
        assert.deepEqual(validator.validate(hbDef, step.raw, where), []);
      }
    }
  });

  test(`totality: ${scenario.name} never throws`, () => {
    const sink = new RecordingSink();
    for (const frame of scenario.frames) {
      const raw = frameText(frame);
      assert.doesNotThrow(() => decode(sink, 1, raw));
      for (let cut = 0; cut < raw.length; cut += Math.max(1, Math.floor(raw.length / 7))) {
        assert.doesNotThrow(() => decode(sink, 1, raw.slice(0, cut)));
        assert.doesNotThrow(() => decode(sink, 1, raw.slice(cut)));
      }
    }
  });

  test(`invariants: ${scenario.name}`, () => {
    const ctx = replay(scenario);
    const { held, violated } = checkAll({
      steps: ctx.steps.map((s) => ({ index: s.index, decoded: s.decoded })),
      close: ctx.close,
      query: ctx.query,
      handshake: ctx.handshake,
    });
    const violatedRules = violated.map((v) => v.rule);
    for (const rule of scenario.invariants ?? []) {
      assert.ok(
        held.includes(rule),
        `${rule} should hold for ${scenario.name}: ${violated.find((v) => v.rule === rule)?.message}`,
      );
    }
    for (const rule of scenario.violates ?? []) {
      assert.ok(violatedRules.includes(rule), `${rule} should be REPORTED violated for ${scenario.name}`);
    }
  });
}

test("corpus covers every emitted server event type", () => {
  const seen = new Set<string>();
  for (const scenario of corpus.scenarios) {
    for (const frame of scenario.frames) {
      if (frame.expect?.startsWith("event:")) seen.add(frame.expect.slice("event:".length));
    }
  }
  const expected = [...serverDefs.entries()]
    .filter(([, entry]) => entry.def["x-omi-emitted"] !== false)
    .map(([type]) => type);
  const missing = expected.filter((type) => !seen.has(type));
  assert.deepEqual(missing, [], `corpus is missing frames for: ${missing.join(", ")}`);
});

test("corpus exercises every non-envelope frame and every invalid reason", () => {
  const tags = corpus.scenarios.flatMap((s) => s.frames.map((f) => f.expect));
  assert.ok(tags.includes("heartbeat"));
  assert.ok(tags.some((t) => t.startsWith("transcript_batch:")));
  for (const reason of ["not_json", "empty", "no_type_field", "missing_required_fields", "not_an_object"]) {
    assert.ok(tags.includes(`invalid:${reason}`), `no corpus frame produces invalid:${reason}`);
  }
  assert.ok(tags.some((t) => t.startsWith("unknown_event:")));
  assert.ok(tags.includes("event:entitlement"), "reserved entitlement frame must be in corpus");
});

test("INV-LISTEN-006: unknown frame kinds emit telemetry via degrade()", () => {
  const sink = new RecordingSink();
  const result = decode(sink, 42, JSON.stringify({ type: "conversation_summary_ready", x: 1 }));
  assert.ok(isDegraded(result));
  assert.equal(result.value.kind, "unknown_event");
  assert.equal(sink.events.length, 1);
  assert.equal(sink.events[0]!.path, "listen.decode.unknown-frame");
  assert.equal(sink.events[0]!.from, "conversation_summary_ready");
  assert.equal(sink.events[0]!.to, "unknown_event");
  assert.equal(sink.events[0]!.at, 42);
});

test("entitlement frame: paused state is not a close; payload is closed+strict", () => {
  const entitlementDef = schema.$defs["EntitlementEvent"];
  assert.ok(entitlementDef);
  const good: EntitlementEvent = {
    type: "entitlement",
    state: "transcription_paused_capture_continuing",
    reason: "free_tier_transcription_limit",
    usage: { amount: 3600, unit: "seconds" },
    limit: { kind: "metered", amount: 3600, unit: "seconds" },
    upgrade_target: "plans",
  };
  // red-proof: delete additionalProperties:false from EntitlementEvent in the
  // schema — the extra-key assertion below then sees an empty errors array.
  assert.deepEqual(validator.validate(entitlementDef, good, "good"), []);
  assert.ok(
    validator
      .validate(entitlementDef, { ...good, capture_continues: true }, "extra")
      .some((e) => e.includes("unexpected property")),
  );
  assert.ok(validator.validate(entitlementDef, { ...good, state: "ok" }, "bad-state").length > 0);
  assert.ok(
    validator.validate(entitlementDef, { ...good, reason: "something free text" }, "bad-reason")
      .length > 0,
  );
  assert.ok(
    validator
      .validate(entitlementDef, { ...good, limit: { kind: "metered", amount: -1, unit: "seconds" } }, "sentinel")
      .length > 0,
  );
  assert.deepEqual(
    validator.validate(entitlementDef, { ...good, limit: { kind: "unmetered" } }, "unmetered"),
    [],
  );
  assert.deepEqual(
    validator.validate(entitlementDef, { ...good, limit: { kind: "unknown" } }, "unknown"),
    [],
  );

  const sink = new RecordingSink();
  const result = decode(sink, 1, JSON.stringify(good));
  assert.ok(!isDegraded(result));
  const decoded = unwrapDecoded(result);
  assert.equal(decoded.kind, "event");
  if (decoded.kind === "event") {
    assert.equal(decoded.event.type, "entitlement");
    assert.equal(decoded.event.state, "transcription_paused_capture_continuing");
    assert.deepEqual(listenEntitlementPayloadFromEvent(decoded.event), {
      state: "transcription_paused_capture_continuing",
      reason: "free_tier_transcription_limit",
      usage: { amount: 3600, unit: "seconds" },
      limit: { kind: "metered", amount: 3600, unit: "seconds" },
      upgradeTarget: "plans",
    });
  }
  assert.equal(LISTEN_CLOSE_CODES[4020]?.emittedByListen, false);
});

test("reserved entitlement exhaustion close code does not collide with existing codes", () => {
  // red-proof: change LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION to 1008 —
  // info.emittedByListen becomes true (1008 is an emitted policy_violation code).
  const info = listenReservedCloseEntitlementExhaustionInfo();
  assert.ok(info);
  assert.equal(info.code, LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION);
  assert.equal(info.emittedByListen, false);
  assert.equal(info.name, "entitlement_upgrade_required");
  assert.equal(info.clientShouldRetry, false);
  assert.match(info.meaning, /RESERVED/);
  const colliding = Object.values(LISTEN_CLOSE_CODES).filter(
    (c) => c.code === LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION && c.name !== "entitlement_upgrade_required",
  );
  assert.deepEqual(colliding, []);
  for (const code of [1000, 1001, 1003, 1008, 1011, 4001, 4004]) {
    assert.notEqual(code, LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION);
  }
});

test("listen capture stream port surfaces transcript, connection, and entitlement", () => {
  const sink = new RecordingSink();
  const env = new ManualEnv();
  const { port, ingest } = createListenCaptureStreamPort({ sink, env, schema });

  const transcripts: string[][] = [];
  const connections: string[] = [];
  const entitlements: Array<string | null> = [];
  port.subscribeTranscriptSegments((segments) => {
    transcripts.push(segments.map((s) => `${s.id}:${s.text}`));
  });
  port.observeConnectionState((state) => {
    connections.push(state.status === "closed" ? `closed:${state.code}` : state.status);
  });
  port.observeEntitlementState((payload) => {
    entitlements.push(payload ? `${payload.status}|${payload.upgradeTarget}|${payload.limit.kind}` : null);
  });

  assert.deepEqual(port.getConnectionState(), { status: "idle" });
  assert.equal(port.getEntitlementState(), null);

  ingest.acceptTextFrame(JSON.stringify({ type: "service_status", status: "ready" }));
  ingest.acceptTextFrame(
    JSON.stringify([
      { id: "seg-port-1", text: "hello port", is_user: true, start: 0, end: 1 },
    ]),
  );
  // red-proof: remove the setEntitlement call after validator.validate in
  // createListenCaptureStreamPort — entitlements stays [null,null] and the
  // upgradeTarget content assertion below fails.
  ingest.acceptTextFrame(
    JSON.stringify({
      type: "entitlement",
      state: "upgrade_required",
      reason: "trial_expired",
      usage: { amount: 120, unit: "seconds" },
      limit: { kind: "unmetered" },
      upgrade_target: "plans",
    }),
  );
  // Malformed entitlement (extra key) must NOT update entitlement state.
  ingest.acceptTextFrame(
    JSON.stringify({
      type: "entitlement",
      state: "limit_reached",
      reason: "free_tier_transcription_limit",
      usage: { amount: 120, unit: "seconds" },
      limit: { kind: "metered", amount: 120, unit: "seconds" },
      upgrade_target: "plans",
      extra: true,
    }),
  );
  ingest.acceptClose(LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION);

  assert.deepEqual(transcripts, [["seg-port-1:hello port"]]);
  assert.deepEqual(connections, ["idle", "open", `closed:${LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION}`]);
  assert.deepEqual(entitlements, [null, "upgrade_required|plans|unmetered"]);
  assert.deepEqual(port.getEntitlementState()?.upgradeTarget, "plans");
  assert.deepEqual(port.getConnectionState(), {
    status: "closed",
    code: LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION,
  });
});

for (const message of corpus.client_messages) {
  test(`client message: ${message.name}`, () => {
    const entry = clientDefs.get(message.json.type);
    if (!entry) {
      assert.equal(message.valid, false, `${message.json.type} has no $def but is marked valid`);
      return;
    }
    const errors = validator.validate(entry.def, message.json, message.name);
    assert.equal(errors.length === 0, message.valid, `${message.name}: ${errors.join("; ")}`);
    if (entry.def["x-omi-handshake-only"]) {
      assert.equal(message.handshake_only, entry.def["x-omi-handshake-only"]);
    }
  });
}

test("handshake query strings only use params their variant accepts", () => {
  for (const scenario of corpus.scenarios) {
    const variant = LISTEN_HANDSHAKES.find((h) => h.id === scenario.handshake);
    assert.ok(variant, `unknown handshake ${scenario.handshake}`);
    for (const [key] of new URLSearchParams(scenario.query ?? "")) {
      assert.ok(
        (variant.params as readonly string[]).includes(key),
        `${scenario.name}: ${key} is not accepted by ${variant.path}`,
      );
    }
  }
});

test("handshake params validate against the canonical param schema", () => {
  const paramSchema = schema.$defs["HandshakeParams"];
  assert.ok(paramSchema, "HandshakeParams $def missing");
  for (const scenario of corpus.scenarios) {
    const parsed: Record<string, unknown> = {};
    for (const [key, value] of new URLSearchParams(scenario.query ?? "")) {
      const spec = (paramSchema as { properties: Record<string, { type?: string | string[] }> }).properties[key]!;
      const types = Array.isArray(spec.type) ? spec.type : [spec.type];
      if (types.includes("integer")) parsed[key] = Number.parseInt(value, 10);
      else if (types.includes("boolean")) parsed[key] = value === "true";
      else parsed[key] = value;
    }
    const errors = validator.validate(paramSchema, parsed, scenario.name);
    assert.deepEqual(errors, [], `${scenario.name}: ${errors.join("; ")}`);
  }
});
