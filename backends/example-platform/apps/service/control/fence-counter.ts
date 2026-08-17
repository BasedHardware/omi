/**
 * THE PRODUCER-SIDE ARBITER for the epoch fence.
 *
 * `STATE.md`: "a claim of working behaviour names a producer-side counter *and* a
 * consumer-side observation, joined by run id, and the claiming agent runs both.
 * A dispatch-side number never appears in a verdict."
 *
 * This is that producer-side counter. Two properties make it usable as evidence
 * rather than decoration:
 *
 * 1. **It is keyed by run id.** A total is not joinable — a suite that leaves
 *    residue, a retry, or a second test hitting the same process all inflate it,
 *    and the number still looks right. `readsByThisRun` on the read path exists
 *    for the same reason. An absent or empty run id is counted under a reserved
 *    bucket rather than dropped, so "the header never arrived" is visible instead
 *    of looking like zero traffic.
 *
 * 2. **It is recorded where the decision is PRODUCED**, from the decision value
 *    itself — never at request entry and never from what the handler intended to
 *    do. `routes/memories.ts` learned this the hard way: a served count that moves
 *    when nothing was served makes a stalled backend look healthy. `record` takes
 *    a `WriteFenceDecision`, not an outcome string, so a caller cannot report an
 *    outcome the fence did not reach.
 */

import type { WriteFenceOutcome } from "../../../core/control/write-fence";
import type { WriteEnforcementDecision } from "./write-enforcement-decision";

/** Bucket for requests that carried no usable run id. Never a real run id. */
export const UNATTRIBUTED_RUN = "__unattributed__";

export interface WriteFenceRunTally {
  readonly admitted: number;
  readonly refused: Readonly<Record<WriteFenceOutcome, number>>;
  /** Refusals whose disposition preserves the envelope — the straggler count. */
  readonly preservedEnvelopes: number;
}

export interface WriteFenceCounter {
  /** Called with the decision the fence actually produced, at the point it is produced. */
  record(runId: string | null | undefined, decision: WriteEnforcementDecision): void;
  /** `null` when this run produced no fence decision at all — distinct from all-zero. */
  tally(runId: string): WriteFenceRunTally | null;
}

const zeroTally = (): {
  admitted: number;
  refused: Record<WriteFenceOutcome, number>;
  preservedEnvelopes: number;
} => ({
  admitted: 0,
  refused: {
    authentication: 0,
    authorization: 0,
    entitlement: 0,
    stale_epoch: 0,
    control_unavailable: 0,
  },
  preservedEnvelopes: 0,
});

const normaliseRunId = (runId: string | null | undefined): string => {
  if (typeof runId !== "string") return UNATTRIBUTED_RUN;
  const trimmed = runId.trim();
  return trimmed.length === 0 ? UNATTRIBUTED_RUN : trimmed;
};

export const createWriteFenceCounter = (): WriteFenceCounter => {
  const runs = new Map<string, ReturnType<typeof zeroTally>>();

  return Object.freeze({
    record(runId: string | null | undefined, decision: WriteEnforcementDecision): void {
      const key = normaliseRunId(runId);
      const tally = runs.get(key) ?? zeroTally();
      if (decision.admitted) {
        tally.admitted += 1;
      } else {
        tally.refused[decision.outcome] += 1;
        if (decision.evidence === "preserve_envelope") tally.preservedEnvelopes += 1;
      }
      runs.set(key, tally);
    },

    tally(runId: string): WriteFenceRunTally | null {
      const tally = runs.get(normaliseRunId(runId));
      if (tally === undefined) return null;
      return Object.freeze({
        admitted: tally.admitted,
        refused: Object.freeze({ ...tally.refused }),
        preservedEnvelopes: tally.preservedEnvelopes,
      });
    },
  });
};
