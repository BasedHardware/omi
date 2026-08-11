import { isProxy } from "node:util/types";

import type {
  DurableMemoryWorkErrorCode,
  DurableMemoryWorkJob,
  DurableMemoryWorkResultKind,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalJson } from "../../../core/ledger";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import {
  assertAuthoritativeLedgerAppend,
  type AuthoritativeLedgerAppend,
} from "../stores/authoritative-ledger-repository";
import type {
  DurableMemoryWorkExecutionRepository,
  DurableMemoryWorkFailureOutcome,
} from "../stores/durable-memory-work-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  normalizeDurableMemoryWorkResultJson,
  type DurableMemoryWorkResultRepository,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import {
  durableMemoryWorkSuccessRequestDigest,
  type DurableMemoryWorkSuccessBody,
  type DurableMemoryWorkSuccessOutcome,
  type DurableMemoryWorkSuccessRepository,
} from "../stores/durable-memory-work-success-repository";

const RUNNER_PORT: unique symbol = Symbol("durable-memory-work-runner");
const MAX_PARENT_REBUILDS = 10;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ERROR_CODES = new Set<DurableMemoryWorkErrorCode>([
  "model_timeout", "model_rate_limited", "model_response_invalid",
  "prompt_budget_exceeded", "dependency_unavailable", "serialization_retryable",
  "worker_lost",
]);

export type DurableMemoryWorkProduceOutcome =
  | Readonly<{
      kind: "produced";
      result_contract_version: string;
      response_digest: string;
      normalized_result: Readonly<Record<string, CanonicalJson>>;
    }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export type DurableMemoryWorkMaterializeOutcome =
  | Readonly<{
      kind: "ready";
      result_kind: DurableMemoryWorkResultKind;
      authoritative_append: AuthoritativeLedgerAppend | null;
    }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export interface DurableMemoryWorkRunnerDependencies {
  readonly work_repository: DurableMemoryWorkExecutionRepository;
  readonly result_repository: DurableMemoryWorkResultRepository;
  readonly success_repository: DurableMemoryWorkSuccessRepository;
  readonly resolve_strategy: (
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<RegisteredMemoryStrategy | null>;
  readonly produce: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<DurableMemoryWorkProduceOutcome>;
  readonly materialize: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<DurableMemoryWorkMaterializeOutcome>;
  readonly max_parent_rematerializations: number;
}

export type DurableMemoryWorkRunStopCode =
  | "authorization_or_context"
  | "stale_lease"
  | "ineligible_state"
  | "idempotency_conflict"
  | "storage_retryable";

export type DurableMemoryWorkRunOutcome =
  | Readonly<{
      kind: "succeeded";
      outcome: Extract<DurableMemoryWorkSuccessOutcome, { kind: "committed" | "replayed" }>;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>
  | Readonly<{
      kind: "failure_recorded";
      error_code: DurableMemoryWorkErrorCode;
      outcome: DurableMemoryWorkFailureOutcome;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>
  | Readonly<{
      kind: "stopped";
      stop_code: DurableMemoryWorkRunStopCode;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>;

export interface DurableMemoryWorkRunner {
  readonly [RUNNER_PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    leasedJob: Readonly<DurableMemoryWorkJob>,
  ): Promise<DurableMemoryWorkRunOutcome>;
}

function fail(code: string): never {
  throw new TypeError(`durable memory work runner ${code}`);
}

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const errorCode = (value: unknown): DurableMemoryWorkErrorCode => {
  if (typeof value !== "string" || !ERROR_CODES.has(value as DurableMemoryWorkErrorCode)) {
    fail("invalid_dependency_outcome");
  }
  return value as DurableMemoryWorkErrorCode;
};

const stopCodeFor = (kind: string): DurableMemoryWorkRunStopCode => {
  if (kind === "stale_lease") return "stale_lease";
  if (kind === "ineligible_state") return "ineligible_state";
  if (kind === "idempotency_conflict") return "idempotency_conflict";
  if (kind === "serialization_retryable") return "storage_retryable";
  return "authorization_or_context";
};

const parseProduce = (value: unknown): DurableMemoryWorkProduceOutcome => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependency_outcome");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_dependency_outcome");
  if (kind === "failed") {
    const input = exactRecord(value, ["kind", "error_code"], "invalid_dependency_outcome");
    return Object.freeze({ kind, error_code: errorCode(input["error_code"]) });
  }
  if (kind !== "produced") return fail("invalid_dependency_outcome");
  const input = exactRecord(value, [
    "kind", "result_contract_version", "response_digest", "normalized_result",
  ], "invalid_dependency_outcome");
  if (typeof input["result_contract_version"] !== "string"
    || !TOKEN.test(input["result_contract_version"])
    || typeof input["response_digest"] !== "string"
    || !DIGEST.test(input["response_digest"])) fail("invalid_dependency_outcome");
  return Object.freeze({
    kind,
    result_contract_version: input["result_contract_version"],
    response_digest: input["response_digest"],
    normalized_result: normalizeDurableMemoryWorkResultJson(input["normalized_result"]),
  });
};

const parseMaterialize = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
): DurableMemoryWorkMaterializeOutcome => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependency_outcome");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_dependency_outcome");
  if (kind === "failed") {
    const input = exactRecord(value, ["kind", "error_code"], "invalid_dependency_outcome");
    return Object.freeze({ kind, error_code: errorCode(input["error_code"]) });
  }
  if (kind !== "ready") return fail("invalid_dependency_outcome");
  const input = exactRecord(value, [
    "kind", "result_kind", "authoritative_append",
  ], "invalid_dependency_outcome");
  if (input["result_kind"] !== "successful" && input["result_kind"] !== "successful_empty") {
    fail("invalid_dependency_outcome");
  }
  const authoritativeAppend = input["authoritative_append"] === null
    ? null
    : assertAuthoritativeLedgerAppend(context, input["authoritative_append"]);
  return Object.freeze({
    kind,
    result_kind: input["result_kind"],
    authoritative_append: authoritativeAppend,
  });
};

