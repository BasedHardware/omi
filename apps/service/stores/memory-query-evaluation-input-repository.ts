import { isProxy } from "node:util/types";

import type { GraphSnapshot } from "../../../core/retrieve";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const PORT: unique symbol = Symbol("memory-query-evaluation-input-repository");
const CAPABILITY = "memories.experiments.shadow";
const VERSION = "memory-query-evaluation-input-v1" as const;
const INPUT_REF = /^mqir1_[a-f0-9]{64}$/;
const SOURCE_REF = /^mqes1_[a-f0-9]{64}$/;
const FRONTIER = /^mqef1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const TIMEZONE = /^[\x21-\x7e]{1,128}$/;
const MAX_QUERY_CODE_POINTS = 4_096;
const verified = new WeakSet<object>();

export interface MemoryQueryEvaluationInputBody {
  readonly input_ref: string;
  readonly query_text: string;
  readonly account_timezone: string;
  readonly graph_snapshot: GraphSnapshot;
}

export interface MemoryQueryEvaluationInput {
  readonly version: typeof VERSION;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly input_ref: string;
  readonly source_ref: string;
  readonly input_frontier: string;
  readonly query_text: string;
  readonly account_timezone: string;
  readonly graph_generation: number;
  readonly graph_snapshot_digest: string;
  readonly stage_request_digest: string;
}

type CommonOutcome =
  | Readonly<{ kind: "serialization_retryable" }>
  | Readonly<{ kind: "stale_context"; reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive" }>
  | Readonly<{ kind: "authorization_denied"; reason: "credential_inactive" | "grant_inactive" | "capability_denied" }>;

export type MemoryQueryEvaluationInputStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; input: Readonly<MemoryQueryEvaluationInput> }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export type MemoryQueryEvaluationInputLoadOutcome =
  | Readonly<{ kind: "found"; input: Readonly<MemoryQueryEvaluationInput> }>
  | Readonly<{ kind: "missing" }>
  | CommonOutcome;

export interface MemoryQueryEvaluationInputRepository {
  readonly [PORT]: true;
  stage(context: AuthorizedLedgerWriteContext, input: MemoryQueryEvaluationInput): Promise<MemoryQueryEvaluationInputStageOutcome>;
  load(context: AuthorizedLedgerWriteContext, sourceRef: string): Promise<MemoryQueryEvaluationInputLoadOutcome>;
}

export interface MemoryQueryEvaluationInputRepositoryImplementation {
  stage(context: AuthorizedLedgerWriteContext, input: Readonly<MemoryQueryEvaluationInput>): Promise<unknown>;
  load(context: AuthorizedLedgerWriteContext, sourceRef: string): Promise<unknown>;
}

