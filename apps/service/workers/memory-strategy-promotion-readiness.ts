import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  parseMemoryContaminationReport,
  type MemoryContaminationReport,
} from "./memory-contamination-audit";
import {
  analyzeExternalMemoryEvaluationLabels,
  parseExternalMemoryEvaluationLabels,
  parseMemoryEvaluationCohort,
  type ExternalMemoryEvaluationLabels,
  type MemoryEvaluationCohortManifest,
  type MemoryEvaluationStatisticsReport,
} from "./memory-evaluation-statistics";

const VERSION = "memory-strategy-promotion-readiness-v1" as const;

export type MemoryStrategyReadinessGateCode =
  | "regression_size"
  | "generalization_size"
  | "complete_labels"
  | "zero_candidate_wrong"
  | "candidate_success_nonregression"
  | "regression_win_floor"
  | "regression_significance"
  | "generalization_paired_nonregression"
  | "contamination_nonregression";

export interface MemoryStrategyPromotionEvidence {
  readonly cohort: MemoryEvaluationCohortManifest;
  readonly labels: ExternalMemoryEvaluationLabels;
  readonly contamination: MemoryContaminationReport;
}

export interface MemoryStrategyPromotionReadinessInput {
  readonly regression: MemoryStrategyPromotionEvidence;
  readonly generalization: MemoryStrategyPromotionEvidence;
}

export interface MemoryStrategyReadinessSummary {
  readonly cohort_digest: string;
  readonly labels_digest: string;
  readonly statistics_digest: string;
  readonly contamination_digest: string;
  readonly input_count: number;
  readonly repeat_count: number;
  readonly baseline_success: number;
  readonly candidate_success: number;
  readonly candidate_wrong: number;
  readonly candidate_wins: number;
  readonly baseline_wins: number;
  readonly mcnemar_numerator: string;
  readonly mcnemar_denominator_power_of_two: number;
  readonly baseline_grade_flip_rate: number;
  readonly candidate_grade_flip_rate: number;
  readonly baseline_contaminated: number;
  readonly candidate_contaminated: number;
}

export interface MemoryStrategyPromotionReadiness {
  readonly version: typeof VERSION;
  readonly outcome: "blocked" | "ready_for_david_review";
  readonly baseline_strategy_ref: string;
  readonly candidate_strategy_ref: string;
  readonly regression: Readonly<MemoryStrategyReadinessSummary>;
  readonly generalization: Readonly<MemoryStrategyReadinessSummary>;
  readonly gates: readonly Readonly<{ code: MemoryStrategyReadinessGateCode; passed: boolean }>[];
  readonly readiness_digest: string;
}

const fail = (code: string): never => { throw new TypeError(`memory strategy readiness ${code}`); };

const exactContainer = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value as object)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_input");
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.length !== keys.length
    || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail("invalid_input");
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_input");
  }
  return value as Record<string, unknown>;
};

const successCount = (report: Readonly<MemoryEvaluationStatisticsReport>, role: "baseline" | "candidate"): number => {
  const grades = role === "baseline" ? report.baseline_primary_grades : report.candidate_primary_grades;
  return grades.correct + grades.partly;
};

const exactPAtMostFivePercent = (report: Readonly<MemoryEvaluationStatisticsReport>): boolean => {
  const value = report.mcnemar_exact_two_sided;
  return BigInt(value.numerator) * 20n <= (1n << BigInt(value.denominator_power_of_two));
};

const summarize = (
  statistics: Readonly<MemoryEvaluationStatisticsReport>,
  contamination: Readonly<MemoryContaminationReport>,
): Readonly<MemoryStrategyReadinessSummary> => Object.freeze({
  cohort_digest: statistics.cohort_digest,
  labels_digest: statistics.labels_digest,
  statistics_digest: statistics.report_digest,
  contamination_digest: contamination.report_digest,
  input_count: statistics.input_count,
  repeat_count: statistics.repeat_count,
  baseline_success: successCount(statistics, "baseline"),
  candidate_success: successCount(statistics, "candidate"),
  candidate_wrong: statistics.candidate_primary_wrong,
  candidate_wins: statistics.candidate_wins,
  baseline_wins: statistics.baseline_wins,
  mcnemar_numerator: statistics.mcnemar_exact_two_sided.numerator,
  mcnemar_denominator_power_of_two: statistics.mcnemar_exact_two_sided.denominator_power_of_two,
  baseline_grade_flip_rate: statistics.baseline_self_noise.flip_rate,
  candidate_grade_flip_rate: statistics.candidate_self_noise.flip_rate,
  baseline_contaminated: contamination.baseline_all_repeats.contaminated_answers,
  candidate_contaminated: contamination.candidate_all_repeats.contaminated_answers,
});

