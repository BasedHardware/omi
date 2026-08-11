import { isProxy } from "node:util/types";

import {
  durableMemoryWorkStateDigest,
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkResultKind,
} from "../../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertAuthoritativeLedgerAppend,
  type AuthoritativeLedgerAppend,
  type NonFormationAppendReason,
} from "./authoritative-ledger-repository";

const SUCCESS_PORT: unique symbol = Symbol("durable-memory-work-success-repository");
const EXECUTE_CAPABILITY = "memories.work.execute";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface DurableMemoryWorkSuccessBody {
  readonly leased_job: Readonly<DurableMemoryWorkJob>;
  readonly result_kind: DurableMemoryWorkResultKind;
  readonly response_digest: string;
  readonly result_digest: string;
  readonly authoritative_append: AuthoritativeLedgerAppend | null;
}

export interface DurableMemoryWorkSuccessRequest extends DurableMemoryWorkSuccessBody {
  readonly request_digest: string;
}

export type DurableMemoryWorkSuccessOutcome =
  | Readonly<{
      kind: "committed" | "replayed";
      job: Readonly<DurableMemoryWorkJob>;
      commit_id: string | null;
      sequence: number | null;
      outbox_id: string;
    }>
  | Readonly<{ kind: "idempotency_conflict" | "stale_lease" | "ineligible_state" | "stale_parent" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>
  | Readonly<{ kind: "serialization_retryable" }>;

export interface DurableMemoryWorkSuccessRepository {
  readonly [SUCCESS_PORT]: true;
  commit(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkSuccessRequest,
  ): Promise<DurableMemoryWorkSuccessOutcome>;
}

export type DurableMemoryWorkSuccessImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkSuccessRequest,
) => Promise<unknown>;

function fail(code: string): never {
  throw new TypeError(`durable memory work success repository ${code}`);
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

const expectedNonFormationOrigin = (
  workKind: DurableMemoryWorkJob["work_kind"],
): NonFormationAppendReason | null => {
  if (workKind === "promotion") return "promotion";
  if (workKind === "identity_cluster") return "identity_consolidation";
  if (workKind === "predicate_batch") return "predicate_alignment";
  return null;
};

export const durableMemoryWorkSuccessRequestDigest = (body: DurableMemoryWorkSuccessBody): string => {
  const job = parseDurableMemoryWorkJob(body.leased_job);
  return sha256CanonicalContent({
    contract_version: "durable-memory-work-success-repository-v1",
    leased_job_state_digest: durableMemoryWorkStateDigest(job),
    result_kind: body.result_kind,
    response_digest: body.response_digest,
    result_digest: body.result_digest,
    authoritative_append_request_digest: body.authoritative_append?.append_attempt.request_digest ?? null,
  });
};

/** Opaque replay-stable identity for the one terminal success outbox event. */
export const durableMemoryWorkSuccessOutboxId = (body: DurableMemoryWorkSuccessBody): string => {
  const job = parseDurableMemoryWorkJob(body.leased_job);
  return `mwo1_${sha256CanonicalContent({
    contract_version: "durable-memory-work-success-outbox-v1",
    owner_account_id: job.owner_account_id,
    job_id: job.job_id,
    accepted_work_digest: job.accepted_work_digest,
    attempt: job.attempt,
    lease_fence: job.lease_fence,
    result_kind: body.result_kind,
    response_digest: body.response_digest,
    result_digest: body.result_digest,
  })}`;
};

export const assertDurableMemoryWorkSuccessRequest = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): DurableMemoryWorkSuccessRequest => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== EXECUTE_CAPABILITY) fail("capability_denied");
  const root = exactRecord(value, [
    "leased_job", "result_kind", "response_digest", "result_digest",
    "authoritative_append", "request_digest",
  ], "invalid_request");
  let job: Readonly<DurableMemoryWorkJob>;
  try {
    job = parseDurableMemoryWorkJob(root["leased_job"]);
  } catch {
    return fail("invalid_job");
  }
  if (job.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (job.account_epoch !== context.account_epoch) fail("epoch_mismatch");
  if (job.state !== "leased" || job.lease === null
    || job.lease.worker_id !== context.principal_id) fail("stale_lease");
  const resultKind = root["result_kind"];
  if (resultKind !== "successful" && resultKind !== "successful_empty") fail("invalid_result");
  const responseDigest = digest(root["response_digest"], "invalid_result");
  const resultDigest = digest(root["result_digest"], "invalid_result");
  let append: AuthoritativeLedgerAppend | null = null;
  if (root["authoritative_append"] !== null) {
    append = assertAuthoritativeLedgerAppend(context, root["authoritative_append"]);
  }
  if (resultKind === "successful_empty") {
    if (append !== null) fail("unexpected_graph_append");
  } else {
    if (append === null) fail("missing_graph_append");
    if (append.append_attempt.request_digest !== resultDigest
      || append.transition.derivation.commit.success_kind !== "success") fail("result_append_mismatch");
    if (job.work_kind === "formation") {
      if (append.origin.kind !== "formation"
        || append.origin.outcome.work_id !== job.job_id
        || append.origin.outcome.input_frontier !== job.input_frontier
        || append.origin.outcome.response_digest !== responseDigest) fail("origin_mismatch");
    } else {
      const expectedReason = expectedNonFormationOrigin(job.work_kind);
      if (expectedReason === null || append.origin.kind !== "non_formation"
        || append.origin.reason !== expectedReason) fail("origin_mismatch");
    }
  }
  const body = Object.freeze({
    leased_job: job,
    result_kind: resultKind,
    response_digest: responseDigest,
    result_digest: resultDigest,
    authoritative_append: append,
  }) as DurableMemoryWorkSuccessBody;
  const requestDigest = digest(root["request_digest"], "invalid_request");
  if (durableMemoryWorkSuccessRequestDigest(body) !== requestDigest) fail("request_digest_mismatch");
  return Object.freeze({ ...body, request_digest: requestDigest });
};

