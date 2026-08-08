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

/**
 * The ONE internal entitlement state a surface consumes, normalised from BOTH
 * wire shapes (coordinator ruling, decisions/COORD-entitlement-frame-collision.md).
 *
 * Two frames describe "the user has hit a plan limit":
 * `freemium_threshold_reached` is what the legacy server emits TODAY, and
 * `entitlement` is reserved for the rewritten wire and emitted by nobody yet.
 * Replacing the reserve with the emitted frame would fix today and break
 * tomorrow — a reserve priced before a binding exists is cheap, a reshape after
 * two consumers exist is not. So the client accepts both and the surface never
 * learns there were two.
 *
 * WHAT IS NULL HERE IS NULL ON PURPOSE. The two wires carry genuinely different
 * information: the entitlement frame knows usage/limit/reason/upgrade target and
 * not remaining time; the freemium frame knows remaining seconds and a suggested
 * action and none of the rest. Every field a given wire does not carry is
 * `null`, never a plausible default. A fabricated `limit` here would be read by
 * a surface as a real ceiling and shown to a user as a number the server never
 * said — the same class of fabrication as a synthesized memory carrying
 * `locked: false`.
 *
 * `status` and `captureContinuing` are the normalised decision fields: they are
 * the two things BOTH wires can always answer, and therefore the only two a
 * surface may branch on without checking `source`.
 */
export interface ListenEntitlementSnapshot {
  /** Which wire shape produced this. Provenance for telemetry — NOT presentational. */
  readonly source: "entitlement" | "freemium_threshold_reached";
  /** Normalised severity. Both wires can always answer this. */
  readonly status: ListenEntitlementStatus;
  /** Is audio capture still running? Both wires can always answer this. */
  readonly captureContinuing: boolean;
  /** Remaining allowance, when the wire carried one. */
  readonly remaining: { readonly amount: number; readonly unit: "seconds" } | null;
  readonly usage: ListenEntitlementUsage | null;
  /** `{ kind: "unknown" }` when the wire stated no ceiling — distinct from unmetered. */
  readonly limit: ListenEntitlementLimit;
  readonly reason: ListenEntitlementReason | null;
  readonly upgradeTarget: string | null;
  readonly suggestedAction: "setup_on_device_stt" | "none" | null;
}

/**
 * Closed union so a surface's exhaustive switch breaks at COMPILE time when a
 * new severity appears — which is the moment a human must decide how to phrase
 * it, not a moment to fall through to generic copy.
 */
export type ListenEntitlementStatus =
  /** Credit is running low; capture and transcription both continue. */
  | "approaching_limit"
  /** The ceiling was reached. `captureContinuing` says whether audio survives. */
  | "limit_reached"
  /** Nothing further without a plan change; expect a close to follow. */
  | "upgrade_required";

/** Parse result of the reserved `entitlement` frame specifically. */
export interface ListenEntitlementPayload {
  readonly state: ListenEntitlementState;
  readonly reason: ListenEntitlementReason;
  readonly usage: ListenEntitlementUsage;
  readonly limit: ListenEntitlementLimit;
  readonly upgradeTarget: string;
}

/** Which wire shape this generation is expected to emit (ADR-010: never mixed). */
export type ListenEntitlementGeneration = "legacy" | "platform";

const EXPECTED_ENTITLEMENT_FRAME: Readonly<Record<ListenEntitlementGeneration, string>> = {
  legacy: "freemium_threshold_reached",
  platform: "entitlement",
};

/** Reserved `entitlement` frame -> the normalised state. */
export function listenEntitlementSnapshotFromEntitlement(
  payload: ListenEntitlementPayload,
): ListenEntitlementSnapshot {
  return {
    source: "entitlement",
    status:
      payload.state === "upgrade_required"
        ? "upgrade_required"
        : "limit_reached",
    // Only this one state keeps audio alive, and it says so in its name.
    captureContinuing: payload.state === "transcription_paused_capture_continuing",
    // The entitlement frame carries usage against a ceiling, not a countdown.
    remaining: null,
    usage: payload.usage,
    limit: payload.limit,
    reason: payload.reason,
    upgradeTarget: payload.upgradeTarget,
    suggestedAction: null,
  };
}

/**
 * Legacy `freemium_threshold_reached` -> the same normalised state.
 *
 * `remaining_seconds === 0` is `upgrade_required` rather than `limit_reached`
 * because the schema is explicit that this frame at zero is sent "pre-emptively
 * at connect when already exhausted/paywalled … immediately before a 1008
 * trial_expired close". Calling that `limit_reached` would tell a surface that
 * capture might continue, moments before the socket dies.
 */
