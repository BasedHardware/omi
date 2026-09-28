/**
 * Bridge stream lifecycle — ADR-009 §4.
 *
 * Streams cross the privileged bridge as explicit lifecycle messages with
 * credit-based backpressure. This holds on every surface and both transports
 * (the ship-origin spike showed cancellation does not propagate through
 * loopback HTTP either — the bridge owns stream lifecycle everywhere).
 *
 * Rules a binding must uphold:
 * - Every `open` eventually receives exactly one of `end` | `error` | `cancel`-ack.
 * - The producer may send at most `credit` unacknowledged `data` frames;
 *   `grant` replenishes. Exceeding credit is a contract violation, not backpressure.
 * - `cancel` is honored promptly; frames already in flight may still arrive
 *   and MUST be dropped by the consumer after cancel.
 */

export type StreamId = string;

export type StreamToShell =
  | { t: "open"; id: StreamId; channel: string; params: string; credit: number }
  | { t: "grant"; id: StreamId; credit: number }
  | { t: "cancel"; id: StreamId; reason?: string };

export type StreamFromShell =
  | { t: "data"; id: StreamId; payload: string }
  | { t: "end"; id: StreamId }
  | { t: "error"; id: StreamId; failure: string };

/**
 * The single host-visible message channel used for every bridge stream. The
 * logical stream channel remains in each message; this name only identifies
 * the native message handler.
 */
export const BRIDGE_STREAM_MESSAGE_CHANNEL = "omiStream";

/** The global sink a one-way host invokes with one JSON-encoded shell frame. */
export const BRIDGE_STREAM_SINK_FUNCTION = "__omiStreamFrame";

/** The logical channel whose params are `ChatGenerationStreamParams`. */
export const CHAT_GENERATION_STREAM_CHANNEL = "chat-generation-events";

/**
 * Host-owned generation identity and reconnect cursor. The host constructs
 * the fixed authenticated GET route; no origin, token, or caller-authored
 * headers cross into JavaScript.
 */
export interface ChatGenerationStreamParams {
  generationId: string;
  lastEventId?: string;
}

/**
 * Host-facing wire. `channel` is repeated after `open` so a frame routed from
 * the wrong logical producer can be rejected before it reaches a stream.
 * This wraps the ratified lifecycle without changing its three messages in
 * either direction.
 */
export type StreamToShellWire = StreamToShell & { channel: string };
export type StreamFromShellWire = StreamFromShell & { channel: string };

export interface BridgeStreamOpenRequest {
  channel: string;
  params: string;
  initialCredit: number;
}

/** One incrementally consumed payload stream owned by the bridge binding. */
export interface BridgePayloadStream extends AsyncIterable<string> {
  readonly id: StreamId;
  readonly channel: string;
  cancel(reason?: string): void;
}

/** Reusable typed port implemented by `@omi-core/bridge-web`. */
export interface BridgeStreamPort {
  open(request: BridgeStreamOpenRequest): BridgePayloadStream;
}

/**
 * The bundle manifest gate — ADR-009 §5. The shell reads this BEFORE
 * navigation and refuses/rolls back on mismatch; the surface must then send
 * `surface-ready` over the bridge within the shell's deadline.
 */
export interface BundleManifest {
  bundleVersion: string;
  bridgeContractVersion: number;
  entry: string;
}

/** Bumped on ANY breaking change to bridge messages or storage contracts. */
export const BRIDGE_CONTRACT_VERSION = 1;
