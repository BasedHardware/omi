import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type {
  PredicateBatchSchedulingOutcome,
  PredicateBatchWorkSchedulingRequest,
} from "../../apps/service/workers/predicate-batch-work-scheduler";
import { definePredicateBatchWorkScheduler } from "../../apps/service/workers/predicate-batch-work-scheduler";
import {
  defineConsolidationWorkAdapter,
  defineConsolidationWorkService,
  type ConsolidationWorkAdapter,
  type ConsolidationWorkKind,
} from "../../apps/service/workers/consolidation-work-service";
import {
  definePredicateBatchConsolidationWorkAdapter,
} from "../../apps/service/workers/predicate-batch-work-adapter";
import {
  definePredicateBatchWorkDispatch,
  type PredicateBatchWorkDispatchOutcome,
} from "../../apps/service/workers/predicate-batch-work-dispatch";
import type { DurableMemoryWorkRecoveryOutcome } from
  "../../apps/service/stores/durable-memory-work-repository";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type { DurableMemoryWorkJob } from "../../core/consolidate/state-machine";
import type { ModelPort } from "../model/port";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresPredicateBatchWorkInputRepository } from "./predicate-batch-work-input";
import type { PostgresTransactionObservability } from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-predicate-batch-one-shot-runtime");
const MAX_STRATEGIES = 32;

export interface PostgresPredicateBatchOneShotRuntimeOptions {
  readonly pool: PostgresTransactionPool;
  readonly strategies: readonly Readonly<RegisteredMemoryStrategy>[];
  readonly resolve_model: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<ModelPort | null>;
  readonly max_parent_rematerializations: number;
  readonly observability?: PostgresTransactionObservability;
}

export interface PostgresPredicateBatchOneShotRuntime {
  readonly [RUNTIME_PORT]: true;
  schedule(
    context: AuthorizedLedgerWriteContext,
    request: PredicateBatchWorkSchedulingRequest,
  ): Promise<PredicateBatchSchedulingOutcome>;
  runNext(context: AuthorizedLedgerWriteContext): Promise<PredicateBatchWorkDispatchOutcome>;
  recoverExpired(
    context: AuthorizedLedgerWriteContext,
    job_id: string,
  ): Promise<DurableMemoryWorkRecoveryOutcome>;
}

const strategyRegistry = (
  values: readonly Readonly<RegisteredMemoryStrategy>[],
): ReadonlyMap<string, Readonly<RegisteredMemoryStrategy>> => {
  if (!Array.isArray(values) || values.length === 0 || values.length > MAX_STRATEGIES) {
    throw new TypeError("postgres predicate runtime invalid_strategy_registry");
  }
  const byContract = new Map<string, Readonly<RegisteredMemoryStrategy>>();
  for (const value of values) {
    const strategy = parseRegisteredMemoryStrategy(value);
    if (strategy.work_kind !== "predicate_batch"
      || byContract.has(strategy.execution_contract_digest)) {
      throw new TypeError("postgres predicate runtime invalid_strategy_registry");
    }
    byContract.set(strategy.execution_contract_digest, strategy);
  }
  return byContract;
};

const unsupportedAdapter = (kind: Exclude<ConsolidationWorkKind, "predicate_batch">): ConsolidationWorkAdapter =>
  defineConsolidationWorkAdapter(kind, {
    produce: async () => Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const }),
    materialize: async () => Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const }),
  });

/**
 * Route-free PostgreSQL predicate-batch composition.
 *
 * Construction adds no timer, polling loop, route, credential, model default,
 * identity worker, promotion worker, or activation. Every public call is one
 * explicitly invoked bounded operation under a separately issued context.
 */
export const createPostgresPredicateBatchOneShotRuntime = (
  options: PostgresPredicateBatchOneShotRuntimeOptions,
): PostgresPredicateBatchOneShotRuntime => {
  const strategies = strategyRegistry(options.strategies);
  const repositoryOptions = {
    pool: options.pool,
    ...(options.observability ? { observability: options.observability } : {}),
  };
  const acceptanceRepository = createPostgresDurableMemoryWorkAcceptanceRepository(repositoryOptions);
  const executionRepository = createPostgresDurableMemoryWorkExecutionRepository(repositoryOptions);
  const resultRepository = createPostgresDurableMemoryWorkResultRepository(repositoryOptions);
  const successRepository = createPostgresDurableMemoryWorkSuccessRepository(repositoryOptions);
  const inputRepository = createPostgresPredicateBatchWorkInputRepository(repositoryOptions);
  const graphRepository = createPostgresAuthoritativeGraphSnapshotRepository(repositoryOptions);
  const predicateAdapter = definePredicateBatchConsolidationWorkAdapter({
    load_input: async (context, job) => {
      const loaded = await inputRepository.load(context, job);
      if (loaded.kind === "found" || loaded.kind === "not_found") return loaded;
      if (loaded.kind === "serialization_retryable") {
        return Object.freeze({ kind: "failed" as const, error_code: "serialization_retryable" as const });
      }
      return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
    },
    resolve_model: options.resolve_model,
    load_current_parent: (context) => graphRepository.loadCurrentParent(context),
  });
  const service = defineConsolidationWorkService({
    execution_repository: executionRepository,
    result_repository: resultRepository,
    success_repository: successRepository,
    resolve_strategy: async (job) => strategies.get(job.execution_contract_digest) ?? null,
    adapters: {
      identity_cluster: unsupportedAdapter("identity_cluster"),
      predicate_batch: predicateAdapter,
      promotion: unsupportedAdapter("promotion"),
    },
    max_parent_rematerializations: options.max_parent_rematerializations,
    ...(options.observability ? { worker_observability: options.observability } : {}),
  });
  const scheduler = definePredicateBatchWorkScheduler(acceptanceRepository, inputRepository);
  const dispatch = definePredicateBatchWorkDispatch({
    execution_repository: executionRepository,
    predicate_batch: service,
  });

  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    schedule: (context, request) => scheduler.schedule(context, request),
    runNext: (context) => dispatch.runNext(context),
    recoverExpired: async (context, job_id) => {
      const loaded = await executionRepository.load(context, { job_id });
      if (loaded.kind !== "found") {
        if (loaded.kind === "not_found") return Object.freeze({ kind: "ineligible_state" as const });
        return loaded;
      }
      if (loaded.job.work_kind !== "predicate_batch") {
        return Object.freeze({ kind: "ineligible_state" as const });
      }
      return executionRepository.recoverExpired(context, { job_id });
    },
  });
};
