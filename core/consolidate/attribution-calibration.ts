import { isProxy } from "node:util/types";

import { sha256CanonicalRedacted, type CanonicalJson } from "../ledger";
import {
  ATTRIBUTION_BELIEF_VERSION,
  PROBABILITY_MICROS_TOTAL,
  AttributionBeliefContractError,
  attributionHypothesisId,
  buildAttributionBeliefRevision,
  type AttributionBeliefKind,
  type AttributionBeliefRevision,
  type AttributionEvidenceFactor,
  type AttributionHypothesisKind,
} from "./attribution-belief";

export const ATTRIBUTION_CALIBRATION_REQUEST_VERSION = "attribution-calibration-request-v1" as const;
export const ATTRIBUTION_CALIBRATION_RECEIPT_VERSION = "attribution-calibration-receipt-v1" as const;

export interface AttributionHypothesisCandidate {
  readonly kind: AttributionHypothesisKind;
  readonly target_ref: string | null;
}

export interface AttributionCalibrationRequest {
  readonly version: typeof ATTRIBUTION_CALIBRATION_REQUEST_VERSION;
  readonly owner_scope_digest: string;
  readonly belief_kind: AttributionBeliefKind;
  readonly about_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly graph_frontier: string;
  readonly hypotheses: readonly {
    readonly hypothesis_id: string;
    readonly kind: AttributionHypothesisKind;
    readonly target_ref: string | null;
  }[];
  readonly evidence_groups: readonly {
    readonly independence_group_ref: string;
    readonly factors: readonly AttributionEvidenceFactor[];
  }[];
  readonly attribution_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly calibration_contract_digest: string;
}

export interface AttributionCalibrationReceipt {
  readonly version: typeof ATTRIBUTION_CALIBRATION_RECEIPT_VERSION;
  readonly request_digest: string;
  readonly response_digest: string;
  readonly result_digest: string;
  readonly calibration_contract_digest: string;
  readonly belief_revision_id: string;
}

export interface CalibratedAttributionBelief {
  readonly belief: AttributionBeliefRevision;
  readonly receipt: AttributionCalibrationReceipt;
}

export interface CalibrateAttributionBeliefInput {
  readonly owner_account_id: string;
  readonly belief_kind: AttributionBeliefKind;
  readonly about_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly graph_frontier: string;
  readonly hypothesis_candidates: readonly AttributionHypothesisCandidate[];
  readonly evidence_factors: readonly AttributionEvidenceFactor[];
  readonly attribution_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly calibration_contract_digest: string;
  readonly created_at_event_time: number;
  readonly previous_revision: AttributionBeliefRevision | null;
}

export interface AttributionCalibratorPort {
  calibrate(request: AttributionCalibrationRequest): Promise<unknown>;
}

export type AttributionCalibrationErrorCode =
  | "invalid_attribution_calibration_input"
  | "invalid_attribution_calibration_output"
  | "attribution_calibration_failed";

export class AttributionCalibrationError extends Error {
  constructor(readonly code: AttributionCalibrationErrorCode) {
    super(code);
    this.name = "AttributionCalibrationError";
  }
}

const ARRAY_INDEX = /^(0|[1-9]\d*)$/;
const HYPOTHESIS_ID = /^athyp1_[a-f0-9]{64}$/;
const MAX_HYPOTHESES = 1_024;
const MAX_FACTORS = 10_000;

const fail = (code: AttributionCalibrationErrorCode): never => {
  throw new AttributionCalibrationError(code);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: AttributionCalibrationErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (
  value: unknown,
  maximum: number,
  code: AttributionCalibrationErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const array = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(array);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== array.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < array.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!ARRAY_INDEX.test(String(index)) || !descriptor || !descriptor.enumerable
      || !("value" in descriptor)) fail(code);
    output.push(descriptor!.value);
  }
  return output;
};

