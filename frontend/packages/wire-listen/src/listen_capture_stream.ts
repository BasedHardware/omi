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
 */

import type { FallbackSink } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { unwrapDecoded } from "./invariants.js";
import {
  LISTEN_CLOSE_CODES,
  decode,
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
 * Client-side port a surface binds to: transcript segments, connection state,
 * and entitlement state. Domain-prefixed so barrel `export *` cannot collide.
 */
export interface ListenCaptureStreamPort {
  subscribeTranscriptSegments(
    listener: (segments: readonly TranscriptSegment[]) => void,
  ): () => void;
  observeConnectionState(listener: (state: ListenStreamConnectionState) => void): () => void;
  observeEntitlementState(listener: (payload: ListenEntitlementPayload | null) => void): () => void;
  getConnectionState(): ListenStreamConnectionState;
  getEntitlementState(): ListenEntitlementPayload | null;
}

export interface ListenCaptureStreamIngest {
  /** Push one inbound server text frame (already UTF-8 text; not binary audio). */
  acceptTextFrame(raw: string): void;
  /** Push a WebSocket close code observed by the shell transport. */
  acceptClose(code: number): void;
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

/**
 * Pure adapter: shell feeds text frames / close codes; surfaces subscribe.
 * Entitlement frames must pass the schema Validator (extra keys rejected).
 */
export function createListenCaptureStreamPort(deps: ListenCaptureStreamDeps): ListenCaptureStreamHandle {
  const validator = new Validator(deps.schema);
  const entitlementDef = deps.schema.$defs["EntitlementEvent"];
  if (!entitlementDef) throw new Error("schema missing EntitlementEvent $def");

  let connection: ListenStreamConnectionState = { status: "idle" };
  let entitlement: ListenEntitlementPayload | null = null;

  const transcriptListeners = new Set<(segments: readonly TranscriptSegment[]) => void>();
  const connectionListeners = new Set<(state: ListenStreamConnectionState) => void>();
  const entitlementListeners = new Set<(payload: ListenEntitlementPayload | null) => void>();

  function setConnection(next: ListenStreamConnectionState): void {
    connection = next;
    for (const listener of connectionListeners) listener(connection);
  }

  function setEntitlement(next: ListenEntitlementPayload | null): void {
    entitlement = next;
    for (const listener of entitlementListeners) listener(entitlement);
  }

  const port: ListenCaptureStreamPort = {
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
    getConnectionState: () => connection,
    getEntitlementState: () => entitlement,
  };

  const ingest: ListenCaptureStreamIngest = {
    acceptTextFrame(raw: string) {
      if (connection.status === "closed") return;
      const unwrapped = unwrapDecoded(decode(deps.sink, deps.env.now(), raw));
      if (unwrapped.kind === "invalid") return;

      if (connection.status === "idle") setConnection({ status: "open" });

      if (unwrapped.kind === "transcript_batch") {
        for (const listener of transcriptListeners) listener(unwrapped.segments);
        return;
      }

      if (unwrapped.kind === "event" && unwrapped.event.type === "entitlement") {
        const errors = validator.validate(entitlementDef, unwrapped.event, "entitlement");
        if (errors.length > 0) return;
        setEntitlement(listenEntitlementPayloadFromEvent(unwrapped.event));
      }
    },
    acceptClose(code: number) {
      setConnection({ status: "closed", code });
    },
  };

  return { port, ingest };
}
