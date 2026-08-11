import { describe, expect, test } from "bun:test";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type { MemoryContaminationReport } from "./memory-contamination-audit";
import type { MemoryEvaluationExportManifest } from "./memory-evaluation-export";
import {
  buildMemoryEvaluationCohort,
  externalMemoryEvaluationLabelsDigest,
  type ExternalMemoryEvaluationLabels,
  type MemoryEvaluationCohortManifest,
  type MemoryEvaluationGrade,
} from "./memory-evaluation-statistics";
import { assessMemoryStrategyPromotionReadiness } from "./memory-strategy-promotion-readiness";

const opaque = (prefix: string, value: string): string => `${prefix}_${sha256CanonicalContent({ value })}`;
const baselineStrategy = opaque("mes1", "baseline");
const candidateStrategy = opaque("mes1", "candidate");

const unit = (
  cohortTag: string,
  index: number,
  repeats: readonly number[] = [0, 1],
  inputRef = opaque("mei1", `${cohortTag}:input:${index}`),
): Readonly<MemoryEvaluationExportManifest> => {
  const pairs = repeats.map((repeat, ordinal) => Object.freeze({
    ordinal,
    pair_ref: opaque("mep1", `${cohortTag}:pair:${index}:${repeat}`),
    repeat_ordinal: repeat,
    baseline_result_ref: opaque("msr1", `${cohortTag}:baseline:${index}:${repeat}`),
    baseline_strategy_ref: baselineStrategy,
    candidate_result_ref: opaque("msr1", `${cohortTag}:candidate:${index}:${repeat}`),
    candidate_strategy_ref: candidateStrategy,
  }));
  const core = Object.freeze({
    version: "memory-evaluation-export-v1" as const,
    evaluation_mode: "offline_replay" as const,
    evaluation_run_ref: opaque("mer1", `${cohortTag}:run`),
    assignment_bundle_ref: opaque("mea1", `${cohortTag}:assignment:${index}`),
    input_ref: inputRef,
    pair_count: pairs.length,
    repeat_count: repeats.length,
    candidate_strategy_count: 1,
    pairs: Object.freeze(pairs),
  });
  return Object.freeze({ ...core, export_digest: sha256CanonicalContent(core) });
};

type GradeSelector = (
  role: "baseline" | "candidate",
  index: number,
  repeat: number,
) => MemoryEvaluationGrade;

const labels = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  tag: string,
  select: GradeSelector,
): Readonly<ExternalMemoryEvaluationLabels> => {
  const grades = cohort.units.flatMap((cohortUnit, index) => cohortUnit.pairs.flatMap((pair) => [
    { result_ref: pair.baseline_result_ref, grade: select("baseline", index, pair.repeat_ordinal) },
    { result_ref: pair.candidate_result_ref, grade: select("candidate", index, pair.repeat_ordinal) },
  ])).sort((left, right) => left.result_ref < right.result_ref ? -1 : left.result_ref > right.result_ref ? 1 : 0);
  const core = Object.freeze({
    version: "memory-evaluation-labels-v1" as const,
    cohort_digest: cohort.cohort_digest,
    grading_protocol_version: "owner-truth-five-grade-v1" as const,
    grader_session_ref: opaque("meg1", "grader"),
    blind_sheet_digest: sha256CanonicalContent({ tag, artifact: "sheet" }),
    hidden_key_digest: sha256CanonicalContent({ tag, artifact: "key" }),
    grades: Object.freeze(grades),
  });
  return Object.freeze({ ...core, labels_digest: externalMemoryEvaluationLabelsDigest(core) });
};

const contamination = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  baselineOnly = 0,
  candidateOnly = 0,
): Readonly<MemoryContaminationReport> => {
  const total = cohort.unit_count * cohort.repeat_count;
  const count = (contaminated: number) => Object.freeze({
    answers: total,
    second_person_answers: contaminated,
    contaminated_answers: contaminated,
    contaminated_percent_of_second_person: contaminated ? 100 : 0,
  });
  const trials = baselineOnly + candidateOnly;
  const tail = Math.min(baselineOnly, candidateOnly);
  let combination = 1n;
  let sum = 1n;
  for (let index = 1; index <= tail; index += 1) {
    combination = (combination * BigInt(trials - index + 1)) / BigInt(index);
    sum += combination;
  }
  let numerator = 2n * sum;
  let denominatorPower = trials;
  const denominator = 1n << BigInt(trials);
  if (trials === 0 || numerator >= denominator) {
    numerator = 1n;
    denominatorPower = 0;
  } else {
    while (denominatorPower > 0 && numerator % 2n === 0n) {
      numerator /= 2n;
      denominatorPower -= 1;
    }
  }
  const mcnemar = Object.freeze({
    numerator: numerator.toString(),
    denominator_power_of_two: denominatorPower,
    approximate: Number(numerator) / (2 ** denominatorPower),
  });
  const noise = Object.freeze({
    comparisons: cohort.unit_count * (cohort.repeat_count - 1),
    contamination_flips: 0,
    flip_rate: 0,
  });
  const core = Object.freeze({
    version: "memory-contamination-report-v1" as const,
    cohort_digest: cohort.cohort_digest,
    input_count: cohort.unit_count,
    repeat_count: cohort.repeat_count,
    result_count: cohort.unit_count * cohort.repeat_count * 2,
    primary_repeat_ordinal: 0 as const,
    baseline_all_repeats: count(baselineOnly),
    candidate_all_repeats: count(candidateOnly),
    both_contaminated: 0,
    baseline_only_contaminated: baselineOnly,
    candidate_only_contaminated: candidateOnly,
    neither_contaminated: cohort.unit_count - baselineOnly - candidateOnly,
    net_removed: baselineOnly - candidateOnly,
    mcnemar_exact_two_sided: mcnemar,
    baseline_self_noise: noise,
    candidate_self_noise: noise,
  });
  return Object.freeze({ ...core, report_digest: sha256CanonicalContent(core) });
};

