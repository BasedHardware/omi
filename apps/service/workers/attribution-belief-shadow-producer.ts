import { isProxy } from "node:util/types";

import {
  AttributionCalibrationError,
  calibrateAttributionBelief,
  type AttributionCalibratorPort,
  type CalibrateAttributionBeliefInput,
} from "../../../core/consolidate/attribution-calibration";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  normalizeDurableMemoryWorkResultJson,
  type NormalizedDurableMemoryWorkResultJson,
} from "../stores/durable-memory-work-result-repository";
import type {
  OfflineMemoryEvaluationProduceOutcome,
  OfflineMemoryReplayProducerRequest,
} from "./memory-offline-replay-coordinator";

export const ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION =
  "attribution-belief-shadow-input-v1" as const;
export const ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION =
  "attribution-belief-shadow-result-v1" as const;

export interface AttributionBeliefShadowProducerDependencies {
  readonly resolve_calibrator: (
    strategy: Readonly<RegisteredMemoryStrategy>,
    evaluationRole: "baseline" | "candidate",
  ) => Promise<AttributionCalibratorPort | null>;
}

export type AttributionBeliefShadowProducer = (
  request: OfflineMemoryReplayProducerRequest,
  lossSignal?: AbortSignal,
) => Promise<OfflineMemoryEvaluationProduceOutcome>;

const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;

const fail = (code: string): never => {
  throw new TypeError(`attribution belief shadow producer ${code}`);
};

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string")) fail(code);
  const actualStrings = (actual as string[]).sort();
  const expected = [...keys].sort();
  if (actualStrings.length !== expected.length
    || actualStrings.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actualStrings) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const exactDependencies = (
  value: unknown,
): ((
  strategy: Readonly<RegisteredMemoryStrategy>,
  role: "baseline" | "candidate",
) => Promise<AttributionCalibratorPort | null>) => {
  const row = exactRecord(value, ["resolve_calibrator"], "invalid_dependencies");
  const resolver = row["resolve_calibrator"];
  if (typeof resolver !== "function" || isProxy(resolver)) fail("invalid_dependencies");
  return resolver.bind(value) as (
    strategy: Readonly<RegisteredMemoryStrategy>,
    role: "baseline" | "candidate",
  ) => Promise<AttributionCalibratorPort | null>;
};

const exactCalibrator = (value: unknown): AttributionCalibratorPort => {
  const row = exactRecord(value, ["calibrate"], "invalid_calibrator");
  const calibrate = row["calibrate"];
  if (typeof calibrate !== "function" || isProxy(calibrate)) fail("invalid_calibrator");
  return Object.freeze({ calibrate: calibrate.bind(value) });
};

const parseRequest = (value: unknown): Readonly<{
  copied_input: Readonly<{
    owner_account_id: string;
    input_frontier: string;
    payload: NormalizedDurableMemoryWorkResultJson;
  }>;
  strategy: Readonly<RegisteredMemoryStrategy>;
  evaluation_role: "baseline" | "candidate";
}> => {
  const row = exactRecord(value, [
    "copied_input", "strategy", "evaluation_role", "repeat_ordinal",
  ], "invalid_request");
  const copiedRow = exactRecord(row["copied_input"], [
    "version", "owner_account_id", "account_epoch", "source_kind", "source_ref_digest",
    "input_frontier", "input_digest", "payload",
  ], "invalid_copied_input");
  if (copiedRow["version"] !== "copied-memory-evaluation-input-v2"
    || (copiedRow["source_kind"] !== "formation_input_snapshot"
      && copiedRow["source_kind"] !== "authorized_graph_snapshot")
    || !Number.isSafeInteger(copiedRow["account_epoch"])
    || (copiedRow["account_epoch"] as number) < 0) fail("invalid_copied_input");
  const owner = token(copiedRow["owner_account_id"], "invalid_copied_input");
  const sourceRefDigest = digest(copiedRow["source_ref_digest"], "invalid_copied_input");
  const inputFrontier = digest(copiedRow["input_frontier"], "invalid_copied_input");
  const inputDigest = digest(copiedRow["input_digest"], "invalid_copied_input");
  const payload = normalizeDurableMemoryWorkResultJson(copiedRow["payload"]);
  const expectedInputDigest = sha256CanonicalContent({
    contract_version: "copied-memory-evaluation-input-v2",
    owner_account_id: owner,
    account_epoch: copiedRow["account_epoch"] as number,
    source_kind: copiedRow["source_kind"] as "formation_input_snapshot" | "authorized_graph_snapshot",
    source_ref_digest: sourceRefDigest,
    input_frontier: inputFrontier,
    payload,
  });
  if (inputDigest !== expectedInputDigest) fail("copied_input_digest_mismatch");
  const strategy = parseRegisteredMemoryStrategy(row["strategy"]);
  if (strategy.work_kind !== "identity_cluster"
    || strategy.coordinates.result_contract_version !== ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION) {
    fail("ineligible_strategy");
  }
  if (row["evaluation_role"] !== "baseline" && row["evaluation_role"] !== "candidate") {
    fail("invalid_request");
  }
  if (!Number.isSafeInteger(row["repeat_ordinal"])
    || (row["repeat_ordinal"] as number) < 0 || (row["repeat_ordinal"] as number) >= 20) {
    fail("invalid_request");
  }
  return Object.freeze({
    copied_input: Object.freeze({ owner_account_id: owner, input_frontier: inputFrontier, payload }),
    strategy,
    evaluation_role: row["evaluation_role"] as "baseline" | "candidate",
  });
};

