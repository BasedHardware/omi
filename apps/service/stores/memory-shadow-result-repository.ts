import { isProxy } from "node:util/types";

import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type MemoryStrategyAssignmentEntry,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalJson } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  durableMemoryWorkNormalizedResultDigest,
  normalizeDurableMemoryWorkResultJson,
  type NormalizedDurableMemoryWorkResultJson,
} from "./durable-memory-work-result-repository";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const SHADOW_RESULT_PORT: unique symbol = Symbol("memory-shadow-result-repository");
const CAPABILITY = "memories.experiments.shadow";
const RESULT_VERSION = "memory-evaluation-result-v1" as const;
const PAIR_VERSION = "memory-evaluation-pair-v1" as const;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const RUN_ID = /^mer1_[a-f0-9]{64}$/;
const RESULT_ID = /^msr1_[a-f0-9]{64}$/;
const MAX_REPEAT = 999;
const verifiedResults = new WeakSet<object>();
const verifiedPairs = new WeakSet<object>();

export type MemoryEvaluationRole = "baseline" | "candidate";
export type MemoryEvaluationMode = "live_shadow" | "offline_replay";

export interface MemoryEvaluationCoordinate {
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly assignment_id: string;
  readonly account_epoch: number;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly evaluation_mode: MemoryEvaluationMode;
  readonly evaluation_run_id: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly repeat_ordinal: number;
}

export interface MemoryEvaluationStageBody extends MemoryEvaluationCoordinate {
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result: NormalizedDurableMemoryWorkResultJson;
}

export interface MemoryEvaluationStageRequest extends MemoryEvaluationStageBody {
  readonly request_digest: string;
}

export interface MemoryEvaluationResult {
  readonly version: typeof RESULT_VERSION;
  readonly evaluation_result_id: string;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly assignment_bundle_id: string;
  readonly assignment_bundle_digest: string;
  readonly assignment_id: string;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly evaluation_mode: MemoryEvaluationMode;
  readonly evaluation_run_id: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly repeat_ordinal: number;
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result: NormalizedDurableMemoryWorkResultJson;
  readonly stage_request_digest: string;
}

export interface MemoryEvaluationPair {
  readonly version: typeof PAIR_VERSION;
  readonly pair_id: string;
  readonly pair_digest: string;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly assignment_bundle_id: string;
  readonly evaluation_mode: MemoryEvaluationMode;
  readonly evaluation_run_id: string;
  readonly input_frontier_digest: string;
  readonly input_digest: string;
  readonly repeat_ordinal: number;
  readonly baseline_result_id: string;
  readonly baseline_strategy_id: string;
  readonly baseline_result_digest: string;
  readonly candidate_result_id: string;
  readonly candidate_strategy_id: string;
  readonly candidate_result_digest: string;
}

type CommonOutcome =
  | Readonly<{ kind: "serialization_retryable" }>
  | Readonly<{ kind: "stale_context"; reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive" }>
  | Readonly<{ kind: "authorization_denied"; reason: "credential_inactive" | "grant_inactive" | "capability_denied" }>;

export type MemoryEvaluationStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; result: MemoryEvaluationResult }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export type MemoryEvaluationLoadOutcome =
  | Readonly<{ kind: "found"; result: MemoryEvaluationResult }>
  | Readonly<{ kind: "missing" }>
  | CommonOutcome;

export type MemoryEvaluationPairOutcome =
  | Readonly<{ kind: "recorded" | "replayed"; pair: MemoryEvaluationPair }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export interface MemoryShadowResultRepository {
  readonly [SHADOW_RESULT_PORT]: true;
  load(context: AuthorizedLedgerWriteContext, coordinate: MemoryEvaluationCoordinate): Promise<MemoryEvaluationLoadOutcome>;
  stage(context: AuthorizedLedgerWriteContext, request: MemoryEvaluationStageRequest): Promise<MemoryEvaluationStageOutcome>;
  recordPair(context: AuthorizedLedgerWriteContext, pair: MemoryEvaluationPair): Promise<MemoryEvaluationPairOutcome>;
}

