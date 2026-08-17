import {
  acceptDurableMemoryWork,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  parseDurableMemoryWorkJob,
  succeedDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  defineDurableMemoryWorkAcceptanceRepository,
  defineDurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkAcceptanceRepository,
  type DurableMemoryWorkExecutionRepository,
} from "./durable-memory-work-repository";
import {
  defineDurableMemoryWorkResultRepository,
  materializeStagedDurableMemoryWorkResult,
  type DurableMemoryWorkResultRepository,
  type StagedDurableMemoryWorkResult,
} from "./durable-memory-work-result-repository";
import {
  defineDurableMemoryWorkSuccessRepository,
  durableMemoryWorkSuccessOutboxId,
  type DurableMemoryWorkSuccessRepository,
} from "./durable-memory-work-success-repository";
import {
  defineFormationWorkInputRepository,
  materializeStagedFormationWorkInput,
  type FormationWorkInputRepository,
  type StagedFormationWorkInput,
} from "../workers/formation-work-input-repository";
import type { SqliteLedger } from "../../../drivers/sqlite";
import {
  GraphHeadConflictError,
  IdempotencyConflictError,
} from "../../../drivers/sqlite";

export interface InMemoryDurableMemoryWorkStores {
  readonly acceptance: DurableMemoryWorkAcceptanceRepository;
  readonly execution: DurableMemoryWorkExecutionRepository;
  readonly results: DurableMemoryWorkResultRepository;
  readonly success: DurableMemoryWorkSuccessRepository;
  readonly formationInput: FormationWorkInputRepository;
}

export const createInMemoryDurableMemoryWorkStores = (
  ledger: SqliteLedger,
  leaseDurationSeconds: number,
): InMemoryDurableMemoryWorkStores => {
  const jobs = new Map<string, DurableMemoryWorkJob>();
  const inputs = new Map<string, StagedFormationWorkInput>();
  const stagedResults = new Map<string, StagedDurableMemoryWorkResult>();
  const committedSuccess = new Map<string, {
    readonly job: DurableMemoryWorkJob;
    readonly commit_id: string | null;
    readonly sequence: number | null;
    readonly outbox_id: string;
  }>();

  const acceptance = defineDurableMemoryWorkAcceptanceRepository(async (_context, request) => {
    const existing = jobs.get(request.pending_job.job_id);
    if (existing !== undefined) {
      if (existing.accepted_work_digest !== request.pending_job.accepted_work_digest) {
        return { kind: "idempotency_conflict" as const };
      }
      return { kind: "replayed" as const, job: existing };
    }
    jobs.set(request.pending_job.job_id, request.pending_job);
    return { kind: "accepted" as const, job: request.pending_job };
  });

  const execution = defineDurableMemoryWorkExecutionRepository({
    async leaseNext(context, request) {
      const eligible = [...jobs.values()]
        .filter((job) => job.state === "pending" && request.work_kinds.includes(job.work_kind)
          && job.owner_account_id === context.account_id)
        .sort((left, right) => left.job_id < right.job_id ? -1 : left.job_id > right.job_id ? 1 : 0);
      const next = eligible[0];
      if (next === undefined) return { kind: "none_available" as const };
      const leased = leaseDurableMemoryWork(
        next,
        context.principal_id,
        Math.max(next.accepted_at_event_time, context.issued_at_epoch_seconds),
        leaseDurationSeconds,
      );
      jobs.set(leased.job_id, leased);
      return { kind: "leased" as const, job: leased };
    },
    async load(context, request) {
      const job = jobs.get(request.job_id);
      if (job === undefined || job.owner_account_id !== context.account_id) {
        return { kind: "not_found" as const };
      }
      return { kind: "found" as const, job };
    },
    async recordFailure(_context, request) {
      const job = jobs.get(request.job_id);
      if (job === undefined || job.state !== "leased" || job.lease === null) {
        return { kind: "ineligible_state" as const };
      }
      if (job.lease.fence !== request.lease_fence) return { kind: "stale_lease" as const };
      const at = job.lease.leased_at_event_time + 1;
      const failed = failDurableMemoryWork(
        job,
        { worker_id: job.lease.worker_id, fence: job.lease.fence },
        at,
        request.error_code,
        job.attempt >= job.max_attempts ? null : at + 1,
      );
      jobs.set(failed.job_id, failed);
      return { kind: "recorded" as const, job: failed };
    },
    async recoverExpired() {
      return { kind: "not_expired" as const };
    },
  });

  const results = defineDurableMemoryWorkResultRepository({
    async load(_context, request) {
      const staged = stagedResults.get(request.leased_job.job_id);
      if (staged === undefined) return { kind: "missing" as const };
      return { kind: "found" as const, result: staged };
    },
    async stage(_context, request) {
      const existing = stagedResults.get(request.leased_job.job_id);
      const materialized = materializeStagedDurableMemoryWorkResult(request);
      if (existing !== undefined) {
        return { kind: "replayed" as const, result: existing };
      }
      stagedResults.set(request.leased_job.job_id, materialized);
      return { kind: "staged" as const, result: materialized };
    },
  });

  const success = defineDurableMemoryWorkSuccessRepository(async (_context, request) => {
    const prior = committedSuccess.get(request.leased_job.job_id);
    if (prior !== undefined) {
      return {
        kind: "replayed" as const,
        job: prior.job,
        commit_id: prior.commit_id,
        sequence: prior.sequence,
        outbox_id: prior.outbox_id,
      };
    }
    const lease = request.leased_job.lease;
    if (lease === null) return { kind: "ineligible_state" as const };
    let commitId: string | null = null;
    let sequence: number | null = null;
    if (request.authoritative_append !== null) {
      try {
        const appended = ledger.append(request.authoritative_append.transition);
        commitId = appended.commit_id;
        sequence = appended.sequence;
      } catch (error) {
        if (error instanceof GraphHeadConflictError) return { kind: "stale_parent" as const };
        if (error instanceof IdempotencyConflictError) return { kind: "idempotency_conflict" as const };
        throw error;
      }
    }
    const succeeded = succeedDurableMemoryWork(
      request.leased_job,
      { worker_id: lease.worker_id, fence: lease.fence },
      lease.leased_at_event_time + 1,
      request.result_kind,
      request.response_digest,
      request.result_digest,
    );
    jobs.set(succeeded.job_id, succeeded);
    const outboxId = durableMemoryWorkSuccessOutboxId(request);
    const recorded = {
      job: succeeded,
      commit_id: commitId,
      sequence,
      outbox_id: outboxId,
    };
    committedSuccess.set(succeeded.job_id, recorded);
    return { kind: "committed" as const, ...recorded };
  });

  const formationInput = defineFormationWorkInputRepository({
    async stage(_context, request) {
      const existing = inputs.get(request.pending_job.job_id);
      const materialized = materializeStagedFormationWorkInput(request);
      if (existing !== undefined) {
        return { kind: "replayed" as const, input: existing };
      }
      inputs.set(request.pending_job.job_id, materialized);
      return { kind: "staged" as const, input: materialized };
    },
    async load(_context, job) {
      const staged = inputs.get(parseDurableMemoryWorkJob(job).job_id);
      if (staged === undefined) return { kind: "not_found" as const };
      return { kind: "found" as const, input: staged };
    },
  });

  return Object.freeze({
    acceptance,
    execution,
    results,
    success,
    formationInput,
  });
};