const normalizeInput = (value: unknown): CalibrateAttributionBeliefInput => {
  const code = "invalid_attribution_calibration_input" as const;
  const row = exactRecord(value, [
    "owner_account_id", "belief_kind", "about_ref", "observation_ref",
    "observation_content_digest", "graph_frontier", "hypothesis_candidates",
    "evidence_factors", "attribution_contract_digest", "aggregation_contract_digest",
    "calibration_contract_digest", "created_at_event_time", "previous_revision",
  ], code);
  const candidates = exactArray(row["hypothesis_candidates"], MAX_HYPOTHESES, code).map((entry) => {
    const candidate = exactRecord(entry, ["kind", "target_ref"], code);
    return Object.freeze({
      kind: candidate["kind"] as AttributionHypothesisKind,
      target_ref: candidate["target_ref"] as string | null,
    });
  });
  const factors = exactArray(row["evidence_factors"], MAX_FACTORS, code);
  return Object.freeze({
    owner_account_id: row["owner_account_id"] as string,
    belief_kind: row["belief_kind"] as AttributionBeliefKind,
    about_ref: row["about_ref"] as string,
    observation_ref: row["observation_ref"] as string,
    observation_content_digest: row["observation_content_digest"] as string,
    graph_frontier: row["graph_frontier"] as string,
    hypothesis_candidates: Object.freeze(candidates),
    evidence_factors: Object.freeze(factors) as readonly AttributionEvidenceFactor[],
    attribution_contract_digest: row["attribution_contract_digest"] as string,
    aggregation_contract_digest: row["aggregation_contract_digest"] as string,
    calibration_contract_digest: row["calibration_contract_digest"] as string,
    created_at_event_time: row["created_at_event_time"] as number,
    previous_revision: row["previous_revision"] as AttributionBeliefRevision | null,
  });
};

const freezeRequest = (request: AttributionCalibrationRequest): AttributionCalibrationRequest => {
  for (const hypothesis of request.hypotheses) Object.freeze(hypothesis);
  Object.freeze(request.hypotheses);
  for (const group of request.evidence_groups) {
    for (const factor of group.factors) Object.freeze(factor);
    Object.freeze(group.factors);
    Object.freeze(group);
  }
  Object.freeze(request.evidence_groups);
  return Object.freeze(request);
};

const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const requestFor = (provisional: AttributionBeliefRevision): AttributionCalibrationRequest => {
  const grouped = new Map<string, AttributionEvidenceFactor[]>();
  for (const factor of provisional.evidence_factors) {
    const entries = grouped.get(factor.independence_group_ref) ?? [];
    entries.push(factor);
    grouped.set(factor.independence_group_ref, entries);
  }
  return freezeRequest({
    version: ATTRIBUTION_CALIBRATION_REQUEST_VERSION,
    owner_scope_digest: sha256CanonicalRedacted({ owner_account_id: provisional.owner_account_id }),
    belief_kind: provisional.belief_kind,
    about_ref: provisional.about_ref,
    observation_ref: provisional.observation_ref,
    observation_content_digest: provisional.observation_content_digest,
    graph_frontier: provisional.graph_frontier,
    hypotheses: provisional.hypotheses.map((item) => ({
      hypothesis_id: item.hypothesis_id,
      kind: item.kind,
      target_ref: item.target_ref,
    })),
    evidence_groups: [...grouped.entries()]
      .sort(([left], [right]) => compare(left, right))
      .map(([independence_group_ref, factors]) => ({
        independence_group_ref,
        factors: [...factors].sort((left, right) => compare(left.factor_ref, right.factor_ref)),
      })),
    attribution_contract_digest: provisional.attribution_contract_digest,
    aggregation_contract_digest: provisional.aggregation_contract_digest,
    calibration_contract_digest: provisional.calibration_contract_digest,
  });
};

const parseProbabilities = (
  value: unknown,
  request: AttributionCalibrationRequest,
): readonly number[] => {
  const code = "invalid_attribution_calibration_output" as const;
  const envelope = exactRecord(value, ["probabilities"], code);
  const rows = exactArray(envelope["probabilities"], MAX_HYPOTHESES, code);
  if (rows.length !== request.hypotheses.length) fail(code);
  let total = 0;
  const probabilities = rows.map((entry, index) => {
    const row = exactRecord(entry, ["hypothesis_id", "probability_micros"], code);
    const id = row["hypothesis_id"];
    if (typeof id !== "string" || !HYPOTHESIS_ID.test(id)
      || id !== request.hypotheses[index]?.hypothesis_id) fail(code);
    const probability = row["probability_micros"];
    if (!Number.isSafeInteger(probability) || (probability as number) < 0
      || (probability as number) > PROBABILITY_MICROS_TOTAL) fail(code);
    total += probability as number;
    return probability as number;
  });
  if (total !== PROBABILITY_MICROS_TOTAL) fail(code);
  return Object.freeze(probabilities);
};

