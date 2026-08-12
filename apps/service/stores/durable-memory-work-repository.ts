import { isProxy } from "node:util/types";

import {
  acceptDurableMemoryWork,
  durableMemoryWorkStateDigest,
  parseDurableMemoryWorkJob,
  type AcceptedDurableMemoryWork,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import {
  parseRegisteredDurableMemoryWorkExecutionPolicy,
  type RegisteredDurableMemoryWorkExecutionPolicy,
} from "../../../core/consolidate/execution-policy";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const ACCEPTANCE_PORT: unique symbol = Symbol("durable-memory-work-acceptance-repository");
const EXECUTION_PORT: unique symbol = Symbol("durable-memory-work-execution-repository");
const ACCEPT_CAPABILITY = "memories.work.accept";
const EXECUTE_CAPABILITY = "memories.work.execute";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ARRAY_INDEX = /^(0|[1-9]\d*)$/;
const MAX_MANIFEST_ENTRIES = 10_000;
const INPUT_KINDS = new Set<DurableMemoryWorkInputKind>([
  "event_revision", "evidence_revision", "claim_revision", "mention_revision",
  "entity_revision", "predicate_revision", "identity_revision",
  "identity_authorization_revision", "graph_frontier",
]);
const WORK_KINDS = new Set<DurableMemoryWorkKind>([
  "formation", "promotion", "identity_cluster", "predicate_batch",
]);
const ERROR_CODES = new Set<DurableMemoryWorkErrorCode>([
  "model_timeout", "model_rate_limited", "model_response_invalid",
  "prompt_budget_exceeded", "dependency_unavailable", "serialization_retryable",
  "worker_lost",
]);
const compareStrings = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export type DurableMemoryWorkInputKind =
  | "event_revision"
  | "evidence_revision"
  | "claim_revision"
  | "mention_revision"
  | "entity_revision"
  | "predicate_revision"
  | "identity_revision"
  | "identity_authorization_revision"
  | "graph_frontier";

export interface DurableMemoryWorkInputManifestEntry {
  readonly input_kind: DurableMemoryWorkInputKind;
  readonly input_ref: string;
  readonly input_digest: string;
}

export interface DurableMemoryWorkAcceptanceRequest {
  readonly accepted_work: AcceptedDurableMemoryWork;
  readonly input_manifest: readonly DurableMemoryWorkInputManifestEntry[];
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly execution_policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  readonly request_digest: string;
}

export interface NormalizedDurableMemoryWorkAcceptanceRequest extends DurableMemoryWorkAcceptanceRequest {
  readonly pending_job: Readonly<DurableMemoryWorkJob>;
  readonly state_digest: string;
}

type StaleContextOutcome = Readonly<{
  kind: "stale_context";
  reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
}>;
type AuthorizationDeniedOutcome = Readonly<{
  kind: "authorization_denied";
  reason: "credential_inactive" | "grant_inactive" | "capability_denied";
}>;
type CommonRepositoryOutcome = StaleContextOutcome | AuthorizationDeniedOutcome
  | Readonly<{ kind: "serialization_retryable" }>;

export type DurableMemoryWorkAcceptanceOutcome =
  | Readonly<{ kind: "accepted" | "replayed"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonRepositoryOutcome;

export interface DurableMemoryWorkAcceptanceRepository {
  readonly [ACCEPTANCE_PORT]: true;
  accept(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkAcceptanceRequest,
  ): Promise<DurableMemoryWorkAcceptanceOutcome>;
}

export type DurableMemoryWorkAcceptanceImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: NormalizedDurableMemoryWorkAcceptanceRequest,
) => Promise<unknown>;

export interface DurableMemoryWorkLeaseNextRequest {
  readonly work_kinds: readonly DurableMemoryWorkKind[];
}

export interface DurableMemoryWorkJobRequest {
  readonly job_id: string;
}

export interface DurableMemoryWorkFailureRequest extends DurableMemoryWorkJobRequest {
  readonly lease_fence: number;
  readonly error_code: DurableMemoryWorkErrorCode;
}

export type DurableMemoryWorkLeaseNextOutcome =
  | Readonly<{ kind: "leased"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "none_available" }>
  | CommonRepositoryOutcome;

export type DurableMemoryWorkLoadOutcome =
  | Readonly<{ kind: "found"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "not_found" }>
  | CommonRepositoryOutcome;

export type DurableMemoryWorkFailureOutcome =
  | Readonly<{ kind: "recorded"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "stale_lease" | "ineligible_state" }>
  | CommonRepositoryOutcome;

export type DurableMemoryWorkRecoveryOutcome =
  | Readonly<{ kind: "recovered"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "not_expired" | "ineligible_state" }>
  | CommonRepositoryOutcome;

export interface DurableMemoryWorkExecutionRepository {
  readonly [EXECUTION_PORT]: true;
  leaseNext(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkLeaseNextRequest,
  ): Promise<DurableMemoryWorkLeaseNextOutcome>;
  load(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkJobRequest,
  ): Promise<DurableMemoryWorkLoadOutcome>;
  recordFailure(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkFailureRequest,
  ): Promise<DurableMemoryWorkFailureOutcome>;
  recoverExpired(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkJobRequest,
  ): Promise<DurableMemoryWorkRecoveryOutcome>;
}

export interface DurableMemoryWorkExecutionImplementation {
  leaseNext(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkLeaseNextRequest,
  ): Promise<unknown>;
  load(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkJobRequest,
  ): Promise<unknown>;
  recordFailure(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkFailureRequest,
  ): Promise<unknown>;
  recoverExpired(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkJobRequest,
  ): Promise<unknown>;
}

function fail(code: string): never {
  throw new TypeError(`durable memory work repository ${code}`);
}

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number, code: string): readonly unknown[] => {
  if (value === null || typeof value !== "object" || !Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Array.prototype || value.length > maximum) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== value.length + 1 || keys.some((key) => typeof key !== "string")
    || (keys as string[]).some((key) => key !== "length"
      && (!ARRAY_INDEX.test(key) || Number(key) >= value.length))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const positive = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) fail(code);
  return value as number;
};

