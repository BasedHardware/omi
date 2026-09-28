import {
  parseAttributionBeliefRevision,
  PROBABILITY_MICROS_TOTAL,
} from "../core/consolidate/attribution-belief";
import {
  identityExpressionLabelForBelief,
  IDENTITY_EXPRESSION_LABEL_VERSION,
  type IdentityExpressionLabel,
} from "../core/retrieve/identity-expression-label";

export const IDENTITY_EXPRESSION_PROBE_ARM_VERSION = "identity-expression-probe-arm-v1" as const;

/**
 * EVALUATION ONLY. This arm is the reason the identity floor can fail at all.
 *
 * The shipping labeler (`core/retrieve/identity-expression-label.ts`) can emit
 * only `source_local` or `abstain`, and hard-fails on `certain_owner`. The dream
 * planner independently refuses any belief carrying an `owner` hypothesis. That
 * is the ratified posture and it is correct: the product does not speak certain
 * voice.
 *
 * But ADR-015's machine rule blocks only when candidate primary
 * `certain_owner_mismatch` is nonzero. If nothing can ever be certain voice,
 * that count is structurally zero and a graded sheet reports a passing identity
 * floor for a trivial reason. The floor is vacuously *satisfied*; the
 * measurement is worthless. Spending a paid 25-question corpus against an
 * unfailable gate buys nothing.
 *
 * So certain voice is made reachable **in evaluation only**. This module lives
 * under `harness/`, which no production module imports — only tests do — so the
 * production import graph and the shipping posture are unchanged. Nothing here
 * relaxes `identity-expression-label.ts` or the dream planner guard.
 *
 * The owner probability must come from the attribution-belief pipeline, not
 * from dream output: the dream planner forbids owner hypotheses outright, so a
 * dream-derived belief always scores zero here.
 */
export interface IdentityExpressionProbeOptions {
  /**
   * Probe-only threshold, in micros, at or above which the arm treats the
   * composed expression as unhedged certain voice.
   *
   * There is deliberately **no default**. Compose-voice thresholds are a
   * David-gated product decision, and a default here would quietly become one
   * by being copied. Every caller states its own probe value and owns it.
   */
  readonly certain_voice_threshold_micros: number;
}

export interface ProbeIdentityExpressionAssignment {
  readonly version: typeof IDENTITY_EXPRESSION_LABEL_VERSION;
  readonly arm_version: typeof IDENTITY_EXPRESSION_PROBE_ARM_VERSION;
  readonly about_ref: string;
  readonly label: IdentityExpressionLabel;
  readonly owner_probability_micros: number;
  /** True only when this arm, not the shipping labeler, chose the label. */
  readonly probe_forced_certain_voice: boolean;
}

const fail = (code: string): never => {
  throw new TypeError(`identity expression probe ${code}`);
};

const threshold = (options: IdentityExpressionProbeOptions): number => {
  const value = options?.certain_voice_threshold_micros;
  if (!Number.isSafeInteger(value) || value < 1 || value > PROBABILITY_MICROS_TOTAL) {
    fail("invalid_certain_voice_threshold");
  }
  return value;
};

/**
 * Label one belief through the probe arm.
 *
 * At or above the probe threshold the row is `certain_owner`, which the grader
 * then resolves to `certain_owner_match` or `certain_owner_mismatch` via
 * `ratifiedIdentityExpressionClass`. Below it the shipping labeler decides, so
 * the arm cannot make the product look more hedged than it is either.
 */
export const probeIdentityExpressionLabel = (
  beliefValue: unknown,
  options: IdentityExpressionProbeOptions,
): ProbeIdentityExpressionAssignment => {
  const bound = threshold(options);
  const belief = parseAttributionBeliefRevision(beliefValue);
  if (belief.belief_kind !== "claim_subject") fail("unsupported_belief_kind");
  const owner = belief.hypotheses.find((hypothesis) => hypothesis.kind === "owner");
  const ownerMicros = owner?.probability_micros ?? 0;

  if (ownerMicros >= bound) {
    return Object.freeze({
      version: IDENTITY_EXPRESSION_LABEL_VERSION,
      arm_version: IDENTITY_EXPRESSION_PROBE_ARM_VERSION,
      about_ref: belief.about_ref,
      label: "certain_owner" as const,
      owner_probability_micros: ownerMicros,
      probe_forced_certain_voice: true,
    });
  }

  const shipping = identityExpressionLabelForBelief(belief);
  return Object.freeze({
    version: shipping.version,
    arm_version: IDENTITY_EXPRESSION_PROBE_ARM_VERSION,
    about_ref: shipping.about_ref,
    label: shipping.label,
    owner_probability_micros: shipping.owner_probability_micros,
    probe_forced_certain_voice: false,
  });
};

export const probeIdentityExpressionLabels = (
  beliefsValue: readonly unknown[],
  options: IdentityExpressionProbeOptions,
): readonly ProbeIdentityExpressionAssignment[] => {
  if (!Array.isArray(beliefsValue)) fail("invalid_beliefs");
  return Object.freeze(beliefsValue.map((item) => probeIdentityExpressionLabel(item, options)));
};