export interface MemoryShadowResultImplementation {
  load(context: AuthorizedLedgerWriteContext, coordinate: MemoryEvaluationCoordinate): Promise<unknown>;
  stage(context: AuthorizedLedgerWriteContext, request: MemoryEvaluationStageRequest): Promise<unknown>;
  recordPair(context: AuthorizedLedgerWriteContext, pair: MemoryEvaluationPair): Promise<unknown>;
}

const fail = (code: string): never => { throw new TypeError(`memory shadow result repository ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(code);
  const objectValue = value as object;
  if (isProxy(objectValue) || Object.getPrototypeOf(objectValue) !== Object.prototype) fail(code);
  const actual = Reflect.ownKeys(objectValue);
  if (actual.some((key) => typeof key !== "string")) fail(code);
  const strings = (actual as string[]).sort();
  const expected = [...keys].sort();
  if (strings.length !== expected.length || strings.some((key, index) => key !== expected[index])) fail(code);
  for (const key of strings) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};
const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value as string;
};
const epoch = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail("invalid_coordinate");
  return value as number;
};
const repeat = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > MAX_REPEAT) {
    fail("invalid_coordinate");
  }
  return value as number;
};

interface NormalizedCoordinate extends MemoryEvaluationCoordinate {
  readonly selected_assignment: Readonly<MemoryStrategyAssignmentEntry>;
  readonly selected_strategy: Readonly<RegisteredMemoryStrategy>;
}

const coordinateFields = (input: Record<string, unknown>): MemoryEvaluationCoordinate => ({
  assignment_bundle: input["assignment_bundle"] as MemoryStrategyAssignmentBundle,
  assignment_id: input["assignment_id"] as string,
  account_epoch: input["account_epoch"] as number,
  evaluation_role: input["evaluation_role"] as MemoryEvaluationRole,
  evaluation_mode: input["evaluation_mode"] as MemoryEvaluationMode,
  evaluation_run_id: input["evaluation_run_id"] as string,
  input_frontier: input["input_frontier"] as string,
  input_digest: input["input_digest"] as string,
  repeat_ordinal: input["repeat_ordinal"] as number,
});

const coordinate = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<NormalizedCoordinate> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  const input = exactRecord(value, [
    "assignment_bundle", "assignment_id", "account_epoch", "evaluation_role",
    "evaluation_mode", "evaluation_run_id", "input_frontier", "input_digest",
    "repeat_ordinal",
  ], "invalid_coordinate");
  const bundle = assertMintedMemoryStrategyAssignment(input["assignment_bundle"]);
  if (bundle.owner_account_id !== context.account_id) fail("owner_mismatch");
  const accountEpoch = epoch(input["account_epoch"]);
  if (accountEpoch !== context.account_epoch) fail("epoch_mismatch");
  const role = input["evaluation_role"];
  if (role !== "baseline" && role !== "candidate") fail("invalid_coordinate");
  const mode = input["evaluation_mode"];
  if (mode !== "live_shadow" && mode !== "offline_replay") fail("invalid_coordinate");
  const assignmentId = token(input["assignment_id"], "invalid_coordinate");
  const selected = role === "baseline"
    ? bundle.authority.assignment_id === assignmentId ? bundle.authority : null
    : bundle.shadows.find((entry) => entry.assignment_id === assignmentId) ?? null;
  if (selected === null || selected.mode !== (role === "baseline" ? "authority" : "shadow")) {
    fail("assignment_role_mismatch");
  }
  const strategy = bundle.strategies.find((entry) => entry.strategy_id === selected!.strategy_id);
  if (!strategy || strategy.execution_contract_digest !== selected!.execution_contract_digest) {
    fail("strategy_mismatch");
  }
  const runId = token(input["evaluation_run_id"], "invalid_coordinate");
  if (!RUN_ID.test(runId)) fail("invalid_coordinate");
  return Object.freeze({
    assignment_bundle: bundle,
    assignment_id: assignmentId,
    account_epoch: accountEpoch,
    evaluation_role: role as MemoryEvaluationRole,
    evaluation_mode: mode as MemoryEvaluationMode,
    evaluation_run_id: runId,
    input_frontier: token(input["input_frontier"], "invalid_coordinate"),
    input_digest: digest(input["input_digest"], "invalid_coordinate"),
    repeat_ordinal: repeat(input["repeat_ordinal"]),
    selected_assignment: selected!,
    selected_strategy: strategy!,
  });
};

const persistedCoordinate = (value: Readonly<NormalizedCoordinate>) => ({
  owner_account_id: value.assignment_bundle.owner_account_id,
  account_epoch: value.account_epoch,
  assignment_bundle_id: value.assignment_bundle.assignment_bundle_id,
  assignment_bundle_digest: value.assignment_bundle.assignment_bundle_digest,
  assignment_id: value.assignment_id,
  evaluation_role: value.evaluation_role,
  evaluation_mode: value.evaluation_mode,
  evaluation_run_id: value.evaluation_run_id,
  input_frontier: value.input_frontier,
  input_digest: value.input_digest,
  repeat_ordinal: value.repeat_ordinal,
  strategy_id: value.selected_strategy.strategy_id,
  execution_contract_digest: value.selected_strategy.execution_contract_digest,
});

const externalCoordinate = (
  value: Readonly<NormalizedCoordinate>,
): Readonly<MemoryEvaluationCoordinate> => Object.freeze({
  assignment_bundle: value.assignment_bundle,
  assignment_id: value.assignment_id,
  account_epoch: value.account_epoch,
  evaluation_role: value.evaluation_role,
  evaluation_mode: value.evaluation_mode,
  evaluation_run_id: value.evaluation_run_id,
  input_frontier: value.input_frontier,
  input_digest: value.input_digest,
  repeat_ordinal: value.repeat_ordinal,
});

export const memoryEvaluationResultId = (
  context: AuthorizedLedgerWriteContext,
  value: MemoryEvaluationCoordinate,
): string => {
  const normalized = coordinate(context, value);
  return `msr1_${sha256CanonicalContent({
    contract_version: "memory-evaluation-result-id-v1",
    ...persistedCoordinate(normalized),
  })}`;
};

export const memoryEvaluationStageRequestDigest = (
  context: AuthorizedLedgerWriteContext,
  value: MemoryEvaluationStageBody,
): string => {
  const input = exactRecord(value, [
    "assignment_bundle", "assignment_id", "account_epoch", "evaluation_role",
    "evaluation_mode", "evaluation_run_id", "input_frontier", "input_digest",
    "repeat_ordinal", "result_contract_version", "response_digest",
    "normalized_result_digest", "normalized_result",
  ], "invalid_stage_request");
  const normalizedCoordinate = coordinate(context, coordinateFields(input));
  const contract = token(input["result_contract_version"], "invalid_stage_request");
  if (contract !== normalizedCoordinate.selected_strategy.coordinates.result_contract_version) {
    fail("result_contract_mismatch");
  }
  const result = normalizeDurableMemoryWorkResultJson(input["normalized_result"]);
  const resultDigest = digest(input["normalized_result_digest"], "invalid_stage_request");
  if (durableMemoryWorkNormalizedResultDigest(contract, result) !== resultDigest) fail("result_digest_mismatch");
  return sha256CanonicalContent({
    contract_version: "memory-evaluation-stage-request-v1",
    ...persistedCoordinate(normalizedCoordinate),
    result_contract_version: contract,
    response_digest: digest(input["response_digest"], "invalid_stage_request"),
    normalized_result_digest: resultDigest,
    normalized_result: result,
  });
};

const stageRequest = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<MemoryEvaluationStageRequest> => {
  const input = exactRecord(value, [
    "assignment_bundle", "assignment_id", "account_epoch", "evaluation_role",
    "evaluation_mode", "evaluation_run_id", "input_frontier", "input_digest",
    "repeat_ordinal", "result_contract_version", "response_digest",
    "normalized_result_digest", "normalized_result", "request_digest",
  ], "invalid_stage_request");
  const body: MemoryEvaluationStageBody = {
    ...coordinateFields(input),
    result_contract_version: input["result_contract_version"] as string,
    response_digest: input["response_digest"] as string,
    normalized_result_digest: input["normalized_result_digest"] as string,
    normalized_result: input["normalized_result"] as NormalizedDurableMemoryWorkResultJson,
  };
  const expected = memoryEvaluationStageRequestDigest(context, body);
  const requestDigest = digest(input["request_digest"], "invalid_stage_request");
  if (requestDigest !== expected) fail("request_digest_mismatch");
  const normalizedCoordinate = coordinate(
    context,
    coordinateFields(body as unknown as Record<string, unknown>),
  );
  const result = normalizeDurableMemoryWorkResultJson(input["normalized_result"]);
  return Object.freeze({
    assignment_bundle: normalizedCoordinate.assignment_bundle,
    assignment_id: normalizedCoordinate.assignment_id,
    account_epoch: normalizedCoordinate.account_epoch,
    evaluation_role: normalizedCoordinate.evaluation_role,
    evaluation_mode: normalizedCoordinate.evaluation_mode,
    evaluation_run_id: normalizedCoordinate.evaluation_run_id,
    input_frontier: normalizedCoordinate.input_frontier,
    input_digest: normalizedCoordinate.input_digest,
    repeat_ordinal: normalizedCoordinate.repeat_ordinal,
    result_contract_version: normalizedCoordinate.selected_strategy.coordinates.result_contract_version,
    response_digest: digest(input["response_digest"], "invalid_stage_request"),
    normalized_result_digest: digest(input["normalized_result_digest"], "invalid_stage_request"),
    normalized_result: result,
    request_digest: requestDigest,
  });
};

export const materializeMemoryEvaluationResult = (
  context: AuthorizedLedgerWriteContext,
  request: MemoryEvaluationStageRequest,
): Readonly<MemoryEvaluationResult> => {
  const validated = stageRequest(context, request);
  const normalized = coordinate(context, coordinateFields(validated as unknown as Record<string, unknown>));
  const result = Object.freeze({
    version: RESULT_VERSION,
    evaluation_result_id: memoryEvaluationResultId(context, externalCoordinate(normalized)),
    ...persistedCoordinate(normalized),
    result_contract_version: validated.result_contract_version,
    response_digest: validated.response_digest,
    normalized_result_digest: validated.normalized_result_digest,
    normalized_result: validated.normalized_result,
    stage_request_digest: validated.request_digest,
  });
  verifiedResults.add(result);
  return result;
};

const parseResult = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
  expected: MemoryEvaluationCoordinate,
): Readonly<MemoryEvaluationResult> => {
  const input = exactRecord(value, [
    "version", "evaluation_result_id", "owner_account_id", "account_epoch",
    "assignment_bundle_id", "assignment_bundle_digest", "assignment_id",
    "evaluation_role", "evaluation_mode", "evaluation_run_id", "input_frontier",
    "input_digest", "repeat_ordinal", "strategy_id", "execution_contract_digest",
    "result_contract_version", "response_digest", "normalized_result_digest",
    "normalized_result", "stage_request_digest",
  ], "invalid_result");
  if (input["version"] !== RESULT_VERSION) fail("invalid_result");
  const expectedCoordinate = coordinate(
    context,
    coordinateFields(expected as unknown as Record<string, unknown>),
  );
  const result = normalizeDurableMemoryWorkResultJson(input["normalized_result"]);
  const normalized = Object.freeze({
    version: RESULT_VERSION,
    evaluation_result_id: token(input["evaluation_result_id"], "invalid_result"),
    owner_account_id: token(input["owner_account_id"], "invalid_result"),
    account_epoch: epoch(input["account_epoch"]),
    assignment_bundle_id: token(input["assignment_bundle_id"], "invalid_result"),
    assignment_bundle_digest: digest(input["assignment_bundle_digest"], "invalid_result"),
    assignment_id: token(input["assignment_id"], "invalid_result"),
    evaluation_role: input["evaluation_role"] as MemoryEvaluationRole,
    evaluation_mode: input["evaluation_mode"] as MemoryEvaluationMode,
    evaluation_run_id: token(input["evaluation_run_id"], "invalid_result"),
    input_frontier: token(input["input_frontier"], "invalid_result"),
    input_digest: digest(input["input_digest"], "invalid_result"),
    repeat_ordinal: repeat(input["repeat_ordinal"]),
    strategy_id: token(input["strategy_id"], "invalid_result"),
    execution_contract_digest: digest(input["execution_contract_digest"], "invalid_result"),
    result_contract_version: token(input["result_contract_version"], "invalid_result"),
    response_digest: digest(input["response_digest"], "invalid_result"),
    normalized_result_digest: digest(input["normalized_result_digest"], "invalid_result"),
    normalized_result: result,
    stage_request_digest: digest(input["stage_request_digest"], "invalid_result"),
  }) satisfies MemoryEvaluationResult;
  const expectedPersisted = persistedCoordinate(expectedCoordinate);
  for (const [key, expectedValue] of Object.entries(expectedPersisted)) {
    if ((normalized as unknown as Record<string, unknown>)[key] !== expectedValue) fail("result_coordinate_mismatch");
  }
  if (!RESULT_ID.test(normalized.evaluation_result_id)
    || normalized.evaluation_result_id !== memoryEvaluationResultId(context, externalCoordinate(expectedCoordinate))
    || normalized.result_contract_version !== expectedCoordinate.selected_strategy.coordinates.result_contract_version
    || durableMemoryWorkNormalizedResultDigest(normalized.result_contract_version, result)
      !== normalized.normalized_result_digest) fail("invalid_result");
  const expectedStageDigest = memoryEvaluationStageRequestDigest(context, {
    ...externalCoordinate(expectedCoordinate),
    result_contract_version: normalized.result_contract_version,
    response_digest: normalized.response_digest,
    normalized_result_digest: normalized.normalized_result_digest,
    normalized_result: normalized.normalized_result,
  });
  if (normalized.stage_request_digest !== expectedStageDigest) fail("invalid_result");
  verifiedResults.add(normalized);
  return normalized;
};

export const pairMemoryEvaluationResults = (
  baseline: MemoryEvaluationResult,
  candidate: MemoryEvaluationResult,
): Readonly<MemoryEvaluationPair> => {
  if (!verifiedResults.has(baseline) || !verifiedResults.has(candidate)) fail("unverified_result");
  if (baseline.evaluation_role !== "baseline" || candidate.evaluation_role !== "candidate") fail("invalid_pair");
  const sharedKeys = [
    "owner_account_id", "account_epoch", "assignment_bundle_id", "evaluation_mode",
    "evaluation_run_id", "input_frontier", "input_digest", "repeat_ordinal",
  ] as const;
  for (const key of sharedKeys) if (baseline[key] !== candidate[key]) fail("unpaired_results");
  if (baseline.strategy_id === candidate.strategy_id) fail("invalid_pair");
  const core = Object.freeze({
    version: PAIR_VERSION,
    owner_account_id: baseline.owner_account_id,
    account_epoch: baseline.account_epoch,
    assignment_bundle_id: baseline.assignment_bundle_id,
    evaluation_mode: baseline.evaluation_mode,
    evaluation_run_id: baseline.evaluation_run_id,
    input_frontier_digest: sha256CanonicalContent({
      contract_version: "memory-evaluation-frontier-ref-v1",
      input_frontier: baseline.input_frontier,
    }),
    input_digest: baseline.input_digest,
    repeat_ordinal: baseline.repeat_ordinal,
    baseline_result_id: baseline.evaluation_result_id,
    baseline_strategy_id: baseline.strategy_id,
    baseline_result_digest: baseline.normalized_result_digest,
    candidate_result_id: candidate.evaluation_result_id,
    candidate_strategy_id: candidate.strategy_id,
    candidate_result_digest: candidate.normalized_result_digest,
  });
  const pairDigest = sha256CanonicalContent(core);
  const pair = Object.freeze({ ...core, pair_id: `mep1_${pairDigest}`, pair_digest: pairDigest });
  verifiedPairs.add(pair);
  return pair;
};

export const assertVerifiedMemoryEvaluationPair = (value: unknown): Readonly<MemoryEvaluationPair> => {
  if (value === null || typeof value !== "object" || !verifiedPairs.has(value)) fail("unverified_pair");
  return value as Readonly<MemoryEvaluationPair>;
};

const parsePairReplay = (
  value: unknown,
  expected: Readonly<MemoryEvaluationPair>,
): Readonly<MemoryEvaluationPair> => {
  const keys = [
    "version", "pair_id", "pair_digest", "owner_account_id", "account_epoch",
    "assignment_bundle_id", "evaluation_mode", "evaluation_run_id", "input_frontier_digest",
    "input_digest", "repeat_ordinal", "baseline_result_id", "baseline_strategy_id",
    "baseline_result_digest", "candidate_result_id", "candidate_strategy_id",
    "candidate_result_digest",
  ] as const;
  const input = exactRecord(value, keys, "invalid_pair_outcome");
  for (const key of keys) if (input[key] !== expected[key]) fail("invalid_pair_outcome");
  return expected;
};

const commonOutcome = (value: unknown): CommonOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) fail("invalid_outcome");
  const kind = Object.getOwnPropertyDescriptor(value, "kind");
  const name = kind && "value" in kind && kind.enumerable ? kind.value : fail("invalid_outcome");
  if (name === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: name });
  }
  if (name === "stale_context" || name === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const allowed = name === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !allowed.includes(input["reason"])) fail("invalid_outcome");
    return Object.freeze({ kind: name, reason: input["reason"] }) as CommonOutcome;
  }
  return null;
};

export const defineMemoryShadowResultRepository = (
  implementation: MemoryShadowResultImplementation,
): MemoryShadowResultRepository => Object.freeze({
  [SHADOW_RESULT_PORT]: true as const,
  async load(
    contextValue: AuthorizedLedgerWriteContext,
    coordinateValue: MemoryEvaluationCoordinate,
  ): Promise<MemoryEvaluationLoadOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    const normalized = coordinate(context, coordinateValue);
    const requested = externalCoordinate(normalized);
    const raw = await implementation.load(context, requested);
    const common = commonOutcome(raw);
    if (common) return common;
    const root = exactRecord(raw, ["kind", ...((raw as { kind?: unknown }).kind === "found" ? ["result"] : [])], "invalid_outcome");
    if (root["kind"] === "missing") return Object.freeze({ kind: "missing" as const });
    if (root["kind"] === "found") return Object.freeze({
      kind: "found" as const,
      result: parseResult(context, root["result"], requested),
    });
    return fail("invalid_outcome");
  },
  async stage(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: MemoryEvaluationStageRequest,
  ): Promise<MemoryEvaluationStageOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    const normalized = stageRequest(context, requestValue);
    const raw = await implementation.stage(context, normalized);
    const common = commonOutcome(raw);
    if (common) return common;
    const root = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "staged" || (raw as { kind?: unknown }).kind === "replayed"
        ? ["result"] : []
    )], "invalid_outcome");
    if (root["kind"] === "idempotency_conflict") return Object.freeze({ kind: "idempotency_conflict" as const });
    if (root["kind"] === "staged" || root["kind"] === "replayed") return Object.freeze({
      kind: root["kind"] as "staged" | "replayed",
      result: parseResult(context, root["result"], normalized),
    });
    return fail("invalid_outcome");
  },
  async recordPair(
    contextValue: AuthorizedLedgerWriteContext,
    pairValue: MemoryEvaluationPair,
  ): Promise<MemoryEvaluationPairOutcome> {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== CAPABILITY) fail("capability_denied");
    const pair = assertVerifiedMemoryEvaluationPair(pairValue);
    if (pair.owner_account_id !== context.account_id) fail("owner_mismatch");
    if (pair.account_epoch !== context.account_epoch) fail("epoch_mismatch");
    const raw = await implementation.recordPair(context, pair);
    const common = commonOutcome(raw);
    if (common) return common;
    const root = exactRecord(raw, ["kind", ...(
      (raw as { kind?: unknown }).kind === "recorded" || (raw as { kind?: unknown }).kind === "replayed"
        ? ["pair"] : []
    )], "invalid_outcome");
    if (root["kind"] === "idempotency_conflict") return Object.freeze({ kind: "idempotency_conflict" as const });
    if (root["kind"] === "recorded" || root["kind"] === "replayed") return Object.freeze({
      kind: root["kind"] as "recorded" | "replayed",
      pair: parsePairReplay(root["pair"], pair),
    });
    return fail("invalid_outcome");
  },
});
