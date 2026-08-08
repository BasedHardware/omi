/**
 * Typed client port for the /listen capture + transcript stream.
 *
 * This is a TYPE + a pure adapter over `decode` / `Validator`. It is not a
 * WebSocket, does not touch the network, and takes time only via `Env`.
 *
 * Design tradeoffs (entitlement frame, schema 0.3.0):
 *
 * 1. `state` closed union =
 *    `transcription_paused_capture_continuing` | `limit_reached` | `upgrade_required`.
 *    Kept the three values already reserved on the wire rather than inventing a
 *    parallel vocabulary. Folded the former `capture_continues` boolean INTO
 *    `state`: a separate bool can contradict
 *    `state=transcription_paused_capture_continuing` + `capture_continues=false`.
 *    Tradeoff: clients that branched on the bool must switch on `state` instead;
 *    that is intentional — one source of truth.
 *
 * 2. `usage` vs `limit` are sibling fields. `usage` is always a real consumed
 *    amount (`{ amount, unit:"seconds" }`). `limit` is a tagged union
 *    `metered | unmetered | unknown` — NEVER a sentinel number (-1/0) for
 *    unlimited. Tradeoff: paid/unmetered payloads still carry a usage amount
 *    (what was consumed before the decision) even when there is no ceiling;
 *    callers must read `limit.kind`, not compare usage to a magic limit.
 *
 * 3. `reason` is a closed enum (`free_tier_transcription_limit` |
 *    `free_tier_chat_limit` | `trial_expired` | `paywalled`) so clients can
 *    branch without parsing free text. No accompanying free-text field on the
 *    listen frame — presentational copy is a client concern keyed by the enum.
 *    Tradeoff: new backend reasons require a schema ratchet; that is preferred
 *    over silent string drift.
 *
 * 4. `upgrade_target` (wire snake_case; opaque string) is an identifier the
 *    shell hands to an existing plan-upgrade flow — never a URL the client
 *    constructs (FEAT-APPS-031). Tradeoff: the client cannot deep-link without
 *    the shell; that is the product rule.
 *
 * RESERVED close: `LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION` (= 4020).
 * Another agent implements the server emit; this package only reserves the
 * number next to the existing close-code table and refuses retry.
 *
 * Transcript accumulation (client-side; protocol is silent on render order):
 * - Segments with an id are keyed by that id. A redelivered id after reconnect
 *   replaces the prior entry (no duplicate rows). A same-id revision with new
 *   text is last-writer-wins.
 * - The snapshot a surface renders is ordered by `(start, end, id)` — content
 *   order, not arrival order — so out-of-order frames still paint coherently.
 * - Null/missing segment ids have no identity on the wire; each is kept as its
 *   own row (protocol INV-LISTEN segment-id-dedupe only applies when id ≠ null).
 */

import type { FallbackRecord, FallbackSink } from "@omi-core/contracts";
import { isDegraded } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { degrade } from "@omi-core/kernel";
import { unwrapDecoded } from "./invariants.js";
import {
  LISTEN_CLOSE_CODES,
  decode,
  shouldRetryAfterClose,
  type EntitlementEvent,
  type EntitlementLimit,
  type EntitlementUsage,
  type TranscriptSegment,
} from "./listen_protocol.generated.js";
import { Validator, type SchemaDocument } from "./validator.js";

/** RESERVED — entitlement exhaustion / upgrade-required. Not emitted at baseline. */
export const LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION = 4020 as const;

/** Assert the named constant sits in the generated close-code table. */
export function listenReservedCloseEntitlementExhaustionInfo() {
  return LISTEN_CLOSE_CODES[LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION];
}

export type ListenEntitlementState = EntitlementEvent["state"];
export type ListenEntitlementReason = EntitlementEvent["reason"];
export type ListenEntitlementUsage = EntitlementUsage;
export type ListenEntitlementLimit = EntitlementLimit;

/** Payload surfaces consume after the adapter validates the entitlement frame. */
export interface ListenEntitlementPayload {
  readonly state: ListenEntitlementState;
  readonly reason: ListenEntitlementReason;
  readonly usage: ListenEntitlementUsage;
  readonly limit: ListenEntitlementLimit;
  readonly upgradeTarget: string;
}

export type ListenStreamConnectionState =
  | { readonly status: "idle" }
  | { readonly status: "open" }
  | { readonly status: "closed"; readonly code: number };

/**
 * Retry / entitlement advice for a close code. Derived from the generated
 * close-code table; unknown codes fail-open as retryable (same as
 * `shouldRetryAfterClose`).
 */
export interface ListenCaptureCloseAdvice {
  readonly code: number;
  readonly clientShouldRetry: boolean;
  /** True iff this is the reserved entitlement-exhaustion close (4020). */
  readonly entitlementExhaustion: boolean;
}

/** Observable evidence that the port dropped or substituted mid-stream. */
export type ListenCaptureDegradation = FallbackRecord;

