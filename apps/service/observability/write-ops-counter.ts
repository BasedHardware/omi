/**
 * THE PRODUCER-SIDE ARBITER for `POST /v1/{domain}/ops`.
 *
 * `STATE.md`: "a claim of working behaviour names a producer-side counter *and*
 * a consumer-side observation, joined by run id, and the claiming agent runs
 * both. A dispatch-side number never appears in a verdict."
 *
 * Three properties make this evidence rather than decoration, and they are the
 * same three `control/fence-counter.ts` states for the fence:
 *
 * 1. **Keyed by run id**, because a total is not joinable — a retry, a suite
 *    leaving residue, or a second test against the same process all inflate it
 *    while the number still looks right. A run that produced no outcome reports
 *    `null`, never an all-zero tally, so a broken join fails loudly instead of
 *    agreeing with an empty expectation.
 * 2. **Recorded where the outcome is PRODUCED**, from the outcome the handler
 *    actually reached — never at request entry, never from what it intended.
 *    `routes/memories.ts` paid for that lesson: a served count that moves when
 *    nothing was served makes a stalled backend look healthy.
 * 3. **The vocabulary is the ratified corpus's**, not this route's own. Every
 *    value below is a `wireOutcome` in `fixtures/write-ops-conformance.json`,
 *    so a conformance test can join a corpus case to a counted outcome without
 *    a translation table in between — and a translation table is where two
 *    honest numbers stop meaning the same thing.
 *
 * This counter is DISTINCT from the fence counter and deliberately overlaps it:
 * the fence counts decisions it produced, this counts responses the route
 * emitted. Where both moved, they are two independent measurements of one event,
 * which is the only kind of agreement this program accepts.
 */

/** Exactly the `wireOutcome` vocabulary of the ratified conformance corpus. */
export const WRITE_OPS_WIRE_OUTCOMES = [
  "accepted",
  "accepted_idempotent",
  "authentication",
  "authorization",
  "entitlement",
  "stale_epoch",
  "validation",
  "write_id_reuse",
  "conflict",
  "control_unavailable",
] as const;

export type WriteOpsWireOutcome = (typeof WRITE_OPS_WIRE_OUTCOMES)[number];

/**
 * Joins a route outcome to the run that caused it.
 *
 * THE single definition. It used to be spelled twice — here and in the fence
 * harness's own constants module — and that duplication is not a tidiness
 * footnote: the harness's copy of the ROUTE constant is what let a second door
 * name `/v1/tasks/ops` without rule 17 ever seeing the literal. The harness was
 * retired under R5 and its constants went with it.
 */
export const WRITE_RUN_ID_HEADER = "x-omi-run-id";

/** Bucket for requests that carried no usable run id. Never a real run id. */
export const UNATTRIBUTED_RUN = "__unattributed__";

export interface WriteOpsRunTally {
  readonly outcomes: Readonly<Record<WriteOpsWireOutcome, number>>;
  /** Envelopes retained under ruling B3 during this run. */
  readonly preservedEnvelopes: number;
  /**
   * Requests that reached the route's top-level guard — an unhandled failure,
   * answered 500.
   *
   * Deliberately NOT a `wireOutcome`. The outcome vocabulary is the ratified
   * corpus's, so a conformance test can join a corpus case to a counted outcome
   * with no translation table in between; adding a value the corpus does not
   * have would quietly end that property. An internal failure is also not a
   * decision about the caller or the request — it is this side failing — which
   * is the same distinction the contract draws when it keeps
   * `control_unavailable` out of `WriteRefusalOutcome`.
   *
   * It is counted at all because zero is the only acceptable value and an
   * uncounted 500 is indistinguishable from no traffic.
   */
  readonly internalErrors: number;
}

export interface WriteOpsCounter {
  /** Called with the outcome the route actually produced, where it is produced. */
  record(runId: string | null | undefined, outcome: WriteOpsWireOutcome): void;
  /** Called only when a row was actually written to the straggler table. */
  recordPreservedEnvelope(runId: string | null | undefined): void;
  /** Called from the route's top-level guard, where nothing else can be known. */
  recordInternalError(runId: string | null | undefined): void;
  /** `null` when this run produced no outcome at all — distinct from all-zero. */
  tally(runId: string): WriteOpsRunTally | null;
}

const zeroOutcomes = (): Record<WriteOpsWireOutcome, number> => {
  const outcomes = {} as Record<WriteOpsWireOutcome, number>;
  for (const outcome of WRITE_OPS_WIRE_OUTCOMES) outcomes[outcome] = 0;
  return outcomes;
};

const normaliseRunId = (runId: string | null | undefined): string => {
  if (typeof runId !== "string") return UNATTRIBUTED_RUN;
  const trimmed = runId.trim();
  return trimmed.length === 0 ? UNATTRIBUTED_RUN : trimmed;
};

export const createWriteOpsCounter = (): WriteOpsCounter => {
  const runs = new Map<string, {
    outcomes: Record<WriteOpsWireOutcome, number>;
    preservedEnvelopes: number;
    internalErrors: number;
  }>();

  const bucket = (runId: string | null | undefined) => {
    const key = normaliseRunId(runId);
    const existing = runs.get(key);
    if (existing !== undefined) return existing;
    const created = { outcomes: zeroOutcomes(), preservedEnvelopes: 0, internalErrors: 0 };
    runs.set(key, created);
    return created;
  };

  return Object.freeze({
    record(runId: string | null | undefined, outcome: WriteOpsWireOutcome): void {
      bucket(runId).outcomes[outcome] += 1;
    },

    recordPreservedEnvelope(runId: string | null | undefined): void {
      bucket(runId).preservedEnvelopes += 1;
    },

    recordInternalError(runId: string | null | undefined): void {
      bucket(runId).internalErrors += 1;
    },

    tally(runId: string): WriteOpsRunTally | null {
      const tally = runs.get(normaliseRunId(runId));
      if (tally === undefined) return null;
      return Object.freeze({
        outcomes: Object.freeze({ ...tally.outcomes }),
        preservedEnvelopes: tally.preservedEnvelopes,
        internalErrors: tally.internalErrors,
      });
    },
  });
};
