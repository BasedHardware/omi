import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type {
  FormationWorkIngestionOutcome,
  FormationWorkIngestionRequest,
} from "../../apps/service/workers/formation-work-ingestion";
import {
  defineFormationWorkDispatch,
  type FormationWorkDispatchOutcome,
} from "../../apps/service/workers/formation-work-dispatch";
import {
  defineFormationWorkService,
} from "../../apps/service/workers/formation-work-service";
import type { ModelPort } from "../model/port";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type {
  DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import type {
  DurableMemoryWorkRecoveryOutcome,
} from "../../apps/service/stores/durable-memory-work-repository";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresFormationWorkInputRepository } from "./formation-work-input";
import type { PostgresTransactionObservability } from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-formation-one-shot-runtime");
const MAX_STRATEGIES = 32;

export interface PostgresFormationOneShotRuntimeOptions {
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

export interface PostgresFormationOneShotRuntime {
  readonly [RUNTIME_PORT]: true;
  accept(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkIngestionRequest,
  ): Promise<FormationWorkIngestionOutcome>;
  runNext(context: AuthorizedLedgerWriteContext): Promise<FormationWorkDispatchOutcome>;
  recoverExpired(
    context: AuthorizedLedgerWriteContext,
    job_id: string,
  ): Promise<DurableMemoryWorkRecoveryOutcome>;
}

const strategyRegistry = (
  values: readonly Readonly<RegisteredMemoryStrategy>[],
): ReadonlyMap<string, Readonly<RegisteredMemoryStrategy>> => {
  if (!Array.isArray(values) || values.length === 0 || values.length > MAX_STRATEGIES) {
    throw new TypeError("postgres formation runtime invalid_strategy_registry");
  }
  const byContract = new Map<string, Readonly<RegisteredMemoryStrategy>>();
  for (const value of values) {
    const strategy = parseRegisteredMemoryStrategy(value);
    if (strategy.work_kind !== "formation"
      || byContract.has(strategy.execution_contract_digest)) {
      throw new TypeError("postgres formation runtime invalid_strategy_registry");
    }
    byContract.set(strategy.execution_contract_digest, strategy);
  }
  return byContract;
};

/**
 * Route-free PostgreSQL formation composition.
 *
 * Construction adds no timer, polling loop, application route, credential,
 * model default, or Listen integration. Callers must supply already-issued
 * accept/execute contexts and invoke each bounded operation explicitly.
 */
export const createPostgresFormationOneShotRuntime = (
  options: PostgresFormationOneShotRuntimeOptions,
): PostgresFormationOneShotRuntime => {
  const strategies = strategyRegistry(options.strategies);
  const repositoryOptions = {
    pool: options.pool,
    ...(options.observability ? { observability: options.observability } : {}),
  };
  const acceptanceRepository = createPostgresDurableMemoryWorkAcceptanceRepository(repositoryOptions);
  const executionRepository = createPostgresDurableMemoryWorkExecutionRepository(repositoryOptions);
  const resultRepository = createPostgresDurableMemoryWorkResultRepository(repositoryOptions);
  const successRepository = createPostgresDurableMemoryWorkSuccessRepository(repositoryOptions);
  const inputRepository = createPostgresFormationWorkInputRepository(repositoryOptions);
  const graphRepository = createPostgresAuthoritativeGraphSnapshotRepository(repositoryOptions);
  const service = defineFormationWorkService({
    acceptance_repository: acceptanceRepository,
    execution_repository: executionRepository,
    result_repository: resultRepository,
    success_repository: successRepository,
    input_repository: inputRepository,
    resolve_strategy: async (job) => strategies.get(job.execution_contract_digest) ?? null,
    formation: {
      resolve_model: options.resolve_model,
      load_current_parent: (context) => graphRepository.loadCurrentParent(context),
    },
    max_parent_rematerializations: options.max_parent_rematerializations,
  });
  const dispatch = defineFormationWorkDispatch({
    execution_repository: executionRepository,
    formation: service,
  });

  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    accept: (context: AuthorizedLedgerWriteContext, request: FormationWorkIngestionRequest) =>
      service.accept(context, request),
    runNext: (context: AuthorizedLedgerWriteContext) => dispatch.runNext(context),
    recoverExpired: (
      context: AuthorizedLedgerWriteContext,
      job_id: string,
    ) => executionRepository.recoverExpired(context, { job_id }),
  });
};
