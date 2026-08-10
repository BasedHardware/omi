/**
 * ListenCaptureStreamPort — accumulation, reconnect, entitlement, degradation.
 *
 * Hermetic only (ManualEnv + RecordingSink). Does not duplicate the corpus /
 * schema conformance suite in listen-conformance.test.ts.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import type { FallbackRecord, FallbackSink } from "@omi-core/contracts";
import {
  LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION,
  createListenCaptureStreamPort,
  listenCaptureCloseAdvice,
  type ListenCaptureDegradation,
  type ListenStreamConnectionState,
  type SchemaDocument,
  type TranscriptSegment,
} from "@omi-core/wire-listen";
import { ManualEnv } from "../fakes.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_ROOT = join(HERE, "../../../..");
const schema = JSON.parse(
  readFileSync(join(CORE_ROOT, "contracts/wire/listen/listen-protocol.schema.json"), "utf8"),
) as SchemaDocument;

class RecordingSink implements FallbackSink {
  readonly events: FallbackRecord[] = [];
  record(event: FallbackRecord): void {
    this.events.push(event);
  }
}

function seg(partial: {
  id?: string | null;
  text: string;
  start: number;
  end: number;
}): TranscriptSegment {
  const base: TranscriptSegment = {
    text: partial.text,
    is_user: true,
    start: partial.start,
    end: partial.end,
  };
  if (partial.id !== undefined) {
    return { ...base, id: partial.id };
  }
  return base;
}

function batch(...segments: TranscriptSegment[]): string {
  return JSON.stringify(segments);
}

function acceptReady(ingest: ReturnType<typeof openPort>["ingest"]): void {
  ingest.acceptTextFrame(JSON.stringify({ type: "service_status", status: "ready" }));
}

function textsOf(segments: readonly TranscriptSegment[]): string[] {
  return segments.map((s) => s.text);
}

function idsAndTexts(segments: readonly TranscriptSegment[]): string[] {
  return segments.map((s) => `${s.id ?? "∅"}:${s.text}`);
}

function openPort() {
  const sink = new RecordingSink();
  const env = new ManualEnv();
  const handle = createListenCaptureStreamPort({ sink, env, schema });
  return { ...handle, sink, env };
}

test("out-of-order segment arrival paints by content order (start), not arrival", () => {
  // red-proof: replace listenCaptureCompareSegments body with `return 0` (arrival
  // / Map insertion order) — textsOf then equals ["later line", "earlier line"].
  const { port, ingest } = openPort();
  const snapshots: string[][] = [];
  port.subscribeTranscriptSegments((segments) => {
    snapshots.push(textsOf(segments));
  });

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "b", text: "later line", start: 4, end: 5 })));
  ingest.acceptTextFrame(batch(seg({ id: "a", text: "earlier line", start: 0, end: 1 })));

  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["earlier line", "later line"]);
  assert.deepEqual(snapshots.at(-1), ["earlier line", "later line"]);
});

test("duplicate segment id after reconnect does not duplicate rendered transcript", () => {
  // red-proof: in applySegment, change segmentsById.set(id, segment) to always
  // push into anonymousSegments instead — idsAndTexts then contains
  // "same:hello" twice after reconnect redelivery.
  const { port, ingest } = openPort();

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "same", text: "hello", start: 0, end: 1 })));
  ingest.acceptTextFrame(batch(seg({ id: "other", text: "world", start: 2, end: 3 })));
  assert.deepEqual(idsAndTexts(port.getTranscriptSegments()), ["same:hello", "other:world"]);

  ingest.acceptClose(1001);
  ingest.acceptReconnect();
  acceptReady(ingest);
  // Redeliver the same id with the same text after reconnect.
  ingest.acceptTextFrame(batch(seg({ id: "same", text: "hello", start: 0, end: 1 })));

  assert.deepEqual(idsAndTexts(port.getTranscriptSegments()), ["same:hello", "other:world"]);
  assert.equal(
    port.getTranscriptSegments().filter((s) => s.id === "same").length,
    1,
  );
});

test("same-id revision is last-writer-wins on rendered text", () => {
  // red-proof: skip segmentsById.set when the id is already present — text stays
  // "draft" and never becomes "final wording".
  const { port, ingest } = openPort();
  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "rev", text: "draft", start: 0, end: 1 })));
  ingest.acceptTextFrame(batch(seg({ id: "rev", text: "final wording", start: 0, end: 1.5 })));

  assert.deepEqual(idsAndTexts(port.getTranscriptSegments()), ["rev:final wording"]);
  assert.equal(port.getTranscriptSegments()[0]!.end, 1.5);
});

test("malformed frame mid-stream is dropped, stream survives, port reports degradation", () => {
  // red-proof: remove the recordDrop call in the invalid branch of acceptTextFrame
  // — getListenCaptureDegradation() stays null after the bad frame.
  const { port, ingest, sink } = openPort();
  const degradations: Array<ListenCaptureDegradation | null> = [];
  port.observeListenCaptureDegradation((d) => degradations.push(d));

  assert.equal(port.getListenCaptureDegradation(), null);
  assert.equal(degradations.length, 1);
  assert.equal(degradations[0], null);

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "ok", text: "before", start: 0, end: 1 })));
  ingest.acceptTextFrame("{not-json");
  ingest.acceptTextFrame(batch(seg({ id: "ok2", text: "after", start: 2, end: 3 })));

  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["before", "after"]);
  assert.equal(port.getConnectionState().status, "open");
  const deg = port.getListenCaptureDegradation();
  if (deg === null) throw new Error("expected listen capture degradation after malformed frame");
  assert.equal(deg.path, "listen.capture.malformed-frame");
  assert.equal(deg.from, "invalid:not_json");
  assert.equal(deg.to, "dropped_keep_stream");
  assert.ok(sink.events.some((e) => e.path === "listen.capture.malformed-frame"));
  const lastDeg = degradations[degradations.length - 1];
  if (lastDeg == null) throw new Error("expected degradation observer emission");
  assert.equal(lastDeg.path, "listen.capture.malformed-frame");
});

test("connection lifecycle: idle -> open -> closed(code) -> reconnect preserves transcript", () => {
  // red-proof: clear segmentsById inside acceptReconnect — texts after reconnect
  // become [] before the new frame, and the post-reconnect snapshot loses "kept".
  const { port, ingest } = openPort();
  const connections: string[] = [];
  port.observeConnectionState((state: ListenStreamConnectionState) => {
    connections.push(state.status === "closed" ? `closed:${state.code}` : state.status);
  });

  assert.deepEqual(port.getConnectionState(), { status: "idle" });
  assert.equal(port.getListenCaptureCloseAdvice(), null);

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "k", text: "kept", start: 0, end: 1 })));
  assert.deepEqual(port.getConnectionState(), { status: "open" });

  ingest.acceptClose(1001);
  assert.deepEqual(port.getConnectionState(), { status: "closed", code: 1001 });
  const ordinary = port.getListenCaptureCloseAdvice();
  assert.ok(ordinary);
  assert.equal(ordinary.clientShouldRetry, true);
  assert.equal(ordinary.entitlementExhaustion, false);

  // Frames while closed are ignored (no double / no loss once we reconnect).
  ingest.acceptTextFrame(batch(seg({ id: "ignored", text: "nope", start: 9, end: 10 })));
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["kept"]);

  ingest.acceptReconnect();
  assert.deepEqual(port.getConnectionState(), { status: "idle" });
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["kept"]);

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "more", text: "and more", start: 2, end: 3 })));
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["kept", "and more"]);
  assert.deepEqual(connections, ["idle", "open", "closed:1001", "idle", "open"]);
});

test("entitlement exhaustion close is distinguishable and marked do-not-retry", () => {
  // red-proof: change listenCaptureCloseAdvice entitlementExhaustion check from
  // LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION to 1001 — ordinary close 1001
  // would then report entitlementExhaustion:true and this 4020 assertion fails
  // when compared against an ordinary 1000 close's advice.
  const { port, ingest } = openPort();
  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "x", text: "hi", start: 0, end: 1 })));
  ingest.acceptClose(LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION);

  const advice = port.getListenCaptureCloseAdvice();
  assert.ok(advice);
  assert.equal(advice.code, LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION);
  assert.equal(advice.entitlementExhaustion, true);
  assert.equal(advice.clientShouldRetry, false);

  const ordinary = listenCaptureCloseAdvice(1000);
  assert.equal(ordinary.entitlementExhaustion, false);
  assert.equal(ordinary.clientShouldRetry, true);
  assert.notEqual(advice.entitlementExhaustion, ordinary.entitlementExhaustion);
  assert.notEqual(advice.clientShouldRetry, ordinary.clientShouldRetry);
});

test("entitlement state is null before any frame; paused state does not terminate transcript", () => {
  // red-proof: call acceptClose after setEntitlement in the entitlement branch —
  // connection becomes closed and the later "still here" segment is ignored.
  const { port, ingest } = openPort();
  const entitlements: Array<string | null> = [];
  port.observeEntitlementState((p) => {
    entitlements.push(p ? `${p.status}|${p.captureContinuing}|${p.upgradeTarget}` : null);
  });

  assert.equal(port.getEntitlementState(), null);
  assert.equal(entitlements.length, 1);
  assert.equal(entitlements[0], null);

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "t1", text: "speaking", start: 0, end: 1 })));
  ingest.acceptTextFrame(
    JSON.stringify({
      type: "entitlement",
      state: "transcription_paused_capture_continuing",
      reason: "free_tier_transcription_limit",
      usage: { amount: 3600, unit: "seconds" },
      limit: { kind: "metered", amount: 3600, unit: "seconds" },
      upgrade_target: "plans",
    }),
  );

  assert.equal(port.getConnectionState().status, "open");
  // Normalised: the surface reads status + captureContinuing, never the wire state.
  assert.equal(port.getEntitlementState()?.status, "limit_reached");
  assert.equal(port.getEntitlementState()?.captureContinuing, true);
  assert.equal(port.getEntitlementState()?.source, "entitlement");
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["speaking"]);

  ingest.acceptTextFrame(batch(seg({ id: "t2", text: "still here", start: 2, end: 3 })));
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["speaking", "still here"]);
  assert.equal(port.getConnectionState().status, "open");
  assert.deepEqual(entitlements, [null, "limit_reached|true|plans"]);
});

test("acceptReconnect is a no-op while open or idle", () => {
  const { port, ingest } = openPort();
  ingest.acceptReconnect();
  assert.deepEqual(port.getConnectionState(), { status: "idle" });
  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "a", text: "x", start: 0, end: 1 })));
  ingest.acceptReconnect();
  assert.deepEqual(port.getConnectionState(), { status: "open" });
});

test("transcript content is dropped until this socket reports service_status:ready", () => {
  const { port, ingest } = openPort();
  ingest.acceptTextFrame(batch(seg({ id: "early", text: "unsafe", start: 0, end: 1 })));
  assert.deepEqual(port.getTranscriptSegments(), []);
  assert.equal(port.getConnectionState().status, "idle");
  assert.equal(
    port.getListenCaptureDegradation()?.path,
    "listen.capture.transcript-before-ready",
  );

  acceptReady(ingest);
  ingest.acceptTextFrame(batch(seg({ id: "safe", text: "accepted", start: 1, end: 2 })));
  assert.deepEqual(textsOf(port.getTranscriptSegments()), ["accepted"]);
  assert.equal(port.getConnectionState().status, "open");
  // red-proof: remove the protocolReady guard from the transcript_batch branch;
  // the first transcript assertion contains "unsafe" and the port opens early.
});
