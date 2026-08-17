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

const VERSION = "memory-strategy-promotion-readiness-v2" as const;
const IDENTITY_VERSION = "memory-identity-expression-labels-v1" as const;
const IDENTITY_PROTOCOL = "owner-expression-five-class-v1" as const;
const DIGEST = /^[a-f0-9]{64}$/;
const RESULT_REF = /^msr1_[a-f0-9]{64}$/;
const GRADER_REF = /^meg1_[a-f0-9]{64}$/;

const IDENTITY_CLASSES = [
  "certain_owner_match",
  "certain_owner_mismatch",
  "qualified",
  "source_local",
  "abstain",
] as const;

export type MemoryIdentityExpressionClass = typeof IDENTITY_CLASSES[number];

export type MemoryStrategyReadinessGateCode =
  | "regression_size"
  | "generalization_size"
  | "zero_certain_owner_mismatch"
  | "contamination_nonregression";

export interface MemoryIdentityExpressionLabels {
  readonly version: typeof IDENTITY_VERSION;
  readonly cohort_digest: string;
  readonly grading_protocol_version: typeof IDENTITY_PROTOCOL;
  readonly grader_session_ref: string;
  readonly labels: readonly Readonly<{
    result_ref: string;
    expression: MemoryIdentityExpressionClass;
  }>[];
  readonly labels_digest: string;
}

export interface MemoryIdentityExpressionCounts {
  readonly certain_owner_match: number;
  readonly certain_owner_mismatch: number;
  readonly qualified: number;
  readonly source_local: number;
  readonly abstain: number;
}

export interface MemoryStrategyPromotionEvidence {
  readonly cohort: MemoryEvaluationCohortManifest;
  readonly labels: ExternalMemoryEvaluationLabels;
  readonly contamination: MemoryContaminationReport;
  readonly identity_expression: MemoryIdentityExpressionLabels;
}

export interface MemoryStrategyPromotionReadinessInput {
  readonly regression: MemoryStrategyPromotionEvidence;
  readonly generalization: MemoryStrategyPromotionEvidence;
}

export interface MemoryStrategyReadinessSummary {
  readonly cohort_digest: string;
  readonly labels_digest: string;
  readonly identity_expression_digest: string;
  readonly statistics_digest: string;
  readonly contamination_digest: string;
  readonly input_count: number;
  readonly repeat_count: number;
  readonly baseline_success: number;
  readonly candidate_success: number;
  readonly candidate_wrong: number;
  readonly candidate_unsure: number;
  readonly candidate_wins: number;
  readonly baseline_wins: number;
  readonly mcnemar_numerator: string;
  readonly mcnemar_denominator_power_of_two: number;
  readonly baseline_grade_flip_rate: number;
  readonly candidate_grade_flip_rate: number;
  readonly baseline_contaminated: number;
  readonly candidate_contaminated: number;
  readonly candidate_certain_owner_match: number;
  readonly candidate_certain_owner_mismatch: number;
  readonly candidate_qualified: number;
  readonly candidate_source_local: number;
  readonly candidate_abstain: number;
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

const exactArray = (value: unknown, length: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length !== length) fail("invalid_identity_expression");
  const values = value as unknown[];
  const keys = Reflect.ownKeys(values);
  if (keys.length !== values.length + 1 || keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= values.length)))) {
    fail("invalid_identity_expression");
  }
  return values;
};

const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export const memoryIdentityExpressionLabelsDigest = (
  value: Omit<MemoryIdentityExpressionLabels, "labels_digest">,
): string => sha256CanonicalContent({
  version: value.version,
  cohort_digest: value.cohort_digest,
  grading_protocol_version: value.grading_protocol_version,
  grader_session_ref: value.grader_session_ref,
  labels: [...value.labels].sort((left, right) => compare(left.result_ref, right.result_ref)),
});

export const parseMemoryIdentityExpressionLabels = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  value: unknown,
): Readonly<MemoryIdentityExpressionLabels> => {
  const root = exactContainer(value as object, [
    "version", "cohort_digest", "grading_protocol_version", "grader_session_ref",
    "labels", "labels_digest",
  ]);
  if (root["version"] !== IDENTITY_VERSION || root["grading_protocol_version"] !== IDENTITY_PROTOCOL
    || root["cohort_digest"] !== cohort.cohort_digest) fail("invalid_identity_expression");
  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ])).sort(compare);
  const labels = Object.freeze(exactArray(root["labels"], expectedRefs.length).map((rowValue) => {
    const row = exactContainer(rowValue as object, ["result_ref", "expression"]);
    if (!(IDENTITY_CLASSES as readonly string[]).includes(row["expression"] as string)) {
      fail("invalid_identity_expression_row");
    }
    const resultRef = row["result_ref"];
    if (typeof resultRef !== "string" || !RESULT_REF.test(resultRef)) fail("invalid_identity_expression_row");
    return Object.freeze({
      result_ref: resultRef,
      expression: row["expression"] as MemoryIdentityExpressionClass,
    });
  }).sort((left, right) => compare(left.result_ref, right.result_ref)));
  if (labels.some((row, index) => row.result_ref !== expectedRefs[index])) fail("incomplete_identity_expression");
  const grader = root["grader_session_ref"];
  if (typeof grader !== "string" || !GRADER_REF.test(grader)) fail("invalid_identity_expression");
  const core = Object.freeze({
    version: IDENTITY_VERSION,
    cohort_digest: cohort.cohort_digest,
    grading_protocol_version: IDENTITY_PROTOCOL,
    grader_session_ref: grader,
    labels,
  });
  const digest = root["labels_digest"];
  if (typeof digest !== "string" || !DIGEST.test(digest)
    || digest !== sha256CanonicalContent(core)) fail("invalid_identity_expression_digest");
  return Object.freeze({ ...core, labels_digest: digest });
};

