import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

export const DURABLE_MEMORY_WORK_VERSION = "durable-memory-work-v1" as const;

export type DurableMemoryWorkKind =
  | "formation"
  | "promotion"
  | "identity_cluster"
  | "predicate_batch"
  | "derived_group_dream";

export type DurableMemoryWorkErrorCode =
  | "model_timeout"
  | "model_rate_limited"
  | "model_response_invalid"
  | "prompt_budget_exceeded"
  | "dependency_unavailable"
  | "serialization_retryable"
  | "worker_lost";

export type DurableMemoryWorkResultKind = "successful" | "successful_empty";
export type DurableMemoryWorkState =
  | "pending"
  | "leased"
  | "retryable_failed"
  | "succeeded"
  | "dead_letter";

export interface AcceptedDurableMemoryWork {
  readonly version: typeof DURABLE_MEMORY_WORK_VERSION;
  readonly job_id: string;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly lifecycle_state: "active";
  readonly deletion_epoch: null;
  readonly work_kind: DurableMemoryWorkKind;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly accepted_at_event_time: number;
  readonly max_attempts: number;
}

export interface DurableMemoryWorkLease {
  readonly worker_id: string;
  readonly fence: number;
  readonly leased_at_event_time: number;
  readonly expires_at_event_time: number;
}

export type DurableMemoryWorkOutcome =
  | Readonly<{
    kind: "retryable_error";
    error_code: DurableMemoryWorkErrorCode;
    failed_at_event_time: number;
    next_eligible_event_time: number;
  }>
  | Readonly<{
    kind: "succeeded";
    result_kind: DurableMemoryWorkResultKind;
    response_digest: string;
    result_digest: string;
    succeeded_at_event_time: number;
  }>
  | Readonly<{
    kind: "dead_letter";
    error_code: DurableMemoryWorkErrorCode;
    attempts: number;
    failed_at_event_time: number;
  }>;

export interface DurableMemoryWorkJob extends AcceptedDurableMemoryWork {
  readonly accepted_work_digest: string;
  readonly state: DurableMemoryWorkState;
  readonly attempt: number;
  readonly lease_fence: number;
  readonly lease: Readonly<DurableMemoryWorkLease> | null;
  readonly outcome: DurableMemoryWorkOutcome | null;
}

export interface DurableMemoryWorkLeaseRef {
  readonly worker_id: string;
  readonly fence: number;
}

export type DurableMemoryWorkTransitionErrorCode =
  | "invalid_job"
  | "ineligible_state"
  | "not_yet_eligible"
  | "expired_lease_requires_recovery"
  | "attempt_budget_exhausted"
  | "stale_lease"
  | "invalid_transition";

export class DurableMemoryWorkTransitionError extends Error {
  constructor(readonly code: DurableMemoryWorkTransitionErrorCode) {
    super(code);
    this.name = "DurableMemoryWorkTransitionError";
  }
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const MAX_ATTEMPTS = 100;
const WORK_KINDS = new Set<DurableMemoryWorkKind>([
  "formation", "promotion", "identity_cluster", "predicate_batch", "derived_group_dream",
]);
const ERROR_CODES = new Set<DurableMemoryWorkErrorCode>([
  "model_timeout", "model_rate_limited", "model_response_invalid",
  "prompt_budget_exceeded", "dependency_unavailable",
  "serialization_retryable", "worker_lost",
]);
const RESULT_KINDS = new Set<DurableMemoryWorkResultKind>(["successful", "successful_empty"]);
const STATES = new Set<DurableMemoryWorkState>([
  "pending", "leased", "retryable_failed", "succeeded", "dead_letter",
]);

const failShape = (): never => { throw new DurableMemoryWorkTransitionError("invalid_job"); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) return failShape();
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.some((key) => typeof key !== "string")) failShape();
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) failShape();
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) failShape();
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) return failShape();
  return value;
};

const digest = (value: unknown): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) return failShape();
  return value;
};

const nonnegative = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) failShape();
  return value as number;
};

const positive = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) failShape();
  return value as number;
};