export function listenEntitlementSnapshotFromFreemium(event: {
  readonly remaining_seconds: number;
  readonly action: string;
}): ListenEntitlementSnapshot {
  const exhausted = event.remaining_seconds <= 0;
  return {
    source: "freemium_threshold_reached",
    status: exhausted ? "upgrade_required" : "approaching_limit",
    captureContinuing: !exhausted,
    remaining: { amount: event.remaining_seconds, unit: "seconds" },
    // This wire says nothing about consumption, the ceiling, the reason, or
    // where to upgrade. Every one of those stays null rather than invented.
    usage: null,
    limit: { kind: "unknown" },
    reason: null,
    upgradeTarget: null,
    suggestedAction:
      event.action === "setup_on_device_stt" || event.action === "none" ? event.action : null,
  };
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
  observeEntitlementState(listener: (payload: ListenEntitlementSnapshot | null) => void): () => void;
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
  getEntitlementState(): ListenEntitlementSnapshot | null;
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
  /**
   * Which generation this client is running. Determines which entitlement
   * frame is EXPECTED — both are still accepted, but receiving the other one
   * is reported, because ADR-010's whole-account cutover means the two are
   * never intentionally mixed, so a mismatch is real signal rather than noise.
   * Defaults to "legacy", which is what a server actually emits today.
   */
  readonly generation?: ListenEntitlementGeneration;
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
  let entitlement: ListenEntitlementSnapshot | null = null;
  let degradation: ListenCaptureDegradation | null = null;
  /** Id → segment. Last writer wins on same id (revision / reconnect redelivery). */
  const segmentsById = new Map<string, TranscriptSegment>();
  /** Rows with null/missing id — no wire identity; each arrival is its own row. */
  const anonymousSegments: TranscriptSegment[] = [];

  const transcriptListeners = new Set<(segments: readonly TranscriptSegment[]) => void>();
  const connectionListeners = new Set<(state: ListenStreamConnectionState) => void>();
  const entitlementListeners = new Set<(payload: ListenEntitlementSnapshot | null) => void>();
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

  function setEntitlement(next: ListenEntitlementSnapshot | null): void {
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

  const generation: ListenEntitlementGeneration = deps.generation ?? "legacy";

  /**
   * Accept an entitlement frame from the OTHER generation, and say so.
   *
   * Not a drop: the state is real and the surface gets it. But ADR-010
   * guarantees generations are never intentionally mixed, so this is either a
   * misconfigured client or a server mid-cutover, and both are worth a
   * telemetry record. Silence here is how "my entitlement UI never fires"
   * becomes a bug nobody can see.
   */
  function reportGenerationMismatch(received: string): void {
    const expected = EXPECTED_ENTITLEMENT_FRAME[generation];
    if (received === expected) return;
    const degraded = degrade(
      deps.sink,
      {
        path: "listen.capture.entitlement-generation-mismatch",
        from: `${generation}:expected:${expected}`,
        to: `received:${received}`,
        detail: `accepted a ${received} frame on the ${generation} generation, which expects ${expected}`,
        at: deps.env.now(),
      },
      "accepted_normalized",
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
        reportGenerationMismatch("entitlement");
        setEntitlement(
          listenEntitlementSnapshotFromEntitlement(listenEntitlementPayloadFromEvent(unwrapped.event)),
        );
        return;
      }

      if (unwrapped.kind === "event" && unwrapped.event.type === "freemium_threshold_reached") {
        // The frame a real server emits TODAY. Normalised into the same state
        // as the reserved one so the surface never learns there were two.
        const freemiumDef = deps.schema.$defs["FreemiumThresholdReachedEvent"];
        const errors = freemiumDef
          ? validator.validate(freemiumDef, unwrapped.event, "freemium_threshold_reached")
          : ["schema missing FreemiumThresholdReachedEvent $def"];
        if (errors.length > 0) {
          recordDrop(
            {
              path: "listen.capture.malformed-entitlement",
              from: "freemium_threshold_reached",
              to: "dropped_keep_stream",
              detail: errors.join("; "),
            },
            "dropped_keep_stream",
          );
          return;
        }
        reportGenerationMismatch("freemium_threshold_reached");
        setEntitlement(
          listenEntitlementSnapshotFromFreemium(
            unwrapped.event as unknown as { remaining_seconds: number; action: string },
          ),
        );
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