const emptyIdentityCounts = (): Record<MemoryIdentityExpressionClass, number> => ({
  certain_owner_match: 0,
  certain_owner_mismatch: 0,
  qualified: 0,
  source_local: 0,
  abstain: 0,
});

const identityCounts = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  labels: Readonly<MemoryIdentityExpressionLabels>,
  role: "baseline" | "candidate",
): Readonly<MemoryIdentityExpressionCounts> => {
  const byRef = new Map(labels.labels.map((row) => [row.result_ref, row.expression]));
  const counts = emptyIdentityCounts();
  for (const unit of cohort.units) {
    const pair = unit.pairs[0]!;
    const ref = role === "baseline" ? pair.baseline_result_ref : pair.candidate_result_ref;
    counts[byRef.get(ref)!] += 1;
  }
  return Object.freeze(counts);
};

const successCount = (report: Readonly<MemoryEvaluationStatisticsReport>, role: "baseline" | "candidate"): number => {
  const grades = role === "baseline" ? report.baseline_primary_grades : report.candidate_primary_grades;
  return grades.correct + grades.partly;
};

const summarize = (
  statistics: Readonly<MemoryEvaluationStatisticsReport>,
  contamination: Readonly<MemoryContaminationReport>,
  identity: Readonly<MemoryIdentityExpressionCounts>,
  identityDigest: string,
): Readonly<MemoryStrategyReadinessSummary> => Object.freeze({
  cohort_digest: statistics.cohort_digest,
  labels_digest: statistics.labels_digest,
  identity_expression_digest: identityDigest,
  statistics_digest: statistics.report_digest,
  contamination_digest: contamination.report_digest,
  input_count: statistics.input_count,
  repeat_count: statistics.repeat_count,
  baseline_success: successCount(statistics, "baseline"),
  candidate_success: successCount(statistics, "candidate"),
  candidate_wrong: statistics.candidate_primary_wrong,
  candidate_unsure: statistics.candidate_primary_grades.unsure,
  candidate_wins: statistics.candidate_wins,
  baseline_wins: statistics.baseline_wins,
  mcnemar_numerator: statistics.mcnemar_exact_two_sided.numerator,
  mcnemar_denominator_power_of_two: statistics.mcnemar_exact_two_sided.denominator_power_of_two,
  baseline_grade_flip_rate: statistics.baseline_self_noise.flip_rate,
  candidate_grade_flip_rate: statistics.candidate_self_noise.flip_rate,
  baseline_contaminated: contamination.baseline_all_repeats.contaminated_answers,
  candidate_contaminated: contamination.candidate_all_repeats.contaminated_answers,
  candidate_certain_owner_match: identity.certain_owner_match,
  candidate_certain_owner_mismatch: identity.certain_owner_mismatch,
  candidate_qualified: identity.qualified,
  candidate_source_local: identity.source_local,
  candidate_abstain: identity.abstain,
});

const evidence = (value: MemoryStrategyPromotionEvidence) => {
  const input = exactContainer(value, ["cohort", "labels", "contamination", "identity_expression"]);
  const cohort = parseMemoryEvaluationCohort(input["cohort"]);
  const labels = parseExternalMemoryEvaluationLabels(cohort, input["labels"]);
  const statistics = analyzeExternalMemoryEvaluationLabels(cohort, labels);
  const contamination = parseMemoryContaminationReport(input["contamination"]);
  const identityExpression = parseMemoryIdentityExpressionLabels(cohort, input["identity_expression"]);
  if (contamination.cohort_digest !== cohort.cohort_digest
    || contamination.input_count !== cohort.unit_count
    || contamination.repeat_count !== cohort.repeat_count) fail("contamination_coordinate_mismatch");
  return Object.freeze({
    cohort,
    labels,
    statistics,
    contamination,
    identityExpression,
    candidateIdentity: identityCounts(cohort, identityExpression, "candidate"),
  });
};

/**
 * Builds decision support only. A positive result has no assignment, work,
 * graph, product, route, cohort, deployment, or policy authority.
 * Identity-floor gates determine outcome; usefulness counts are reported only.
 */
export const assessMemoryStrategyPromotionReadiness = (
  value: MemoryStrategyPromotionReadinessInput,
): Readonly<MemoryStrategyPromotionReadiness> => {
  const input = exactContainer(value, ["regression", "generalization"]);
  const regression = evidence(input["regression"] as MemoryStrategyPromotionEvidence);
  const generalization = evidence(input["generalization"] as MemoryStrategyPromotionEvidence);
  if (regression.cohort.cohort_digest === generalization.cohort.cohort_digest
    || regression.labels.labels_digest === generalization.labels.labels_digest
    || regression.identityExpression.labels_digest === generalization.identityExpression.labels_digest
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
    ["zero_certain_owner_mismatch",
      regression.candidateIdentity.certain_owner_mismatch === 0
      && generalization.candidateIdentity.certain_owner_mismatch === 0],
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
    regression: summarize(r, rc, regression.candidateIdentity, regression.identityExpression.labels_digest),
    generalization: summarize(g, gc, generalization.candidateIdentity, generalization.identityExpression.labels_digest),
    gates,
  });
  return Object.freeze({ ...core, readiness_digest: sha256CanonicalContent(core) });
};

export const MEMORY_STRATEGY_PROMOTION_READINESS_VERSION = VERSION;
export const MEMORY_IDENTITY_EXPRESSION_LABELS_VERSION = IDENTITY_VERSION;
export const MEMORY_IDENTITY_EXPRESSION_PROTOCOL = IDENTITY_PROTOCOL;