const normalizeManifest = (value: unknown): readonly DurableMemoryWorkInputManifestEntry[] => {
  const entries = exactArray(value, MAX_MANIFEST_ENTRIES, "invalid_manifest").map((item) => {
    const input = exactRecord(item, ["input_kind", "input_ref", "input_digest"], "invalid_manifest");
    if (typeof input["input_kind"] !== "string"
      || !INPUT_KINDS.has(input["input_kind"] as DurableMemoryWorkInputKind)) fail("invalid_manifest");
    return Object.freeze({
      input_kind: input["input_kind"] as DurableMemoryWorkInputKind,
      input_ref: token(input["input_ref"], "invalid_manifest"),
      input_digest: digest(input["input_digest"], "invalid_manifest"),
    });
  });
  if (entries.length === 0) fail("invalid_manifest");
  entries.sort((left, right) => compareStrings(left.input_kind, right.input_kind)
    || compareStrings(left.input_ref, right.input_ref));
  for (let index = 1; index < entries.length; index += 1) {
    const previous = entries[index - 1]!;
    const current = entries[index]!;
    if (previous.input_kind === current.input_kind && previous.input_ref === current.input_ref) {
      fail("invalid_manifest");
    }
  }
  return Object.freeze(entries);
};

export const durableMemoryWorkInputManifestDigest = (
  manifest: readonly DurableMemoryWorkInputManifestEntry[],
): string => sha256CanonicalContent({
  contract_version: "durable-memory-work-input-manifest-v1",
  inputs: normalizeManifest(manifest),
});

export const durableMemoryWorkAcceptanceRequestDigest = (
  pendingJob: DurableMemoryWorkJob,
  manifest: readonly DurableMemoryWorkInputManifestEntry[],
  strategyAssignment: Readonly<MemoryStrategyAssignmentBundle>,
  executionPolicy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>,
): string => sha256CanonicalContent({
  contract_version: "durable-memory-work-acceptance-repository-v3",
  pending_job: parseDurableMemoryWorkJob(pendingJob),
  input_manifest: normalizeManifest(manifest),
  strategy_assignment: assertMintedMemoryStrategyAssignment(strategyAssignment),
  execution_policy: parseRegisteredDurableMemoryWorkExecutionPolicy(executionPolicy),
});

