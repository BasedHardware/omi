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
