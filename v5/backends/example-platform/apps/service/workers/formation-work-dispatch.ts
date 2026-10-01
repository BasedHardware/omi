import type { DurableMemoryWorkErrorCode } from "../../../core/consolidate/state-machine";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { DurableMemoryWorkExecutionRepository } from "../stores/durable-memory-work-repository";
import type { DurableMemoryWorkRunOutcome } from "./durable-memory-work-runner";
import type { FormationWorkService } from "./formation-work-service";

const DISPATCH_PORT: unique symbol = Symbol("formation-work-dispatch");

type FormationExecutor = Pick<FormationWorkService, "run">;

export interface FormationWorkDispatchDependencies {
  readonly execution_repository: DurableMemoryWorkExecutionRepository;
  readonly formation: FormationExecutor;
}

export type FormationWorkDispatchStopCode =
  | "authorization_or_context"
  | "storage_retryable"
  | "stale_lease"
  | "ineligible_state"
  | "idempotency_conflict";

export type FormationWorkDispatchOutcome =
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
      stop_code: FormationWorkDispatchStopCode;
      leased: 0 | 1;
      producer_calls: 0 | 1;
      materialization_attempts: number;
    }>;

export interface FormationWorkDispatch {
  readonly [DISPATCH_PORT]: true;
  runNext(context: AuthorizedLedgerWriteContext): Promise<FormationWorkDispatchOutcome>;
}

const stopped = (
  stop_code: FormationWorkDispatchStopCode,
  leased: 0 | 1,
  producer_calls: 0 | 1 = 0,
  materialization_attempts = 0,
): FormationWorkDispatchOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code,
  leased,
  producer_calls,
  materialization_attempts,
});

const summarizeRun = (outcome: DurableMemoryWorkRunOutcome): FormationWorkDispatchOutcome => {
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

/** One bounded dispatch step. Runtime scheduling remains outside this port. */
export const defineFormationWorkDispatch = (
  dependencies: FormationWorkDispatchDependencies,
): FormationWorkDispatch => Object.freeze({
  [DISPATCH_PORT]: true as const,
  async runNext(contextValue: AuthorizedLedgerWriteContext): Promise<FormationWorkDispatchOutcome> {
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
        work_kinds: ["formation"],
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
      return summarizeRun(await dependencies.formation.run(context, leased.job));
    } catch {
      return stopped("storage_retryable", 1);
    }
  },
});