export const assertDurableMemoryWorkAcceptanceRequest = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): NormalizedDurableMemoryWorkAcceptanceRequest => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== ACCEPT_CAPABILITY) fail("capability_denied");
  const root = exactRecord(value, [
    "accepted_work", "input_manifest", "strategy_assignment", "execution_policy", "request_digest",
  ], "invalid_acceptance");
  let pendingJob: Readonly<DurableMemoryWorkJob>;
  try {
    pendingJob = acceptDurableMemoryWork(root["accepted_work"] as AcceptedDurableMemoryWork);
  } catch {
    return fail("invalid_acceptance");
  }
  if (pendingJob.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (pendingJob.account_epoch !== context.account_epoch) fail("epoch_mismatch");
  const manifest = normalizeManifest(root["input_manifest"]);
  const frontierWitnesses = manifest.filter((item) => item.input_kind === "graph_frontier");
  if (frontierWitnesses.length !== 1
    || frontierWitnesses[0]!.input_ref !== pendingJob.input_frontier) fail("frontier_mismatch");
  if (durableMemoryWorkInputManifestDigest(manifest) !== pendingJob.input_digest) fail("manifest_digest_mismatch");
  const strategyAssignment = assertMintedMemoryStrategyAssignment(root["strategy_assignment"]);
  if (strategyAssignment.owner_account_id !== pendingJob.owner_account_id) fail("assignment_owner_mismatch");
  if (strategyAssignment.work_kind !== pendingJob.work_kind) fail("assignment_work_kind_mismatch");
  if (strategyAssignment.authority.execution_contract_digest !== pendingJob.execution_contract_digest) {
    fail("assignment_execution_contract_mismatch");
  }
  let executionPolicy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  try {
    executionPolicy = parseRegisteredDurableMemoryWorkExecutionPolicy(root["execution_policy"]);
  } catch {
    return fail("invalid_execution_policy");
  }
  if (executionPolicy.work_kind !== pendingJob.work_kind) fail("execution_policy_work_kind_mismatch");
  if (executionPolicy.execution_contract_digest !== pendingJob.execution_contract_digest) {
    fail("execution_policy_contract_mismatch");
  }
  if (executionPolicy.max_attempts !== pendingJob.max_attempts) {
    fail("execution_policy_attempts_mismatch");
  }
  const requestDigest = digest(root["request_digest"], "invalid_acceptance");
  if (durableMemoryWorkAcceptanceRequestDigest(
    pendingJob, manifest, strategyAssignment, executionPolicy,
  ) !== requestDigest) {
    fail("request_digest_mismatch");
  }
  return Object.freeze({
    accepted_work: Object.freeze({
      version: pendingJob.version,
      job_id: pendingJob.job_id,
      owner_account_id: pendingJob.owner_account_id,
      account_epoch: pendingJob.account_epoch,
      lifecycle_state: pendingJob.lifecycle_state,
      deletion_epoch: pendingJob.deletion_epoch,
      work_kind: pendingJob.work_kind,
      input_frontier: pendingJob.input_frontier,
      input_digest: pendingJob.input_digest,
      execution_contract_digest: pendingJob.execution_contract_digest,
      accepted_at_event_time: pendingJob.accepted_at_event_time,
      max_attempts: pendingJob.max_attempts,
    }),
    input_manifest: manifest,
    strategy_assignment: strategyAssignment,
    execution_policy: executionPolicy,
    request_digest: requestDigest,
    pending_job: pendingJob,
    state_digest: durableMemoryWorkStateDigest(pendingJob),
  });
};

const assertContext = (value: AuthorizedLedgerWriteContext, capability: string): AuthorizedLedgerWriteContext => {
  const context = assertAuthorizedLedgerWriteContext(value);
  if (context.capability !== capability) fail("capability_denied");
  return context;
};

const normalizedJobForContext = (value: unknown, context: AuthorizedLedgerWriteContext): Readonly<DurableMemoryWorkJob> => {
  let job: Readonly<DurableMemoryWorkJob>;
  try {
    job = parseDurableMemoryWorkJob(value);
  } catch {
    return fail("invalid_job_output");
  }
  if (job.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (job.account_epoch !== context.account_epoch) fail("epoch_mismatch");
  return job;
};

const outcomeRoot = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "string") fail("invalid_outcome");
  return value as Record<string, unknown>;
};

