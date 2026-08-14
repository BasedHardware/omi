import type { DurableMemoryWorkErrorCode } from "../../../core/consolidate/state-machine";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { DurableMemoryWorkExecutionRepository } from "../stores/durable-memory-work-repository";
import type { DurableMemoryWorkRunOutcome } from "./durable-memory-work-runner";
import type { ConsolidationWorkService } from "./consolidation-work-service";

const DISPATCH_PORT: unique symbol = Symbol("derived-group-dream-work-dispatch");

type DerivedGroupDreamExecutor = Pick<ConsolidationWorkService, "run">;

export interface DerivedGroupDreamWorkDispatchDependencies {
  readonly execution_repository: DurableMemoryWorkExecutionRepository;
  readonly derived_group_dream: DerivedGroupDreamExecutor;
}

export type DerivedGroupDreamWorkDispatchStopCode =
  | "authorization_or_context"
  | "storage_retryable"
  | "stale_lease"
  | "ineligible_state"
  | "idempotency_conflict";

export type DerivedGroupDreamWorkDispatchOutcome =
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
      stop_code: DerivedGroupDreamWorkDispatchStopCode;
      leased: 0 | 1;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>;

export interface DerivedGroupDreamWorkDispatch {
  readonly [DISPATCH_PORT]: true;
  runNext(context: AuthorizedLedgerWriteContext): Promise<DerivedGroupDreamWorkDispatchOutcome>;
}

const stopped = (
  stop_code: DerivedGroupDreamWorkDispatchStopCode,
  leased: 0 | 1,
  producer_calls: 0 | 1 = 0,
  materialization_attempts = 0,
): DerivedGroupDreamWorkDispatchOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code,
  leased,
  producer_calls,
  materialization_attempts,
});

const summarizeRun = (outcome: DurableMemoryWorkRunOutcome): DerivedGroupDreamWorkDispatchOutcome => {
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
  return stopped(
    outcome.stop_code,
    1,
    outcome.producer_calls,
    outcome.materialization_attempts,
  );
};

/**
 * One bounded dream-only dispatch step.
 *
 * The lease filter names `derived_group_dream` alone, so this port can never
 * consume another kind's backlog. It adds no timer, poll loop, or scheduler:
 * runtime scheduling stays outside this port.
 */
export const defineDerivedGroupDreamWorkDispatch = (
  dependencies: DerivedGroupDreamWorkDispatchDependencies,
): DerivedGroupDreamWorkDispatch => Object.freeze({
  [DISPATCH_PORT]: true as const,
  async runNext(contextValue: AuthorizedLedgerWriteContext): Promise<DerivedGroupDreamWorkDispatchOutcome> {
    let context: AuthorizedLedgerWriteContext;
    try {
      context = assertAuthorizedLedgerWriteContext(contextValue);
    } catch {
      return stopped("authorization_or_context", 0);
    }
    if (context.capability !== "memories.work.execute") {
      return stopped("authorization_or_context", 0);
    }
    let leased: Awaited<ReturnType<DurableMemoryWorkExecutionRepository["leaseNext"]>>;
    try {
      leased = await dependencies.execution_repository.leaseNext(context, {
        work_kinds: ["derived_group_dream"],
      });
    } catch {
      return stopped("storage_retryable", 0);
    }
    if (leased.kind === "none_available") {
      return Object.freeze({
        kind: "idle" as const,
        leased: 0 as const,
        producer_calls: 0 as const,
        materialization_attempts: 0,
      });
    }
    if (leased.kind === "serialization_retryable") return stopped("storage_retryable", 0);
    if (leased.kind === "stale_context" || leased.kind === "authorization_denied") {
      return stopped("authorization_or_context", 0);
    }
    try {
      return summarizeRun(await dependencies.derived_group_dream.run(context, leased.job));
    } catch {
      return stopped("storage_retryable", 1);
    }
  },
});
