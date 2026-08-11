import { isProxy } from "node:util/types";

import type {
  DurableMemoryWorkErrorCode,
} from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type MemoryStrategyAssignmentEntry,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalJson } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkNormalizedResultDigest,
  normalizeDurableMemoryWorkResultJson,
  type NormalizedDurableMemoryWorkResultJson,
} from "../stores/durable-memory-work-result-repository";
import {
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationCoordinate,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageBody,
  type MemoryShadowResultRepository,
} from "../stores/memory-shadow-result-repository";

const COORDINATOR_PORT: unique symbol = Symbol("memory-offline-replay-coordinator");
const CAPABILITY = "memories.experiments.shadow";
const MAX_REPEATS = 20;
const RUN_ID = /^mer1_[a-f0-9]{64}$/;
const copiedInputs = new WeakSet<object>();
const ERROR_CODES = new Set<DurableMemoryWorkErrorCode>([
  "model_timeout", "model_rate_limited", "model_response_invalid",
  "prompt_budget_exceeded", "dependency_unavailable", "serialization_retryable",
  "worker_lost",
]);

export interface CopiedMemoryEvaluationInput {
  readonly version: "copied-memory-evaluation-input-v1";
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly payload: NormalizedDurableMemoryWorkResultJson;
}

export type OfflineMemoryEvaluationProduceOutcome =
  | Readonly<{
      kind: "produced";
      result_contract_version: string;
      response_digest: string;
      normalized_result: Readonly<Record<string, CanonicalJson>>;
    }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export interface OfflineMemoryReplayProducerRequest {
  readonly copied_input: Readonly<CopiedMemoryEvaluationInput>;
  readonly strategy: Readonly<RegisteredMemoryStrategy>;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly repeat_ordinal: number;
}

export interface OfflineMemoryReplayRequest {
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly evaluation_run_id: string;
  readonly copied_input: Readonly<CopiedMemoryEvaluationInput>;
  readonly repeats: number;
}

export type OfflineMemoryReplayStopCode =
  | "authorization_or_context"
  | "storage_retryable"
  | "idempotency_conflict"
  | "producer_failed"
  | "invalid_result";

export type OfflineMemoryReplayOutcome =
  | Readonly<{
      kind: "completed";
      pairs: readonly Readonly<MemoryEvaluationPair>[];
      model_calls: number;
      reused_results: number;
    }>
  | Readonly<{
      kind: "stopped";
      stop_code: OfflineMemoryReplayStopCode;
      failure_code: DurableMemoryWorkErrorCode | null;
      pairs: readonly Readonly<MemoryEvaluationPair>[];
      model_calls: number;
      reused_results: number;
    }>;

export interface MemoryOfflineReplayCoordinator {
  readonly [COORDINATOR_PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    request: OfflineMemoryReplayRequest,
  ): Promise<OfflineMemoryReplayOutcome>;
}