const commonOutcome = (value: unknown): CommonRepositoryOutcome | null => {
  const root = outcomeRoot(value);
  if (root["kind"] === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: "serialization_retryable" as const });
  }
  if (root["kind"] === "stale_context") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = new Set(["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]);
    if (typeof input["reason"] !== "string" || !reasons.has(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind: "stale_context" as const, reason: input["reason"] as StaleContextOutcome["reason"] });
  }
  if (root["kind"] === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = new Set(["credential_inactive", "grant_inactive", "capability_denied"]);
    if (typeof input["reason"] !== "string" || !reasons.has(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind: "authorization_denied" as const, reason: input["reason"] as AuthorizationDeniedOutcome["reason"] });
  }
  return null;
};

const parseAcceptanceOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: NormalizedDurableMemoryWorkAcceptanceRequest,
): DurableMemoryWorkAcceptanceOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const root = outcomeRoot(value);
  if (root["kind"] === "idempotency_conflict") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: "idempotency_conflict" as const });
  }
  if (root["kind"] === "accepted" || root["kind"] === "replayed") {
    const input = exactRecord(value, ["kind", "job"], "invalid_outcome");
    const job = normalizedJobForContext(input["job"], context);
    if (job.state !== "pending" || job.accepted_work_digest !== request.pending_job.accepted_work_digest
      || durableMemoryWorkStateDigest(job) !== request.state_digest) fail("invalid_outcome");
    return Object.freeze({ kind: root["kind"] as "accepted" | "replayed", job });
  }
  return fail("invalid_outcome");
};

const parseLeaseRequest = (value: unknown): DurableMemoryWorkLeaseNextRequest => {
  const root = exactRecord(value, ["work_kinds"], "invalid_lease_request");
  const kinds = exactArray(root["work_kinds"], WORK_KINDS.size, "invalid_lease_request")
    .map((item) => {
      if (typeof item !== "string" || !WORK_KINDS.has(item as DurableMemoryWorkKind)) fail("invalid_lease_request");
      return item as DurableMemoryWorkKind;
    });
  if (kinds.length === 0) fail("invalid_lease_request");
  for (let index = 1; index < kinds.length; index += 1) {
    if (compareStrings(kinds[index - 1]!, kinds[index]!) >= 0) fail("invalid_lease_request");
  }
  return Object.freeze({ work_kinds: Object.freeze(kinds) });
};

const parseJobRequest = (value: unknown): DurableMemoryWorkJobRequest => {
  const root = exactRecord(value, ["job_id"], "invalid_job_request");
  return Object.freeze({ job_id: token(root["job_id"], "invalid_job_request") });
};

const parseFailureRequest = (value: unknown): DurableMemoryWorkFailureRequest => {
  const root = exactRecord(value, ["job_id", "lease_fence", "error_code"], "invalid_failure_request");
  if (typeof root["error_code"] !== "string"
    || !ERROR_CODES.has(root["error_code"] as DurableMemoryWorkErrorCode)) fail("invalid_failure_request");
  return Object.freeze({
    job_id: token(root["job_id"], "invalid_failure_request"),
    lease_fence: positive(root["lease_fence"], "invalid_failure_request"),
    error_code: root["error_code"] as DurableMemoryWorkErrorCode,
  });
};

const parseLeaseOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkLeaseNextRequest,
): DurableMemoryWorkLeaseNextOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const root = outcomeRoot(value);
  if (root["kind"] === "none_available") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: "none_available" as const });
  }
  if (root["kind"] === "leased") {
    const input = exactRecord(value, ["kind", "job"], "invalid_outcome");
    const job = normalizedJobForContext(input["job"], context);
    if (job.state !== "leased" || job.lease?.worker_id !== context.principal_id
      || !request.work_kinds.includes(job.work_kind)) fail("invalid_outcome");
    return Object.freeze({ kind: "leased" as const, job });
  }
  return fail("invalid_outcome");
};

const parseLoadOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkJobRequest,
): DurableMemoryWorkLoadOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const root = outcomeRoot(value);
  if (root["kind"] === "not_found") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: "not_found" as const });
  }
  if (root["kind"] === "found") {
    const input = exactRecord(value, ["kind", "job"], "invalid_outcome");
    const job = normalizedJobForContext(input["job"], context);
    if (job.job_id !== request.job_id) fail("invalid_outcome");
    return Object.freeze({ kind: "found" as const, job });
  }
  return fail("invalid_outcome");
};

const parseFailureOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkFailureRequest,
): DurableMemoryWorkFailureOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const root = outcomeRoot(value);
  if (root["kind"] === "stale_lease" || root["kind"] === "ineligible_state") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: root["kind"] as "stale_lease" | "ineligible_state" });
  }
  if (root["kind"] === "recorded") {
    const input = exactRecord(value, ["kind", "job"], "invalid_outcome");
    const job = normalizedJobForContext(input["job"], context);
    if (job.job_id !== request.job_id || job.lease_fence !== request.lease_fence
      || (job.state !== "retryable_failed" && job.state !== "dead_letter")
      || job.outcome?.kind === "succeeded" || job.outcome?.error_code !== request.error_code) fail("invalid_outcome");
    return Object.freeze({ kind: "recorded" as const, job });
  }
  return fail("invalid_outcome");
};

const parseRecoveryOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkJobRequest,
): DurableMemoryWorkRecoveryOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const root = outcomeRoot(value);
  if (root["kind"] === "not_expired" || root["kind"] === "ineligible_state") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: root["kind"] as "not_expired" | "ineligible_state" });
  }
  if (root["kind"] === "recovered") {
    const input = exactRecord(value, ["kind", "job"], "invalid_outcome");
    const job = normalizedJobForContext(input["job"], context);
    if (job.job_id !== request.job_id
      || (job.state !== "retryable_failed" && job.state !== "dead_letter")
      || job.outcome?.kind === "succeeded" || job.outcome?.error_code !== "worker_lost") fail("invalid_outcome");
    return Object.freeze({ kind: "recovered" as const, job });
  }
  return fail("invalid_outcome");
};

export const defineDurableMemoryWorkAcceptanceRepository = (
  implementation: DurableMemoryWorkAcceptanceImplementation,
): DurableMemoryWorkAcceptanceRepository => Object.freeze({
  [ACCEPTANCE_PORT]: true as const,
  async accept(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkAcceptanceRequest,
  ): Promise<DurableMemoryWorkAcceptanceOutcome> {
    const context = assertContext(contextValue, ACCEPT_CAPABILITY);
    const request = assertDurableMemoryWorkAcceptanceRequest(context, requestValue);
    return parseAcceptanceOutcome(await implementation(context, request), context, request);
  },
});

export const defineDurableMemoryWorkExecutionRepository = (
  implementation: DurableMemoryWorkExecutionImplementation,
): DurableMemoryWorkExecutionRepository => Object.freeze({
  [EXECUTION_PORT]: true as const,
  async leaseNext(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkLeaseNextRequest,
  ): Promise<DurableMemoryWorkLeaseNextOutcome> {
    const context = assertContext(contextValue, EXECUTE_CAPABILITY);
    const request = parseLeaseRequest(requestValue);
    return parseLeaseOutcome(await implementation.leaseNext(context, request), context, request);
  },
  async load(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkJobRequest,
  ): Promise<DurableMemoryWorkLoadOutcome> {
    const context = assertContext(contextValue, EXECUTE_CAPABILITY);
    const request = parseJobRequest(requestValue);
    return parseLoadOutcome(await implementation.load(context, request), context, request);
  },
  async recordFailure(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkFailureRequest,
  ): Promise<DurableMemoryWorkFailureOutcome> {
    const context = assertContext(contextValue, EXECUTE_CAPABILITY);
    const request = parseFailureRequest(requestValue);
    return parseFailureOutcome(await implementation.recordFailure(context, request), context, request);
  },
  async recoverExpired(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkJobRequest,
  ): Promise<DurableMemoryWorkRecoveryOutcome> {
    const context = assertContext(contextValue, EXECUTE_CAPABILITY);
    const request = parseJobRequest(requestValue);
    return parseRecoveryOutcome(await implementation.recoverExpired(context, request), context, request);
  },
});
