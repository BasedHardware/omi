import { isProxy } from "node:util/types";

import { parseAttributionBeliefRevision } from "../../../core/consolidate/attribution-belief";
import { sha256CanonicalRedacted, type CanonicalJson } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertVerifiedMemoryEvaluationResult,
  type MemoryEvaluationResult,
} from "../stores/memory-shadow-result-repository";
import { ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION } from "./attribution-belief-shadow-producer";
import {
  parseListenAttributionBlindKey,
  parseListenAttributionBlindLabels,
  parseListenAttributionBlindSheet,
  type ListenAttributionBlindKey,
  type ListenAttributionBlindLabels,
  type ListenAttributionBlindSheet,
} from "./listen-attribution-blind-calibration-sheet";
import {
  parseMemoryEvaluationCohort,
  type MemoryEvaluationCohortManifest,
} from "./memory-evaluation-statistics";

const REPORT_VERSION = "listen-attribution-calibration-statistics-v1" as const;
const CAPABILITY = "memories.experiments.shadow";
const DIGEST = /^[a-f0-9]{64}$/;
const MAX_RESULTS = 200_000;
const MICROS = 1_000_000n;
const SQUARED_MICROS = MICROS * MICROS;

export interface ListenAttributionReliabilityBin {
  readonly ordinal: number;
  readonly lower_inclusive_micros: number;
  readonly upper_inclusive_micros: number;
  readonly count: number;
  readonly predicted_owner_micros_sum: string;
  readonly owner_truth_count: number;
}

export interface ListenAttributionArmCalibrationStatistics {
  readonly included_count: number;
  readonly brier_numerator: string;
  readonly brier_denominator: string;
  readonly reliability_bins: readonly Readonly<ListenAttributionReliabilityBin>[];
}

export interface ListenAttributionPairedCalibrationStatistics {
  readonly labelled_observation_count: number;
  readonly owner_count: number;
  readonly non_owner_count: number;
  readonly unclear_count: number;
  readonly baseline: Readonly<ListenAttributionArmCalibrationStatistics>;
  readonly candidate: Readonly<ListenAttributionArmCalibrationStatistics>;
  readonly candidate_minus_baseline_brier_numerator: string;
  readonly paired_brier_denominator: string;
}

export interface ListenAttributionCalibrationStatisticsReport {
  readonly version: typeof REPORT_VERSION;
  readonly cohort_digest: string;
  readonly labels_digest: string;
  readonly observation_count: number;
  readonly repeat_count: number;
  readonly repeat_ordinals: readonly number[];
  readonly by_repeat: readonly Readonly<{
    repeat_ordinal: number;
    statistics: Readonly<ListenAttributionPairedCalibrationStatistics>;
  }>[];
  readonly aggregate: Readonly<ListenAttributionPairedCalibrationStatistics>;
  readonly report_digest: string;
}

interface MutableBin {
  count: number;
  predicted: bigint;
  owners: number;
}

interface MutableArm {
  included: number;
  brier: bigint;
  bins: MutableBin[];
}

interface MutablePaired {
  labelled: number;
  owner: number;
  nonOwner: number;
  unclear: number;
  baseline: MutableArm;
  candidate: MutableArm;
}