const fail = (code: string): never => { throw new TypeError(`memory query evaluation input ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || (actual as string[]).some((key) => !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const authority = (value: AuthorizedLedgerWriteContext): AuthorizedLedgerWriteContext => {
  const context = assertAuthorizedLedgerWriteContext(value);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  return context;
};

const graphGeneration = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail("invalid_graph");
  return value as number;
};

const boundedQuery = (value: unknown): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > MAX_QUERY_CODE_POINTS || /[\p{Cs}\u0000]/u.test(value)) fail("invalid_query");
  return value;
};

const accountTimezone = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TIMEZONE.test(value)) fail(code);
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
  } catch {
    fail(code);
  }
  return value;
};

const inputCore = (
  context: AuthorizedLedgerWriteContext,
  inputRef: string,
  queryText: string,
  timezone: string,
  graph: GraphSnapshot,
) => {
  if (!INPUT_REF.test(inputRef)
    || graph === null || typeof graph !== "object" || graph.owner_account_id !== context.account_id) {
    fail("invalid_input");
  }
  const generation = graphGeneration(graph.graph_generation);
  let snapshotDigest: string;
  try { snapshotDigest = sha256CanonicalContent(graph); }
  catch { return fail("invalid_graph"); }
  const coordinate = {
    contract_version: VERSION,
    owner_account_id: context.account_id,
    account_epoch: context.account_epoch,
    input_ref: inputRef,
    query_text: boundedQuery(queryText),
    account_timezone: accountTimezone(timezone, "invalid_input"),
    graph_generation: generation,
    graph_snapshot_digest: snapshotDigest,
  };
  const stageDigest = sha256CanonicalContent(coordinate);
  return Object.freeze({
    ...coordinate,
    source_ref: `mqes1_${sha256CanonicalContent({
      contract_version: "memory-query-evaluation-source-ref-v1",
      owner_account_id: context.account_id,
      account_epoch: context.account_epoch,
      input_ref: inputRef,
    })}`,
    input_frontier: `mqef1_${sha256CanonicalContent({
      contract_version: "memory-query-evaluation-frontier-v1",
      graph_generation: generation,
      graph_snapshot_digest: snapshotDigest,
    })}`,
    stage_request_digest: stageDigest,
  });
};

export const materializeMemoryQueryEvaluationInput = (
  contextValue: AuthorizedLedgerWriteContext,
  bodyValue: MemoryQueryEvaluationInputBody,
): Readonly<MemoryQueryEvaluationInput> => {
  const context = authority(contextValue);
  const body = exactRecord(bodyValue, [
    "input_ref", "query_text", "account_timezone", "graph_snapshot",
  ], "invalid_input");
  const core = inputCore(
    context,
    body["input_ref"] as string,
    body["query_text"] as string,
    body["account_timezone"] as string,
    body["graph_snapshot"] as GraphSnapshot,
  );
  const input = Object.freeze({
    version: VERSION,
    owner_account_id: core.owner_account_id,
    account_epoch: core.account_epoch,
    input_ref: core.input_ref,
    source_ref: core.source_ref,
    input_frontier: core.input_frontier,
    query_text: core.query_text,
    account_timezone: core.account_timezone,
    graph_generation: core.graph_generation,
    graph_snapshot_digest: core.graph_snapshot_digest,
    stage_request_digest: core.stage_request_digest,
  });
  verified.add(input);
  return input;
};

const parseInput = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
  expectedSourceRef: string | null,
): Readonly<MemoryQueryEvaluationInput> => {
  const row = exactRecord(value, [
    "version", "owner_account_id", "account_epoch", "input_ref", "source_ref",
    "input_frontier", "query_text", "account_timezone", "graph_generation",
    "graph_snapshot_digest", "stage_request_digest",
  ], "invalid_stored_input");
  if (row["version"] !== VERSION || row["owner_account_id"] !== context.account_id
    || row["account_epoch"] !== context.account_epoch
    || typeof row["input_ref"] !== "string" || !INPUT_REF.test(row["input_ref"])
    || typeof row["source_ref"] !== "string" || !SOURCE_REF.test(row["source_ref"])
    || (expectedSourceRef !== null && row["source_ref"] !== expectedSourceRef)
    || typeof row["input_frontier"] !== "string" || !FRONTIER.test(row["input_frontier"])
    || typeof row["graph_snapshot_digest"] !== "string" || !DIGEST.test(row["graph_snapshot_digest"])
    || typeof row["stage_request_digest"] !== "string" || !DIGEST.test(row["stage_request_digest"])) {
    fail("invalid_stored_input");
  }
  const detached = Object.freeze({
    version: VERSION,
    owner_account_id: row["owner_account_id"] as string,
    account_epoch: row["account_epoch"] as number,
    input_ref: row["input_ref"] as string,
    source_ref: row["source_ref"] as string,
    input_frontier: row["input_frontier"] as string,
    query_text: boundedQuery(row["query_text"]),
    account_timezone: accountTimezone(row["account_timezone"], "invalid_stored_input"),
    graph_generation: graphGeneration(row["graph_generation"]),
    graph_snapshot_digest: row["graph_snapshot_digest"] as string,
    stage_request_digest: row["stage_request_digest"] as string,
  });
  const expectedSource = `mqes1_${sha256CanonicalContent({
    contract_version: "memory-query-evaluation-source-ref-v1",
    owner_account_id: detached.owner_account_id,
    account_epoch: detached.account_epoch,
    input_ref: detached.input_ref,
  })}`;
  const expectedFrontier = `mqef1_${sha256CanonicalContent({
    contract_version: "memory-query-evaluation-frontier-v1",
    graph_generation: detached.graph_generation,
    graph_snapshot_digest: detached.graph_snapshot_digest,
  })}`;
  const expectedStageDigest = sha256CanonicalContent({
    contract_version: VERSION,
    owner_account_id: detached.owner_account_id,
    account_epoch: detached.account_epoch,
    input_ref: detached.input_ref,
    query_text: detached.query_text,
    account_timezone: detached.account_timezone,
    graph_generation: detached.graph_generation,
    graph_snapshot_digest: detached.graph_snapshot_digest,
  });
  if (detached.source_ref !== expectedSource || detached.input_frontier !== expectedFrontier
    || detached.stage_request_digest !== expectedStageDigest) fail("invalid_stored_input");
  verified.add(detached);
  return detached;
};

export const assertVerifiedMemoryQueryEvaluationInput = (
  value: unknown,
): Readonly<MemoryQueryEvaluationInput> => {
  if (value === null || typeof value !== "object" || !verified.has(value)) fail("unverified_input");
  return value as Readonly<MemoryQueryEvaluationInput>;
};

const common = (value: unknown): CommonOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) fail("invalid_outcome");
  const kind = Object.getOwnPropertyDescriptor(value, "kind");
  const name = kind && "value" in kind && kind.enumerable ? kind.value : fail("invalid_outcome");
  if (name === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: name });
  }
  if (name === "stale_context" || name === "authorization_denied") {
    const result = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const allowed = name === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof result["reason"] !== "string" || !allowed.includes(result["reason"] as string)) fail("invalid_outcome");
    return Object.freeze({ kind: name, reason: result["reason"] }) as CommonOutcome;
  }
  return null;
};

const outcomeKind = (value: unknown): string => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "string") fail("invalid_outcome");
  return descriptor.value;
};

export const defineMemoryQueryEvaluationInputRepository = (
  implementation: MemoryQueryEvaluationInputRepositoryImplementation,
): MemoryQueryEvaluationInputRepository => Object.freeze({
  [PORT]: true as const,
  async stage(contextValue, inputValue) {
    const context = authority(contextValue);
    const input = assertVerifiedMemoryQueryEvaluationInput(inputValue);
    if (input.owner_account_id !== context.account_id || input.account_epoch !== context.account_epoch) fail("authority_mismatch");
    const raw = await implementation.stage(context, input);
    const shared = common(raw);
    if (shared) return shared;
    const kind = outcomeKind(raw);
    const outcome = exactRecord(raw, ["kind", ...(
      kind === "staged" || kind === "replayed"
        ? ["input"] : []
    )], "invalid_outcome");
    if (outcome["kind"] === "idempotency_conflict") return Object.freeze({ kind: "idempotency_conflict" as const });
    if (outcome["kind"] !== "staged" && outcome["kind"] !== "replayed") fail("invalid_outcome");
    const persisted = parseInput(context, outcome["input"], input.source_ref);
    if (persisted.stage_request_digest !== input.stage_request_digest) fail("stage_result_mismatch");
    return Object.freeze({ kind: outcome["kind"] as "staged" | "replayed", input: persisted });
  },
  async load(contextValue, sourceRefValue) {
    const context = authority(contextValue);
    if (typeof sourceRefValue !== "string" || !SOURCE_REF.test(sourceRefValue)) fail("invalid_source_ref");
    const raw = await implementation.load(context, sourceRefValue);
    const shared = common(raw);
    if (shared) return shared;
    const kind = outcomeKind(raw);
    const outcome = exactRecord(raw, ["kind", ...(kind === "found" ? ["input"] : [])], "invalid_outcome");
    if (outcome["kind"] === "missing") return Object.freeze({ kind: "missing" as const });
    if (outcome["kind"] !== "found") fail("invalid_outcome");
    return Object.freeze({ kind: "found" as const, input: parseInput(context, outcome["input"], sourceRefValue) });
  },
});

export const MEMORY_QUERY_EVALUATION_INPUT_VERSION = VERSION;
