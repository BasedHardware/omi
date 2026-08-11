import { isProxy } from "node:util/types";

import {
  durableMemoryWorkStateDigest,
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import type { CanonicalJson } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { deepFreezePlainJson, normalizePlainJson } from "../../../core/retrieve/plain-json";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const RESULT_PORT: unique symbol = Symbol("durable-memory-work-result-repository");
const EXECUTE_CAPABILITY = "memories.work.execute";
const RESULT_VERSION = "durable-memory-work-result-v1" as const;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
// Keep headroom below the SQL jsonb::text defense-in-depth ceiling: PostgreSQL
// may add canonical separators that JSON.stringify does not render.
const MAX_RESULT_BYTES = 448 * 1024;
const MAX_RESULT_DEPTH = 64;
const MAX_RESULT_NODES = 50_000;

export type NormalizedDurableMemoryWorkResultJson = Readonly<Record<string, CanonicalJson>>;

export interface DurableMemoryWorkResultStageBody {
  readonly leased_job: Readonly<DurableMemoryWorkJob>;
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result: NormalizedDurableMemoryWorkResultJson;
}

export interface DurableMemoryWorkResultStageRequest extends DurableMemoryWorkResultStageBody {
  readonly request_digest: string;
}

export interface StagedDurableMemoryWorkResult {
  readonly version: typeof RESULT_VERSION;
  readonly staged_result_id: string;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly accepted_work_digest: string;
  readonly work_kind: DurableMemoryWorkKind;
  readonly input_frontier: string;
  readonly execution_contract_digest: string;
  readonly produced_attempt: number;
  readonly produced_lease_fence: number;
  readonly produced_state_digest: string;
  readonly producer_worker_id: string;
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result: NormalizedDurableMemoryWorkResultJson;
  readonly stage_request_digest: string;
}

export interface DurableMemoryWorkResultLoadRequest {
  readonly leased_job: Readonly<DurableMemoryWorkJob>;
}

type CommonOutcome =
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>
  | Readonly<{ kind: "serialization_retryable" }>;

export type DurableMemoryWorkResultStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; result: StagedDurableMemoryWorkResult }>
  | Readonly<{ kind: "idempotency_conflict" | "stale_lease" | "ineligible_state" }>
  | CommonOutcome;

export type DurableMemoryWorkResultLoadOutcome =
  | Readonly<{ kind: "found"; result: StagedDurableMemoryWorkResult }>
  | Readonly<{ kind: "missing" | "stale_lease" | "ineligible_state" }>
  | CommonOutcome;

export interface DurableMemoryWorkResultRepository {
  readonly [RESULT_PORT]: true;
  load(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkResultLoadRequest,
  ): Promise<DurableMemoryWorkResultLoadOutcome>;
  stage(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkResultStageRequest,
  ): Promise<DurableMemoryWorkResultStageOutcome>;
}

export interface DurableMemoryWorkResultImplementation {
  load(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkResultLoadRequest,
  ): Promise<unknown>;
  stage(
    context: AuthorizedLedgerWriteContext,
    request: DurableMemoryWorkResultStageRequest,
  ): Promise<unknown>;
}

function fail(code: string): never {
  throw new TypeError(`durable memory work result repository ${code}`);
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

const assertPlainTree = (value: unknown): void => {
  const seen = new WeakSet<object>();
  let nodes = 0;
  const visit = (node: unknown, depth: number): void => {
    nodes += 1;
    if (nodes > MAX_RESULT_NODES || depth > MAX_RESULT_DEPTH) fail("invalid_result");
    if (node === null || typeof node === "string" || typeof node === "boolean") return;
    if (typeof node === "number") {
      if (!Number.isFinite(node)) fail("invalid_result");
      return;
    }
    if (typeof node !== "object" || isProxy(node) || seen.has(node)) fail("invalid_result");
    seen.add(node);
    const array = Array.isArray(node);
    const prototype = Object.getPrototypeOf(node);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
      fail("invalid_result");
    }
    const keys = Reflect.ownKeys(node);
    if (keys.some((key) => typeof key !== "string")) fail("invalid_result");
    if (array) {
      if (keys.length !== node.length + 1) fail("invalid_result");
      for (let index = 0; index < node.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(node, String(index));
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_result");
        visit(descriptor.value, depth + 1);
      }
      if ((keys as string[]).some((key) => key !== "length"
        && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= node.length))) fail("invalid_result");
      return;
    }
    for (const key of keys as string[]) {
      const descriptor = Object.getOwnPropertyDescriptor(node, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_result");
      visit(descriptor.value, depth + 1);
    }
  };
  visit(value, 0);
};