const boundedAttempts = (value: unknown): number => {
  const attempts = positive(value);
  if (attempts > MAX_ATTEMPTS) return failShape();
  return attempts;
};

const safeAdd = (left: number, right: number): number => {
  const value = left + right;
  if (!Number.isSafeInteger(value)) throw new DurableMemoryWorkTransitionError("invalid_transition");
  return value;
};

const acceptedFields = (value: unknown): AcceptedDurableMemoryWork => {
  const input = exactRecord(value, [
    "version", "job_id", "owner_account_id", "account_epoch", "lifecycle_state",
    "deletion_epoch", "work_kind", "input_frontier", "input_digest",
    "execution_contract_digest", "accepted_at_event_time", "max_attempts",
  ]);
  if (input["version"] !== DURABLE_MEMORY_WORK_VERSION
    || input["lifecycle_state"] !== "active" || input["deletion_epoch"] !== null
    || typeof input["work_kind"] !== "string"
    || !WORK_KINDS.has(input["work_kind"] as DurableMemoryWorkKind)) failShape();
  return Object.freeze({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: token(input["job_id"]),
    owner_account_id: token(input["owner_account_id"]),
    account_epoch: nonnegative(input["account_epoch"]),
    lifecycle_state: "active" as const,
    deletion_epoch: null,
    work_kind: input["work_kind"] as DurableMemoryWorkKind,
    input_frontier: token(input["input_frontier"]),
    input_digest: digest(input["input_digest"]),
    execution_contract_digest: digest(input["execution_contract_digest"]),
    accepted_at_event_time: nonnegative(input["accepted_at_event_time"]),
    max_attempts: boundedAttempts(input["max_attempts"]),
  });
};

export const acceptedDurableMemoryWorkDigest = (input: AcceptedDurableMemoryWork): string => {
  const accepted = acceptedFields(input);
  return createHash("sha256").update(JSON.stringify({
    version: accepted.version,
    job_id: accepted.job_id,
    owner_account_id: accepted.owner_account_id,
    account_epoch: accepted.account_epoch,
    lifecycle_state: accepted.lifecycle_state,
    deletion_epoch: accepted.deletion_epoch,
    work_kind: accepted.work_kind,
    input_frontier: accepted.input_frontier,
    input_digest: accepted.input_digest,
    execution_contract_digest: accepted.execution_contract_digest,
    accepted_at_event_time: accepted.accepted_at_event_time,
    max_attempts: accepted.max_attempts,
  })).digest("hex");
};

const leaseFields = (value: unknown): Readonly<DurableMemoryWorkLease> => {
  const input = exactRecord(value, [
    "worker_id", "fence", "leased_at_event_time", "expires_at_event_time",
  ]);
  const leasedAt = nonnegative(input["leased_at_event_time"]);
  const expiresAt = positive(input["expires_at_event_time"]);
  if (expiresAt <= leasedAt) failShape();
  return Object.freeze({
    worker_id: token(input["worker_id"]),
    fence: positive(input["fence"]),
    leased_at_event_time: leasedAt,
    expires_at_event_time: expiresAt,
  });
};

