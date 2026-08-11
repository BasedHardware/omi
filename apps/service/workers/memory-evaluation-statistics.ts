import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  parseMemoryEvaluationExport,
  type MemoryEvaluationExportManifest,
} from "./memory-evaluation-export";

const COHORT_VERSION = "memory-evaluation-cohort-v1" as const;
const LABEL_VERSION = "memory-evaluation-labels-v1" as const;
const REPORT_VERSION = "memory-evaluation-statistics-v1" as const;
const GRADING_PROTOCOL = "owner-truth-five-grade-v1" as const;
const MAX_UNITS = 10_000;
const MAX_PAIRS = 100_000;
const DIGEST = /^[a-f0-9]{64}$/;
const RUN_REF = /^mer1_[a-f0-9]{64}$/;
const ASSIGNMENT_REF = /^mea1_[a-f0-9]{64}$/;
const INPUT_REF = /^mei1_[a-f0-9]{64}$/;
const PAIR_REF = /^mep1_[a-f0-9]{64}$/;
const RESULT_REF = /^msr1_[a-f0-9]{64}$/;
const STRATEGY_REF = /^mes1_[a-f0-9]{64}$/;
const GRADER_REF = /^meg1_[a-f0-9]{64}$/;

export type MemoryEvaluationGrade = "correct" | "partly" | "wrong" | "empty" | "unsure";

export interface MemoryEvaluationCohortPair {
  readonly repeat_ordinal: number;
  readonly pair_ref: string;
  readonly baseline_result_ref: string;
  readonly candidate_result_ref: string;
}

export interface MemoryEvaluationCohortUnit {
  readonly ordinal: number;
  readonly assignment_bundle_ref: string;
  readonly input_ref: string;
  readonly pairs: readonly Readonly<MemoryEvaluationCohortPair>[];
}

export interface MemoryEvaluationCohortManifest {
  readonly version: typeof COHORT_VERSION;
  readonly evaluation_mode: "live_shadow" | "offline_replay";
  readonly evaluation_run_ref: string;
  readonly baseline_strategy_ref: string;
  readonly candidate_strategy_ref: string;
  readonly unit_count: number;
  readonly repeat_count: number;
  readonly pair_count: number;
  readonly repeat_ordinals: readonly number[];
  readonly units: readonly Readonly<MemoryEvaluationCohortUnit>[];
  readonly cohort_digest: string;
}

export interface ExternalMemoryEvaluationLabels {
  readonly version: typeof LABEL_VERSION;
  readonly cohort_digest: string;
  readonly grading_protocol_version: typeof GRADING_PROTOCOL;
  readonly grader_session_ref: string;
  readonly blind_sheet_digest: string;
  readonly hidden_key_digest: string;
  readonly grades: readonly Readonly<{ result_ref: string; grade: MemoryEvaluationGrade }>[];
  readonly labels_digest: string;
}

export interface MemoryEvaluationGradeCounts {
  readonly correct: number;
  readonly partly: number;
  readonly wrong: number;
  readonly empty: number;
  readonly unsure: number;
}

export interface MemoryEvaluationStatisticsReport {
  readonly version: typeof REPORT_VERSION;
  readonly cohort_digest: string;
  readonly labels_digest: string;
  readonly input_count: number;
  readonly repeat_count: number;
  readonly primary_repeat_ordinal: 0;
  readonly baseline_primary_grades: Readonly<MemoryEvaluationGradeCounts>;
  readonly candidate_primary_grades: Readonly<MemoryEvaluationGradeCounts>;
  readonly primary_pairs_included: number;
  readonly primary_pairs_excluded_unsure: number;
  readonly both_success: number;
  readonly both_nonsuccess: number;
  readonly candidate_wins: number;
  readonly baseline_wins: number;
  readonly mcnemar_exact_two_sided: Readonly<{
    numerator: string;
    denominator_power_of_two: number;
    approximate: number;
  }>;
  readonly baseline_primary_wrong: number;
  readonly candidate_primary_wrong: number;
  readonly baseline_self_noise: Readonly<{ comparisons: number; grade_flips: number; flip_rate: number }>;
  readonly candidate_self_noise: Readonly<{ comparisons: number; grade_flips: number; flip_rate: number }>;
  readonly report_digest: string;
}