const regressionGrades: GradeSelector = (role, index) => index < 14
  ? role === "candidate" ? "correct" : "empty"
  : index === 14
    ? role === "baseline" ? "correct" : "empty"
    : "correct";

const generalizationGrades: GradeSelector = (role, index) => index < 3
  ? role === "candidate" ? "partly" : "empty"
  : "correct";

const artifacts = (
  repeats: readonly number[] = [0, 1],
  generalizationSelector: GradeSelector = generalizationGrades,
) => {
  const regression = buildMemoryEvaluationCohort(Array.from(
    { length: 25 },
    (_, index) => unit("regression", index, repeats),
  ));
  const generalization = buildMemoryEvaluationCohort(Array.from(
    { length: 10 },
    (_, index) => unit("generalization", index, repeats),
  ));
  return {
    regression: {
      cohort: regression,
      labels: labels(regression, "regression", regressionGrades),
      contamination: contamination(regression),
    },
    generalization: {
      cohort: generalization,
      labels: labels(generalization, "generalization", generalizationSelector),
      contamination: contamination(generalization),
    },
  };
};

describe("memory strategy promotion readiness", () => {
  test("the frozen 14-1 floor plus a disjoint harder cohort is only ready for David review", () => {
    const report = assessMemoryStrategyPromotionReadiness(artifacts());
    expect(report.outcome).toBe("ready_for_david_review");
    expect(report.gates.every((gate) => gate.passed)).toBe(true);
    expect(report.regression).toMatchObject({
      input_count: 25,
      repeat_count: 2,
      candidate_wrong: 0,
      candidate_wins: 14,
      baseline_wins: 1,
      mcnemar_numerator: "1",
      mcnemar_denominator_power_of_two: 10,
    });
    expect(report.generalization).toMatchObject({
      input_count: 10,
      candidate_wrong: 0,
      candidate_wins: 3,
      baseline_wins: 0,
    });
    expect(Object.isFrozen(report)).toBe(true);
    expect(Object.isFrozen(report.gates)).toBe(true);
    expect(JSON.stringify(report)).not.toContain("input:");
    expect(JSON.stringify(report)).not.toContain("grader");
    expect("promote" in report).toBe(false);
  });

  test("one wrong candidate answer blocks despite the regression win", () => {
    const report = assessMemoryStrategyPromotionReadiness(artifacts([0, 1], (role, index) => {
      if (index === 9 && role === "candidate") return "wrong";
      return generalizationGrades(role, index, 0);
    }));
    expect(report.outcome).toBe("blocked");
    expect(report.gates.find((gate) => gate.code === "zero_candidate_wrong")?.passed).toBe(false);
  });

  test("unsure blocks instead of silently shrinking primary N", () => {
    const report = assessMemoryStrategyPromotionReadiness(artifacts([0, 1], (role, index) => {
      if (index === 9 && role === "baseline") return "unsure";
      return generalizationGrades(role, index, 0);
    }));
    expect(report.outcome).toBe("blocked");
    expect(report.gates.find((gate) => gate.code === "complete_labels")?.passed).toBe(false);
  });

  test("candidate-only contamination blocks without exposing a finding", () => {
    const value = artifacts();
    const report = assessMemoryStrategyPromotionReadiness({
      ...value,
      generalization: {
        ...value.generalization,
        contamination: contamination(value.generalization.cohort, 0, 1),
      },
    });
    expect(report.outcome).toBe("blocked");
    expect(report.gates.find((gate) => gate.code === "contamination_nonregression")?.passed).toBe(false);
    expect(JSON.stringify(report)).not.toContain("result_ref");
  });

  test("added repeats change noise evidence but never primary counts or significance", () => {
    const two = assessMemoryStrategyPromotionReadiness(artifacts([0, 1]));
    const three = assessMemoryStrategyPromotionReadiness(artifacts([0, 1, 2]));
    expect(three.regression.repeat_count).toBe(3);
    for (const key of [
      "candidate_wrong", "candidate_wins", "baseline_wins", "mcnemar_numerator",
      "mcnemar_denominator_power_of_two", "baseline_success", "candidate_success",
    ] as const) expect(three.regression[key]).toEqual(two.regression[key]);
    expect(three.outcome).toBe(two.outcome);
  });

  test("overlapping input or forged contamination fails closed", () => {
    const value = artifacts();
    const overlapping = buildMemoryEvaluationCohort([
      unit("overlap", 0, [0, 1], value.regression.cohort.units[0]!.input_ref),
      ...Array.from({ length: 9 }, (_, index) => unit("overlap", index + 1)),
    ]);
    expect(() => assessMemoryStrategyPromotionReadiness({
      regression: value.regression,
      generalization: {
        cohort: overlapping,
        labels: labels(overlapping, "overlap", generalizationGrades),
        contamination: contamination(overlapping),
      },
    })).toThrow("cohort_inputs_overlap");

    expect(() => assessMemoryStrategyPromotionReadiness({
      ...value,
      generalization: {
        ...value.generalization,
        contamination: { ...value.generalization.contamination, report_digest: "0".repeat(64) },
      },
    })).toThrow("invalid_report_digest");
    expect(() => assessMemoryStrategyPromotionReadiness(new Proxy(value, {}) as never)).toThrow();
  });
});
