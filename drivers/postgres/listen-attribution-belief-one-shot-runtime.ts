import { isProxy } from "node:util/types";

import type { AttributionCalibratorPort } from
  "../../core/consolidate/attribution-calibration";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type RegisteredMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type { AuthorizedLedgerWriteContext } from
  "../../apps/service/auth/authorized-context";
import {
  defineListenAttributionBeliefEvaluationSource,
} from "../../apps/service/listen/attribution-belief-input-source";
import {
  defineAttributionBeliefShadowProducer,
} from "../../apps/service/workers/attribution-belief-shadow-producer";
import {
  defineMemoryOfflineReplayCoordinator,
  type OfflineMemoryReplayOutcome,
} from "../../apps/service/workers/memory-offline-replay-coordinator";
import type { PostgresTransactionPool } from "./connection";
import {
  createPostgresListenAttributionBeliefInputRepository,
} from "./listen-attribution-belief-input";
import { createPostgresMemoryShadowResultRepository } from
  "./memory-experiment-repository";
import type { PostgresTransactionObservability } from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-listen-attribution-belief-one-shot-runtime");
const INPUT_REF = /^labinput1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const RUN_ID = /^mer1_[a-f0-9]{64}$/;

export interface PostgresListenAttributionBeliefOneShotOptions {
  readonly pool: PostgresTransactionPool;
  readonly resolve_calibrator: (
    strategy: Readonly<RegisteredMemoryStrategy>,
    evaluationRole: "baseline" | "candidate",
  ) => Promise<AttributionCalibratorPort | null>;
  readonly observability?: PostgresTransactionObservability;
}

export interface PostgresListenAttributionBeliefOneShotRequest {
  readonly input_ref: string;
  readonly input_frontier: string;
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly evaluation_run_id: string;
  readonly repeats: number;
}

export type PostgresListenAttributionBeliefOneShotOutcome = OfflineMemoryReplayOutcome
  | Readonly<{
      kind: "source_stopped";
      stop_code: "not_found" | "source_unavailable" | "authorization_or_context" | "storage_retryable";
    }>;

export interface PostgresListenAttributionBeliefOneShotRuntime {
  readonly [RUNTIME_PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    request: PostgresListenAttributionBeliefOneShotRequest,
  ): Promise<PostgresListenAttributionBeliefOneShotOutcome>;
}

const fail = (code: string): never => {
  throw new TypeError(`postgres Listen attribution belief runtime ${code}`);
};

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

const options = (value: unknown): Readonly<{
  pool: PostgresTransactionPool;
  resolve_calibrator: PostgresListenAttributionBeliefOneShotOptions["resolve_calibrator"];
  observability?: PostgresTransactionObservability;
}> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_options");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const row = exactRecord(value, [
    "pool", "resolve_calibrator", ...(descriptors["observability"] ? ["observability"] : []),
  ], "invalid_options");
  const pool = row["pool"] as PostgresTransactionPool;
  const withTransaction = pool?.withTransaction;
  const resolver = row["resolve_calibrator"];
  if (typeof withTransaction !== "function" || isProxy(withTransaction)
    || typeof resolver !== "function" || isProxy(resolver)) fail("invalid_options");
  const result = {
    pool: Object.freeze({
      withTransaction: <Result>(
        transactionOptions: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: Parameters<PostgresTransactionPool["withTransaction"]>[1],
      ): Promise<Result> => withTransaction.call(
        pool, transactionOptions, callback,
      ) as Promise<Result>,
    }) as PostgresTransactionPool,
    resolve_calibrator: (resolver as PostgresListenAttributionBeliefOneShotOptions["resolve_calibrator"])
      .bind(value),
    ...(row["observability"] === undefined
      ? {} : { observability: row["observability"] as PostgresTransactionObservability }),
  };
  return Object.freeze(result);
};

const request = (value: unknown): Readonly<PostgresListenAttributionBeliefOneShotRequest> => {
  const row = exactRecord(value, [
    "input_ref", "input_frontier", "assignment_bundle", "evaluation_run_id", "repeats",
  ], "invalid_request");
  if (typeof row["input_ref"] !== "string" || !INPUT_REF.test(row["input_ref"])
    || typeof row["input_frontier"] !== "string" || !DIGEST.test(row["input_frontier"])
    || typeof row["evaluation_run_id"] !== "string" || !RUN_ID.test(row["evaluation_run_id"])
    || !Number.isSafeInteger(row["repeats"]) || (row["repeats"] as number) < 1
    || (row["repeats"] as number) > 20) fail("invalid_request");
  return Object.freeze({
    input_ref: row["input_ref"],
    input_frontier: row["input_frontier"],
    assignment_bundle: assertMintedMemoryStrategyAssignment(row["assignment_bundle"]),
    evaluation_run_id: row["evaluation_run_id"],
    repeats: row["repeats"],
  } as PostgresListenAttributionBeliefOneShotRequest);
};

const sourceStop = (
  kind: string,
): PostgresListenAttributionBeliefOneShotOutcome => Object.freeze({
  kind: "source_stopped" as const,
  stop_code: kind === "not_found" ? "not_found" as const
    : kind === "serialization_retryable" ? "storage_retryable" as const
      : kind === "source_unavailable" ? "source_unavailable" as const
        : "authorization_or_context" as const,
});

/**
 * Route-free, timer-free, explicitly invoked paired attribution evaluation.
 * Construction selects no calibrator, model, threshold, worker credential, or
 * production behavior; those remain injected by the caller.
 */
export const createPostgresListenAttributionBeliefOneShotRuntime = (
  optionsValue: PostgresListenAttributionBeliefOneShotOptions,
): PostgresListenAttributionBeliefOneShotRuntime => {
  const configured = options(optionsValue);
  const repositoryOptions = {
    pool: configured.pool,
    ...(configured.observability ? { observability: configured.observability } : {}),
  };
  const source = defineListenAttributionBeliefEvaluationSource(
    createPostgresListenAttributionBeliefInputRepository(repositoryOptions),
  );
  const coordinator = defineMemoryOfflineReplayCoordinator({
    result_repository: createPostgresMemoryShadowResultRepository(repositoryOptions),
    produce: defineAttributionBeliefShadowProducer({
      resolve_calibrator: configured.resolve_calibrator,
    }),
  });
  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async run(
      context: AuthorizedLedgerWriteContext,
      requestValue: PostgresListenAttributionBeliefOneShotRequest,
    ) {
      const normalized = request(requestValue);
      const loaded = await source.load(context, {
        source_kind: "formation_input_snapshot",
        source_ref: normalized.input_ref,
        input_frontier: normalized.input_frontier,
      });
      if (loaded.kind !== "found") return sourceStop(loaded.kind);
      return coordinator.run(context, {
        assignment_bundle: normalized.assignment_bundle,
        evaluation_run_id: normalized.evaluation_run_id,
        copied_input: loaded.copied_input,
        repeats: normalized.repeats,
      });
    },
  });
};
