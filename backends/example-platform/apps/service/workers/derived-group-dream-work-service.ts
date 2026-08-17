import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import type { RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { DurableMemoryWorkExecutionRepository } from "../stores/durable-memory-work-repository";
import type { DurableMemoryWorkResultRepository } from "../stores/durable-memory-work-result-repository";
import type { DurableMemoryWorkSuccessRepository } from "../stores/durable-memory-work-success-repository";
import {
  defineDurableMemoryWorkRunner,
  type DurableMemoryWorkRunnerObservability,
  type DurableMemoryWorkRunOutcome,
} from "./durable-memory-work-runner";
import type { DerivedGroupDreamWorkInputRepository } from "./derived-group-dream-work-input-repository";
import {
  defineDerivedGroupDreamWorkAdapter,
  type DerivedGroupDreamWorkAdapterDependencies,
} from "./derived-group-dream-work-producer";

const SERVICE_PORT: unique symbol = Symbol("derived-group-dream-work-service");

export interface DerivedGroupDreamWorkServiceDependencies {
  readonly execution_repository: DurableMemoryWorkExecutionRepository;
  readonly result_repository: DurableMemoryWorkResultRepository;
  readonly success_repository: DurableMemoryWorkSuccessRepository;
  readonly input_repository: DerivedGroupDreamWorkInputRepository;
  readonly resolve_strategy: (
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<RegisteredMemoryStrategy | null>;
  readonly dream: Omit<DerivedGroupDreamWorkAdapterDependencies, "load_input">;
  readonly produce_exclusive?: NonNullable<Parameters<typeof defineDurableMemoryWorkRunner>[0]["produce_exclusive"]>;
  readonly max_parent_rematerializations: number;
  readonly worker_observability?: DurableMemoryWorkRunnerObservability;
}

export interface DerivedGroupDreamWorkService {
  readonly [SERVICE_PORT]: true;
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
 * The single production-neutral composition for derived-group dream work.
 *
 * It exposes no scheduler, route, database connection, model default, or
 * success commit. Runtime composition must inject PostgreSQL repositories and
 * scheduler wiring separately after their gates.
 */
export const defineDerivedGroupDreamWorkService = (
  dependencies: DerivedGroupDreamWorkServiceDependencies,
): DerivedGroupDreamWorkService => {
  const adapter = defineDerivedGroupDreamWorkAdapter({
    ...dependencies.dream,
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
    [SERVICE_PORT]: true as const,
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
      if (job.work_kind !== "derived_group_dream") {
        return Promise.resolve(stopped("ineligible_state"));
      }
      return runner.run(context, job);
    },
  });
};