export const normalizeDurableMemoryWorkResultJson = (
  value: unknown,
): NormalizedDurableMemoryWorkResultJson => {
  assertPlainTree(value);
  let normalized: unknown;
  try {
    normalized = normalizePlainJson(value);
  } catch {
    return fail("invalid_result");
  }
  if (normalized === null || typeof normalized !== "object" || Array.isArray(normalized)) {
    fail("invalid_result");
  }
  if (Buffer.byteLength(JSON.stringify(normalized), "utf8") > MAX_RESULT_BYTES) fail("result_too_large");
  return deepFreezePlainJson(normalized) as NormalizedDurableMemoryWorkResultJson;
};

const leasedJobForContext = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<DurableMemoryWorkJob> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== EXECUTE_CAPABILITY) fail("capability_denied");
  let job: Readonly<DurableMemoryWorkJob>;
  try {
    job = parseDurableMemoryWorkJob(value);
  } catch {
    return fail("invalid_job");
  }
  if (job.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (job.account_epoch !== context.account_epoch) fail("epoch_mismatch");
  if (job.state !== "leased" || job.lease === null
    || job.lease.worker_id !== context.principal_id) fail("stale_lease");
  return job;
};

export const durableMemoryWorkStagedResultId = (jobValue: DurableMemoryWorkJob): string => {
  const job = parseDurableMemoryWorkJob(jobValue);
  return `mwr1_${sha256CanonicalContent({
    contract_version: "durable-memory-work-staged-result-id-v1",
    owner_account_id: job.owner_account_id,
    job_id: job.job_id,
    accepted_work_digest: job.accepted_work_digest,
  })}`;
};

export const durableMemoryWorkNormalizedResultDigest = (
  resultContractVersion: string,
  result: NormalizedDurableMemoryWorkResultJson,
): string => {
  const contract = token(resultContractVersion, "invalid_result");
  const normalized = normalizeDurableMemoryWorkResultJson(result);
  return sha256CanonicalContent({
    contract_version: "durable-memory-work-normalized-result-v1",
    result_contract_version: contract,
    normalized_result: normalized,
  });
};

export const durableMemoryWorkResultStageRequestDigest = (
  body: DurableMemoryWorkResultStageBody,
): string => {
  const job = parseDurableMemoryWorkJob(body.leased_job);
  const contract = token(body.result_contract_version, "invalid_result");
  const responseDigest = digest(body.response_digest, "invalid_result");
  const resultDigest = digest(body.normalized_result_digest, "invalid_result");
  const result = normalizeDurableMemoryWorkResultJson(body.normalized_result);
  return sha256CanonicalContent({
    contract_version: "durable-memory-work-result-stage-request-v1",
    leased_job_state_digest: durableMemoryWorkStateDigest(job),
    result_contract_version: contract,
    response_digest: responseDigest,
    normalized_result_digest: resultDigest,
    normalized_result: result,
  });
};