/**
 * Client-side port a surface binds to: coherent transcript, connection state,
 * entitlement state, and degradation. Domain-prefixed so barrel `export *`
 * cannot collide.
 */
export interface ListenCaptureStreamPort {
  /** Current coherent transcript — ordered for direct render. */
  getTranscriptSegments(): readonly TranscriptSegment[];
  /**
   * Fires with the full ordered transcript after each successful segment apply.
   * Does not replay on subscribe (pull via `getTranscriptSegments` instead).
   */
  subscribeTranscriptSegments(
    listener: (segments: readonly TranscriptSegment[]) => void,
  ): () => void;
  observeConnectionState(listener: (state: ListenStreamConnectionState) => void): () => void;
  observeEntitlementState(listener: (payload: ListenEntitlementPayload | null) => void): () => void;
  /**
   * Latest degradation evidence (malformed / unknown frame dropped while
   * keeping the stream). `null` before any degradation. Emits current value
   * immediately on subscribe.
   */
  observeListenCaptureDegradation(
    listener: (degradation: ListenCaptureDegradation | null) => void,
  ): () => void;
  getListenCaptureDegradation(): ListenCaptureDegradation | null;
  getConnectionState(): ListenStreamConnectionState;
  getEntitlementState(): ListenEntitlementPayload | null;
  /**
   * Close advice for the current closed state, or `null` while idle/open.
   * Entitlement exhaustion (4020) is distinguishable and marked do-not-retry.
   */
  getListenCaptureCloseAdvice(): ListenCaptureCloseAdvice | null;
}

export interface ListenCaptureStreamIngest {
  /** Push one inbound server text frame (already UTF-8 text; not binary audio). */
  acceptTextFrame(raw: string): void;
  /** Push a WebSocket close code observed by the shell transport. */
  acceptClose(code: number): void;
  /**
   * Re-open after a close. Preserves the accumulated transcript (and
   * entitlement). Does not clear degradation evidence. No-op while not closed.
   */
  acceptReconnect(): void;
}

export interface ListenCaptureStreamHandle {
  readonly port: ListenCaptureStreamPort;
  readonly ingest: ListenCaptureStreamIngest;
}

export interface ListenCaptureStreamDeps {
  readonly sink: FallbackSink;
  readonly env: Env;
  /** Full listen-protocol schema document (contracts/wire/listen/...). */
  readonly schema: SchemaDocument;
}

/** Map a validated entitlement event onto the surface-facing payload. */
export function listenEntitlementPayloadFromEvent(event: EntitlementEvent): ListenEntitlementPayload {
  return {
    state: event.state,
    reason: event.reason,
    usage: event.usage,
    limit: event.limit,
    upgradeTarget: event.upgrade_target,
  };
}

/** Close-code advice a surface uses to decide retry vs upgrade UI. */
export function listenCaptureCloseAdvice(code: number): ListenCaptureCloseAdvice {
  return {
    code,
    clientShouldRetry: shouldRetryAfterClose(code),
    entitlementExhaustion: code === LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION,
  };
}

function listenCaptureSegmentSortKey(segment: TranscriptSegment): [number, number, string] {
  const id = segment.id ?? "";
  return [segment.start, segment.end, id];
}

function listenCaptureCompareSegments(a: TranscriptSegment, b: TranscriptSegment): number {
  const [as, ae, ai] = listenCaptureSegmentSortKey(a);
  const [bs, be, bi] = listenCaptureSegmentSortKey(b);
  if (as !== bs) return as - bs;
  if (ae !== be) return ae - be;
  return ai < bi ? -1 : ai > bi ? 1 : 0;
}

/**
 * Pure adapter: shell feeds text frames / close codes; surfaces subscribe.
 * Entitlement frames must pass the schema Validator (extra keys rejected).
 * Malformed frames are dropped via `degrade()` — stream and transcript survive.
 */