export const defineDurableMemoryWorkRunner = (
  dependencies: DurableMemoryWorkRunnerDependencies,
): DurableMemoryWorkRunner => {
  if (!Number.isSafeInteger(dependencies.max_parent_rematerializations)
    || dependencies.max_parent_rematerializations < 1
    || dependencies.max_parent_rematerializations > MAX_PARENT_REBUILDS) {
    fail("invalid_parent_retry_bound");
  }

  const recordFailure = async (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    code: DurableMemoryWorkErrorCode,
    producerCalls: 0 | 1,
    materializationAttempts: number,
  ): Promise<DurableMemoryWorkRunOutcome> => {
    const outcome = await dependencies.work_repository.recordFailure(context, {
      job_id: job.job_id,
      lease_fence: job.lease_fence,
      error_code: code,
    });
    if (outcome.kind !== "recorded") {
      return Object.freeze({
        kind: "stopped" as const,
        stop_code: stopCodeFor(outcome.kind),
        producer_calls: producerCalls,
        materialization_attempts: materializationAttempts,
      });
    }
    return Object.freeze({
      kind: "failure_recorded" as const,
      error_code: code,
      outcome,
      producer_calls: producerCalls,
      materialization_attempts: materializationAttempts,
    });
  };

  return Object.freeze({
    [RUNNER_PORT]: true as const,
    async run(
      context: AuthorizedLedgerWriteContext,
      leasedJob: Readonly<DurableMemoryWorkJob>,
    ): Promise<DurableMemoryWorkRunOutcome> {
      let producerCalls: 0 | 1 = 0;
      let materializationAttempts = 0;
      let resolvedStrategy: Readonly<RegisteredMemoryStrategy>;
      try {
        const candidate = await dependencies.resolve_strategy(leasedJob);
        if (candidate === null) {
          return recordFailure(context, leasedJob, "dependency_unavailable", producerCalls, 0);
        }
        resolvedStrategy = parseRegisteredMemoryStrategy(candidate);
      } catch {
        return recordFailure(context, leasedJob, "dependency_unavailable", producerCalls, 0);
      }
      if (resolvedStrategy.work_kind !== leasedJob.work_kind
        || resolvedStrategy.execution_contract_digest !== leasedJob.execution_contract_digest) {
        return recordFailure(context, leasedJob, "dependency_unavailable", producerCalls, 0);
      }
      const loaded = await dependencies.result_repository.load(context, { leased_job: leasedJob });
      let staged: StagedDurableMemoryWorkResult;
      if (loaded.kind === "found") {
        staged = loaded.result;
      } else if (loaded.kind === "missing") {
        producerCalls = 1;
        let rawProduced: unknown;
        try {
          rawProduced = await dependencies.produce(context, leasedJob, resolvedStrategy);
        } catch {
          return recordFailure(context, leasedJob, "dependency_unavailable", producerCalls, 0);
        }
        let produced: DurableMemoryWorkProduceOutcome;
        try {
          produced = parseProduce(rawProduced);
        } catch {
          return recordFailure(
            context, leasedJob, "model_response_invalid", producerCalls, 0,
          );
        }
        if (produced.kind === "failed") {
          return recordFailure(context, leasedJob, produced.error_code, producerCalls, 0);
        }
        if (produced.result_contract_version !== resolvedStrategy.coordinates.result_contract_version) {
          return recordFailure(context, leasedJob, "model_response_invalid", producerCalls, 0);
        }
        const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
          produced.result_contract_version,
          produced.normalized_result,
        );
        const stageBody = {
          leased_job: leasedJob,
          result_contract_version: produced.result_contract_version,
          response_digest: produced.response_digest,
          normalized_result_digest: normalizedResultDigest,
          normalized_result: produced.normalized_result,
        };
        const stagedOutcome = await dependencies.result_repository.stage(context, {
          ...stageBody,
          request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
        });
        if (stagedOutcome.kind !== "staged" && stagedOutcome.kind !== "replayed") {
          return Object.freeze({
            kind: "stopped" as const,
            stop_code: stopCodeFor(stagedOutcome.kind),
            producer_calls: producerCalls,
            materialization_attempts: 0,
          });
        }
        staged = stagedOutcome.result;
      } else {
        return Object.freeze({
          kind: "stopped" as const,
          stop_code: stopCodeFor(loaded.kind),
          producer_calls: producerCalls,
          materialization_attempts: 0,
        });
      }

      if (staged.result_contract_version !== resolvedStrategy.coordinates.result_contract_version) {
        return recordFailure(context, leasedJob, "model_response_invalid", producerCalls, 0);
      }

      for (let attempt = 0; attempt < dependencies.max_parent_rematerializations; attempt += 1) {
        materializationAttempts += 1;
        let rawMaterialized: unknown;
        try {
          rawMaterialized = await dependencies.materialize(
            context, leasedJob, staged, resolvedStrategy,
          );
        } catch {
          return recordFailure(
            context, leasedJob, "dependency_unavailable", producerCalls, materializationAttempts,
          );
        }
        let materialized: DurableMemoryWorkMaterializeOutcome;
        try {
          materialized = parseMaterialize(rawMaterialized, context);
        } catch {
          return recordFailure(
            context, leasedJob, "model_response_invalid", producerCalls, materializationAttempts,
          );
        }
        if (materialized.kind === "failed") {
          return recordFailure(
            context, leasedJob, materialized.error_code, producerCalls, materializationAttempts,
          );
        }
        const resultDigest = materialized.authoritative_append?.append_attempt.request_digest
          ?? staged.normalized_result_digest;
        const successBody: DurableMemoryWorkSuccessBody = {
          leased_job: leasedJob,
          result_kind: materialized.result_kind,
          response_digest: staged.response_digest,
          result_digest: resultDigest,
          staged_result: staged,
          authoritative_append: materialized.authoritative_append,
        };
        const outcome = await dependencies.success_repository.commit(context, {
          ...successBody,
          request_digest: durableMemoryWorkSuccessRequestDigest(successBody),
        });
        if (outcome.kind === "committed" || outcome.kind === "replayed") {
          return Object.freeze({
            kind: "succeeded" as const,
            outcome,
            producer_calls: producerCalls,
            materialization_attempts: materializationAttempts,
          });
        }
        if (outcome.kind !== "stale_parent") {
          return Object.freeze({
            kind: "stopped" as const,
            stop_code: stopCodeFor(outcome.kind),
            producer_calls: producerCalls,
            materialization_attempts: materializationAttempts,
          });
        }
      }
      return recordFailure(
        context, leasedJob, "serialization_retryable", producerCalls, materializationAttempts,
      );
    },
  });
};