export const assertDurableMemoryWorkResultStageRequest = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): DurableMemoryWorkResultStageRequest => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  const input = exactRecord(value, [
    "leased_job", "result_contract_version", "response_digest",
    "normalized_result_digest", "normalized_result", "request_digest",
  ], "invalid_stage_request");
  const job = leasedJobForContext(context, input["leased_job"]);
  const contract = token(input["result_contract_version"], "invalid_result");
  const responseDigest = digest(input["response_digest"], "invalid_result");
  const result = normalizeDurableMemoryWorkResultJson(input["normalized_result"]);
  const resultDigest = digest(input["normalized_result_digest"], "invalid_result");
  if (durableMemoryWorkNormalizedResultDigest(contract, result) !== resultDigest) {
    fail("result_digest_mismatch");
  }
  const body = Object.freeze({
    leased_job: job,
    result_contract_version: contract,
    response_digest: responseDigest,
    normalized_result_digest: resultDigest,
    normalized_result: result,
  });
  const requestDigest = digest(input["request_digest"], "invalid_stage_request");
  if (durableMemoryWorkResultStageRequestDigest(body) !== requestDigest) {
    fail("request_digest_mismatch");
  }
  return Object.freeze({ ...body, request_digest: requestDigest });
};

export const materializeStagedDurableMemoryWorkResult = (
  request: DurableMemoryWorkResultStageRequest,
): StagedDurableMemoryWorkResult => Object.freeze({
  version: RESULT_VERSION,
  staged_result_id: durableMemoryWorkStagedResultId(request.leased_job),
  owner_account_id: request.leased_job.owner_account_id,
  job_id: request.leased_job.job_id,
  accepted_work_digest: request.leased_job.accepted_work_digest,
  work_kind: request.leased_job.work_kind,
  input_frontier: request.leased_job.input_frontier,
  execution_contract_digest: request.leased_job.execution_contract_digest,
  produced_attempt: request.leased_job.attempt,
  produced_lease_fence: request.leased_job.lease_fence,
  produced_state_digest: durableMemoryWorkStateDigest(request.leased_job),
  producer_worker_id: request.leased_job.lease!.worker_id,
  result_contract_version: request.result_contract_version,
  response_digest: request.response_digest,
  normalized_result_digest: request.normalized_result_digest,
  normalized_result: request.normalized_result,
  stage_request_digest: request.request_digest,
});

export const parseStagedDurableMemoryWorkResult = (
  value: unknown,
  expectedJob?: DurableMemoryWorkJob,
): StagedDurableMemoryWorkResult => {
  const input = exactRecord(value, [
    "version", "staged_result_id", "owner_account_id", "job_id",
    "accepted_work_digest", "work_kind", "input_frontier",
    "execution_contract_digest", "produced_attempt", "produced_lease_fence",
    "produced_state_digest", "producer_worker_id", "result_contract_version", "response_digest",
    "normalized_result_digest", "normalized_result", "stage_request_digest",
  ], "invalid_staged_result");
  if (input["version"] !== RESULT_VERSION) fail("invalid_staged_result");
  const result = normalizeDurableMemoryWorkResultJson(input["normalized_result"]);
  const contract = token(input["result_contract_version"], "invalid_staged_result");
  const resultDigest = digest(input["normalized_result_digest"], "invalid_staged_result");
  if (durableMemoryWorkNormalizedResultDigest(contract, result) !== resultDigest) {
    fail("invalid_staged_result");
  }
  const workKind = input["work_kind"];
  if (workKind !== "formation" && workKind !== "promotion"
    && workKind !== "identity_cluster" && workKind !== "predicate_batch") {
    fail("invalid_staged_result");
  }
  const producedAttempt = positive(input["produced_attempt"], "invalid_staged_result");
  const producedFence = positive(input["produced_lease_fence"], "invalid_staged_result");
  if (producedAttempt !== producedFence) fail("invalid_staged_result");
  const normalized = Object.freeze({
    version: RESULT_VERSION,
    staged_result_id: token(input["staged_result_id"], "invalid_staged_result"),
    owner_account_id: token(input["owner_account_id"], "invalid_staged_result"),
    job_id: token(input["job_id"], "invalid_staged_result"),
    accepted_work_digest: digest(input["accepted_work_digest"], "invalid_staged_result"),
    work_kind: workKind,
    input_frontier: token(input["input_frontier"], "invalid_staged_result"),
    execution_contract_digest: digest(input["execution_contract_digest"], "invalid_staged_result"),
    produced_attempt: producedAttempt,
    produced_lease_fence: producedFence,
    produced_state_digest: digest(input["produced_state_digest"], "invalid_staged_result"),
    producer_worker_id: token(input["producer_worker_id"], "invalid_staged_result"),
    result_contract_version: contract,
    response_digest: digest(input["response_digest"], "invalid_staged_result"),
    normalized_result_digest: resultDigest,
    normalized_result: result,
    stage_request_digest: digest(input["stage_request_digest"], "invalid_staged_result"),
  }) satisfies StagedDurableMemoryWorkResult;
  if (expectedJob !== undefined) {
    const job = parseDurableMemoryWorkJob(expectedJob);
    if (normalized.staged_result_id !== durableMemoryWorkStagedResultId(job)
      || normalized.owner_account_id !== job.owner_account_id
      || normalized.job_id !== job.job_id
      || normalized.accepted_work_digest !== job.accepted_work_digest
      || normalized.work_kind !== job.work_kind
      || normalized.input_frontier !== job.input_frontier
      || normalized.execution_contract_digest !== job.execution_contract_digest) {
      fail("staged_result_mismatch");
    }
  }
  return normalized;
};

