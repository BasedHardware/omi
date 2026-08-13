import { isProxy } from "node:util/types";

import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import type { RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { DurableMemoryWorkExecutionRepository } from
  "../stores/durable-memory-work-repository";
import type {
  DurableMemoryWorkResultRepository,
  StagedDurableMemoryWorkResult,
} from
  "../stores/durable-memory-work-result-repository";
import type { DurableMemoryWorkSuccessRepository } from
  "../stores/durable-memory-work-success-repository";
import {
  defineDurableMemoryWorkRunner,
  type DurableMemoryWorkRunnerObservability,
  type DurableMemoryWorkMaterializeOutcome,
  type DurableMemoryWorkProduceOutcome,
  type DurableMemoryWorkRunOutcome,
} from "./durable-memory-work-runner";

const ADAPTER_PORT: unique symbol = Symbol("consolidation-work-adapter");
const SERVICE_PORT: unique symbol = Symbol("consolidation-work-service");
const MAX_PARENT_REMATERIALIZATIONS = 10;

export const CONSOLIDATION_WORK_KINDS = Object.freeze([
  "identity_cluster", "predicate_batch", "promotion",
] as const satisfies readonly DurableMemoryWorkKind[]);

export type ConsolidationWorkKind = typeof CONSOLIDATION_WORK_KINDS[number];

export interface ConsolidationWorkAdapter {
  readonly [ADAPTER_PORT]: true;
  readonly work_kind: ConsolidationWorkKind;
  produce(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkProduceOutcome>;
  materialize(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkMaterializeOutcome>;
}

export interface ConsolidationWorkAdapterImplementation {
  readonly produce: ConsolidationWorkAdapter["produce"];
  readonly materialize: ConsolidationWorkAdapter["materialize"];
}

export interface ConsolidationWorkServiceDependencies {
  readonly execution_repository: DurableMemoryWorkExecutionRepository;
  readonly result_repository: DurableMemoryWorkResultRepository;
  readonly success_repository: DurableMemoryWorkSuccessRepository;
  readonly resolve_strategy: (
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<RegisteredMemoryStrategy | null>;
  readonly adapters: Readonly<Record<ConsolidationWorkKind, ConsolidationWorkAdapter>>;
  readonly max_parent_rematerializations: number;
  readonly produce_exclusive?: NonNullable<Parameters<typeof defineDurableMemoryWorkRunner>[0]["produce_exclusive"]>;
  readonly worker_observability?: DurableMemoryWorkRunnerObservability;
}

export type ConsolidationWorkDispatchStopCode =
  | "authorization_or_context"
  | "storage_retryable"
  | "stale_lease"
  | "ineligible_state"
  | "idempotency_conflict";

export type ConsolidationWorkDispatchOutcome =
  | Readonly<{ kind: "idle"; leased: 0; producer_calls: 0; materialization_attempts: 0 }>
  | Readonly<{
      kind: "completed";
      result: "succeeded" | "failure_recorded";
      error_code: DurableMemoryWorkErrorCode | null;
      leased: 1;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>
  | Readonly<{
      kind: "stopped";
      stop_code: ConsolidationWorkDispatchStopCode;
      leased: 0 | 1;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>;

export interface ConsolidationWorkService {
  readonly [SERVICE_PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    leasedJob: Readonly<DurableMemoryWorkJob>,
  ): Promise<DurableMemoryWorkRunOutcome>;
  runNext(context: AuthorizedLedgerWriteContext): Promise<ConsolidationWorkDispatchOutcome>;
}

const adapterIdentities = new WeakSet<object>();
const KIND_SET = new Set<ConsolidationWorkKind>(CONSOLIDATION_WORK_KINDS);

const fail = (code: string): never => {
  throw new TypeError(`consolidation work service ${code}`);
};

const exactRecord = (value: unknown, expected: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const keys = Reflect.ownKeys(value as object);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const callable = <T>(value: unknown, code: string): T => {
  if (typeof value !== "function" || isProxy(value)) fail(code);
  return value as T;
};

const workKind = (value: unknown): ConsolidationWorkKind => {
  if (typeof value !== "string" || !KIND_SET.has(value as ConsolidationWorkKind)) {
    fail("invalid_work_kind");
  }
  return value as ConsolidationWorkKind;
};

export const defineConsolidationWorkAdapter = (
  kindValue: ConsolidationWorkKind,
  implementationValue: ConsolidationWorkAdapterImplementation,
): ConsolidationWorkAdapter => {
  const kind = workKind(kindValue);
  const implementation = exactRecord(
    implementationValue,
    ["produce", "materialize"],
    "invalid_adapter",
  );
  const adapter: ConsolidationWorkAdapter = Object.freeze({
    [ADAPTER_PORT]: true as const,
    work_kind: kind,
    produce: callable<ConsolidationWorkAdapter["produce"]>(
      implementation["produce"], "invalid_adapter",
    ),
    materialize: callable<ConsolidationWorkAdapter["materialize"]>(
      implementation["materialize"], "invalid_adapter",
    ),
  });
  adapterIdentities.add(adapter);
  return adapter;
};

const inspectAdapter = (
  value: unknown,
  expectedKind: ConsolidationWorkKind,
): ConsolidationWorkAdapter => {
  if (value === null || typeof value !== "object" || !adapterIdentities.has(value)) {
    fail("unsealed_adapter");
  }
  const adapter = value as ConsolidationWorkAdapter;
  if (adapter.work_kind !== expectedKind) fail("adapter_kind_mismatch");
  return adapter;
};

const stoppedRun = (
  stop_code: "authorization_or_context" | "ineligible_state" | "storage_retryable",
): DurableMemoryWorkRunOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code,
  producer_calls: 0 as const,
  materialization_attempts: 0,
});

const stoppedDispatch = (
  stop_code: ConsolidationWorkDispatchStopCode,
  leased: 0 | 1,
  producer_calls: 0 | 1 = 0,
  materialization_attempts = 0,
): ConsolidationWorkDispatchOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code,
  leased,
  producer_calls,
  materialization_attempts,
});

const dispatchSummary = (outcome: DurableMemoryWorkRunOutcome): ConsolidationWorkDispatchOutcome => {
  if (outcome.kind === "succeeded") {
    return Object.freeze({
      kind: "completed" as const,
      result: "succeeded" as const,
      error_code: null,
      leased: 1 as const,
      producer_calls: outcome.producer_calls,
      materialization_attempts: outcome.materialization_attempts,
    });
  }
  if (outcome.kind === "failure_recorded") {
    return Object.freeze({
      kind: "completed" as const,
      result: "failure_recorded" as const,
      error_code: outcome.error_code,
      leased: 1 as const,
      producer_calls: outcome.producer_calls,
      materialization_attempts: outcome.materialization_attempts,
    });
  }
  return stoppedDispatch(
    outcome.stop_code,
    1,
    outcome.producer_calls,
    outcome.materialization_attempts,
  );
};

/**
 * The only production-neutral composition for non-formation durable memory
 * work. Semantic adapters remain injected and inert until separately landed.
 */
export const defineConsolidationWorkService = (
  dependenciesValue: ConsolidationWorkServiceDependencies,
): ConsolidationWorkService => {
  const dependencies = exactRecord(dependenciesValue, [
    "execution_repository", "result_repository", "success_repository",
    "resolve_strategy", "adapters", "max_parent_rematerializations",
    ...(Object.prototype.hasOwnProperty.call(dependenciesValue, "worker_observability")
      ? ["worker_observability"] : []),
    ...(Object.prototype.hasOwnProperty.call(dependenciesValue, "produce_exclusive")
      ? ["produce_exclusive"] : []),
  ], "invalid_dependencies");
  const maximum = dependencies["max_parent_rematerializations"];
  if (!Number.isSafeInteger(maximum) || (maximum as number) < 1
    || (maximum as number) > MAX_PARENT_REMATERIALIZATIONS) {
    fail("invalid_parent_retry_bound");
  }
  const adaptersValue = exactRecord(
    dependencies["adapters"],
    CONSOLIDATION_WORK_KINDS,
    "invalid_adapters",
  );
  const adapters = Object.fromEntries(CONSOLIDATION_WORK_KINDS.map((kind) => [
    kind, inspectAdapter(adaptersValue[kind], kind),
  ])) as Record<ConsolidationWorkKind, ConsolidationWorkAdapter>;
  const executionRepository = dependencies["execution_repository"] as DurableMemoryWorkExecutionRepository;
  const resultRepository = dependencies["result_repository"] as DurableMemoryWorkResultRepository;
  const successRepository = dependencies["success_repository"] as DurableMemoryWorkSuccessRepository;
  const resolveStrategy = callable<ConsolidationWorkServiceDependencies["resolve_strategy"]>(
    dependencies["resolve_strategy"], "invalid_strategy_resolver",
  );
  const runners = Object.fromEntries(CONSOLIDATION_WORK_KINDS.map((kind) => {
    const adapter = adapters[kind];
    return [kind, defineDurableMemoryWorkRunner({
      work_repository: executionRepository,
      result_repository: resultRepository,
      success_repository: successRepository,
      resolve_strategy: resolveStrategy,
      produce: adapter.produce,
      ...(dependencies["produce_exclusive"]
        ? { produce_exclusive: callable(
          dependencies["produce_exclusive"], "invalid_producer_exclusivity",
        ) as NonNullable<ConsolidationWorkServiceDependencies["produce_exclusive"]> }
        : {}),
      materialize: adapter.materialize,
      max_parent_rematerializations: maximum as number,
      ...(dependencies["worker_observability"]
        ? { observability: dependencies["worker_observability"] as DurableMemoryWorkRunnerObservability }
        : {}),
    })];
  })) as Record<ConsolidationWorkKind, ReturnType<typeof defineDurableMemoryWorkRunner>>;

  const run = async (
    contextValue: AuthorizedLedgerWriteContext,
    jobValue: Readonly<DurableMemoryWorkJob>,
  ): Promise<DurableMemoryWorkRunOutcome> => {
    let context: AuthorizedLedgerWriteContext;
    let job: Readonly<DurableMemoryWorkJob>;
    try {
      context = assertAuthorizedLedgerWriteContext(contextValue);
      job = parseDurableMemoryWorkJob(jobValue);
    } catch {
      return stoppedRun("authorization_or_context");
    }
    if (context.capability !== "memories.work.execute"
      || context.account_id !== job.owner_account_id
      || context.account_epoch !== job.account_epoch) {
      return stoppedRun("authorization_or_context");
    }
    if (job.state !== "leased" || job.lease === null) {
      return stoppedRun("ineligible_state");
    }
    if (!KIND_SET.has(job.work_kind as ConsolidationWorkKind)) {
      return stoppedRun("ineligible_state");
    }
    try {
      return await runners[job.work_kind as ConsolidationWorkKind].run(context, job);
    } catch {
      return stoppedRun("storage_retryable");
    }
  };

  const service: ConsolidationWorkService = Object.freeze({
    [SERVICE_PORT]: true as const,
    run,
    async runNext(
      contextValue: AuthorizedLedgerWriteContext,
    ): Promise<ConsolidationWorkDispatchOutcome> {
      let context: AuthorizedLedgerWriteContext;
      try {
        context = assertAuthorizedLedgerWriteContext(contextValue);
      } catch {
        return stoppedDispatch("authorization_or_context", 0);
      }
      if (context.capability !== "memories.work.execute") {
        return stoppedDispatch("authorization_or_context", 0);
      }
      let leased: Awaited<ReturnType<DurableMemoryWorkExecutionRepository["leaseNext"]>>;
      try {
        leased = await executionRepository.leaseNext(context, {
          work_kinds: CONSOLIDATION_WORK_KINDS,
        });
      } catch {
        return stoppedDispatch("storage_retryable", 0);
      }
      if (leased.kind === "none_available") {
        return Object.freeze({
          kind: "idle" as const,
          leased: 0 as const,
          producer_calls: 0 as const,
          materialization_attempts: 0,
        });
      }
      if (leased.kind === "serialization_retryable") {
        return stoppedDispatch("storage_retryable", 0);
      }
      if (leased.kind === "stale_context" || leased.kind === "authorization_denied") {
        return stoppedDispatch("authorization_or_context", 0);
      }
      return dispatchSummary(await run(context, leased.job));
    },
  });
  return service;
};