const outcomeFields = (value: unknown): DurableMemoryWorkOutcome => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) return failShape();
  const kind = Object.getOwnPropertyDescriptor(value, "kind");
  const kindValue = kind && "value" in kind && kind.enumerable ? kind.value : failShape();
  if (kindValue === "retryable_error") {
    const input = exactRecord(value, ["kind", "error_code", "failed_at_event_time", "next_eligible_event_time"]);
    if (typeof input["error_code"] !== "string"
      || !ERROR_CODES.has(input["error_code"] as DurableMemoryWorkErrorCode)) failShape();
    const failedAt = nonnegative(input["failed_at_event_time"]);
    const nextEligible = nonnegative(input["next_eligible_event_time"]);
    if (nextEligible <= failedAt) failShape();
    return Object.freeze({
      kind: "retryable_error" as const,
      error_code: input["error_code"] as DurableMemoryWorkErrorCode,
      failed_at_event_time: failedAt,
      next_eligible_event_time: nextEligible,
    });
  }
  if (kindValue === "succeeded") {
    const input = exactRecord(value, ["kind", "result_kind", "response_digest", "result_digest", "succeeded_at_event_time"]);
    if (typeof input["result_kind"] !== "string"
      || !RESULT_KINDS.has(input["result_kind"] as DurableMemoryWorkResultKind)) failShape();
    return Object.freeze({
      kind: "succeeded" as const,
      result_kind: input["result_kind"] as DurableMemoryWorkResultKind,
      response_digest: digest(input["response_digest"]),
      result_digest: digest(input["result_digest"]),
      succeeded_at_event_time: nonnegative(input["succeeded_at_event_time"]),
    });
  }
  if (kindValue === "dead_letter") {
    const input = exactRecord(value, ["kind", "error_code", "attempts", "failed_at_event_time"]);
    if (typeof input["error_code"] !== "string"
      || !ERROR_CODES.has(input["error_code"] as DurableMemoryWorkErrorCode)) failShape();
    return Object.freeze({
      kind: "dead_letter" as const,
      error_code: input["error_code"] as DurableMemoryWorkErrorCode,
      attempts: positive(input["attempts"]),
      failed_at_event_time: nonnegative(input["failed_at_event_time"]),
    });
  }
  return failShape();
};

const JOB_KEYS = [
  "version", "job_id", "owner_account_id", "account_epoch", "lifecycle_state",
  "deletion_epoch", "work_kind", "input_frontier", "input_digest",
  "execution_contract_digest", "accepted_at_event_time", "max_attempts",
  "accepted_work_digest", "state", "attempt", "lease_fence", "lease", "outcome",
] as const;

export const parseDurableMemoryWorkJob = (value: unknown): Readonly<DurableMemoryWorkJob> => {
  const input = exactRecord(value, JOB_KEYS);
  const accepted = acceptedFields(Object.fromEntries([
    "version", "job_id", "owner_account_id", "account_epoch", "lifecycle_state",
    "deletion_epoch", "work_kind", "input_frontier", "input_digest",
    "execution_contract_digest", "accepted_at_event_time", "max_attempts",
  ].map((key) => [key, input[key]])));
  const acceptedDigest = digest(input["accepted_work_digest"]);
  if (acceptedDigest !== acceptedDurableMemoryWorkDigest(accepted)) failShape();
  if (typeof input["state"] !== "string" || !STATES.has(input["state"] as DurableMemoryWorkState)) failShape();
  const state = input["state"] as DurableMemoryWorkState;
  const attempt = nonnegative(input["attempt"]);
  const leaseFence = nonnegative(input["lease_fence"]);
  if (attempt > accepted.max_attempts || leaseFence !== attempt) failShape();
  const lease = input["lease"] === null ? null : leaseFields(input["lease"]);
  const outcome = input["outcome"] === null ? null : outcomeFields(input["outcome"]);

  if (state === "pending" && (attempt !== 0 || lease !== null || outcome !== null)) failShape();
  if (state === "leased" && (attempt < 1 || lease === null || outcome !== null
    || lease.fence !== leaseFence || lease.leased_at_event_time < accepted.accepted_at_event_time)) failShape();
  if (state === "retryable_failed" && (attempt < 1 || attempt >= accepted.max_attempts
    || lease !== null || outcome?.kind !== "retryable_error"
    || outcome.failed_at_event_time < accepted.accepted_at_event_time)) failShape();
  if (state === "succeeded" && (attempt < 1 || lease !== null || outcome?.kind !== "succeeded"
    || outcome.succeeded_at_event_time < accepted.accepted_at_event_time)) failShape();
  if (state === "dead_letter" && (attempt < 1 || attempt !== accepted.max_attempts
    || lease !== null || outcome?.kind !== "dead_letter" || outcome.attempts !== attempt
    || outcome.failed_at_event_time < accepted.accepted_at_event_time)) failShape();

  return Object.freeze({
    ...accepted,
    accepted_work_digest: acceptedDigest,
    state,
    attempt,
    lease_fence: leaseFence,
    lease,
    outcome,
  });
};