export function createListenCaptureStreamPort(deps: ListenCaptureStreamDeps): ListenCaptureStreamHandle {
  const validator = new Validator(deps.schema);
  const entitlementDef = deps.schema.$defs["EntitlementEvent"];
  if (!entitlementDef) throw new Error("schema missing EntitlementEvent $def");

  let connection: ListenStreamConnectionState = { status: "idle" };
  let entitlement: ListenEntitlementPayload | null = null;
  let degradation: ListenCaptureDegradation | null = null;
  /** Id → segment. Last writer wins on same id (revision / reconnect redelivery). */
  const segmentsById = new Map<string, TranscriptSegment>();
  /** Rows with null/missing id — no wire identity; each arrival is its own row. */
  const anonymousSegments: TranscriptSegment[] = [];

  const transcriptListeners = new Set<(segments: readonly TranscriptSegment[]) => void>();
  const connectionListeners = new Set<(state: ListenStreamConnectionState) => void>();
  const entitlementListeners = new Set<(payload: ListenEntitlementPayload | null) => void>();
  const degradationListeners = new Set<(d: ListenCaptureDegradation | null) => void>();

  function snapshotTranscript(): TranscriptSegment[] {
    const rows = [...segmentsById.values(), ...anonymousSegments];
    rows.sort(listenCaptureCompareSegments);
    return rows;
  }

  function publishTranscript(): void {
    const snapshot = snapshotTranscript();
    for (const listener of transcriptListeners) listener(snapshot);
  }

  function setConnection(next: ListenStreamConnectionState): void {
    connection = next;
    for (const listener of connectionListeners) listener(connection);
  }

  function setEntitlement(next: ListenEntitlementPayload | null): void {
    entitlement = next;
    for (const listener of entitlementListeners) listener(entitlement);
  }

  function setDegradation(next: ListenCaptureDegradation): void {
    degradation = next;
    for (const listener of degradationListeners) listener(degradation);
  }

  function recordDrop(fallback: Omit<FallbackRecord, "at">, substituted: "dropped_keep_stream"): void {
    // Fallback path: substitute "keep current transcript + stay connected".
    const degraded = degrade(
      deps.sink,
      { ...fallback, at: deps.env.now() },
      substituted,
    );
    setDegradation(degraded.fallback);
  }

  function applySegment(segment: TranscriptSegment): void {
    const id = segment.id;
    if (id != null && id !== "") {
      // Last writer wins: same id with new text revises in place (reconnect
      // redelivery of an unchanged id is a no-op for content; a revision
      // replaces the prior text under the same id).
      segmentsById.set(id, segment);
      return;
    }
    anonymousSegments.push(segment);
  }

  const port: ListenCaptureStreamPort = {
    getTranscriptSegments: () => snapshotTranscript(),
    subscribeTranscriptSegments(listener) {
      transcriptListeners.add(listener);
      return () => void transcriptListeners.delete(listener);
    },
    observeConnectionState(listener) {
      connectionListeners.add(listener);
      listener(connection);
      return () => void connectionListeners.delete(listener);
    },
    observeEntitlementState(listener) {
      entitlementListeners.add(listener);
      listener(entitlement);
      return () => void entitlementListeners.delete(listener);
    },
    observeListenCaptureDegradation(listener) {
      degradationListeners.add(listener);
      listener(degradation);
      return () => void degradationListeners.delete(listener);
    },
    getListenCaptureDegradation: () => degradation,
    getConnectionState: () => connection,
    getEntitlementState: () => entitlement,
    getListenCaptureCloseAdvice: () =>
      connection.status === "closed" ? listenCaptureCloseAdvice(connection.code) : null,
  };

  const ingest: ListenCaptureStreamIngest = {
    acceptTextFrame(raw: string) {
      if (connection.status === "closed") return;

      const decoded = decode(deps.sink, deps.env.now(), raw);
      const unwrapped = unwrapDecoded(decoded);

      if (unwrapped.kind === "invalid") {
        recordDrop(
          {
            path: "listen.capture.malformed-frame",
            from: `invalid:${unwrapped.reason}`,
            to: "dropped_keep_stream",
            detail: `dropped malformed listen frame (${unwrapped.reason})`,
          },
          "dropped_keep_stream",
        );
        return;
      }

      if (unwrapped.kind === "unknown_event") {
        // Decode already emitted Degraded telemetry (INV-LISTEN-006); surface it
        // without double-recording.
        if (isDegraded(decoded)) {
          setDegradation(decoded.fallback);
        } else {
          recordDrop(
            {
              path: "listen.capture.unknown-frame",
              from: unwrapped.type,
              to: "dropped_keep_stream",
              detail: `dropped unknown listen frame type: ${unwrapped.type}`,
            },
            "dropped_keep_stream",
          );
        }
        return;
      }

      if (connection.status === "idle") setConnection({ status: "open" });

      if (unwrapped.kind === "heartbeat") return;

      if (unwrapped.kind === "transcript_batch") {
        for (const segment of unwrapped.segments) applySegment(segment);
        publishTranscript();
        return;
      }

      if (unwrapped.kind === "event" && unwrapped.event.type === "entitlement") {
        const errors = validator.validate(entitlementDef, unwrapped.event, "entitlement");
        if (errors.length > 0) {
          recordDrop(
            {
              path: "listen.capture.malformed-entitlement",
              from: "entitlement",
              to: "dropped_keep_stream",
              detail: errors.join("; "),
            },
            "dropped_keep_stream",
          );
          return;
        }
        // Mid-session entitlement does NOT terminate the transcript or close
        // the socket — especially state=transcription_paused_capture_continuing.
        setEntitlement(listenEntitlementPayloadFromEvent(unwrapped.event));
        return;
      }

      // Other validated events are acknowledged by opening the stream above;
      // transcript accumulation only cares about transcript_batch frames.
    },
    acceptClose(code: number) {
      setConnection({ status: "closed", code });
    },
    acceptReconnect() {
      if (connection.status !== "closed") return;
      // Transcript (and entitlement) intentionally preserved — reconnect must
      // neither lose nor double accumulated segments.
      setConnection({ status: "open" });
    },
  };

  return { port, ingest };
}
