import { describe, expect, test } from "bun:test";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type { MemoryEvaluationExportManifest } from "./memory-evaluation-export";
import {
  analyzeExternalMemoryEvaluationLabels,
  buildMemoryEvaluationCohort,
  externalMemoryEvaluationLabelsDigest,
  type ExternalMemoryEvaluationLabels,
  type MemoryEvaluationCohortManifest,
  type MemoryEvaluationGrade,
} from "./memory-evaluation-statistics";

const opaque = (prefix: string, value: string): string => `${prefix}_${sha256CanonicalContent({ value })}`;
const runRef = opaque("mer1", "run");
const baselineStrategyRef = opaque("mes1", "baseline");
const candidateStrategyRef = opaque("mes1", "candidate");

const unit = (
  index: number,
  repeats: readonly number[] = [0, 1],
  options: Readonly<{ run?: string; baseline?: string; candidate?: string; input?: string }> = {},
): Readonly<MemoryEvaluationExportManifest> => {
  const pairs = repeats.map((repeat, ordinal) => Object.freeze({
    ordinal,
    pair_ref: opaque("mep1", `pair:${index}:${repeat}`),
    repeat_ordinal: repeat,
    baseline_result_ref: opaque("msr1", `baseline:${index}:${repeat}`),
    baseline_strategy_ref: options.baseline ?? baselineStrategyRef,
    candidate_result_ref: opaque("msr1", `candidate:${index}:${repeat}`),
    candidate_strategy_ref: options.candidate ?? candidateStrategyRef,
  }));
  const core = Object.freeze({
    version: "memory-evaluation-export-v1" as const,
    evaluation_mode: "offline_replay" as const,
    evaluation_run_ref: options.run ?? runRef,
    assignment_bundle_ref: opaque("mea1", `assignment:${index}`),
    input_ref: options.input ?? opaque("mei1", `input:${index}`),
    pair_count: pairs.length,
    repeat_count: new Set(repeats).size,
    candidate_strategy_count: 1,
    pairs: Object.freeze(pairs),
  });
  return Object.freeze({ ...core, export_digest: sha256CanonicalContent(core) });
};

type GradeSelector = (
  role: "baseline" | "candidate",
  unitIndex: number,
  repeat: number,
) => MemoryEvaluationGrade;

const labels = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  select: GradeSelector,
): Readonly<ExternalMemoryEvaluationLabels> => {
  const grades = cohort.units.flatMap((cohortUnit, unitIndex) => cohortUnit.pairs.flatMap((pair) => [
    { result_ref: pair.baseline_result_ref, grade: select("baseline", unitIndex, pair.repeat_ordinal) },
    { result_ref: pair.candidate_result_ref, grade: select("candidate", unitIndex, pair.repeat_ordinal) },
  ])).sort((left, right) => left.result_ref < right.result_ref ? -1 : left.result_ref > right.result_ref ? 1 : 0);
  const core = Object.freeze({
    version: "memory-evaluation-labels-v1" as const,
    cohort_digest: cohort.cohort_digest,
    grading_protocol_version: "owner-truth-five-grade-v1" as const,
    grader_session_ref: opaque("meg1", "grader"),
    blind_sheet_digest: sha256CanonicalContent({ sheet: "blind" }),
    hidden_key_digest: sha256CanonicalContent({ key: "hidden" }),
    grades: Object.freeze(grades),
  });
  return Object.freeze({ ...core, labels_digest: externalMemoryEvaluationLabelsDigest(core) });
};

const ratifiedShape: GradeSelector = (role, index, repeat) => {
  const primary = index < 14
    ? (role === "baseline" ? "empty" : "correct")
    : index === 14
      ? (role === "baseline" ? "correct" : "empty")
      : "correct";
  if (repeat === 1 && role === "baseline" && index === 0) return "correct";
  if (repeat === 1 && role === "candidate" && index === 1) return "partly";
  return primary;
};

