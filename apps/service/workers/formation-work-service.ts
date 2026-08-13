import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import type { RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type {
  DurableMemoryWorkAcceptanceRepository,
  DurableMemoryWorkExecutionRepository,
} from "../stores/durable-memory-work-repository";
import type { DurableMemoryWorkResultRepository } from "../stores/durable-memory-work-result-repository";
import type { DurableMemoryWorkSuccessRepository } from "../stores/durable-memory-work-success-repository";
import {
  defineDurableMemoryWorkRunner,
  type DurableMemoryWorkRunnerObservability,
  type DurableMemoryWorkRunOutcome,
} from "./durable-memory-work-runner";
import {
  defineFormationWorkAdapter,
  type FormationWorkAdapterDependencies,
} from "./formation-work-producer";
import type { FormationWorkInputRepository } from "./formation-work-input-repository";
import {
  defineFormationWorkIngestion,
  type FormationWorkIngestionOutcome,
  type FormationWorkIngestionRequest,
} from "./formation-work-ingestion";

const FORMATION_SERVICE_PORT: unique symbol = Symbol("formation-work-service");

export interface FormationWorkServiceDependencies {
  readonly acceptance_repository: DurableMemoryWorkAcceptanceRepository;
  readonly execution_repository: DurableMemoryWorkExecutionRepository;
  readonly result_repository: DurableMemoryWorkResultRepository;
  readonly success_repository: DurableMemoryWorkSuccessRepository;
  readonly input_repository: FormationWorkInputRepository;
  readonly resolve_strategy: (
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<RegisteredMemoryStrategy | null>;
  readonly formation: Omit<FormationWorkAdapterDependencies, "load_input">;
  readonly produce_exclusive?: NonNullable<Parameters<typeof defineDurableMemoryWorkRunner>[0]["produce_exclusive"]>;
  readonly max_parent_rematerializations: number;
  readonly worker_observability?: DurableMemoryWorkRunnerObservability;
}

export interface FormationWorkService {
  readonly [FORMATION_SERVICE_PORT]: true;
  accept(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkIngestionRequest,
  ): Promise<FormationWorkIngestionOutcome>;
  run(
    context: AuthorizedLedgerWriteContext,
    leasedJob: Readonly<DurableMemoryWorkJob>,
  ): Promise<DurableMemoryWorkRunOutcome>;
}

const stopped = (
  stop_code: "authorization_or_context" | "ineligible_state",
): DurableMemoryWorkRunOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code,
  producer_calls: 0 as const,
  materialization_attempts: 0,
});

/**
 * The single production-neutral composition for formation work.
 *
 * It exposes no scheduler, route, database connection, authority issuer, or
 * worker grant. Runtime composition must inject those separately after their
 * gates. The work-kind fence is intentionally outside the generic runner so a
 * formation executor can never record a failure against another work kind.
 */
export const defineFormationWorkService = (
  dependencies: FormationWorkServiceDependencies,
): FormationWorkService => {
  const ingestion = defineFormationWorkIngestion(
    dependencies.acceptance_repository,
    dependencies.input_repository,
  );
  const adapter = defineFormationWorkAdapter({
    ...dependencies.formation,
    load_input: async (context, job) => dependencies.input_repository.load(context, job),
  });
  const runner = defineDurableMemoryWorkRunner({
    work_repository: dependencies.execution_repository,
    result_repository: dependencies.result_repository,
    success_repository: dependencies.success_repository,
    resolve_strategy: dependencies.resolve_strategy,
    produce: adapter.produce,
    ...(dependencies.produce_exclusive ? { produce_exclusive: dependencies.produce_exclusive } : {}),
    materialize: adapter.materialize,
    max_parent_rematerializations: dependencies.max_parent_rematerializations,
    ...(dependencies.worker_observability
      ? { observability: dependencies.worker_observability }
      : {}),
  });

  return Object.freeze({
    [FORMATION_SERVICE_PORT]: true as const,
    accept(
      context: AuthorizedLedgerWriteContext,
      request: FormationWorkIngestionRequest,
    ): Promise<FormationWorkIngestionOutcome> {
      return ingestion.accept(context, request);
    },
    run(
      contextValue: AuthorizedLedgerWriteContext,
      jobValue: Readonly<DurableMemoryWorkJob>,
    ): Promise<DurableMemoryWorkRunOutcome> {
      let context: AuthorizedLedgerWriteContext;
      let job: Readonly<DurableMemoryWorkJob>;
      try {
        context = assertAuthorizedLedgerWriteContext(contextValue);
        job = parseDurableMemoryWorkJob(jobValue);
      } catch {
        return Promise.resolve(stopped("authorization_or_context"));
      }
      if (context.capability !== "memories.work.execute"
        || context.account_id !== job.owner_account_id
        || context.account_epoch !== job.account_epoch) {
        return Promise.resolve(stopped("authorization_or_context"));
      }
      if (job.work_kind !== "formation") {
        return Promise.resolve(stopped("ineligible_state"));
      }
      return runner.run(context, job);
    },
  });
};