const commonOutcome = (value: unknown): CommonOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_outcome");
  if (kind === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind });
  }
  if (kind === "stale_context" || kind === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = kind === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !reasons.includes(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind, reason: input["reason"] }) as CommonOutcome;
  }
  return null;
};

export const defineDurableMemoryWorkResultRepository = (
  implementation: DurableMemoryWorkResultImplementation,
): DurableMemoryWorkResultRepository => Object.freeze({
  [RESULT_PORT]: true as const,
  async load(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkResultLoadRequest,
  ): Promise<DurableMemoryWorkResultLoadOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    const input = exactRecord(requestValue, ["leased_job"], "invalid_load_request");
    const leasedJob = leasedJobForContext(context, input["leased_job"]);
    const request = Object.freeze({ leased_job: leasedJob });
    const raw = await implementation.load(context, request);
    const common = commonOutcome(raw);
    if (common !== null) return common;
    const root = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "found" ? ["result"] : []
    )], "invalid_outcome");
    if (root["kind"] === "found") {
      return Object.freeze({
        kind: "found" as const,
        result: parseStagedDurableMemoryWorkResult(root["result"], leasedJob),
      });
    }
    if (root["kind"] === "missing" || root["kind"] === "stale_lease"
      || root["kind"] === "ineligible_state") return Object.freeze({ kind: root["kind"] });
    return fail("invalid_outcome");
  },
  async stage(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: DurableMemoryWorkResultStageRequest,
  ): Promise<DurableMemoryWorkResultStageOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    const request = assertDurableMemoryWorkResultStageRequest(context, requestValue);
    const raw = await implementation.stage(context, request);
    const common = commonOutcome(raw);
    if (common !== null) return common;
    const root = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "staged" || (raw as { kind?: unknown }).kind === "replayed"
        ? ["result"] : []
    )], "invalid_outcome");
    if (root["kind"] === "staged" || root["kind"] === "replayed") {
      const result = parseStagedDurableMemoryWorkResult(root["result"], request.leased_job);
      const expected = materializeStagedDurableMemoryWorkResult(request);
      if (sha256CanonicalContent(result) !== sha256CanonicalContent(expected)) fail("invalid_outcome");
      return Object.freeze({ kind: root["kind"], result });
    }
    if (root["kind"] === "idempotency_conflict" || root["kind"] === "stale_lease"
      || root["kind"] === "ineligible_state") return Object.freeze({ kind: root["kind"] });
    return fail("invalid_outcome");
  },
});