const outcomeKind = (value: unknown): string => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "string") fail("invalid_outcome");
  return descriptor.value;
};

const parseOutcome = (
  value: unknown,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkSuccessRequest,
): DurableMemoryWorkSuccessOutcome => {
  const kind = outcomeKind(value);
  if (["idempotency_conflict", "stale_lease", "ineligible_state", "stale_parent", "serialization_retryable"].includes(kind)) {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind }) as DurableMemoryWorkSuccessOutcome;
  }
  if (kind === "stale_context") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"];
    if (typeof input["reason"] !== "string" || !reasons.includes(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind, reason: input["reason"] }) as DurableMemoryWorkSuccessOutcome;
  }
  if (kind === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !reasons.includes(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind, reason: input["reason"] }) as DurableMemoryWorkSuccessOutcome;
  }
  if (kind !== "committed" && kind !== "replayed") return fail("invalid_outcome");
  const input = exactRecord(value, [
    "kind", "job", "commit_id", "sequence", "outbox_id",
  ], "invalid_outcome");
  let job: Readonly<DurableMemoryWorkJob>;
  try {
    job = parseDurableMemoryWorkJob(input["job"]);
  } catch {
    return fail("invalid_outcome");
  }
  if (job.owner_account_id !== context.account_id || job.account_epoch !== context.account_epoch
    || job.job_id !== request.leased_job.job_id
    || job.accepted_work_digest !== request.leased_job.accepted_work_digest
    || job.attempt !== request.leased_job.attempt || job.lease_fence !== request.leased_job.lease_fence
    || job.state !== "succeeded" || job.outcome?.kind !== "succeeded"
    || job.outcome.result_kind !== request.result_kind
    || job.outcome.response_digest !== request.response_digest
    || job.outcome.result_digest !== request.result_digest) fail("invalid_outcome");
  const heldLease = request.leased_job.lease!;
  if (job.outcome.succeeded_at_event_time < heldLease.leased_at_event_time
    || job.outcome.succeeded_at_event_time >= heldLease.expires_at_event_time) fail("invalid_outcome");
  let commitId: string | null;
  let sequence: number | null;
  if (request.result_kind === "successful_empty") {
    if (input["commit_id"] !== null || input["sequence"] !== null) fail("invalid_outcome");
    commitId = null;
    sequence = null;
  } else {
    commitId = token(input["commit_id"], "invalid_outcome");
    sequence = positive(input["sequence"], "invalid_outcome");
    if (commitId !== request.authoritative_append!.transition.derivation.commit.commit_id) {
      fail("invalid_outcome");
    }
  }
  const outboxId = token(input["outbox_id"], "invalid_outcome");
  if (outboxId !== durableMemoryWorkSuccessOutboxId(request)) fail("invalid_outcome");
  return Object.freeze({
    kind,
    job,
    commit_id: commitId,
    sequence,
    outbox_id: outboxId,
  });
};

export const defineDurableMemoryWorkSuccessRepository = (
  implementation: DurableMemoryWorkSuccessImplementation,
): DurableMemoryWorkSuccessRepository => Object.freeze({
  [SUCCESS_PORT]: true as const,
  async commit(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkSuccessRequest,
  ): Promise<DurableMemoryWorkSuccessOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    const request = assertDurableMemoryWorkSuccessRequest(context, requestValue);
    return parseOutcome(await implementation(context, request), context, request);
  },
});
