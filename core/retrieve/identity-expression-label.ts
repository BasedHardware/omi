import { isProxy } from "node:util/types";

import { parseAttributionBeliefRevision } from "../consolidate/attribution-belief";

export const IDENTITY_EXPRESSION_LABEL_VERSION = "identity-expression-label-v1" as const;

export type IdentityExpressionLabel =
  | "certain_owner"
  | "owner_qualified"
  | "source_attributed"
  | "clarification_required"
  | "abstain";

export interface IdentityExpressionAssignment {
  readonly version: typeof IDENTITY_EXPRESSION_LABEL_VERSION;
  readonly about_ref: string;
  readonly label: IdentityExpressionLabel;
  readonly owner_probability_micros: number;
}

const fail = (code: string): never => { throw new TypeError(`identity expression label ${code}`); };

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
  const label: IdentityExpressionLabel = ownerMicros >= 1_000_000 ? "abstain" : "source_attributed";
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