export interface MemoryOfflineReplayDependencies {
  readonly result_repository: MemoryShadowResultRepository;
  readonly produce: (
    request: OfflineMemoryReplayProducerRequest,
  ) => Promise<OfflineMemoryEvaluationProduceOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`memory offline replay ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(code);
  const objectValue = value as object;
  if (isProxy(objectValue) || Object.getPrototypeOf(objectValue) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || value.length < 1 || value.length > 256
    || !/^[\x21-\x7e]+$/.test(value)) fail(code);
  return value as string;
};

const frozenPairs = (
  pairs: readonly Readonly<MemoryEvaluationPair>[],
): readonly Readonly<MemoryEvaluationPair>[] => Object.freeze([...pairs]);

export const copyMemoryEvaluationInput = (
  inputFrontierValue: string,
  payloadValue: unknown,
): Readonly<CopiedMemoryEvaluationInput> => {
  const inputFrontier = token(inputFrontierValue, "invalid_copied_input");
  const payload = normalizeDurableMemoryWorkResultJson(payloadValue);
  const inputDigest = sha256CanonicalContent({
    contract_version: "copied-memory-evaluation-input-v1",
    payload,
  });
  const copied = Object.freeze({
    version: "copied-memory-evaluation-input-v1" as const,
    input_frontier: inputFrontier,
    input_digest: inputDigest,
    payload,
  });
  copiedInputs.add(copied);
  return copied;
};

const assertCopiedInput = (value: unknown): Readonly<CopiedMemoryEvaluationInput> => {
  if (value === null || typeof value !== "object" || !copiedInputs.has(value)) {
    fail("unverified_copied_input");
  }
  return value as Readonly<CopiedMemoryEvaluationInput>;
};

const strategyFor = (
  bundle: Readonly<MemoryStrategyAssignmentBundle>,
  assignment: Readonly<MemoryStrategyAssignmentEntry>,
): Readonly<RegisteredMemoryStrategy> => bundle.strategies.find(
  (strategy) => strategy.strategy_id === assignment.strategy_id
    && strategy.execution_contract_digest === assignment.execution_contract_digest,
) ?? fail("assignment_strategy_missing");

const parseProduced = (value: unknown): OfflineMemoryEvaluationProduceOutcome => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_producer_outcome");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_producer_outcome");
  if (kind === "failed") {
    const input = exactRecord(value, ["kind", "error_code"], "invalid_producer_outcome");
    if (typeof input["error_code"] !== "string"
      || !ERROR_CODES.has(input["error_code"] as DurableMemoryWorkErrorCode)) {
      fail("invalid_producer_outcome");
    }
    return Object.freeze({
      kind,
      error_code: input["error_code"] as DurableMemoryWorkErrorCode,
    });
  }
  if (kind !== "produced") fail("invalid_producer_outcome");
  const input = exactRecord(value, [
    "kind", "result_contract_version", "response_digest", "normalized_result",
  ], "invalid_producer_outcome");
  return Object.freeze({
    kind,
    result_contract_version: input["result_contract_version"] as string,
    response_digest: input["response_digest"] as string,
    normalized_result: input["normalized_result"] as Readonly<Record<string, CanonicalJson>>,
  });
};

const coordinateFor = (
  bundle: Readonly<MemoryStrategyAssignmentBundle>,
  assignment: Readonly<MemoryStrategyAssignmentEntry>,
  accountEpoch: number,
  role: MemoryEvaluationRole,
  evaluationRunId: string,
  copied: Readonly<CopiedMemoryEvaluationInput>,
  repeatOrdinal: number,
): MemoryEvaluationCoordinate => ({
  assignment_bundle: bundle,
  assignment_id: assignment.assignment_id,
  account_epoch: accountEpoch,
  evaluation_role: role,
  evaluation_mode: "offline_replay",
  evaluation_run_id: evaluationRunId,
  input_frontier: copied.input_frontier,
  input_digest: copied.input_digest,
  repeat_ordinal: repeatOrdinal,
});

const stopCodeForRepository = (kind: string): OfflineMemoryReplayStopCode => {
  if (kind === "serialization_retryable") return "storage_retryable";
  if (kind === "idempotency_conflict") return "idempotency_conflict";
  return "authorization_or_context";
};

export const defineMemoryOfflineReplayCoordinator = (
  dependencies: MemoryOfflineReplayDependencies,
): MemoryOfflineReplayCoordinator => Object.freeze({
  [COORDINATOR_PORT]: true as const,
  async run(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: OfflineMemoryReplayRequest,
  ): Promise<OfflineMemoryReplayOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== CAPABILITY) fail("capability_denied");
    const request = exactRecord(requestValue, [
      "assignment_bundle", "evaluation_run_id", "copied_input", "repeats",
    ], "invalid_request");
    const bundle = assertMintedMemoryStrategyAssignment(request["assignment_bundle"]);
    if (bundle.owner_account_id !== context.account_id) fail("owner_mismatch");
    if (bundle.shadows.length === 0) fail("no_selected_shadow");
    const evaluationRunId = token(request["evaluation_run_id"], "invalid_request");
    if (!RUN_ID.test(evaluationRunId)) fail("invalid_request");
    const copied = assertCopiedInput(request["copied_input"]);
    const repeats = request["repeats"];
    if (!Number.isSafeInteger(repeats) || (repeats as number) < 1 || (repeats as number) > MAX_REPEATS) {
      fail("invalid_repeats");
    }

    let modelCalls = 0;
    let reusedResults = 0;
    const pairs: Readonly<MemoryEvaluationPair>[] = [];
    const stopped = (
      stopCode: OfflineMemoryReplayStopCode,
      failureCode: DurableMemoryWorkErrorCode | null = null,
    ): OfflineMemoryReplayOutcome => Object.freeze({
      kind: "stopped" as const,
      stop_code: stopCode,
      failure_code: failureCode,
      pairs: frozenPairs(pairs),
      model_calls: modelCalls,
      reused_results: reusedResults,
    });

    const loadOrProduce = async (
      assignment: Readonly<MemoryStrategyAssignmentEntry>,
      role: MemoryEvaluationRole,
      repeatOrdinal: number,
    ): Promise<Readonly<MemoryEvaluationResult> | OfflineMemoryReplayOutcome> => {
      const strategy = strategyFor(bundle, assignment);
      const coordinate = coordinateFor(
        bundle, assignment, context.account_epoch, role, evaluationRunId, copied, repeatOrdinal,
      );
      const loaded = await dependencies.result_repository.load(context, coordinate);
      if (loaded.kind === "found") {
        reusedResults += 1;
        return loaded.result;
      }
      if (loaded.kind !== "missing") return stopped(stopCodeForRepository(loaded.kind));

      modelCalls += 1;
      let rawProduced: unknown;
      try {
        rawProduced = await dependencies.produce(Object.freeze({
          copied_input: copied,
          strategy,
          evaluation_role: role,
          repeat_ordinal: repeatOrdinal,
        }));
      } catch {
        return stopped("producer_failed", "dependency_unavailable");
      }
      let produced: OfflineMemoryEvaluationProduceOutcome;
      try {
        produced = parseProduced(rawProduced);
      } catch {
        return stopped("invalid_result");
      }
      if (produced.kind === "failed") return stopped("producer_failed", produced.error_code);
      if (produced.result_contract_version !== strategy.coordinates.result_contract_version) {
        return stopped("invalid_result");
      }

      let body: MemoryEvaluationStageBody;
      try {
        const resultDigest = durableMemoryWorkNormalizedResultDigest(
          produced.result_contract_version,
          produced.normalized_result,
        );
        body = {
          ...coordinate,
          result_contract_version: produced.result_contract_version,
          response_digest: produced.response_digest,
          normalized_result_digest: resultDigest,
          normalized_result: produced.normalized_result,
        };
        memoryEvaluationStageRequestDigest(context, body);
      } catch {
        return stopped("invalid_result");
      }
      const staged = await dependencies.result_repository.stage(context, {
        ...body,
        request_digest: memoryEvaluationStageRequestDigest(context, body),
      });
      if (staged.kind !== "staged" && staged.kind !== "replayed") {
        return stopped(stopCodeForRepository(staged.kind));
      }
      return staged.result;
    };

    for (let repeatOrdinal = 0; repeatOrdinal < (repeats as number); repeatOrdinal += 1) {
      const baseline = await loadOrProduce(bundle.authority, "baseline", repeatOrdinal);
      if ("kind" in baseline && baseline.kind === "stopped") return baseline;
      for (const shadow of bundle.shadows) {
        const candidate = await loadOrProduce(shadow, "candidate", repeatOrdinal);
        if ("kind" in candidate && candidate.kind === "stopped") return candidate;
        const pair = pairMemoryEvaluationResults(
          baseline as Readonly<MemoryEvaluationResult>,
          candidate as Readonly<MemoryEvaluationResult>,
        );
        const recorded = await dependencies.result_repository.recordPair(context, pair);
        if (recorded.kind !== "recorded" && recorded.kind !== "replayed") {
          return stopped(stopCodeForRepository(recorded.kind));
        }
        pairs.push(recorded.pair);
      }
    }
    return Object.freeze({
      kind: "completed" as const,
      pairs: frozenPairs(pairs),
      model_calls: modelCalls,
      reused_results: reusedResults,
    });
  },
});
