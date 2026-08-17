import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type { RecallTraceRef } from "../../../core/retrieve/recall-integrity";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertVerifiedMemoryEvaluationResult,
  materializeMemoryEvaluationResult,
  type MemoryEvaluationResult,
  type MemoryEvaluationStageRequest,
} from "./memory-shadow-result-repository";
import { parseMemoryReadEvaluationResult } from "../workers/memory-read-evaluation-result";

const PORT: unique symbol = Symbol("memory-read-grounding-repository");
const VERSION = "finalized-query-grounding-v1" as const;
const CAPABILITY = "memories.experiments.shadow";
const ARTIFACT_ID = /^mgr1_[a-f0-9]{64}$/;
const RESULT_ID = /^msr1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const SUBJECT_CLASS = /^[a-z][a-z0-9_-]{0,63}$/;
const MAX_ROWS = 10_000;
const MAX_CLASSES = 32;
const artifacts = new WeakSet<object>();

export interface FinalizedMemoryReadGroundingRow {
  readonly trace_ref: RecallTraceRef;
  readonly contributing_subject_classes: readonly string[];
}

export interface FinalizedMemoryReadGroundingArtifact {
  readonly version: typeof VERSION;
  readonly grounding_artifact_id: string;
  readonly evaluation_result_ref: string;
  readonly normalized_result_digest: string;
  readonly copied_input_digest: string;
  readonly input_frontier_digest: string;
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projected_content_digest: string;
  readonly response_digest: string;
  readonly grounded_reference_count: number;
  readonly rows: readonly Readonly<FinalizedMemoryReadGroundingRow>[];
  readonly artifact_digest: string;
}

export interface FinalizedMemoryReadGroundingRequest {
  readonly evaluation_result: Readonly<MemoryEvaluationResult>;
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projected_content_digest: string;
  readonly rows: readonly Readonly<FinalizedMemoryReadGroundingRow>[];
}

type CommonOutcome =
  | Readonly<{ kind: "serialization_retryable" | "source_unavailable" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>;

export type MemoryReadGroundingStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; artifact: Readonly<FinalizedMemoryReadGroundingArtifact> }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export type MemoryReadGroundingLoadOutcome =
  | Readonly<{ kind: "found"; artifact: Readonly<FinalizedMemoryReadGroundingArtifact> }>
  | Readonly<{ kind: "missing" }>
  | CommonOutcome;

export interface MemoryReadGroundingRepository {
  readonly [PORT]: true;
  /** Implementation stages the exact evaluation result and artifact in one transaction. */
  stage(
    context: AuthorizedLedgerWriteContext,
    result: Readonly<MemoryEvaluationResult>,
    artifact: FinalizedMemoryReadGroundingArtifact,
    request: MemoryEvaluationStageRequest,
  ): Promise<MemoryReadGroundingStageOutcome>;
  load(
    context: AuthorizedLedgerWriteContext,
    result: Readonly<MemoryEvaluationResult>,
  ): Promise<MemoryReadGroundingLoadOutcome>;
}

export interface MemoryReadGroundingRepositoryImplementation {
  stage(
    context: AuthorizedLedgerWriteContext,
    result: Readonly<MemoryEvaluationResult>,
    artifact: Readonly<FinalizedMemoryReadGroundingArtifact>,
    request: Readonly<MemoryEvaluationStageRequest>,
  ): Promise<unknown>;
  load(
    context: AuthorizedLedgerWriteContext,
    result: Readonly<MemoryEvaluationResult>,
  ): Promise<unknown>;
}

