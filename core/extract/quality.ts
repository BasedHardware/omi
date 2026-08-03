/**
 * Post-extraction degeneracy report.
 *
 * Every claim in the degenerate 72-session glm-4.7 run was individually
 * well-formed: correct JSON, real evidence id, verbatim surface. Structural
 * validation therefore passed on output that carried almost no information.
 * These checks are distributional and shape-based, and they exist because the
 * only cheap way to detect a collapsed extractor is to look at the population
 * of its claims rather than at any one claim.
 *
 * The thresholds are measured against that run, not chosen for taste.
 */
export const extractionQualityThresholds = {
  /** Observed: 93% of 337 claims carried one coined relation (`generic/statement`).
   * A capture that names a different relationship per fact stays far below this;
   * 0.15 leaves room for a genuinely repetitive session without admitting collapse. */
  max_relation_share: 0.15,
  /** Below this many claims a share is a small-sample artefact, not a distribution. */
  min_claims_for_relation_share: 20,
  /** Observed: 85% of claims had a single argument whose surface WAS the cited
   * excerpt. A participant is a noun-like span, so an argument standing for most
   * of its own quote is a quote dump wearing a claim's shape. */
  max_sole_argument_coverage: 0.6,
} as const;

export type QualityFindingCode = "relation_share_exceeded" | "sole_argument_covers_evidence";
export interface QualityFinding { code: QualityFindingCode; detail: string; observed: number; threshold: number; }

/** Identifies a degenerate single-clause claim without flagging a genuinely short quote. */
export const soleArgumentCoversEvidence = (argument_count: number, surface_length: number, cited_length: number): boolean =>
  argument_count === 1 && cited_length > 0 && surface_length / cited_length > extractionQualityThresholds.max_sole_argument_coverage;

/**
 * One relation owning a scope is the signature failure: it means the model
 * answered the shape of the question instead of reading the evidence. Reported
 * rather than thrown so a run stays diagnosable at the session that caused it.
 */
export const checkRelationDistribution = (relations: readonly string[]): readonly QualityFinding[] => {
  if (relations.length < extractionQualityThresholds.min_claims_for_relation_share) return [];
  const counts = new Map<string, number>();
  for (const relation of relations) counts.set(relation, (counts.get(relation) ?? 0) + 1);
  return [...counts]
    .map(([relation, count]) => ({ relation, share: count / relations.length, count }))
    .filter((item) => item.share > extractionQualityThresholds.max_relation_share)
    .sort((left, right) => right.share - left.share || left.relation.localeCompare(right.relation))
    .map((item) => ({ code: "relation_share_exceeded" as const, detail: `${item.relation} used by ${item.count} of ${relations.length} claims`, observed: item.share, threshold: extractionQualityThresholds.max_relation_share }));
};
