/**
 * The write/transport error taxonomy — ADR-004, red-team finding 7, and
 * failure class FC-permanent-write-rejection-retried-forever.
 *
 * Every failure an adapter reports is classified into exactly one of these
 * kinds, and every pending operation ends in exactly one terminal outcome.
 * There is no "unknown" escape hatch: an adapter that cannot classify a
 * failure MUST report `retryable` with `unclassified: true` so the telemetry
 * shows us the taxonomy gap — silently inventing a new shape is a compile
 * error by design.
 */

/** Why a write could not be applied right now (or ever). */
export type WriteFailure =
  | {
      /** Transient: network, 5xx, timeout. The outbox retries with backoff. */
      kind: "retryable";
      /** True when the adapter hit a failure it could not classify. */
      unclassified?: boolean;
      detail: string;
    }
  | {
      /** Server said slow down. Retry after the hint, never before. */
      kind: "rate-limited";
      retryAfterMs: number;
      detail: string;
    }
  | {
      /**
       * Credentials invalid/expired. The outbox PAUSES (never drops, never
       * spins) until the shell reports re-authentication. Operations queued
       * under the old identity are re-validated against the new one before
       * replay — see the account-switch rules in `@omi-core/sync`.
       */
      kind: "auth-invalid";
      detail: string;
    }
  | {
      /**
       * The server will never accept this operation (validation, oversize,
       * unresolvable conflict, entitlement denial). Retrying is forbidden;
       * the operation moves to the dead-letter surface where the user can
       * see, copy out, and discard it.
       */
      kind: "permanent";
      reason: "validation" | "oversize" | "conflict" | "entitlement" | "gone";
      detail: string;
    };

/**
 * The terminal state of every operation ever enqueued. `confirmed` and
 * `superseded` delete the journal entry; `dead` retains it and MUST be
 * user-visible — a retained operation nobody renders is still lost content.
 */
export type OperationOutcome =
  | { state: "confirmed"; serverRevision?: string }
  | {
      /** A later local operation on the same record made this one moot. */
      state: "superseded";
      byOpId: string;
    }
  | { state: "dead"; failure: Extract<WriteFailure, { kind: "permanent" }>; deadAt: number };

/**
 * What the dead-letter ("unsent items") surface renders. Owning this surface
 * is a REQUIREMENT of hosting the sync layer on a shell — not optional.
 *
 * COORD-cross-generation-writes ratified export-then-exclude for stranded
 * writes: nothing is dropped, and each op is preserved with enough detail
 * to reconstruct the user's edit BY HAND. `summary` alone cannot do that —
 * "Edit memory abc123: content" tells a human which record changed, not
 * what the new content was. `payload` is that detail.
 */
export interface DeadLetter {
  opId: string;
  recordId: string;
  domain: string;
  /** Human-readable reconstruction of what the user tried to do. */
  summary: string;
  /**
   * The serialized domain op — same string `PendingOp.payload` carried
   * (the full create/patch/delete, including the actual patch fields, not
   * just their names). This is what lets a human reproduce the edit by
   * hand rather than merely knowing one happened.
   *
   * Optional ONLY for backward compatibility: dead letters journaled before
   * this field existed have no `payload`. Never omit it when constructing a
   * new one — `Outbox` always sets it. A reader must not assume presence;
   * use `deadLetterPayload()` rather than `JSON.parse(letter.payload)`
   * directly, so an old record renders as "unavailable" instead of
   * throwing.
   */
  payload?: string;
  failure: Extract<WriteFailure, { kind: "permanent" }>;
  deadAt: number;
}

/**
 * Safe read of a dead letter's reconstructable edit. Returns `null` — never
 * throws — when `payload` is absent (a dead letter journaled before this
 * field existed) or malformed (should not happen; defensive). Callers that
 * need the patch to reconstruct a user's edit by hand should go through
 * this rather than `JSON.parse(letter.payload)` directly.
 */
export function deadLetterPayload(letter: DeadLetter): unknown | null {
  if (letter.payload === undefined) return null;
  try {
    return JSON.parse(letter.payload) as unknown;
  } catch {
    return null;
  }
}