const fail = (code: string): never => { throw new TypeError(`memory evaluation statistics ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, minimum: number, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < minimum || value.length > maximum) fail(code);
  const values = value as unknown[];
  const keys = Reflect.ownKeys(values);
  if (keys.length !== values.length + 1 || keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= values.length)))) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(values);
  for (let index = 0; index < values.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor)) fail(code);
  }
  return values;
};

const ref = (value: unknown, pattern: RegExp, code: string): string => {
  if (typeof value !== "string" || !pattern.test(value)) fail(code);
  return value as string;
};

const integer = (value: unknown, maximum: number, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) fail(code);
  return value as number;
};

const unique = (values: readonly string[], code: string): void => {
  if (new Set(values).size !== values.length) fail(code);
};

export const buildMemoryEvaluationCohort = (
  exportValues: readonly MemoryEvaluationExportManifest[],
): Readonly<MemoryEvaluationCohortManifest> => {
  const exports = exactArray(exportValues, 2, MAX_UNITS, "invalid_exports").map(parseMemoryEvaluationExport);
  const first = exports[0]!;
  for (const unit of exports) {
    if (unit.evaluation_mode !== first.evaluation_mode || unit.evaluation_run_ref !== first.evaluation_run_ref) {
      fail("mixed_run");
    }
    if (unit.candidate_strategy_count !== 1 || unit.repeat_count < 2) fail("invalid_unit_shape");
  }
  const totalPairs = exports.reduce((total, unit) => total + unit.pair_count, 0);
  if (totalPairs > MAX_PAIRS) fail("cohort_too_large");
  const baselineRefs = new Set(exports.flatMap((unit) => unit.pairs.map((pair) => pair.baseline_strategy_ref)));
  const candidateRefs = new Set(exports.flatMap((unit) => unit.pairs.map((pair) => pair.candidate_strategy_ref)));
  if (baselineRefs.size !== 1 || candidateRefs.size !== 1) fail("mixed_strategy");
  unique(exports.map((unit) => unit.input_ref), "duplicate_input");

  const expectedRepeats = [...new Set(first.pairs.map((pair) => pair.repeat_ordinal))].sort((a, b) => a - b);
  if (expectedRepeats[0] !== 0 || expectedRepeats.length < 2) fail("invalid_repeats");
  for (const unit of exports) {
    const observed = [...new Set(unit.pairs.map((pair) => pair.repeat_ordinal))].sort((a, b) => a - b);
    if (observed.length !== expectedRepeats.length || observed.some((value, index) => value !== expectedRepeats[index])) {
      fail("uneven_repeats");
    }
  }

  const ordered = [...exports].sort((left, right) => compare(left.input_ref, right.input_ref)
    || compare(left.assignment_bundle_ref, right.assignment_bundle_ref));
  const units = Object.freeze(ordered.map((unit, ordinal) => Object.freeze({
    ordinal,
    assignment_bundle_ref: unit.assignment_bundle_ref,
    input_ref: unit.input_ref,
    pairs: Object.freeze([...unit.pairs].sort((left, right) => left.repeat_ordinal - right.repeat_ordinal).map((pair) => Object.freeze({
      repeat_ordinal: pair.repeat_ordinal,
      pair_ref: pair.pair_ref,
      baseline_result_ref: pair.baseline_result_ref,
      candidate_result_ref: pair.candidate_result_ref,
    }))),
  })));
  const allPairs = units.flatMap((unit) => unit.pairs);
  unique(allPairs.map((pair) => pair.pair_ref), "duplicate_pair");
  unique(allPairs.flatMap((pair) => [pair.baseline_result_ref, pair.candidate_result_ref]), "duplicate_result");
  const core = Object.freeze({
    version: COHORT_VERSION,
    evaluation_mode: first.evaluation_mode,
    evaluation_run_ref: first.evaluation_run_ref,
    baseline_strategy_ref: [...baselineRefs][0]!,
    candidate_strategy_ref: [...candidateRefs][0]!,
    unit_count: units.length,
    repeat_count: expectedRepeats.length,
    pair_count: allPairs.length,
    repeat_ordinals: Object.freeze(expectedRepeats),
    units,
  });
  return parseMemoryEvaluationCohort(Object.freeze({ ...core, cohort_digest: sha256CanonicalContent(core) }));
};

export const parseMemoryEvaluationCohort = (value: unknown): Readonly<MemoryEvaluationCohortManifest> => {
  const root = exactRecord(value, [
    "version", "evaluation_mode", "evaluation_run_ref", "baseline_strategy_ref",
    "candidate_strategy_ref", "unit_count", "repeat_count", "pair_count",
    "repeat_ordinals", "units", "cohort_digest",
  ], "invalid_cohort");
  if (root["version"] !== COHORT_VERSION
    || (root["evaluation_mode"] !== "live_shadow" && root["evaluation_mode"] !== "offline_replay")) fail("invalid_cohort");
  const repeats = Object.freeze(exactArray(root["repeat_ordinals"], 2, 1_000, "invalid_cohort")
    .map((item) => integer(item, 999, "invalid_cohort")));
  if (repeats[0] !== 0 || repeats.some((item, index) => index > 0 && item <= repeats[index - 1]!)) fail("invalid_cohort");
  const units = Object.freeze(exactArray(root["units"], 2, MAX_UNITS, "invalid_cohort").map((value, index) => {
    const unit = exactRecord(value, ["ordinal", "assignment_bundle_ref", "input_ref", "pairs"], "invalid_cohort_unit");
    if (integer(unit["ordinal"], MAX_UNITS - 1, "invalid_cohort_unit") !== index) fail("invalid_cohort_unit");
    const pairs = Object.freeze(exactArray(unit["pairs"], repeats.length, repeats.length, "invalid_cohort_unit")
      .map((pairValue, pairIndex) => {
        const pair = exactRecord(pairValue, [
          "repeat_ordinal", "pair_ref", "baseline_result_ref", "candidate_result_ref",
        ], "invalid_cohort_pair");
        const repeatOrdinal = integer(pair["repeat_ordinal"], 999, "invalid_cohort_pair");
        if (repeatOrdinal !== repeats[pairIndex]) fail("invalid_cohort_pair");
        return Object.freeze({
          repeat_ordinal: repeatOrdinal,
          pair_ref: ref(pair["pair_ref"], PAIR_REF, "invalid_cohort_pair"),
          baseline_result_ref: ref(pair["baseline_result_ref"], RESULT_REF, "invalid_cohort_pair"),
          candidate_result_ref: ref(pair["candidate_result_ref"], RESULT_REF, "invalid_cohort_pair"),
        });
      }));
    return Object.freeze({
      ordinal: index,
      assignment_bundle_ref: ref(unit["assignment_bundle_ref"], ASSIGNMENT_REF, "invalid_cohort_unit"),
      input_ref: ref(unit["input_ref"], INPUT_REF, "invalid_cohort_unit"),
      pairs,
    });
  }));
  const allPairs = units.flatMap((unit) => unit.pairs);
  if (integer(root["unit_count"], MAX_UNITS, "invalid_cohort") !== units.length
    || integer(root["repeat_count"], 1_000, "invalid_cohort") !== repeats.length
    || integer(root["pair_count"], MAX_PAIRS, "invalid_cohort") !== allPairs.length) fail("invalid_cohort");
  unique(units.map((unit) => unit.input_ref), "invalid_cohort");
  unique(allPairs.map((pair) => pair.pair_ref), "invalid_cohort");
  unique(allPairs.flatMap((pair) => [pair.baseline_result_ref, pair.candidate_result_ref]), "invalid_cohort");
  const core = Object.freeze({
    version: COHORT_VERSION,
    evaluation_mode: root["evaluation_mode"] as "live_shadow" | "offline_replay",
    evaluation_run_ref: ref(root["evaluation_run_ref"], RUN_REF, "invalid_cohort"),
    baseline_strategy_ref: ref(root["baseline_strategy_ref"], STRATEGY_REF, "invalid_cohort"),
    candidate_strategy_ref: ref(root["candidate_strategy_ref"], STRATEGY_REF, "invalid_cohort"),
    unit_count: units.length,
    repeat_count: repeats.length,
    pair_count: allPairs.length,
    repeat_ordinals: repeats,
    units,
  });
  const digest = ref(root["cohort_digest"], DIGEST, "invalid_cohort");
  if (digest !== sha256CanonicalContent(core)) fail("invalid_cohort_digest");
  return Object.freeze({ ...core, cohort_digest: digest });
};

export const externalMemoryEvaluationLabelsDigest = (
  value: Omit<ExternalMemoryEvaluationLabels, "labels_digest">,
): string => sha256CanonicalContent({
  version: value.version,
  cohort_digest: value.cohort_digest,
  grading_protocol_version: value.grading_protocol_version,
  grader_session_ref: value.grader_session_ref,
  blind_sheet_digest: value.blind_sheet_digest,
  hidden_key_digest: value.hidden_key_digest,
  grades: [...value.grades].sort((left, right) => compare(left.result_ref, right.result_ref)),
});

export const parseExternalMemoryEvaluationLabels = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  value: unknown,
): Readonly<ExternalMemoryEvaluationLabels> => {
  const root = exactRecord(value, [
    "version", "cohort_digest", "grading_protocol_version", "grader_session_ref",
    "blind_sheet_digest", "hidden_key_digest", "grades", "labels_digest",
  ], "invalid_labels");
  if (root["version"] !== LABEL_VERSION || root["grading_protocol_version"] !== GRADING_PROTOCOL
    || root["cohort_digest"] !== cohort.cohort_digest) fail("invalid_labels");
  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ])).sort(compare);
  const grades = Object.freeze(exactArray(root["grades"], expectedRefs.length, expectedRefs.length, "invalid_labels")
    .map((value) => {
      const row = exactRecord(value, ["result_ref", "grade"], "invalid_label_row");
      if (!(["correct", "partly", "wrong", "empty", "unsure"] as readonly unknown[]).includes(row["grade"])) {
        fail("invalid_label_row");
      }
      return Object.freeze({
        result_ref: ref(row["result_ref"], RESULT_REF, "invalid_label_row"),
        grade: row["grade"] as MemoryEvaluationGrade,
      });
    }).sort((left, right) => compare(left.result_ref, right.result_ref)));
  if (grades.some((row, index) => row.result_ref !== expectedRefs[index])) fail("incomplete_labels");
  const core = Object.freeze({
    version: LABEL_VERSION,
    cohort_digest: cohort.cohort_digest,
    grading_protocol_version: GRADING_PROTOCOL,
    grader_session_ref: ref(root["grader_session_ref"], GRADER_REF, "invalid_labels"),
    blind_sheet_digest: ref(root["blind_sheet_digest"], DIGEST, "invalid_labels"),
    hidden_key_digest: ref(root["hidden_key_digest"], DIGEST, "invalid_labels"),
    grades,
  });
  const digest = ref(root["labels_digest"], DIGEST, "invalid_labels");
  if (digest !== sha256CanonicalContent(core)) fail("invalid_labels_digest");
  return Object.freeze({ ...core, labels_digest: digest });
};

type MutableGradeCounts = Record<MemoryEvaluationGrade, number>;
const emptyCounts = (): MutableGradeCounts => ({ correct: 0, partly: 0, wrong: 0, empty: 0, unsure: 0 });
const success = (grade: MemoryEvaluationGrade): boolean => grade === "correct" || grade === "partly";

const exactMcNemar = (left: number, right: number): Readonly<{
  numerator: string; denominator_power_of_two: number; approximate: number;
}> => {
  const trials = left + right;
  const tail = Math.min(left, right);
  if (trials === 0) return Object.freeze({ numerator: "1", denominator_power_of_two: 0, approximate: 1 });
  let combination = 1n;
  let sum = 1n;
  for (let index = 1; index <= tail; index += 1) {
    combination = (combination * BigInt(trials - index + 1)) / BigInt(index);
    sum += combination;
  }
  let numerator = 2n * sum;
  let denominatorPower = trials;
  const denominator = 1n << BigInt(trials);
  if (numerator >= denominator) return Object.freeze({ numerator: "1", denominator_power_of_two: 0, approximate: 1 });
  while (denominatorPower > 0 && numerator % 2n === 0n) {
    numerator /= 2n;
    denominatorPower -= 1;
  }
  const logApproximation = Math.log(2) + Math.log(Number(sum >> BigInt(Math.max(0, sum.toString(2).length - 53))))
    + Math.max(0, sum.toString(2).length - 53) * Math.log(2) - trials * Math.log(2);
  const finiteNumerator = Number(numerator);
  return Object.freeze({
    numerator: numerator.toString(),
    denominator_power_of_two: denominatorPower,
    approximate: Number.isFinite(finiteNumerator) && denominatorPower <= 1_023
      ? finiteNumerator / (2 ** denominatorPower)
      : Math.exp(logApproximation),
  });
};

export const analyzeExternalMemoryEvaluationLabels = (
  cohortValue: MemoryEvaluationCohortManifest,
  labelsValue: ExternalMemoryEvaluationLabels,
): Readonly<MemoryEvaluationStatisticsReport> => {
  const cohort = parseMemoryEvaluationCohort(cohortValue);
  const labels = parseExternalMemoryEvaluationLabels(cohort, labelsValue);
  const gradeByResult = new Map(labels.grades.map((row) => [row.result_ref, row.grade]));
  const baselineCounts = emptyCounts();
  const candidateCounts = emptyCounts();
  let included = 0;
  let excluded = 0;
  let bothSuccess = 0;
  let bothNonsuccess = 0;
  let candidateWins = 0;
  let baselineWins = 0;
  let baselineNoiseComparisons = 0;
  let candidateNoiseComparisons = 0;
  let baselineNoiseFlips = 0;
  let candidateNoiseFlips = 0;
  for (const unit of cohort.units) {
    const primary = unit.pairs[0]!;
    const baselinePrimary = gradeByResult.get(primary.baseline_result_ref)!;
    const candidatePrimary = gradeByResult.get(primary.candidate_result_ref)!;
    baselineCounts[baselinePrimary] += 1;
    candidateCounts[candidatePrimary] += 1;
    if (baselinePrimary === "unsure" || candidatePrimary === "unsure") excluded += 1;
    else {
      included += 1;
      const baselineSucceeded = success(baselinePrimary);
      const candidateSucceeded = success(candidatePrimary);
      if (baselineSucceeded && candidateSucceeded) bothSuccess += 1;
      else if (!baselineSucceeded && !candidateSucceeded) bothNonsuccess += 1;
      else if (candidateSucceeded) candidateWins += 1;
      else baselineWins += 1;
    }
    for (const repeat of unit.pairs.slice(1)) {
      baselineNoiseComparisons += 1;
      candidateNoiseComparisons += 1;
      if (gradeByResult.get(repeat.baseline_result_ref)! !== baselinePrimary) baselineNoiseFlips += 1;
      if (gradeByResult.get(repeat.candidate_result_ref)! !== candidatePrimary) candidateNoiseFlips += 1;
    }
  }
  const core = Object.freeze({
    version: REPORT_VERSION,
    cohort_digest: cohort.cohort_digest,
    labels_digest: labels.labels_digest,
    input_count: cohort.unit_count,
    repeat_count: cohort.repeat_count,
    primary_repeat_ordinal: 0 as const,
    baseline_primary_grades: Object.freeze(baselineCounts),
    candidate_primary_grades: Object.freeze(candidateCounts),
    primary_pairs_included: included,
    primary_pairs_excluded_unsure: excluded,
    both_success: bothSuccess,
    both_nonsuccess: bothNonsuccess,
    candidate_wins: candidateWins,
    baseline_wins: baselineWins,
    mcnemar_exact_two_sided: exactMcNemar(candidateWins, baselineWins),
    baseline_primary_wrong: baselineCounts.wrong,
    candidate_primary_wrong: candidateCounts.wrong,
    baseline_self_noise: Object.freeze({
      comparisons: baselineNoiseComparisons,
      grade_flips: baselineNoiseFlips,
      flip_rate: baselineNoiseComparisons ? baselineNoiseFlips / baselineNoiseComparisons : 0,
    }),
    candidate_self_noise: Object.freeze({
      comparisons: candidateNoiseComparisons,
      grade_flips: candidateNoiseFlips,
      flip_rate: candidateNoiseComparisons ? candidateNoiseFlips / candidateNoiseComparisons : 0,
    }),
  });
  return Object.freeze({ ...core, report_digest: sha256CanonicalContent(core) });
};

export const MEMORY_EVALUATION_COHORT_VERSION = COHORT_VERSION;
export const MEMORY_EVALUATION_LABEL_VERSION = LABEL_VERSION;
export const MEMORY_EVALUATION_GRADING_PROTOCOL = GRADING_PROTOCOL;
export const MEMORY_EVALUATION_STATISTICS_VERSION = REPORT_VERSION;
