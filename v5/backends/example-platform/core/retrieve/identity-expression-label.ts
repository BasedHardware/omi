import { isProxy } from "node:util/types";

import { parseAttributionBeliefRevision } from "../consolidate/attribution-belief";

export const IDENTITY_EXPRESSION_LABEL_VERSION = "identity-expression-label-v2" as const;

/**
 * How the system SPOKE about owner identity. This is a machine observation, not
 * a grade.
 *
 * v1 used `owner_qualified` / `source_attributed`, which did not line up with
 * the ratified expression classes in `DAVID-IDENTITY-EXPRESSION-FLOOR-DECISION`
 * (ADR-015) that `memory-strategy-promotion-readiness.ts` already speaks. Two
 * vocabularies for one concept mis-grade the identity floor, so this side was
 * renamed to match the ratified one.
 *
 * `certain_owner` stays single here on purpose: the machine records how it
 * spoke, and only a grader can say whether the person actually was the owner.
 * The match/mismatch split is therefore derived at grading time, never emitted.
 */
export type IdentityExpressionLabel =
  | "certain_owner"
  | "qualified"
  | "source_local"
  | "clarification_required"
  | "abstain";

/** The five ratified grading classes (ADR-015). */
export type RatifiedIdentityExpressionClass =
  | "certain_owner_match"
  | "certain_owner_mismatch"
  | "qualified"
  | "source_local"
  | "abstain";

export interface IdentityExpressionAssignment {
  readonly version: typeof IDENTITY_EXPRESSION_LABEL_VERSION;
  readonly about_ref: string;
  readonly label: IdentityExpressionLabel;
  readonly owner_probability_micros: number;
}

const fail = (code: string): never => { throw new TypeError(`identity expression label ${code}`); };

/**
 * Maps a machine label onto its ratified grading class.
 *
 * `certain_owner` requires the grader's owner determination; passing `null` for
 * a certain-voice row is a programming error, not a defensible abstention.
 *
 * `clarification_required` grades as `qualified`: asking "do you mean you?" is
 * disclosed uncertainty, which is exactly what `qualified` names. It is not
 * `abstain` — surfacing an owner hypothesis to the reader is an identity-claim
 * act, only a hedged one. It stays a distinct machine label because it drives a
 * different product behaviour, and it does not add a sixth ratified class.
 */
export const ratifiedIdentityExpressionClass = (
  label: IdentityExpressionLabel,
  isOwner: boolean | null,
): RatifiedIdentityExpressionClass => {
  if (label === "certain_owner") {
    if (typeof isOwner !== "boolean") fail("certain_owner_requires_grader_determination");
    return isOwner ? "certain_owner_match" : "certain_owner_mismatch";
  }
  if (label === "clarification_required") return "qualified";
  return label;
};

/**
 * Emit identity-expression labels from people beliefs. Certain-owner is never
 * selected here: compose-voice thresholds wait on David-graded sheets.
 */
export const identityExpressionLabelForBelief = (
  beliefValue: unknown,
): IdentityExpressionAssignment => {
  const belief = parseAttributionBeliefRevision(beliefValue);
  if (belief.belief_kind !== "claim_subject") fail("unsupported_belief_kind");
  const owner = belief.hypotheses.find((hypothesis) => hypothesis.kind === "owner");
  const ownerMicros = owner?.probability_micros ?? 0;
  const label: IdentityExpressionLabel = ownerMicros >= 1_000_000 ? "abstain" : "source_local";
  if ((label as string) === "certain_owner") fail("certain_owner_forbidden");
  return Object.freeze({
    version: IDENTITY_EXPRESSION_LABEL_VERSION,
    about_ref: belief.about_ref,
    label,
    owner_probability_micros: ownerMicros,
  });
};

export const identityExpressionLabelsForBeliefs = (
  beliefsValue: unknown,
): readonly IdentityExpressionAssignment[] => {
  if (!Array.isArray(beliefsValue) || isProxy(beliefsValue)) fail("invalid_beliefs");
  return Object.freeze((beliefsValue as unknown[]).map((item) => identityExpressionLabelForBelief(item)));
};