describe("paired memory evaluation statistics", () => {
  test("uses distinct inputs for McNemar and reports repeats only as self-noise", () => {
    const exports = Array.from({ length: 16 }, (_, index) => unit(index));
    const cohort = buildMemoryEvaluationCohort([...exports].reverse());
    expect(buildMemoryEvaluationCohort(exports)).toEqual(cohort);
    const report = analyzeExternalMemoryEvaluationLabels(cohort, labels(cohort, ratifiedShape));
    expect(report).toMatchObject({
      input_count: 16,
      repeat_count: 2,
      primary_pairs_included: 16,
      primary_pairs_excluded_unsure: 0,
      both_success: 1,
      both_nonsuccess: 0,
      candidate_wins: 14,
      baseline_wins: 1,
      baseline_primary_wrong: 0,
      candidate_primary_wrong: 0,
      mcnemar_exact_two_sided: {
        numerator: "1",
        denominator_power_of_two: 10,
      },
      baseline_self_noise: { comparisons: 16, grade_flips: 1, flip_rate: 1 / 16 },
      candidate_self_noise: { comparisons: 16, grade_flips: 1, flip_rate: 1 / 16 },
    });
    expect(report.baseline_primary_grades).toEqual({ correct: 2, partly: 0, wrong: 0, empty: 14, unsure: 0 });
    expect(report.candidate_primary_grades).toEqual({ correct: 15, partly: 0, wrong: 0, empty: 1, unsure: 0 });
    expect(report.mcnemar_exact_two_sided.approximate).toBe(0.0009765625);
  });

  test("additional repeats cannot inflate primary sample size or significance", () => {
    const two = buildMemoryEvaluationCohort(Array.from({ length: 16 }, (_, index) => unit(index, [0, 1])));
    const three = buildMemoryEvaluationCohort(Array.from({ length: 16 }, (_, index) => unit(index, [0, 1, 2])));
    const twoReport = analyzeExternalMemoryEvaluationLabels(two, labels(two, ratifiedShape));
    const threeReport = analyzeExternalMemoryEvaluationLabels(three, labels(three, ratifiedShape));
    for (const key of [
      "primary_pairs_included", "candidate_wins", "baseline_wins", "both_success",
      "both_nonsuccess", "baseline_primary_wrong", "candidate_primary_wrong",
      "mcnemar_exact_two_sided",
    ] as const) expect(threeReport[key]).toEqual(twoReport[key]);
    expect(threeReport.baseline_self_noise.comparisons).toBe(32);
    expect(threeReport.candidate_self_noise.comparisons).toBe(32);
  });

  test("unsure excludes only the paired primary row while empty remains nonsuccess", () => {
    const cohort = buildMemoryEvaluationCohort([unit(0), unit(1), unit(2)]);
    const artifact = labels(cohort, (role, index) => {
      if (index === 0) return role === "baseline" ? "unsure" : "correct";
      if (index === 1) return role === "baseline" ? "correct" : "empty";
      return role === "baseline" ? "empty" : "partly";
    });
    const report = analyzeExternalMemoryEvaluationLabels(cohort, artifact);
    expect(report).toMatchObject({
      primary_pairs_included: 2,
      primary_pairs_excluded_unsure: 1,
      candidate_wins: 1,
      baseline_wins: 1,
      mcnemar_exact_two_sided: { numerator: "1", denominator_power_of_two: 0, approximate: 1 },
    });
    expect(report.baseline_primary_grades).toMatchObject({ correct: 1, empty: 1, unsure: 1 });
    expect(report.candidate_primary_grades).toMatchObject({ correct: 1, partly: 1, empty: 1 });
  });

  test("zero discordants has exact p one", () => {
    const cohort = buildMemoryEvaluationCohort([unit(0), unit(1)]);
    const report = analyzeExternalMemoryEvaluationLabels(cohort, labels(cohort, () => "correct"));
    expect(report.mcnemar_exact_two_sided).toEqual({ numerator: "1", denominator_power_of_two: 0, approximate: 1 });
  });

  test("mixed, duplicate, uneven, forged, and hostile cohort inputs fail closed", () => {
    expect(() => buildMemoryEvaluationCohort([unit(0), unit(1, [0, 1], { run: opaque("mer1", "other") })]))
      .toThrow("mixed_run");
    expect(() => buildMemoryEvaluationCohort([unit(0), unit(1, [0, 1], { candidate: opaque("mes1", "other") })]))
      .toThrow("mixed_strategy");
    expect(() => buildMemoryEvaluationCohort([unit(0), unit(1, [0, 1], { input: unit(0).input_ref })]))
      .toThrow("duplicate_input");
    expect(() => buildMemoryEvaluationCohort([unit(0, [0, 1]), unit(1, [0, 2])]))
      .toThrow("uneven_repeats");
    expect(() => buildMemoryEvaluationCohort(new Proxy([unit(0), unit(1)], {}) as never))
      .toThrow("invalid_exports");
    const cohort = buildMemoryEvaluationCohort([unit(0), unit(1)]);
    expect(() => analyzeExternalMemoryEvaluationLabels(
      { ...cohort, unit_count: cohort.unit_count + 1 } as never,
      labels(cohort, () => "correct"),
    )).toThrow("invalid_cohort");
  });

  test("labels require an exact complete result set and exact blind digests", () => {
    const cohort = buildMemoryEvaluationCohort([unit(0), unit(1)]);
    const valid = labels(cohort, () => "correct");
    const reversedCore = { ...valid, grades: [...valid.grades].reverse() };
    const reversed = { ...reversedCore, labels_digest: externalMemoryEvaluationLabelsDigest(reversedCore) };
    expect(analyzeExternalMemoryEvaluationLabels(cohort, reversed)).toEqual(
      analyzeExternalMemoryEvaluationLabels(cohort, valid),
    );
    const missingCore = { ...valid, grades: valid.grades.slice(1) };
    const missing = { ...missingCore, labels_digest: externalMemoryEvaluationLabelsDigest(missingCore) };
    expect(() => analyzeExternalMemoryEvaluationLabels(cohort, missing as never)).toThrow("invalid_labels");
    expect(() => analyzeExternalMemoryEvaluationLabels(cohort, { ...valid, labels_digest: "0".repeat(64) } as never))
      .toThrow("invalid_labels_digest");
    const duplicateCore = { ...valid, grades: [valid.grades[0]!, ...valid.grades.slice(0, -1)] };
    const duplicate = { ...duplicateCore, labels_digest: externalMemoryEvaluationLabelsDigest(duplicateCore) };
    expect(() => analyzeExternalMemoryEvaluationLabels(cohort, duplicate as never)).toThrow("incomplete_labels");
    const accessor = { ...valid } as Record<string, unknown>;
    Object.defineProperty(accessor, "grades", { enumerable: true, get: () => valid.grades });
    expect(() => analyzeExternalMemoryEvaluationLabels(cohort, accessor as never)).toThrow("invalid_labels");
  });

  test("cohort and report remain content-safe and make no promotion decision", () => {
    const cohort = buildMemoryEvaluationCohort([unit(0), unit(1)]);
    const report = analyzeExternalMemoryEvaluationLabels(cohort, labels(cohort, () => "wrong"));
    const serialized = JSON.stringify({ cohort, report });
    for (const sentinel of [
      "account:alice", "strategy:raw", "David", "question:secret", "answer:secret",
      "evidence:secret", "frontier:secret", "source:secret", "grader note",
    ]) expect(serialized).not.toContain(sentinel);
    expect(serialized).not.toContain("promot");
  });
});
