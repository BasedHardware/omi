/**
 * The outbox engine as a PURE state machine: `step(state, event) -> {state,
 * effects}`. No I/O, no clock, no randomness — the impure binding
 * (`outbox.ts`) interprets effects and feeds results back as events. This
 * purity is a load-bearing design choice: every failure-class test enumerates
 * event sequences against this function and asserts exact outcomes, and a
 * bug report converts to a failing test by replaying its journal.
 *
 * Invariants encoded here (do not weaken):
 * - An op leaves `pending` only via a terminal `OperationOutcome`.
 * - `permanent` NEVER retries (FC-permanent-write-rejection-retried-forever).
 * - `auth-invalid` pauses the queue; nothing sends until `auth-restored`.
 * - At most one op is in flight (ordering is a correctness property: patches
 *   must not overtake their create).
 */

import type { OperationOutcome, WriteFailure } from "@omi-core/contracts";

export interface PendingOp {
  opId: string;
  domain: string;
  recordId: string;
  /** Serialized domain op — the engine never looks inside. */
  payload: string;
  /** Human-readable summary for the dead-letter surface. */
  summary: string;
  attempts: number;
}

export interface EngineState {
  pending: readonly PendingOp[];
  inFlight: string | null;
  pausedForAuth: boolean;
  /** Backoff step index; resets on any success. */
  backoffStep: number;
}

export const INITIAL_STATE: EngineState = {
  pending: [],
  inFlight: null,
  pausedForAuth: false,
  backoffStep: 0,
};

export type EngineEvent =
  | { t: "enqueued"; op: PendingOp }
  | { t: "flush" }
  | { t: "send-ok"; opId: string; serverRevision?: string }
  | { t: "send-failed"; opId: string; failure: WriteFailure }
  | { t: "auth-restored" };

export type Effect =
  | { t: "send"; op: PendingOp }
  | { t: "schedule-flush"; afterMs: number }
  | { t: "outcome"; opId: string; outcome: OperationOutcome; summaryForDeadLetter?: PendingOp }
  | { t: "telemetry"; path: string; detail: string };

/** Exponential backoff with cap; step 0 = immediate. */
export const BACKOFF_MS = [0, 1_000, 5_000, 30_000, 120_000, 600_000] as const;

export function step(state: EngineState, event: EngineEvent, now: number): { state: EngineState; effects: Effect[] } {
  void now; // reserved for future scheduled-op support; keeps the signature stable
  switch (event.t) {
    case "enqueued": {
      const next = { ...state, pending: [...state.pending, event.op] };
      return { state: next, effects: canSend(next) ? [{ t: "schedule-flush", afterMs: 0 }] : [] };
    }

    case "flush": {
      if (!canSend(state)) return { state, effects: [] };
      const op = state.pending[0]!;
      return { state: { ...state, inFlight: op.opId }, effects: [{ t: "send", op }] };
    }

    case "send-ok": {
      if (state.inFlight !== event.opId) return { state, effects: [] };
      const next: EngineState = {
        ...state,
        pending: state.pending.filter((o) => o.opId !== event.opId),
        inFlight: null,
        backoffStep: 0,
      };
      const effects: Effect[] = [
        {
          t: "outcome",
          opId: event.opId,
          outcome: event.serverRevision !== undefined
            ? { state: "confirmed", serverRevision: event.serverRevision }
            : { state: "confirmed" },
        },
      ];
      if (next.pending.length > 0) effects.push({ t: "schedule-flush", afterMs: 0 });
      return { state: next, effects };
    }

    case "send-failed": {
      if (state.inFlight !== event.opId) return { state, effects: [] };
      const op = state.pending.find((o) => o.opId === event.opId)!;
      const f = event.failure;

      if (f.kind === "permanent") {
        const next: EngineState = {
          ...state,
          pending: state.pending.filter((o) => o.opId !== event.opId),
          inFlight: null,
        };
        const effects: Effect[] = [
          {
            t: "outcome",
            opId: event.opId,
            outcome: { state: "dead", failure: f, deadAt: now },
            summaryForDeadLetter: op,
          },
          { t: "telemetry", path: "sync.outbox.dead-letter", detail: `${op.domain}/${op.recordId}: ${f.reason}` },
        ];
        if (next.pending.length > 0) effects.push({ t: "schedule-flush", afterMs: 0 });
        return { state: next, effects };
      }

      if (f.kind === "auth-invalid") {
        return {
          state: { ...state, inFlight: null, pausedForAuth: true },
          effects: [{ t: "telemetry", path: "sync.outbox.auth-paused", detail: f.detail }],
        };
      }

      const bumped = state.pending.map((o) => (o.opId === event.opId ? { ...o, attempts: o.attempts + 1 } : o));
      const backoffStep = Math.min(state.backoffStep + 1, BACKOFF_MS.length - 1);
      const afterMs = f.kind === "rate-limited" ? f.retryAfterMs : BACKOFF_MS[backoffStep]!;
      const effects: Effect[] = [{ t: "schedule-flush", afterMs }];
      if (f.kind === "retryable" && f.unclassified) {
        effects.push({ t: "telemetry", path: "sync.outbox.unclassified-failure", detail: f.detail });
      }
      return { state: { ...state, pending: bumped, inFlight: null, backoffStep }, effects };
    }

    case "auth-restored": {
      if (!state.pausedForAuth) return { state, effects: [] };
      const next = { ...state, pausedForAuth: false, backoffStep: 0 };
      return { state: next, effects: canSend(next) ? [{ t: "schedule-flush", afterMs: 0 }] : [] };
    }
  }
}

function canSend(s: EngineState): boolean {
  return !s.pausedForAuth && s.inFlight === null && s.pending.length > 0;
}