/** Stable CAS/content coordinate for one fully validated persisted state. */
export const durableMemoryWorkStateDigest = (value: DurableMemoryWorkJob): string =>
  createHash("sha256").update(JSON.stringify(parseDurableMemoryWorkJob(value))).digest("hex");

export const acceptDurableMemoryWork = (input: AcceptedDurableMemoryWork): Readonly<DurableMemoryWorkJob> => {
  const accepted = acceptedFields(input);
  return parseDurableMemoryWorkJob({
    ...accepted,
    accepted_work_digest: acceptedDurableMemoryWorkDigest(accepted),
    state: "pending",
    attempt: 0,
    lease_fence: 0,
    lease: null,
    outcome: null,
  });
};

const eventTime = (value: number): number => {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new DurableMemoryWorkTransitionError("invalid_transition");
  }
  return value;
};

const leaseRef = (value: DurableMemoryWorkLeaseRef): Readonly<DurableMemoryWorkLeaseRef> => {
  const input = exactRecord(value, ["worker_id", "fence"]);
  return Object.freeze({ worker_id: token(input["worker_id"]), fence: positive(input["fence"]) });
};

export const ownsDurableMemoryWorkLease = (
  value: DurableMemoryWorkJob,
  suppliedLease: DurableMemoryWorkLeaseRef,
  atEventTime: number,
): boolean => {
  const job = parseDurableMemoryWorkJob(value);
  const reference = leaseRef(suppliedLease);
  const at = eventTime(atEventTime);
  return job.state === "leased" && job.lease !== null
    && job.lease.worker_id === reference.worker_id
    && job.lease.fence === reference.fence
    && at >= job.lease.leased_at_event_time
    && at < job.lease.expires_at_event_time;
};

export const leaseDurableMemoryWork = (
  value: DurableMemoryWorkJob,
  workerId: string,
  atEventTime: number,
  leaseDuration: number,
): Readonly<DurableMemoryWorkJob> => {
  const job = parseDurableMemoryWorkJob(value);
  const worker = token(workerId);
  const at = eventTime(atEventTime);
  const duration = positive(leaseDuration);
  if (at < job.accepted_at_event_time) throw new DurableMemoryWorkTransitionError("not_yet_eligible");
  if (job.state === "succeeded" || job.state === "dead_letter") {
    throw new DurableMemoryWorkTransitionError("ineligible_state");
  }
  if (job.state === "leased" && job.lease !== null) {
    if (at < job.lease.expires_at_event_time) {
      throw new DurableMemoryWorkTransitionError("not_yet_eligible");
    }
    // Record `worker_lost` explicitly before another attempt. Silently
    // replacing an expired lease would erase why an accepted attempt ended.
    throw new DurableMemoryWorkTransitionError("expired_lease_requires_recovery");
  }
  if (job.state === "retryable_failed" && job.outcome?.kind === "retryable_error"
    && at < job.outcome.next_eligible_event_time) {
    throw new DurableMemoryWorkTransitionError("not_yet_eligible");
  }
  if (job.attempt >= job.max_attempts) {
    throw new DurableMemoryWorkTransitionError("attempt_budget_exhausted");
  }
  const attempt = safeAdd(job.attempt, 1);
  const fence = safeAdd(job.lease_fence, 1);
  return parseDurableMemoryWorkJob({
    ...job,
    state: "leased",
    attempt,
    lease_fence: fence,
    lease: {
      worker_id: worker,
      fence,
      leased_at_event_time: at,
      expires_at_event_time: safeAdd(at, duration),
    },
    outcome: null,
  });
};

const requireOwnedLease = (
  job: Readonly<DurableMemoryWorkJob>,
  suppliedLease: DurableMemoryWorkLeaseRef,
  atEventTime: number,
): void => {
  if (!ownsDurableMemoryWorkLease(job, suppliedLease, atEventTime)) {
    throw new DurableMemoryWorkTransitionError("stale_lease");
  }
};

