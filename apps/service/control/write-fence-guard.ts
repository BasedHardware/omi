/**
 * THE ONE COMPOSITION of the account epoch fence for a request path.
 *
 * Store lookup, fence evaluation and the producer-side count are joined here so
 * that a write route cannot do two of the three. That is not tidiness: a route
 * that evaluated the fence but forgot to count produces a green test and an
 * unjoinable claim, and a route that counted before evaluating produces the
 * wave-9 shape where the number moves and nothing happened.
 *
 * ── FOR THE WRITE LANE ───────────────────────────────────────────────────────
 *
 * Call `applyWriteFence` after authentication and authorization have resolved,
 * and before anything is applied. On `admitted: false`, respond with
 * `writeFenceRefusalResponse(decision)` from `fence-http.ts` and — when
 * `decision.evidence === "preserve_envelope"` — persist the FULL envelope,
 * patch included. That row is the ratified straggler evidence
 * (`COORD-cross-generation-writes.md`); a summary does not satisfy it.
 *
 * The account id comes from the AUTHENTICATED PRINCIPAL and never from the
 * request body. `backend:ADR-012` §4: "No route, job, or record may treat
 * possession of an identifier as evidence of anything." A body-supplied account
 * id would make the fence a lookup of whatever control state the caller chose.
 */

import { evaluateWriteFence, type WriteFenceDecision } from "../../../core/control/write-fence";
import type { WriteFenceCounter } from "./fence-counter";
import type { AccountControlProjectionStore } from "./projection-store";

export interface WriteFenceDependencies {
  readonly store: AccountControlProjectionStore;
  readonly counter: WriteFenceCounter;
}

export interface WriteFenceInput {
  /** From the authenticated principal. Never from the request body. */
  readonly accountId: string;
  /** The epoch the op was created under; `null` when the envelope carried none. */
  readonly requestEpoch: number | null;
  /** Joins this decision to the run that caused it. */
  readonly runId: string | null | undefined;
}

export const applyWriteFence = (
  dependencies: WriteFenceDependencies,
  input: WriteFenceInput,
): WriteFenceDecision => {
  const projection = dependencies.store.read(input.accountId);
  const decision = evaluateWriteFence(projection, { request_epoch: input.requestEpoch });
  // Recorded from the decision, after it exists. Both facts matter; see
  // fence-counter.ts.
  dependencies.counter.record(input.runId, decision);
  return decision;
};