const fail = (code: string): never => {
  throw new TypeError(`Listen attribution calibration statistics ${code}`);
};
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const expected = [...keys].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const exactArray = (value: unknown, length: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length !== length || length > MAX_RESULTS) fail(code);
  const arrayValue = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(arrayValue);
  if (Reflect.ownKeys(descriptors).length !== arrayValue.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < arrayValue.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const unique = (values: readonly string[], code: string): void => {
  if (new Set(values).size !== values.length) fail(code);
};

const emptyArm = (): MutableArm => ({
  included: 0,
  brier: 0n,
  bins: Array.from({ length: 10 }, () => ({ count: 0, predicted: 0n, owners: 0 })),
});

const emptyPaired = (): MutablePaired => ({
  labelled: 0,
  owner: 0,
  nonOwner: 0,
  unclear: 0,
  baseline: emptyArm(),
  candidate: emptyArm(),
});

const recordProbability = (arm: MutableArm, probability: number, ownerTruth: boolean): void => {
  const predicted = BigInt(probability);
  const truth = ownerTruth ? MICROS : 0n;
  const error = predicted - truth;
  arm.included += 1;
  arm.brier += error * error;
  const bin = arm.bins[Math.min(9, Math.floor(probability / 100_000))]!;
  bin.count += 1;
  bin.predicted += predicted;
  if (ownerTruth) bin.owners += 1;
};

const frozenArm = (value: MutableArm): Readonly<ListenAttributionArmCalibrationStatistics> =>
  Object.freeze({
    included_count: value.included,
    brier_numerator: value.brier.toString(),
    brier_denominator: (SQUARED_MICROS * BigInt(value.included)).toString(),
    reliability_bins: Object.freeze(value.bins.map((bin, ordinal) => Object.freeze({
      ordinal,
      lower_inclusive_micros: ordinal * 100_000,
      upper_inclusive_micros: ordinal === 9 ? 1_000_000 : ((ordinal + 1) * 100_000) - 1,
      count: bin.count,
      predicted_owner_micros_sum: bin.predicted.toString(),
      owner_truth_count: bin.owners,
    }))),
  });

const frozenPaired = (value: MutablePaired): Readonly<ListenAttributionPairedCalibrationStatistics> =>
  Object.freeze({
    labelled_observation_count: value.labelled,
    owner_count: value.owner,
    non_owner_count: value.nonOwner,
    unclear_count: value.unclear,
    baseline: frozenArm(value.baseline),
    candidate: frozenArm(value.candidate),
    candidate_minus_baseline_brier_numerator: (value.candidate.brier - value.baseline.brier).toString(),
    paired_brier_denominator: (SQUARED_MICROS * BigInt(value.baseline.included)).toString(),
  });

const strategyRef = (
  result: Readonly<MemoryEvaluationResult>,
): string => `mes1_${sha256CanonicalContent({
  contract_version: "memory-evaluation-export-strategy-ref-v2",
  owner_account_id: result.owner_account_id,
  account_epoch: result.account_epoch,
  evaluation_role: result.evaluation_role,
  strategy_id: result.strategy_id,
})}`;

const beliefObservation = (result: Readonly<MemoryEvaluationResult>): Readonly<{
  probability_micros: number;
  observation_ref: string;
  observation_content_digest: string;
}> => {
  if (result.result_contract_version !== ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION) fail("wrong_result_contract");
  const normalized = exactRecord(result.normalized_result, [
    "version", "belief", "calibration_receipt",
  ], "invalid_result");
  if (normalized["version"] !== ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION) fail("invalid_result");
  const belief = parseAttributionBeliefRevision(normalized["belief"]);
  if (belief.belief_kind !== "source_identity") fail("invalid_result");
  const ownerHypotheses = belief.hypotheses.filter((hypothesis) => hypothesis.kind === "owner");
  if (ownerHypotheses.length !== 1 || ownerHypotheses[0]!.target_ref !== null) fail("invalid_result");
  const receipt = exactRecord(normalized["calibration_receipt"], [
    "version", "request_digest", "response_digest", "result_digest",
    "calibration_contract_digest", "belief_revision_id",
  ], "invalid_result");
  const expectedResponseDigest = sha256CanonicalRedacted({
    probabilities: belief.hypotheses.map((hypothesis) => ({
      hypothesis_id: hypothesis.hypothesis_id,
      probability_micros: hypothesis.probability_micros,
    })),
  });
  if (receipt["version"] !== "attribution-calibration-receipt-v1"
    || typeof receipt["request_digest"] !== "string" || !DIGEST.test(receipt["request_digest"])
    || receipt["response_digest"] !== result.response_digest
    || receipt["response_digest"] !== expectedResponseDigest
    || receipt["result_digest"] !== sha256CanonicalRedacted(belief as unknown as CanonicalJson)
    || receipt["calibration_contract_digest"] !== result.execution_contract_digest
    || receipt["belief_revision_id"] !== belief.belief_revision_id
    || belief.calibration_contract_digest !== result.execution_contract_digest) fail("invalid_result");
  return Object.freeze({
    probability_micros: ownerHypotheses[0]!.probability_micros,
    observation_ref: belief.observation_ref,
    observation_content_digest: belief.observation_content_digest,
  });
};

const verifyArtifactJoins = (
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  sheet: Readonly<ListenAttributionBlindSheet>,
  key: Readonly<ListenAttributionBlindKey>,
  labels: Readonly<ListenAttributionBlindLabels>,
): void => {
  if (sheet.cohort_digest !== cohort.cohort_digest || key.cohort_digest !== cohort.cohort_digest
    || labels.cohort_digest !== cohort.cohort_digest
    || sheet.hidden_key_digest !== key.hidden_key_digest
    || labels.hidden_key_digest !== key.hidden_key_digest
    || labels.blind_sheet_digest !== sheet.blind_sheet_digest
    || sheet.row_count !== key.mappings.length || key.mappings.length !== labels.labels.length) {
    fail("artifact_mismatch");
  }
  const sheetRefs = [...sheet.rows.map((row) => row.row_ref)].sort(compare);
  const keyRefs = [...key.mappings.map((row) => row.row_ref)].sort(compare);
  const labelRefs = [...labels.labels.map((row) => row.row_ref)].sort(compare);
  if (sheetRefs.some((rowRef, index) => rowRef !== keyRefs[index] || rowRef !== labelRefs[index])) {
    fail("artifact_mismatch");
  }
  const keyByRow = new Map(key.mappings.map((row) => [row.row_ref, row]));
  for (const label of labels.labels) {
    const mapping = keyByRow.get(label.row_ref);
    if (!mapping || mapping.input_ref !== label.input_ref || mapping.observation_ref !== label.observation_ref
      || mapping.result_refs.length !== label.result_refs.length
      || mapping.result_refs.some((resultRef, index) => resultRef !== label.result_refs[index])) {
      fail("artifact_mismatch");
    }
  }
};

export const analyzeListenAttributionCalibration = (
  contextValue: AuthorizedLedgerWriteContext,
  cohortValue: MemoryEvaluationCohortManifest,
  sheetValue: ListenAttributionBlindSheet,
  keyValue: ListenAttributionBlindKey,
  labelsValue: ListenAttributionBlindLabels,
  resultValues: readonly MemoryEvaluationResult[],
): Readonly<ListenAttributionCalibrationStatisticsReport> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  const cohort = parseMemoryEvaluationCohort(cohortValue);
  const sheet = parseListenAttributionBlindSheet(sheetValue);
  const key = parseListenAttributionBlindKey(keyValue);
  const labels = parseListenAttributionBlindLabels(labelsValue);
  verifyArtifactJoins(cohort, sheet, key, labels);

  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ]));
  const results = exactArray(resultValues, expectedRefs.length, "invalid_results")
    .map(assertVerifiedMemoryEvaluationResult);
  unique(results.map((result) => result.evaluation_result_id), "duplicate_result");
  const byRef = new Map(results.map((result) => [result.evaluation_result_id, result]));
  if (expectedRefs.some((resultRef) => !byRef.has(resultRef))
    || results.some((result) => !expectedRefs.includes(result.evaluation_result_id))) fail("incomplete_results");

  const unitByResult = new Map<string, Readonly<MemoryEvaluationCohortManifest["units"][number]>>();
  for (const unit of cohort.units) {
    for (const pair of unit.pairs) {
      unitByResult.set(pair.baseline_result_ref, unit);
      unitByResult.set(pair.candidate_result_ref, unit);
    }
  }
  const labelsByResult = new Map<string, Readonly<ListenAttributionBlindLabels["labels"][number]>>();
  for (const label of labels.labels) {
    const units = new Set(label.result_refs.map((resultRef) => unitByResult.get(resultRef)));
    if (units.size !== 1 || units.has(undefined)) fail("label_cohort_mismatch");
    const unit = [...units][0]!;
    const unitRefs = unit.pairs.flatMap((pair) => [pair.baseline_result_ref, pair.candidate_result_ref]).sort(compare);
    if (unitRefs.length !== label.result_refs.length
      || unitRefs.some((resultRef, index) => resultRef !== label.result_refs[index])) {
      fail("label_cohort_mismatch");
    }
    for (const resultRef of label.result_refs) labelsByResult.set(resultRef, label);
  }
  if (labelsByResult.size !== expectedRefs.length) fail("label_cohort_mismatch");

  const byRepeat = new Map(cohort.repeat_ordinals.map((repeat) => [repeat, emptyPaired()]));
  const aggregate = emptyPaired();
  for (const unit of cohort.units) {
    for (const pair of unit.pairs) {
      const baseline = byRef.get(pair.baseline_result_ref)!;
      const candidate = byRef.get(pair.candidate_result_ref)!;
      const label = labelsByResult.get(pair.baseline_result_ref)!;
      if (labelsByResult.get(pair.candidate_result_ref) !== label) fail("label_cohort_mismatch");
      for (const [result, role, expectedStrategy] of [
        [baseline, "baseline", cohort.baseline_strategy_ref],
        [candidate, "candidate", cohort.candidate_strategy_ref],
      ] as const) {
        if (result.owner_account_id !== context.account_id || result.account_epoch !== context.account_epoch
          || result.evaluation_run_id !== cohort.evaluation_run_ref
          || result.evaluation_mode !== cohort.evaluation_mode || result.evaluation_role !== role
          || result.repeat_ordinal !== pair.repeat_ordinal || strategyRef(result) !== expectedStrategy) {
          fail("result_coordinate_mismatch");
        }
      }
      const baselineObservation = beliefObservation(baseline);
      const candidateObservation = beliefObservation(candidate);
      if (baselineObservation.observation_ref !== label.observation_ref
        || candidateObservation.observation_ref !== label.observation_ref
        || baselineObservation.observation_content_digest !== candidateObservation.observation_content_digest) {
        fail("result_observation_mismatch");
      }
      for (const bucket of [byRepeat.get(pair.repeat_ordinal)!, aggregate]) {
        bucket.labelled += 1;
        if (label.label === "unclear") {
          bucket.unclear += 1;
          continue;
        }
        const isOwner = label.label === "owner";
        if (isOwner) bucket.owner += 1;
        else bucket.nonOwner += 1;
        recordProbability(bucket.baseline, baselineObservation.probability_micros, isOwner);
        recordProbability(bucket.candidate, candidateObservation.probability_micros, isOwner);
      }
    }
  }

  const core = Object.freeze({
    version: REPORT_VERSION,
    cohort_digest: cohort.cohort_digest,
    labels_digest: labels.labels_digest,
    observation_count: labels.labels.length,
    repeat_count: cohort.repeat_count,
    repeat_ordinals: cohort.repeat_ordinals,
    by_repeat: Object.freeze(cohort.repeat_ordinals.map((repeatOrdinal) => Object.freeze({
      repeat_ordinal: repeatOrdinal,
      statistics: frozenPaired(byRepeat.get(repeatOrdinal)!),
    }))),
    aggregate: frozenPaired(aggregate),
  });
  return Object.freeze({ ...core, report_digest: sha256CanonicalContent(core) });
};

export const LISTEN_ATTRIBUTION_CALIBRATION_STATISTICS_VERSION = REPORT_VERSION;