const beliefInput = (
  payload: NormalizedDurableMemoryWorkResultJson,
  ownerAccountId: string,
  inputFrontier: string,
  calibrationContractDigest: string,
): CalibrateAttributionBeliefInput => {
  const row = exactRecord(payload, [
    "version", "owner_account_id", "belief_kind", "about_ref", "observation_ref",
    "observation_content_digest", "graph_frontier", "hypothesis_candidates",
    "evidence_factors", "attribution_contract_digest", "aggregation_contract_digest",
    "created_at_event_time", "previous_revision",
  ], "invalid_payload");
  if (row["version"] !== ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION
    || row["owner_account_id"] !== ownerAccountId
    || row["graph_frontier"] !== inputFrontier) fail("payload_coordinate_mismatch");
  return Object.freeze({
    owner_account_id: row["owner_account_id"] as string,
    belief_kind: row["belief_kind"] as CalibrateAttributionBeliefInput["belief_kind"],
    about_ref: row["about_ref"] as string,
    observation_ref: row["observation_ref"] as string,
    observation_content_digest: row["observation_content_digest"] as string,
    graph_frontier: row["graph_frontier"] as string,
    hypothesis_candidates: row["hypothesis_candidates"] as CalibrateAttributionBeliefInput["hypothesis_candidates"],
    evidence_factors: row["evidence_factors"] as CalibrateAttributionBeliefInput["evidence_factors"],
    attribution_contract_digest: row["attribution_contract_digest"] as string,
    aggregation_contract_digest: row["aggregation_contract_digest"] as string,
    calibration_contract_digest: calibrationContractDigest,
    created_at_event_time: row["created_at_event_time"] as number,
    previous_revision: row["previous_revision"] as CalibrateAttributionBeliefInput["previous_revision"],
  });
};

const failed = (error_code: "dependency_unavailable" | "model_response_invalid") =>
  Object.freeze({ kind: "failed" as const, error_code });

export const defineAttributionBeliefShadowProducer = (
  dependenciesValue: AttributionBeliefShadowProducerDependencies,
): AttributionBeliefShadowProducer => {
  const resolveCalibrator = exactDependencies(dependenciesValue);
  return async (requestValue, lossSignal): Promise<OfflineMemoryEvaluationProduceOutcome> => {
    let request: ReturnType<typeof parseRequest>;
    let input: CalibrateAttributionBeliefInput;
    try {
      request = parseRequest(requestValue);
      input = beliefInput(
        request.copied_input.payload,
        request.copied_input.owner_account_id,
        request.copied_input.input_frontier,
        request.strategy.execution_contract_digest,
      );
    } catch {
      return failed("dependency_unavailable");
    }

    let calibrator: AttributionCalibratorPort;
    try {
      const resolved = await resolveCalibrator(request.strategy, request.evaluation_role);
      if (resolved === null) return failed("dependency_unavailable");
      calibrator = exactCalibrator(resolved);
    } catch {
      return failed("dependency_unavailable");
    }

    try {
      const calibrated = await calibrateAttributionBelief(input, calibrator, lossSignal);
      return Object.freeze({
        kind: "produced" as const,
        result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
        response_digest: calibrated.receipt.response_digest,
        normalized_result: normalizeDurableMemoryWorkResultJson({
          version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
          belief: calibrated.belief,
          calibration_receipt: calibrated.receipt,
        }),
      });
    } catch (error) {
      if (error instanceof AttributionCalibrationError
        && error.code === "invalid_attribution_calibration_output") {
        return failed("model_response_invalid");
      }
      return failed("dependency_unavailable");
    }
  };
};