const provisionalFor = (input: CalibrateAttributionBeliefInput): AttributionBeliefRevision => {
  const candidates = input.hypothesis_candidates;
  const unknownCount = candidates.filter((item) => item.kind === "unknown").length;
  if (unknownCount !== 1) fail("invalid_attribution_calibration_input");
  try {
    return buildAttributionBeliefRevision({
      owner_account_id: input.owner_account_id,
      belief_kind: input.belief_kind,
      about_ref: input.about_ref,
      observation_ref: input.observation_ref,
      observation_content_digest: input.observation_content_digest,
      graph_frontier: input.graph_frontier,
      hypotheses: candidates.map((item) => ({
        kind: item.kind,
        target_ref: item.target_ref,
        probability_micros: item.kind === "unknown" ? PROBABILITY_MICROS_TOTAL : 0,
      })),
      evidence_factors: input.evidence_factors,
      attribution_contract_digest: input.attribution_contract_digest,
      aggregation_contract_digest: input.aggregation_contract_digest,
      calibration_contract_digest: input.calibration_contract_digest,
      created_at_event_time: input.created_at_event_time,
      previous_revision: input.previous_revision,
    });
  } catch (error) {
    if (error instanceof AttributionBeliefContractError) fail("invalid_attribution_calibration_input");
    throw error;
  }
};

/** Exact content-safe coordinate for one normalized calibrator request. This
 * lets offline evaluators verify a persisted receipt without replaying the
 * calibrator or exposing owner bytes. */
export const attributionCalibrationRequestDigest = (
  input: CalibrateAttributionBeliefInput,
): string => sha256CanonicalRedacted(
  requestFor(provisionalFor(normalizeInput(input))) as unknown as CanonicalJson,
);

export const calibrateAttributionBelief = async (
  input: CalibrateAttributionBeliefInput,
  calibrator: AttributionCalibratorPort,
): Promise<CalibratedAttributionBelief> => {
  const normalizedInput = normalizeInput(input);
  const provisional = provisionalFor(normalizedInput);
  const request = requestFor(provisional);
  let raw: unknown;
  try {
    raw = await calibrator.calibrate(request);
  } catch {
    return fail("attribution_calibration_failed");
  }
  const probabilities = parseProbabilities(raw, request);
  let belief: AttributionBeliefRevision;
  try {
    belief = buildAttributionBeliefRevision({
      owner_account_id: normalizedInput.owner_account_id,
      belief_kind: normalizedInput.belief_kind,
      about_ref: normalizedInput.about_ref,
      observation_ref: normalizedInput.observation_ref,
      observation_content_digest: normalizedInput.observation_content_digest,
      graph_frontier: normalizedInput.graph_frontier,
      hypotheses: provisional.hypotheses.map((item, index) => ({
        kind: item.kind,
        target_ref: item.target_ref,
        probability_micros: probabilities[index]!,
      })),
      evidence_factors: provisional.evidence_factors,
      attribution_contract_digest: normalizedInput.attribution_contract_digest,
      aggregation_contract_digest: normalizedInput.aggregation_contract_digest,
      calibration_contract_digest: normalizedInput.calibration_contract_digest,
      created_at_event_time: normalizedInput.created_at_event_time,
      previous_revision: normalizedInput.previous_revision,
    });
  } catch (error) {
    if (error instanceof AttributionBeliefContractError) fail("invalid_attribution_calibration_output");
    throw error;
  }
  const normalizedResponse = Object.freeze({
    probabilities: Object.freeze(request.hypotheses.map((item, index) => Object.freeze({
      hypothesis_id: item.hypothesis_id,
      probability_micros: probabilities[index]!,
    }))),
  });
  const receipt = Object.freeze({
    version: ATTRIBUTION_CALIBRATION_RECEIPT_VERSION,
    request_digest: sha256CanonicalRedacted(request as unknown as CanonicalJson),
    response_digest: sha256CanonicalRedacted(normalizedResponse as unknown as CanonicalJson),
    result_digest: sha256CanonicalRedacted(belief as unknown as CanonicalJson),
    calibration_contract_digest: belief.calibration_contract_digest,
    belief_revision_id: belief.belief_revision_id,
  });
  return Object.freeze({ belief, receipt });
};

export const hypothesisIdForCalibrationCandidate = (
  input: Pick<CalibrateAttributionBeliefInput, "owner_account_id" | "belief_kind" | "about_ref">,
  candidate: AttributionHypothesisCandidate,
): string => attributionHypothesisId({
  owner_account_id: input.owner_account_id,
  belief_kind: input.belief_kind,
  about_ref: input.about_ref,
  kind: candidate.kind,
  target_ref: candidate.target_ref,
});