const evidence = (value: MemoryStrategyPromotionEvidence) => {
  const input = exactContainer(value, ["cohort", "labels", "contamination"]);
  const cohort = parseMemoryEvaluationCohort(input["cohort"]);
  const labels = parseExternalMemoryEvaluationLabels(cohort, input["labels"]);
  const statistics = analyzeExternalMemoryEvaluationLabels(cohort, labels);
  const contamination = parseMemoryContaminationReport(input["contamination"]);
  if (contamination.cohort_digest !== cohort.cohort_digest
    || contamination.input_count !== cohort.unit_count
    || contamination.repeat_count !== cohort.repeat_count) fail("contamination_coordinate_mismatch");
  return Object.freeze({ cohort, labels, statistics, contamination });
};

/**
 * Builds decision support only. A positive result has no assignment, work,
 * graph, product, route, cohort, deployment, or policy authority.
 */
export const assessMemoryStrategyPromotionReadiness = (
  value: MemoryStrategyPromotionReadinessInput,
): Readonly<MemoryStrategyPromotionReadiness> => {
  const input = exactContainer(value, ["regression", "generalization"]);
  const regression = evidence(input["regression"] as MemoryStrategyPromotionEvidence);
  const generalization = evidence(input["generalization"] as MemoryStrategyPromotionEvidence);
  if (regression.cohort.cohort_digest === generalization.cohort.cohort_digest
    || regression.labels.labels_digest === generalization.labels.labels_digest
    || regression.labels.blind_sheet_digest === generalization.labels.blind_sheet_digest
    || regression.labels.hidden_key_digest === generalization.labels.hidden_key_digest) fail("evidence_not_distinct");
  if (regression.cohort.baseline_strategy_ref !== generalization.cohort.baseline_strategy_ref
    || regression.cohort.candidate_strategy_ref !== generalization.cohort.candidate_strategy_ref) {
    fail("strategy_coordinate_mismatch");
  }
  const regressionInputs = new Set(regression.cohort.units.map((unit) => unit.input_ref));
  if (generalization.cohort.units.some((unit) => regressionInputs.has(unit.input_ref))) fail("cohort_inputs_overlap");

  const r = regression.statistics;
  const g = generalization.statistics;
  const rc = regression.contamination;
  const gc = generalization.contamination;
  const gateValues: readonly [MemoryStrategyReadinessGateCode, boolean][] = [
    ["regression_size", r.input_count === 25],
    ["generalization_size", g.input_count >= 10],
    ["complete_labels", r.primary_pairs_excluded_unsure === 0 && g.primary_pairs_excluded_unsure === 0],
    ["zero_candidate_wrong", r.candidate_primary_wrong === 0 && g.candidate_primary_wrong === 0],
    ["candidate_success_nonregression", successCount(r, "candidate") >= successCount(r, "baseline")
      && successCount(g, "candidate") >= successCount(g, "baseline")],
    ["regression_win_floor", r.candidate_wins >= 14 && r.baseline_wins <= 1],
    ["regression_significance", exactPAtMostFivePercent(r)],
    ["generalization_paired_nonregression", g.candidate_wins >= g.baseline_wins],
    ["contamination_nonregression", rc.candidate_only_contaminated <= rc.baseline_only_contaminated
      && gc.candidate_only_contaminated <= gc.baseline_only_contaminated
      && rc.candidate_all_repeats.contaminated_answers <= rc.baseline_all_repeats.contaminated_answers
      && gc.candidate_all_repeats.contaminated_answers <= gc.baseline_all_repeats.contaminated_answers],
  ];
  const gates = Object.freeze(gateValues.map(([code, passed]) => Object.freeze({ code, passed })));
  const core = Object.freeze({
    version: VERSION,
    outcome: gates.every((gate) => gate.passed)
      ? "ready_for_david_review" as const
      : "blocked" as const,
    baseline_strategy_ref: regression.cohort.baseline_strategy_ref,
    candidate_strategy_ref: regression.cohort.candidate_strategy_ref,
    regression: summarize(r, rc),
    generalization: summarize(g, gc),
    gates,
  });
  return Object.freeze({ ...core, readiness_digest: sha256CanonicalContent(core) });
};

export const MEMORY_STRATEGY_PROMOTION_READINESS_VERSION = VERSION;
