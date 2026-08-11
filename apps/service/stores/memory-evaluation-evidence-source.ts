import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  normalizeDurableMemoryWorkResultJson,
  type NormalizedDurableMemoryWorkResultJson,
} from "./durable-memory-work-result-repository";

const SOURCE_PORT: unique symbol = Symbol("memory-evaluation-evidence-source");
const CAPABILITY = "memories.experiments.shadow";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const copiedInputs = new WeakSet<object>();

export type MemoryEvaluationEvidenceSourceKind =
  | "formation_input_snapshot"
  | "authorized_graph_snapshot";

export interface MemoryEvaluationEvidenceSourceRequest {
  readonly source_kind: MemoryEvaluationEvidenceSourceKind;
  readonly source_ref: string;
  readonly input_frontier: string;
}

export interface CopiedMemoryEvaluationInput {
  readonly version: "copied-memory-evaluation-input-v2";
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly source_kind: MemoryEvaluationEvidenceSourceKind;
  readonly source_ref_digest: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly payload: NormalizedDurableMemoryWorkResultJson;
}

export type MemoryEvaluationEvidenceSourceOutcome =
  | Readonly<{ kind: "found"; copied_input: Readonly<CopiedMemoryEvaluationInput> }>
  | Readonly<{ kind: "not_found" | "source_unavailable" | "serialization_retryable" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>;

export interface MemoryEvaluationEvidenceSource {
  readonly [SOURCE_PORT]: true;
  load(
    context: AuthorizedLedgerWriteContext,
    request: MemoryEvaluationEvidenceSourceRequest,
  ): Promise<MemoryEvaluationEvidenceSourceOutcome>;
}

export type MemoryEvaluationEvidenceSourceImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: MemoryEvaluationEvidenceSourceRequest,
) => Promise<unknown>;

const fail = (code: string): never => { throw new TypeError(`memory evaluation evidence source ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const sourceKind = (value: unknown): MemoryEvaluationEvidenceSourceKind => {
  if (value !== "formation_input_snapshot" && value !== "authorized_graph_snapshot") {
    fail("invalid_source_kind");
  }
  return value as MemoryEvaluationEvidenceSourceKind;
};

const request = (value: unknown): Readonly<MemoryEvaluationEvidenceSourceRequest> => {
  const input = exactRecord(value, ["source_kind", "source_ref", "input_frontier"], "invalid_request");
  return Object.freeze({
    source_kind: sourceKind(input["source_kind"]),
    source_ref: token(input["source_ref"], "invalid_request"),
    input_frontier: token(input["input_frontier"], "invalid_request"),
  });
};

const materializeCopiedInput = (
  context: AuthorizedLedgerWriteContext,
  requested: Readonly<MemoryEvaluationEvidenceSourceRequest>,
  payloadValue: unknown,
): Readonly<CopiedMemoryEvaluationInput> => {
  const payload = normalizeDurableMemoryWorkResultJson(payloadValue);
  const sourceRefDigest = sha256CanonicalContent({
    contract_version: "memory-evaluation-source-ref-v1",
    owner_account_id: context.account_id,
    account_epoch: context.account_epoch,
    source_kind: requested.source_kind,
    source_ref: requested.source_ref,
  });
  const inputDigest = sha256CanonicalContent({
    contract_version: "copied-memory-evaluation-input-v2",
    owner_account_id: context.account_id,
    account_epoch: context.account_epoch,
    source_kind: requested.source_kind,
    source_ref_digest: sourceRefDigest,
    input_frontier: requested.input_frontier,
    payload,
  });
  const copied = Object.freeze({
    version: "copied-memory-evaluation-input-v2" as const,
    owner_account_id: context.account_id,
    account_epoch: context.account_epoch,
    source_kind: requested.source_kind,
    source_ref_digest: sourceRefDigest,
    input_frontier: requested.input_frontier,
    input_digest: inputDigest,
    payload,
  });
  copiedInputs.add(copied);
  return copied;
};

export const assertCopiedMemoryEvaluationInput = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<CopiedMemoryEvaluationInput> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (value === null || typeof value !== "object" || !copiedInputs.has(value)) {
    fail("unverified_copied_input");
  }
  const copied = value as Readonly<CopiedMemoryEvaluationInput>;
  if (copied.owner_account_id !== context.account_id || copied.account_epoch !== context.account_epoch) {
    fail("copied_input_authority_mismatch");
  }
  return copied;
};

const outcomeRoot = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "string") fail("invalid_outcome");
  return value as Record<string, unknown>;
};

const commonOutcome = (value: unknown): MemoryEvaluationEvidenceSourceOutcome | null => {
  const root = outcomeRoot(value);
  if (root["kind"] === "not_found" || root["kind"] === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: root["kind"] }) as MemoryEvaluationEvidenceSourceOutcome;
  }
  if (root["kind"] === "stale_context") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = new Set(["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]);
    if (typeof input["reason"] !== "string" || !reasons.has(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind: "stale_context" as const, reason: input["reason"] }) as MemoryEvaluationEvidenceSourceOutcome;
  }
  if (root["kind"] === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = new Set(["credential_inactive", "grant_inactive", "capability_denied"]);
    if (typeof input["reason"] !== "string" || !reasons.has(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind: "authorization_denied" as const, reason: input["reason"] }) as MemoryEvaluationEvidenceSourceOutcome;
  }
  return null;
};

export const defineMemoryEvaluationEvidenceSource = (
  implementation: MemoryEvaluationEvidenceSourceImplementation,
): MemoryEvaluationEvidenceSource => Object.freeze({
  [SOURCE_PORT]: true as const,
  async load(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: MemoryEvaluationEvidenceSourceRequest,
  ) {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== CAPABILITY) fail("capability_denied");
    const requested = request(requestValue);
    let raw: unknown;
    try {
      raw = await implementation(context, requested);
    } catch {
      return Object.freeze({ kind: "source_unavailable" as const });
    }
    const common = commonOutcome(raw);
    if (common !== null) return common;
    const input = exactRecord(raw, [
      "kind", "owner_account_id", "account_epoch", "source_kind", "source_ref",
      "input_frontier", "payload",
    ], "invalid_outcome");
    if (input["kind"] !== "found"
      || input["owner_account_id"] !== context.account_id
      || input["account_epoch"] !== context.account_epoch
      || input["source_kind"] !== requested.source_kind
      || input["source_ref"] !== requested.source_ref
      || input["input_frontier"] !== requested.input_frontier) fail("source_coordinate_mismatch");
    return Object.freeze({
      kind: "found" as const,
      copied_input: materializeCopiedInput(context, requested, input["payload"]),
    });
  },
});