const fail = (code: string): never => { throw new TypeError(`memory read grounding repository ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export const assertMemoryReadGroundingRepository = (
  value: unknown,
): MemoryReadGroundingRepository => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("unverified_repository");
  const brand = Object.getOwnPropertyDescriptor(value, PORT);
  const methods = ["stage", "load"].map((name) => Object.getOwnPropertyDescriptor(value, name));
  if (!brand || !("value" in brand) || brand.value !== true
    || methods.some((descriptor) => !descriptor || !("value" in descriptor)
      || typeof descriptor.value !== "function" || !descriptor.enumerable)) {
    fail("unverified_repository");
  }
  return value as MemoryReadGroundingRepository;
};

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== value.length + 1 || keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length)))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const rows = (value: unknown): readonly Readonly<FinalizedMemoryReadGroundingRow>[] => {
  const output = exactArray(value, MAX_ROWS, "invalid_rows").map((item) => {
    const row = exactRecord(item, ["trace_ref", "contributing_subject_classes"], "invalid_row");
    const traceRef = row["trace_ref"];
    if (typeof traceRef !== "string" || !TRACE_REF.test(traceRef)) fail("invalid_row");
    const classes = exactArray(row["contributing_subject_classes"], MAX_CLASSES, "invalid_row").map((item) => {
      if (typeof item !== "string" || !SUBJECT_CLASS.test(item)) fail("invalid_row");
      return item;
    });
    if (classes.length === 0 || new Set(classes).size !== classes.length
      || classes.some((item, index) => index > 0 && compare(classes[index - 1]!, item) >= 0)) fail("invalid_row");
    return Object.freeze({ trace_ref: traceRef as RecallTraceRef, contributing_subject_classes: Object.freeze(classes) });
  });
  if (new Set(output.map((row) => row.trace_ref)).size !== output.length
    || output.some((row, index) => index > 0 && compare(output[index - 1]!.trace_ref, row.trace_ref) >= 0)) fail("invalid_rows");
  return Object.freeze(output);
};

const validateClosure = (
  result: Readonly<MemoryEvaluationResult>,
  normalizedRows: readonly Readonly<FinalizedMemoryReadGroundingRow>[],
): ReturnType<typeof parseMemoryReadEvaluationResult> => {
  if (result.result_contract_version !== "memory-read-evaluation-result-v1") fail("wrong_result_contract");
  const read = parseMemoryReadEvaluationResult(result.normalized_result);
  if (result.input_digest !== read.copied_input_digest
    || result.strategy_id !== read.strategy_id
    || result.execution_contract_digest !== read.execution_contract_digest) fail("result_coordinate_mismatch");
  const expected = [...read.recall_trace.stages.grounded].sort(compare);
  if (normalizedRows.length !== expected.length
    || normalizedRows.some((row, index) => row.trace_ref !== expected[index])) fail("incomplete_grounding");
  const assertionRefs = new Set(read.assertions.flatMap((assertion) => assertion.citations));
  if (assertionRefs.size !== expected.length || expected.some((ref) => !assertionRefs.has(ref))) fail("incomplete_grounding");
  return read;
};

const artifactCore = (
  result: Readonly<MemoryEvaluationResult>,
  projectionAuthorizationDigest: string,
  readerProjectionDigest: string,
  projectedContentDigest: string,
  normalizedRows: readonly Readonly<FinalizedMemoryReadGroundingRow>[],
) => {
  const read = validateClosure(result, normalizedRows);
  return Object.freeze({
    version: VERSION,
    evaluation_result_ref: result.evaluation_result_id,
    normalized_result_digest: result.normalized_result_digest,
    copied_input_digest: read.copied_input_digest,
    input_frontier_digest: read.input_frontier_digest,
    strategy_id: result.strategy_id,
    execution_contract_digest: result.execution_contract_digest,
    projection_authorization_digest: digest(projectionAuthorizationDigest, "invalid_projection_coordinate"),
    reader_projection_digest: digest(readerProjectionDigest, "invalid_projection_coordinate"),
    projected_content_digest: digest(projectedContentDigest, "invalid_projection_coordinate"),
    response_digest: result.response_digest,
    grounded_reference_count: normalizedRows.length,
    rows: normalizedRows,
  });
};

export const materializeFinalizedMemoryReadGrounding = (
  requestValue: FinalizedMemoryReadGroundingRequest,
): Readonly<FinalizedMemoryReadGroundingArtifact> => {
  const request = exactRecord(requestValue, [
    "evaluation_result", "projection_authorization_digest", "reader_projection_digest",
    "projected_content_digest", "rows",
  ], "invalid_request");
  const result = assertVerifiedMemoryEvaluationResult(request["evaluation_result"] as MemoryEvaluationResult);
  const normalizedRows = rows(request["rows"]);
  const core = artifactCore(
    result,
    request["projection_authorization_digest"] as string,
    request["reader_projection_digest"] as string,
    request["projected_content_digest"] as string,
    normalizedRows,
  );
  const artifactDigest = sha256CanonicalContent(core);
  const artifact = Object.freeze({
    ...core,
    grounding_artifact_id: `mgr1_${sha256CanonicalContent({
      contract_version: "finalized-query-grounding-id-v1",
      evaluation_result_ref: result.evaluation_result_id,
      normalized_result_digest: result.normalized_result_digest,
    })}`,
    artifact_digest: artifactDigest,
  });
  artifacts.add(artifact);
  return artifact;
};

const parseArtifact = (
  result: Readonly<MemoryEvaluationResult>,
  value: unknown,
): Readonly<FinalizedMemoryReadGroundingArtifact> => {
  const input = exactRecord(value, [
    "version", "grounding_artifact_id", "evaluation_result_ref", "normalized_result_digest",
    "copied_input_digest", "input_frontier_digest", "strategy_id", "execution_contract_digest",
    "projection_authorization_digest", "reader_projection_digest", "projected_content_digest",
    "response_digest", "grounded_reference_count", "rows", "artifact_digest",
  ], "invalid_artifact");
  if (input["version"] !== VERSION || typeof input["grounding_artifact_id"] !== "string"
    || !ARTIFACT_ID.test(input["grounding_artifact_id"] as string)
    || typeof input["evaluation_result_ref"] !== "string" || !RESULT_ID.test(input["evaluation_result_ref"] as string)
    || input["evaluation_result_ref"] !== result.evaluation_result_id
    || input["normalized_result_digest"] !== result.normalized_result_digest
    || input["strategy_id"] !== result.strategy_id
    || input["execution_contract_digest"] !== result.execution_contract_digest
    || input["response_digest"] !== result.response_digest
    || !Number.isSafeInteger(input["grounded_reference_count"])) fail("invalid_artifact");
  const normalizedRows = rows(input["rows"]);
  if (input["grounded_reference_count"] !== normalizedRows.length) fail("invalid_artifact");
  const core = artifactCore(
    result,
    input["projection_authorization_digest"] as string,
    input["reader_projection_digest"] as string,
    input["projected_content_digest"] as string,
    normalizedRows,
  );
  if (input["copied_input_digest"] !== core.copied_input_digest
    || input["input_frontier_digest"] !== core.input_frontier_digest
    || input["artifact_digest"] !== sha256CanonicalContent(core)) fail("artifact_digest_mismatch");
  const expectedId = `mgr1_${sha256CanonicalContent({
    contract_version: "finalized-query-grounding-id-v1",
    evaluation_result_ref: result.evaluation_result_id,
    normalized_result_digest: result.normalized_result_digest,
  })}`;
  if (input["grounding_artifact_id"] !== expectedId) fail("artifact_id_mismatch");
  const artifact = Object.freeze({ ...core, grounding_artifact_id: expectedId, artifact_digest: input["artifact_digest"] as string });
  artifacts.add(artifact);
  return artifact;
};

const verifiedArtifact = (
  result: Readonly<MemoryEvaluationResult>,
  value: FinalizedMemoryReadGroundingArtifact,
): Readonly<FinalizedMemoryReadGroundingArtifact> => {
  if (value === null || typeof value !== "object" || !artifacts.has(value)) fail("unverified_artifact");
  if (value.evaluation_result_ref !== result.evaluation_result_id
    || value.normalized_result_digest !== result.normalized_result_digest) fail("artifact_result_mismatch");
  return value;
};

const authority = (
  contextValue: AuthorizedLedgerWriteContext,
  resultValue: Readonly<MemoryEvaluationResult>,
): readonly [AuthorizedLedgerWriteContext, Readonly<MemoryEvaluationResult>] => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  const result = assertVerifiedMemoryEvaluationResult(resultValue);
  if (result.owner_account_id !== context.account_id || result.account_epoch !== context.account_epoch) fail("authority_mismatch");
  return [context, result] as const;
};

const commonOutcome = (value: unknown): CommonOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) fail("invalid_outcome");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_outcome");
  if (kind === "serialization_retryable" || kind === "source_unavailable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind });
  }
  if (kind === "stale_context" || kind === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const allowed = kind === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !allowed.includes(input["reason"] as string)) fail("invalid_outcome");
    return Object.freeze({ kind, reason: input["reason"] }) as CommonOutcome;
  }
  return null;
};

export const defineMemoryReadGroundingRepository = (
  implementation: MemoryReadGroundingRepositoryImplementation,
): MemoryReadGroundingRepository => Object.freeze({
  [PORT]: true as const,
  async stage(contextValue, resultValue, artifactValue, requestValue) {
    const [context, result] = authority(contextValue, resultValue);
    const artifact = verifiedArtifact(result, artifactValue);
    const requestResult = materializeMemoryEvaluationResult(context, requestValue);
    if (sha256CanonicalContent(requestResult) !== sha256CanonicalContent(result)) {
      fail("stage_request_result_mismatch");
    }
    let raw: unknown;
    try { raw = await implementation.stage(context, result, artifact, requestValue); }
    catch { return Object.freeze({ kind: "source_unavailable" as const }); }
    const common = commonOutcome(raw);
    if (common) return common;
    if (raw !== null && typeof raw === "object" && !Array.isArray(raw) && !isProxy(raw)) {
      const kind = Object.getOwnPropertyDescriptor(raw, "kind");
      if (kind && "value" in kind && kind.value === "idempotency_conflict") {
        exactRecord(raw, ["kind"], "invalid_outcome");
        return Object.freeze({ kind: "idempotency_conflict" as const });
      }
    }
    const outcome = exactRecord(raw, ["kind", "artifact"], "invalid_outcome");
    if (outcome["kind"] !== "staged" && outcome["kind"] !== "replayed") fail("invalid_outcome");
    const persisted = parseArtifact(result, outcome["artifact"]);
    if (persisted.artifact_digest !== artifact.artifact_digest) fail("stage_result_mismatch");
    return Object.freeze({ kind: outcome["kind"] as "staged" | "replayed", artifact: persisted });
  },
  async load(contextValue, resultValue) {
    const [context, result] = authority(contextValue, resultValue);
    let raw: unknown;
    try { raw = await implementation.load(context, result); }
    catch { return Object.freeze({ kind: "source_unavailable" as const }); }
    const common = commonOutcome(raw);
    if (common) return common;
    if (raw !== null && typeof raw === "object" && !Array.isArray(raw) && !isProxy(raw)) {
      const kind = Object.getOwnPropertyDescriptor(raw, "kind");
      if (kind && "value" in kind && kind.value === "missing") {
        exactRecord(raw, ["kind"], "invalid_outcome");
        return Object.freeze({ kind: "missing" as const });
      }
    }
    const outcome = exactRecord(raw, ["kind", "artifact"], "invalid_outcome");
    if (outcome["kind"] !== "found") fail("invalid_outcome");
    return Object.freeze({ kind: "found" as const, artifact: parseArtifact(result, outcome["artifact"]) });
  },
});

export const FINALIZED_MEMORY_READ_GROUNDING_VERSION = VERSION;
