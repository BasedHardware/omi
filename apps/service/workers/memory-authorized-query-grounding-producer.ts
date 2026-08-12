import { isProxy } from "node:util/types";

import type { DurableMemoryWorkErrorCode } from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type MemoryStrategyAssignmentEntry,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  buildContentSafeRecallTrace,
  type ContentSafeRecallTrace,
  type RecallTraceRef,
} from "../../../core/retrieve/recall-integrity";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkNormalizedResultDigest,
} from "../stores/durable-memory-work-result-repository";
import type {
  CopiedMemoryEvaluationInput,
  MemoryEvaluationEvidenceSource,
  MemoryEvaluationEvidenceSourceRequest,
} from "../stores/memory-evaluation-evidence-source";
import type {
  FinalizedMemoryReadGroundingArtifact,
  MemoryReadGroundingRepository,
} from "../stores/memory-read-grounding-repository";
import {
  materializeFinalizedMemoryReadGrounding,
} from "../stores/memory-read-grounding-repository";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  type MemoryEvaluationCoordinate,
  type MemoryEvaluationResult,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageBody,
  type MemoryEvaluationStageRequest,
  type MemoryShadowResultRepository,
} from "../stores/memory-shadow-result-repository";
import {
  buildMemoryReadEvaluationResult,
  parseMemoryReadEvaluationResult,
  type MemoryReadEvaluationAssertion,
} from "./memory-read-evaluation-result";

const PORT: unique symbol = Symbol("memory-authorized-query-grounding-producer");
const CAPABILITY = "memories.experiments.shadow";
const INPUT_VERSION = "authorized-query-evaluation-input-v1" as const;
const RESULT_CONTRACT = "memory-read-evaluation-result-v1";
const RUN_ID = /^mer1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const SUBJECT_CLASS = /^[a-z][a-z0-9_-]{0,63}$/;
const MAX_CANDIDATES = 10_000;
const MAX_CLASSES = 32;
const MAX_QUERY_CODE_POINTS = 4_096;
const MAX_CANDIDATE_CODE_POINTS = 65_536;
const MAX_REPEAT = 19;
const ERROR_CODES = new Set<DurableMemoryWorkErrorCode>([
  "model_timeout", "model_rate_limited", "model_response_invalid",
  "prompt_budget_exceeded", "dependency_unavailable", "serialization_retryable", "worker_lost",
]);

export interface AuthorizedQueryEvaluationCandidate {
  readonly trace_ref: RecallTraceRef;
  readonly text: string;
  readonly contributing_subject_classes: readonly string[];
}

export interface AuthorizedQueryEvaluationInput {
  readonly version: typeof INPUT_VERSION;
  readonly query_text: string;
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projected_content_digest: string;
  readonly classifier_version: string;
  readonly candidates: readonly Readonly<AuthorizedQueryEvaluationCandidate>[];
}

export interface AuthorizedQueryGroundingProducerRequest {
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly assignment_id: string;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly evaluation_run_id: string;
  readonly repeat_ordinal: number;
  readonly source_request: MemoryEvaluationEvidenceSourceRequest;
}

export interface AuthorizedQueryModelCandidate {
  readonly trace_ref: RecallTraceRef;
  readonly text: string;
}

export interface AuthorizedQueryModelRequest {
  readonly query_text: string;
  readonly candidates: readonly Readonly<AuthorizedQueryModelCandidate>[];
  readonly strategy: Readonly<RegisteredMemoryStrategy>;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly repeat_ordinal: number;
}

export type AuthorizedQueryModelOutcome =
  | Readonly<{
      kind: "produced";
      response_digest: string;
      answer_text: string | null;
      absence: "query_gap" | null;
      assertions: readonly Readonly<MemoryReadEvaluationAssertion>[];
      recall_trace: Readonly<ContentSafeRecallTrace>;
    }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export type AuthorizedQueryGroundingStopCode =
  | "input_unavailable"
  | "invalid_input"
  | "read_invalidated"
  | "producer_failed"
  | "invalid_result"
  | "storage_retryable"
  | "storage_unavailable"
  | "authorization_or_context"
  | "idempotency_conflict"
  | "incomplete_persistence";

export type AuthorizedQueryGroundingProducerOutcome =
  | Readonly<{
      kind: "completed";
      completion: "staged" | "replayed";
      result: Readonly<MemoryEvaluationResult>;
      artifact: Readonly<FinalizedMemoryReadGroundingArtifact>;
      model_calls: 0 | 1;
    }>
  | Readonly<{
      kind: "stopped";
      stop_code: AuthorizedQueryGroundingStopCode;
      failure_code: DurableMemoryWorkErrorCode | null;
      model_calls: 0 | 1;
    }>;