export const succeedDurableMemoryWork = (
  value: DurableMemoryWorkJob,
  suppliedLease: DurableMemoryWorkLeaseRef,
  atEventTime: number,
  resultKind: DurableMemoryWorkResultKind,
  responseDigest: string,
  resultDigest: string,
): Readonly<DurableMemoryWorkJob> => {
  const job = parseDurableMemoryWorkJob(value);
  const at = eventTime(atEventTime);
  requireOwnedLease(job, suppliedLease, at);
  if (!RESULT_KINDS.has(resultKind)) throw new DurableMemoryWorkTransitionError("invalid_transition");
  let response: string;
  let result: string;
  try {
    response = digest(responseDigest);
    result = digest(resultDigest);
  } catch {
    throw new DurableMemoryWorkTransitionError("invalid_transition");
  }
  return parseDurableMemoryWorkJob({
    ...job,
    state: "succeeded",
    lease: null,
    outcome: {
      kind: "succeeded", result_kind: resultKind, response_digest: response,
      result_digest: result, succeeded_at_event_time: at,
    },
  });
};

export const failDurableMemoryWork = (
  value: DurableMemoryWorkJob,
  suppliedLease: DurableMemoryWorkLeaseRef,
  atEventTime: number,
  errorCode: DurableMemoryWorkErrorCode,
  nextEligibleEventTime: number | null,
): Readonly<DurableMemoryWorkJob> => {
  const job = parseDurableMemoryWorkJob(value);
  const at = eventTime(atEventTime);
  requireOwnedLease(job, suppliedLease, at);
  if (!ERROR_CODES.has(errorCode)) throw new DurableMemoryWorkTransitionError("invalid_transition");
  if (job.attempt >= job.max_attempts) {
    if (nextEligibleEventTime !== null) throw new DurableMemoryWorkTransitionError("invalid_transition");
    return parseDurableMemoryWorkJob({
      ...job,
      state: "dead_letter",
      lease: null,
      outcome: {
        kind: "dead_letter", error_code: errorCode, attempts: job.attempt,
        failed_at_event_time: at,
      },
    });
  }
  if (nextEligibleEventTime === null) throw new DurableMemoryWorkTransitionError("invalid_transition");
  const next = eventTime(nextEligibleEventTime);
  if (next <= at) throw new DurableMemoryWorkTransitionError("invalid_transition");
  return parseDurableMemoryWorkJob({
    ...job,
    state: "retryable_failed",
    lease: null,
    outcome: {
      kind: "retryable_error", error_code: errorCode,
      failed_at_event_time: at, next_eligible_event_time: next,
    },
  });
};

/**
 * A worker that vanished on its final attempt cannot present an owned fence to
 * fail the job after expiry. A repository sweeper uses this explicit transition
 * after locking the still-expired row; it never guesses an abstention.
 */
export const expireDurableMemoryWorkLease = (
  value: DurableMemoryWorkJob,
  atEventTime: number,
  nextEligibleEventTime: number | null,
): Readonly<DurableMemoryWorkJob> => {
  const job = parseDurableMemoryWorkJob(value);
  const at = eventTime(atEventTime);
  if (job.state !== "leased" || job.lease === null) {
    throw new DurableMemoryWorkTransitionError("ineligible_state");
  }
  if (at < job.lease.expires_at_event_time) {
    throw new DurableMemoryWorkTransitionError("not_yet_eligible");
  }
  if (job.attempt >= job.max_attempts) {
    if (nextEligibleEventTime !== null) throw new DurableMemoryWorkTransitionError("invalid_transition");
    return parseDurableMemoryWorkJob({
      ...job,
      state: "dead_letter",
      lease: null,
      outcome: {
        kind: "dead_letter", error_code: "worker_lost", attempts: job.attempt,
        failed_at_event_time: at,
      },
    });
  }
  if (nextEligibleEventTime === null) throw new DurableMemoryWorkTransitionError("invalid_transition");
  const next = eventTime(nextEligibleEventTime);
  if (next <= at) throw new DurableMemoryWorkTransitionError("invalid_transition");
  return parseDurableMemoryWorkJob({
    ...job,
    state: "retryable_failed",
    lease: null,
    outcome: {
      kind: "retryable_error", error_code: "worker_lost",
      failed_at_event_time: at, next_eligible_event_time: next,
    },
  });
};
