import { isProxy } from "node:util/types";

import {
  acceptDurableMemoryWork,
  durableMemoryWorkStateDigest,
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertFormationInputSnapshotMatchesJob,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";

const INPUT_REPOSITORY_PORT: unique symbol = Symbol("formation-work-input-repository");
const STAGED_INPUT_VERSION = "formation-work-staged-input-v1" as const;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;

export interface FormationWorkInputStageBody {
  readonly pending_job: Readonly<DurableMemoryWorkJob>;
  readonly snapshot: Readonly<FormationInputSnapshot>;
}

export interface FormationWorkInputStageRequest extends FormationWorkInputStageBody {
  readonly request_digest: string;
}

export interface StagedFormationWorkInput {
  readonly version: typeof STAGED_INPUT_VERSION;
  readonly staged_input_id: string;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly account_epoch: number;
  readonly accepted_work_digest: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly snapshot_digest: string;
  readonly snapshot: Readonly<FormationInputSnapshot>;
  readonly stage_request_digest: string;
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

export type FormationWorkInputStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; input: StagedFormationWorkInput }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export type FormationWorkInputLoadOutcome =
  | Readonly<{ kind: "found"; snapshot: FormationInputSnapshot }>
  | Readonly<{ kind: "not_found" | "stale_lease" | "ineligible_state" }>
  | CommonOutcome;

export interface FormationWorkInputRepository {
  readonly [INPUT_REPOSITORY_PORT]: true;
  stage(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkInputStageRequest,
  ): Promise<FormationWorkInputStageOutcome>;
  load(
    context: AuthorizedLedgerWriteContext,
    leasedJob: Readonly<DurableMemoryWorkJob>,
  ): Promise<FormationWorkInputLoadOutcome>;
}

export interface FormationWorkInputRepositoryImplementation {
  stage(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkInputStageRequest,
  ): Promise<unknown>;
  load(
    context: AuthorizedLedgerWriteContext,
    leasedJob: Readonly<DurableMemoryWorkJob>,
  ): Promise<unknown>;
}

const fail = (code: string): never => { throw new TypeError(`formation work input ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_shape");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail("invalid_shape");
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail("invalid_shape");
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_shape");
  }
  return value as Record<string, unknown>;
};

const digest = (value: unknown): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail("invalid_digest");
  return value;
};

const token = (value: unknown): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail("invalid_token");
  return value;
};

const pendingForContext = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): { context: AuthorizedLedgerWriteContext; job: Readonly<DurableMemoryWorkJob> } => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.work.accept") fail("capability_denied");
  let job: Readonly<DurableMemoryWorkJob>;
  try { job = parseDurableMemoryWorkJob(value); }
  catch { return fail("invalid_job"); }
  if (job.state !== "pending" || job.work_kind !== "formation"
    || job.owner_account_id !== context.account_id
    || job.account_epoch !== context.account_epoch) fail("job_mismatch");
  return { context, job };
};

const leasedForContext = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): { context: AuthorizedLedgerWriteContext; job: Readonly<DurableMemoryWorkJob> } => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.work.execute") fail("capability_denied");
  let job: Readonly<DurableMemoryWorkJob>;
  try { job = parseDurableMemoryWorkJob(value); }
  catch { return fail("invalid_job"); }
  if (job.state !== "leased" || job.work_kind !== "formation" || job.lease === null
    || job.lease.worker_id !== context.principal_id
    || job.owner_account_id !== context.account_id
    || job.account_epoch !== context.account_epoch) fail("job_mismatch");
  return { context, job };
};

export const formationWorkInputSnapshotDigest = (
  snapshotValue: FormationInputSnapshot,
): string => sha256CanonicalContent({
  contract_version: "formation-work-input-snapshot-digest-v1",
  snapshot: parseFormationInputSnapshot(snapshotValue),
});

export const formationWorkInputStageRequestDigest = (
  body: FormationWorkInputStageBody,
): string => {
  const job = parseDurableMemoryWorkJob(body.pending_job);
  const snapshot = parseFormationInputSnapshot(body.snapshot);
  assertFormationInputSnapshotMatchesJob(snapshot, job);
  return sha256CanonicalContent({
    contract_version: "formation-work-input-stage-request-v1",
    pending_state_digest: durableMemoryWorkStateDigest(job),
    snapshot_digest: formationWorkInputSnapshotDigest(snapshot),
  });
};

export const stagedFormationWorkInputId = (jobValue: DurableMemoryWorkJob): string => {
  const job = parseDurableMemoryWorkJob(jobValue);
  return `fwi1_${sha256CanonicalContent({
    contract_version: "formation-work-staged-input-id-v1",
    owner_account_id: job.owner_account_id,
    job_id: job.job_id,
    accepted_work_digest: job.accepted_work_digest,
  })}`;
};

export const materializeStagedFormationWorkInput = (
  request: FormationWorkInputStageRequest,
): StagedFormationWorkInput => {
  const job = parseDurableMemoryWorkJob(request.pending_job);
  const snapshot = parseFormationInputSnapshot(request.snapshot);
  assertFormationInputSnapshotMatchesJob(snapshot, job);
  return Object.freeze({
    version: STAGED_INPUT_VERSION,
    staged_input_id: stagedFormationWorkInputId(job),
    owner_account_id: job.owner_account_id,
    job_id: job.job_id,
    account_epoch: job.account_epoch,
    accepted_work_digest: job.accepted_work_digest,
    input_frontier: job.input_frontier,
    input_digest: job.input_digest,
    execution_contract_digest: job.execution_contract_digest,
    snapshot_digest: formationWorkInputSnapshotDigest(snapshot),
    snapshot,
    stage_request_digest: request.request_digest,
  });
};

export const parseStagedFormationWorkInput = (
  value: unknown,
  expectedJob?: DurableMemoryWorkJob,
): StagedFormationWorkInput => {
  const input = exactRecord(value, [
    "version", "staged_input_id", "owner_account_id", "job_id", "account_epoch",
    "accepted_work_digest", "input_frontier", "input_digest", "execution_contract_digest",
    "snapshot_digest", "snapshot", "stage_request_digest",
  ]);
  if (input["version"] !== STAGED_INPUT_VERSION) fail("invalid_version");
  const snapshot = parseFormationInputSnapshot(input["snapshot"]);
  const staged = Object.freeze({
    version: STAGED_INPUT_VERSION,
    staged_input_id: token(input["staged_input_id"]),
    owner_account_id: token(input["owner_account_id"]),
    job_id: token(input["job_id"]),
    account_epoch: input["account_epoch"] as number,
    accepted_work_digest: digest(input["accepted_work_digest"]),
    input_frontier: token(input["input_frontier"]),
    input_digest: digest(input["input_digest"]),
    execution_contract_digest: digest(input["execution_contract_digest"]),
    snapshot_digest: digest(input["snapshot_digest"]),
    snapshot,
    stage_request_digest: digest(input["stage_request_digest"]),
  }) satisfies StagedFormationWorkInput;
  if (!Number.isSafeInteger(staged.account_epoch) || staged.account_epoch < 0
    || !/^fwi1_[a-f0-9]{64}$/.test(staged.staged_input_id)
    || staged.owner_account_id !== snapshot.owner_account_id
    || staged.job_id !== snapshot.work_id
    || staged.input_frontier !== snapshot.input_frontier
    || staged.snapshot_digest !== formationWorkInputSnapshotDigest(snapshot)) fail("staged_input_mismatch");
  if (expectedJob !== undefined) {
    const job = parseDurableMemoryWorkJob(expectedJob);
    const pending = acceptDurableMemoryWork({
      version: job.version, job_id: job.job_id, owner_account_id: job.owner_account_id,
      account_epoch: job.account_epoch, lifecycle_state: job.lifecycle_state,
      deletion_epoch: job.deletion_epoch, work_kind: job.work_kind,
      input_frontier: job.input_frontier, input_digest: job.input_digest,
      execution_contract_digest: job.execution_contract_digest,
      accepted_at_event_time: job.accepted_at_event_time, max_attempts: job.max_attempts,
    });
    assertFormationInputSnapshotMatchesJob(snapshot, job);
    if (staged.staged_input_id !== stagedFormationWorkInputId(job)
      || staged.owner_account_id !== job.owner_account_id || staged.job_id !== job.job_id
      || staged.account_epoch !== job.account_epoch
      || staged.accepted_work_digest !== job.accepted_work_digest
      || staged.input_frontier !== job.input_frontier || staged.input_digest !== job.input_digest
      || staged.execution_contract_digest !== job.execution_contract_digest
      || staged.stage_request_digest !== formationWorkInputStageRequestDigest({
        pending_job: pending,
        snapshot,
      })) fail("staged_input_mismatch");
  }
  return staged;
};

const common = (value: unknown): CommonOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = descriptor && "value" in descriptor && descriptor.enumerable
    ? descriptor.value : fail("invalid_outcome");
  if (kind === "serialization_retryable") {
    exactRecord(value, ["kind"]);
    return Object.freeze({ kind });
  }
  if (kind === "stale_context" || kind === "authorization_denied") {
    const root = exactRecord(value, ["kind", "reason"]);
    const reasons = kind === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof root["reason"] !== "string" || !reasons.includes(root["reason"])) {
      fail("invalid_outcome");
    }
    return Object.freeze({ kind, reason: root["reason"] }) as CommonOutcome;
  }
  return null;
};

export const defineFormationWorkInputRepository = (
  implementation: FormationWorkInputRepositoryImplementation,
): FormationWorkInputRepository => Object.freeze({
  [INPUT_REPOSITORY_PORT]: true as const,
  async stage(contextValue, requestValue) {
    const root = exactRecord(requestValue, ["pending_job", "snapshot", "request_digest"]);
    const { context, job } = pendingForContext(contextValue, root["pending_job"]);
    const snapshot = parseFormationInputSnapshot(root["snapshot"]);
    assertFormationInputSnapshotMatchesJob(snapshot, job);
    const body = Object.freeze({ pending_job: job, snapshot });
    const requestDigest = digest(root["request_digest"]);
    if (requestDigest !== formationWorkInputStageRequestDigest(body)) fail("request_digest_mismatch");
    const request = Object.freeze({ ...body, request_digest: requestDigest });
    const raw = await implementation.stage(context, request);
    const shared = common(raw);
    if (shared) return shared;
    const outcome = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "staged" || (raw as { kind?: unknown }).kind === "replayed"
        ? ["input"] : []
    )]);
    if (outcome["kind"] === "idempotency_conflict") return Object.freeze({ kind: "idempotency_conflict" });
    if (outcome["kind"] !== "staged" && outcome["kind"] !== "replayed") fail("invalid_outcome");
    const staged = parseStagedFormationWorkInput(outcome["input"], job);
    const expected = materializeStagedFormationWorkInput(request);
    if (sha256CanonicalContent(staged) !== sha256CanonicalContent(expected)) fail("invalid_outcome");
    return Object.freeze({ kind: outcome["kind"], input: staged });
  },
  async load(contextValue, jobValue) {
    const { context, job } = leasedForContext(contextValue, jobValue);
    const raw = await implementation.load(context, job);
    const shared = common(raw);
    if (shared) return shared;
    const root = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "found" ? ["input"] : []
    )]);
    if (root["kind"] === "not_found" || root["kind"] === "stale_lease"
      || root["kind"] === "ineligible_state") return Object.freeze({ kind: root["kind"] });
    if (root["kind"] !== "found") fail("invalid_outcome");
    const staged = parseStagedFormationWorkInput(root["input"], job);
    return Object.freeze({ kind: "found" as const, snapshot: staged.snapshot });
  },
});