export interface MemoryAuthorizedQueryGroundingProducer {
  readonly [PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    request: AuthorizedQueryGroundingProducerRequest,
  ): Promise<AuthorizedQueryGroundingProducerOutcome>;
}

export interface MemoryAuthorizedQueryGroundingDependencies {
  readonly evidence_source: MemoryEvaluationEvidenceSource;
  readonly result_repository: MemoryShadowResultRepository;
  readonly grounding_repository: MemoryReadGroundingRepository;
  readonly produce: (request: AuthorizedQueryModelRequest) => Promise<AuthorizedQueryModelOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`memory authorized query grounding ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export const assertMemoryAuthorizedQueryGroundingProducer = (
  value: unknown,
): MemoryAuthorizedQueryGroundingProducer => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("unverified_producer");
  const brand = Object.getOwnPropertyDescriptor(value, PORT);
  const run = Object.getOwnPropertyDescriptor(value, "run");
  if (!brand || !("value" in brand) || brand.value !== true
    || !run || !("value" in run) || typeof run.value !== "function" || !run.enumerable) {
    fail("unverified_producer");
  }
  return value as MemoryAuthorizedQueryGroundingProducer;
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

const exactArray = (value: unknown, minimum: number, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < minimum || value.length > maximum) fail(code);
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

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const boundedText = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > maximum || /[\p{Cs}\u0000]/u.test(value)) fail(code);
  return value;
};

const parseInput = (copied: Readonly<CopiedMemoryEvaluationInput>): Readonly<AuthorizedQueryEvaluationInput> => {
  if (copied.source_kind !== "authorized_graph_snapshot") fail("invalid_source_kind");
  const input = exactRecord(copied.payload, [
    "version", "query_text", "projection_authorization_digest", "reader_projection_digest",
    "projected_content_digest", "classifier_version", "candidates",
  ], "invalid_input");
  if (input["version"] !== INPUT_VERSION) fail("invalid_input");
  const candidates = exactArray(input["candidates"], 0, MAX_CANDIDATES, "invalid_candidates").map((value) => {
    const candidate = exactRecord(value, [
      "trace_ref", "text", "contributing_subject_classes",
    ], "invalid_candidate");
    const traceRef = candidate["trace_ref"];
    if (typeof traceRef !== "string" || !TRACE_REF.test(traceRef)) fail("invalid_candidate");
    const classes = exactArray(
      candidate["contributing_subject_classes"], 1, MAX_CLASSES, "invalid_candidate",
    ).map((subjectClass) => {
      if (typeof subjectClass !== "string" || !SUBJECT_CLASS.test(subjectClass)) fail("invalid_candidate");
      return subjectClass;
    });
    if (new Set(classes).size !== classes.length
      || classes.some((item, index) => index > 0 && compare(classes[index - 1]!, item) >= 0)) fail("invalid_candidate");
    return Object.freeze({
      trace_ref: traceRef as RecallTraceRef,
      text: boundedText(candidate["text"], MAX_CANDIDATE_CODE_POINTS, "invalid_candidate"),
      contributing_subject_classes: Object.freeze(classes),
    });
  });
  if (new Set(candidates.map((candidate) => candidate.trace_ref)).size !== candidates.length
    || candidates.some((item, index) => index > 0 && compare(candidates[index - 1]!.trace_ref, item.trace_ref) >= 0)) {
    fail("invalid_candidates");
  }
  return Object.freeze({
    version: INPUT_VERSION,
    query_text: boundedText(input["query_text"], MAX_QUERY_CODE_POINTS, "invalid_query"),
    projection_authorization_digest: digest(input["projection_authorization_digest"], "invalid_projection"),
    reader_projection_digest: digest(input["reader_projection_digest"], "invalid_projection"),
    projected_content_digest: digest(input["projected_content_digest"], "invalid_projection"),
    classifier_version: token(input["classifier_version"], "invalid_classifier"),
    candidates: Object.freeze(candidates),
  });
};

interface NormalizedRequest {
  readonly bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly assignment: Readonly<MemoryStrategyAssignmentEntry>;
  readonly strategy: Readonly<RegisteredMemoryStrategy>;
  readonly role: MemoryEvaluationRole;
  readonly run_id: string;
  readonly repeat_ordinal: number;
  readonly source_request: Readonly<MemoryEvaluationEvidenceSourceRequest>;
}

const normalizeRequest = (
  context: AuthorizedLedgerWriteContext,
  value: AuthorizedQueryGroundingProducerRequest,
): NormalizedRequest => {
  const input = exactRecord(value, [
    "assignment_bundle", "assignment_id", "evaluation_role", "evaluation_run_id",
    "repeat_ordinal", "source_request",
  ], "invalid_request");
  const bundle = assertMintedMemoryStrategyAssignment(input["assignment_bundle"]);
  if (bundle.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (bundle.work_kind !== "retrieval" && bundle.work_kind !== "composition") fail("not_read_strategy");
  const role = input["evaluation_role"];
  if (role !== "baseline" && role !== "candidate") fail("invalid_role");
  const assignmentId = token(input["assignment_id"], "invalid_request");
  const assignment = role === "baseline"
    ? bundle.authority.assignment_id === assignmentId ? bundle.authority : null
    : bundle.shadows.find((candidate) => candidate.assignment_id === assignmentId) ?? null;
  if (!assignment || assignment.mode !== (role === "baseline" ? "authority" : "shadow")) fail("assignment_role_mismatch");
  const strategy = bundle.strategies.find((candidate) => candidate.strategy_id === assignment.strategy_id
    && candidate.execution_contract_digest === assignment.execution_contract_digest) ?? fail("strategy_missing");
  if (strategy.coordinates.result_contract_version !== RESULT_CONTRACT) fail("wrong_result_contract");
  const runId = token(input["evaluation_run_id"], "invalid_request");
  if (!RUN_ID.test(runId)) fail("invalid_request");
  const repeat = input["repeat_ordinal"];
  if (!Number.isSafeInteger(repeat) || (repeat as number) < 0 || (repeat as number) > MAX_REPEAT) fail("invalid_repeat");
  const source = exactRecord(input["source_request"], [
    "source_kind", "source_ref", "input_frontier",
  ], "invalid_source_request");
  if (source["source_kind"] !== "authorized_graph_snapshot") fail("invalid_source_kind");
  return Object.freeze({
    bundle,
    assignment,
    strategy,
    role,
    run_id: runId,
    repeat_ordinal: repeat as number,
    source_request: Object.freeze({
      source_kind: "authorized_graph_snapshot" as const,
      source_ref: token(source["source_ref"], "invalid_source_request"),
      input_frontier: token(source["input_frontier"], "invalid_source_request"),
    }),
  });
};

const parseProduced = (value: unknown): AuthorizedQueryModelOutcome => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_producer_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_producer_outcome");
  const kind = descriptor.value;
  const root = exactRecord(value, kind === "produced"
    ? ["kind", "response_digest", "answer_text", "absence", "assertions", "recall_trace"]
    : ["kind", "error_code"], "invalid_producer_outcome");
  if (kind === "failed") {
    if (typeof root["error_code"] !== "string"
      || !ERROR_CODES.has(root["error_code"] as DurableMemoryWorkErrorCode)) fail("invalid_producer_outcome");
    return Object.freeze({ kind: "failed" as const, error_code: root["error_code"] as DurableMemoryWorkErrorCode });
  }
  if (kind !== "produced") fail("invalid_producer_outcome");
  return Object.freeze({
    kind: "produced" as const,
    response_digest: root["response_digest"] as string,
    answer_text: root["answer_text"] as string | null,
    absence: root["absence"] as "query_gap" | null,
    assertions: root["assertions"] as readonly Readonly<MemoryReadEvaluationAssertion>[],
    recall_trace: root["recall_trace"] as Readonly<ContentSafeRecallTrace>,
  });
};

const coordinate = (
  request: NormalizedRequest,
  context: AuthorizedLedgerWriteContext,
  copied: Readonly<CopiedMemoryEvaluationInput>,
): Readonly<MemoryEvaluationCoordinate> => Object.freeze({
  assignment_bundle: request.bundle,
  assignment_id: request.assignment.assignment_id,
  account_epoch: context.account_epoch,
  evaluation_role: request.role,
  evaluation_mode: "offline_replay" as const,
  evaluation_run_id: request.run_id,
  input_frontier: copied.input_frontier,
  input_digest: copied.input_digest,
  repeat_ordinal: request.repeat_ordinal,
});

const stop = (
  code: AuthorizedQueryGroundingStopCode,
  modelCalls: 0 | 1,
  failureCode: DurableMemoryWorkErrorCode | null = null,
): AuthorizedQueryGroundingProducerOutcome => Object.freeze({
  kind: "stopped" as const,
  stop_code: code,
  failure_code: failureCode,
  model_calls: modelCalls,
});

const sourceStop = (kind: string): AuthorizedQueryGroundingStopCode => {
  if (kind === "serialization_retryable") return "storage_retryable";
  if (kind === "stale_context" || kind === "authorization_denied") return "authorization_or_context";
  return "input_unavailable";
};

const storageStop = (kind: string): AuthorizedQueryGroundingStopCode => {
  if (kind === "serialization_retryable") return "storage_retryable";
  if (kind === "stale_context" || kind === "authorization_denied") return "authorization_or_context";
  if (kind === "idempotency_conflict") return "idempotency_conflict";
  return "storage_unavailable";
};

export const defineMemoryAuthorizedQueryGroundingProducer = (
  dependencies: MemoryAuthorizedQueryGroundingDependencies,
): MemoryAuthorizedQueryGroundingProducer => {
  const dependencyRecord = exactRecord(dependencies, [
    "evidence_source", "result_repository", "grounding_repository", "produce",
  ], "invalid_dependencies");
  const evidenceSource = dependencyRecord["evidence_source"] as MemoryEvaluationEvidenceSource;
  const resultRepository = dependencyRecord["result_repository"] as MemoryShadowResultRepository;
  const groundingRepository = dependencyRecord["grounding_repository"] as MemoryReadGroundingRepository;
  const produce = dependencyRecord["produce"];
  if (typeof produce !== "function" || isProxy(produce)) fail("invalid_dependencies");
  return Object.freeze({
    [PORT]: true as const,
    async run(contextValue, requestValue) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== CAPABILITY) fail("capability_denied");
      const request = normalizeRequest(context, requestValue);

      let firstLoad;
      try { firstLoad = await evidenceSource.load(context, request.source_request); }
      catch { return stop("invalid_input", 0); }
      if (firstLoad.kind !== "found") return stop(sourceStop(firstLoad.kind), 0);
      const copied = firstLoad.copied_input;
      let input: Readonly<AuthorizedQueryEvaluationInput>;
      try { input = parseInput(copied); }
      catch { return stop("invalid_input", 0); }
      const resultCoordinate = coordinate(request, context, copied);

      let loadedResult;
      try { loadedResult = await resultRepository.load(context, resultCoordinate); }
      catch { return stop("storage_unavailable", 0); }
      if (loadedResult.kind === "found") {
        let loadedArtifact;
        try { loadedArtifact = await groundingRepository.load(context, loadedResult.result); }
        catch { return stop("storage_unavailable", 0); }
        if (loadedArtifact.kind === "found") {
          let replayRevalidation;
          try { replayRevalidation = await evidenceSource.load(context, request.source_request); }
          catch { return stop("read_invalidated", 0); }
          if (replayRevalidation.kind !== "found"
            || replayRevalidation.copied_input.input_digest !== copied.input_digest) {
            return stop("read_invalidated", 0);
          }
          return Object.freeze({
            kind: "completed" as const,
            completion: "replayed" as const,
            result: loadedResult.result,
            artifact: loadedArtifact.artifact,
            model_calls: 0 as const,
          });
        }
        if (loadedArtifact.kind === "missing") return stop("incomplete_persistence", 0);
        return stop(storageStop(loadedArtifact.kind), 0);
      }
      if (loadedResult.kind !== "missing") return stop(storageStop(loadedResult.kind), 0);

      const modelRequest = Object.freeze({
        query_text: input.query_text,
        candidates: Object.freeze(input.candidates.map((candidate) => Object.freeze({
          trace_ref: candidate.trace_ref,
          text: candidate.text,
        }))),
        strategy: request.strategy,
        evaluation_role: request.role,
        repeat_ordinal: request.repeat_ordinal,
      });
      let modelCalls: 0 | 1;
      let produced: Exclude<AuthorizedQueryModelOutcome, { kind: "failed" }>;
      if (input.candidates.length === 0) {
        modelCalls = 0;
        produced = Object.freeze({
          kind: "produced" as const,
          response_digest: sha256CanonicalContent({
            contract_version: "authorized-query-empty-result-v1",
            input_digest: copied.input_digest,
            strategy_id: request.strategy.strategy_id,
            execution_contract_digest: request.strategy.execution_contract_digest,
            evaluation_role: request.role,
            repeat_ordinal: request.repeat_ordinal,
          }),
          answer_text: null,
          absence: "query_gap" as const,
          assertions: Object.freeze([]),
          recall_trace: buildContentSafeRecallTrace({
            version: "recall-trace-v1",
            traceRef: `tr1_${sha256CanonicalContent({
              contract_version: "authorized-query-empty-trace-v1",
              input_digest: copied.input_digest,
              strategy_id: request.strategy.strategy_id,
              repeat_ordinal: request.repeat_ordinal,
            })}`,
            strategyVersion: request.strategy.coordinates.strategy_version,
            projectionFreshness: "fresh",
            outcome: "no_eligible_candidates",
            latencyMs: 0,
            tokenCounts: { input: 0, output: 0 },
            stages: {
              eligible: [], selected: [], hydrated: [],
              policyEligible: [], cited: [], grounded: [],
            },
          }),
        });
      } else {
        modelCalls = 1;
        let rawProduced: AuthorizedQueryModelOutcome;
        try { rawProduced = parseProduced(await Reflect.apply(produce, undefined, [modelRequest])); }
        catch { return stop("invalid_result", 1); }
        if (rawProduced.kind === "failed") return stop("producer_failed", 1, rawProduced.error_code);
        produced = rawProduced;
      }

      let result: Readonly<MemoryEvaluationResult>;
      let resultStageRequest: Readonly<MemoryEvaluationStageRequest>;
      let read;
      try {
        read = buildMemoryReadEvaluationResult(context, {
          assignment_bundle: request.bundle,
          assignment_id: request.assignment.assignment_id,
          copied_input: copied,
          evaluation_role: request.role,
          repeat_ordinal: request.repeat_ordinal,
          query_text: input.query_text,
          answer_text: produced.answer_text,
          absence: produced.absence,
          assertions: produced.assertions,
          recall_trace: produced.recall_trace,
        });
        const allowed = new Set(input.candidates.map((candidate) => candidate.trace_ref));
        for (const stage of Object.values(read.recall_trace.stages)) {
          if (stage.some((traceRef) => !allowed.has(traceRef))) fail("trace_outside_input");
        }
        const body: MemoryEvaluationStageBody = {
          ...resultCoordinate,
          result_contract_version: read.version,
          response_digest: digest(produced.response_digest, "invalid_response_digest"),
          normalized_result_digest: durableMemoryWorkNormalizedResultDigest(read.version, read as never),
          normalized_result: read as never,
        };
        resultStageRequest = Object.freeze({
          ...body,
          request_digest: memoryEvaluationStageRequestDigest(context, body),
        });
        result = materializeMemoryEvaluationResult(context, resultStageRequest);
      } catch {
        return stop("invalid_result", modelCalls);
      }

      let finalLoad;
      try { finalLoad = await evidenceSource.load(context, request.source_request); }
      catch { return stop("read_invalidated", modelCalls); }
      if (finalLoad.kind !== "found" || finalLoad.copied_input.input_digest !== copied.input_digest) {
        return stop("read_invalidated", modelCalls);
      }

      let artifact: Readonly<FinalizedMemoryReadGroundingArtifact>;
      try {
        const parsedRead = parseMemoryReadEvaluationResult(result.normalized_result);
        const byRef = new Map(input.candidates.map((candidate) => [candidate.trace_ref, candidate]));
        artifact = materializeFinalizedMemoryReadGrounding({
          evaluation_result: result,
          projection_authorization_digest: input.projection_authorization_digest,
          reader_projection_digest: input.reader_projection_digest,
          projected_content_digest: input.projected_content_digest,
          rows: [...parsedRead.recall_trace.stages.grounded].sort(compare).map((traceRef) => ({
            trace_ref: traceRef,
            contributing_subject_classes: byRef.get(traceRef)?.contributing_subject_classes ?? fail("missing_grounding"),
          })),
        });
      } catch {
        return stop("invalid_result", modelCalls);
      }

      let staged;
      try { staged = await groundingRepository.stage(context, result, artifact, resultStageRequest!); }
      catch { return stop("storage_unavailable", modelCalls); }
      if (staged.kind !== "staged" && staged.kind !== "replayed") {
        return stop(storageStop(staged.kind), modelCalls);
      }
      return Object.freeze({
        kind: "completed" as const,
        completion: staged.kind,
        result,
        artifact: staged.artifact,
        model_calls: modelCalls,
      });
    },
  });
};

export const AUTHORIZED_QUERY_EVALUATION_INPUT_VERSION = INPUT_VERSION;
