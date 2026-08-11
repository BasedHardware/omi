import { isProxy } from "node:util/types";

import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import {
  buildContentSafeRecallTrace,
  hasContentSafeRecallTrace,
  type ContentSafeRecallTrace,
  type RecallTraceRef,
} from "../../../core/retrieve/recall-integrity";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertCopiedMemoryEvaluationInput,
  type CopiedMemoryEvaluationInput,
} from "../stores/memory-evaluation-evidence-source";
import type { MemoryEvaluationRole } from "../stores/memory-shadow-result-repository";

const RESULT_VERSION = "memory-read-evaluation-result-v1" as const;
const CAPABILITY = "memories.experiments.shadow";
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const MAX_QUERY_CODE_POINTS = 4_096;
const MAX_ANSWER_CODE_POINTS = 65_536;
const MAX_ASSERTIONS = 128;
const MAX_ASSERTION_CODE_POINTS = 8_192;
const MAX_CITATIONS = 32;
const MAX_REPEAT = 19;

export interface MemoryReadEvaluationAssertion {
  readonly ordinal: number;
  readonly text: string;
  readonly citations: readonly RecallTraceRef[];
}

export interface MemoryReadEvaluationResult {
  readonly version: typeof RESULT_VERSION;
  readonly copied_input_digest: string;
  readonly input_frontier_digest: string;
  readonly strategy_kind: "retrieval" | "composition";
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly repeat_ordinal: number;
  readonly query_text: string;
  readonly answer_text: string | null;
  readonly absence: "query_gap" | null;
  readonly assertions: readonly Readonly<MemoryReadEvaluationAssertion>[];
  readonly recall_trace: Readonly<ContentSafeRecallTrace>;
}

export interface MemoryReadEvaluationResultRequest {
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly assignment_id: string;
  readonly copied_input: Readonly<CopiedMemoryEvaluationInput>;
  readonly evaluation_role: MemoryEvaluationRole;
  readonly repeat_ordinal: number;
  readonly query_text: string;
  readonly answer_text: string | null;
  readonly absence: "query_gap" | null;
  readonly assertions: readonly Readonly<MemoryReadEvaluationAssertion>[];
  readonly recall_trace: Readonly<ContentSafeRecallTrace>;
}

const fail = (code: string): never => { throw new TypeError(`memory read evaluation result ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const array = value as unknown[];
  const keys = Reflect.ownKeys(array);
  if (keys.length !== array.length + 1 || keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= array.length)))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < array.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(array, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const boundedText = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > maximum || /[\p{Cc}\p{Cs}]/u.test(value)) fail(code);
  return value;
};

const assertions = (value: unknown): readonly Readonly<MemoryReadEvaluationAssertion>[] => Object.freeze(
  exactArray(value, MAX_ASSERTIONS, "invalid_assertions").map((item, index) => {
    const input = exactRecord(item, ["ordinal", "text", "citations"], "invalid_assertion");
    if (input["ordinal"] !== index) fail("invalid_assertion");
    const citationValues = exactArray(input["citations"], MAX_CITATIONS, "invalid_assertion");
    if (citationValues.length === 0) fail("invalid_assertion");
    const citations = citationValues.map((citation) => {
      if (typeof citation !== "string" || !TRACE_REF.test(citation)) fail("invalid_assertion");
      return citation as RecallTraceRef;
    });
    const sorted = [...citations].sort();
    if (new Set(citations).size !== citations.length
      || citations.some((citation, citationIndex) => citation !== sorted[citationIndex])) fail("invalid_assertion");
    return Object.freeze({
      ordinal: index,
      text: boundedText(input["text"], MAX_ASSERTION_CODE_POINTS, "invalid_assertion"),
      citations: Object.freeze(citations),
    });
  }),
);

const validateAnswerManifest = (
  answer: string | null,
  absence: unknown,
  normalizedAssertions: readonly Readonly<MemoryReadEvaluationAssertion>[],
  trace: Readonly<ContentSafeRecallTrace>,
): "query_gap" | null => {
  const cited = new Set(trace.stages.cited);
  const grounded = new Set(trace.stages.grounded);
  if (answer === null) {
    if (absence !== "query_gap" || normalizedAssertions.length !== 0
      || trace.outcome === "grounded" || grounded.size !== 0) fail("invalid_no_answer");
    return "query_gap";
  }
  if (absence !== null || trace.outcome !== "grounded" || normalizedAssertions.length === 0) {
    fail("invalid_grounded_answer");
  }
  if (normalizedAssertions.map((assertion) => assertion.text).join(" ") !== answer) fail("answer_manifest_mismatch");
  const used = new Set<RecallTraceRef>();
  for (const assertion of normalizedAssertions) for (const citation of assertion.citations) {
    if (!cited.has(citation) || !grounded.has(citation)) fail("citation_not_grounded");
    used.add(citation);
  }
  if ([...grounded].some((citation) => !used.has(citation))) fail("unused_grounded_reference");
  return null;
};

export const buildMemoryReadEvaluationResult = (
  contextValue: AuthorizedLedgerWriteContext,
  requestValue: MemoryReadEvaluationResultRequest,
): Readonly<MemoryReadEvaluationResult> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  const request = exactRecord(requestValue, [
    "assignment_bundle", "assignment_id", "copied_input", "evaluation_role",
    "repeat_ordinal", "query_text", "answer_text", "absence", "assertions", "recall_trace",
  ], "invalid_request");
  const bundle = assertMintedMemoryStrategyAssignment(request["assignment_bundle"]);
  if (bundle.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (bundle.work_kind !== "retrieval" && bundle.work_kind !== "composition") fail("not_read_strategy");
  const role = request["evaluation_role"];
  if (role !== "baseline" && role !== "candidate") fail("invalid_role");
  const assignmentId = request["assignment_id"];
  if (typeof assignmentId !== "string") fail("invalid_assignment");
  const assignment = role === "baseline"
    ? bundle.authority.assignment_id === assignmentId ? bundle.authority : null
    : bundle.shadows.find((candidate) => candidate.assignment_id === assignmentId) ?? null;
  if (!assignment) fail("invalid_assignment");
  const strategy = bundle.strategies.find((candidate) => candidate.strategy_id === assignment.strategy_id
    && candidate.execution_contract_digest === assignment.execution_contract_digest) ?? fail("invalid_assignment");
  const copied = assertCopiedMemoryEvaluationInput(context, request["copied_input"]);
  if (copied.source_kind !== "authorized_graph_snapshot") fail("invalid_source_kind");
  const repeat = request["repeat_ordinal"];
  if (!Number.isSafeInteger(repeat) || (repeat as number) < 0 || (repeat as number) > MAX_REPEAT) fail("invalid_repeat");
  const query = boundedText(request["query_text"], MAX_QUERY_CODE_POINTS, "invalid_query");
  const normalizedAssertions = assertions(request["assertions"]);
  const traceValue = request["recall_trace"];
  if (!hasContentSafeRecallTrace(traceValue)) fail("unverified_trace");
  const trace = traceValue as Readonly<ContentSafeRecallTrace>;
  if (trace.strategyVersion !== strategy.coordinates.strategy_version) fail("trace_strategy_mismatch");
  const answer = request["answer_text"] === null
    ? null
    : boundedText(request["answer_text"], MAX_ANSWER_CODE_POINTS, "invalid_answer");
  const absence = validateAnswerManifest(answer, request["absence"], normalizedAssertions, trace);
  return Object.freeze({
    version: RESULT_VERSION,
    copied_input_digest: copied.input_digest,
    input_frontier_digest: sha256CanonicalContent({
      contract_version: "memory-read-evaluation-frontier-v1",
      input_frontier: copied.input_frontier,
    }),
    strategy_kind: bundle.work_kind,
    strategy_id: strategy.strategy_id,
    execution_contract_digest: strategy.execution_contract_digest,
    evaluation_role: role,
    repeat_ordinal: repeat as number,
    query_text: query,
    answer_text: answer,
    absence,
    assertions: normalizedAssertions,
    recall_trace: trace,
  });
};

/** Revalidates the exact sensitive result envelope after an isolated-store JSON round trip. */
export const parseMemoryReadEvaluationResult = (value: unknown): Readonly<MemoryReadEvaluationResult> => {
  const input = exactRecord(value, [
    "version", "copied_input_digest", "input_frontier_digest", "strategy_kind", "strategy_id",
    "execution_contract_digest", "evaluation_role", "repeat_ordinal", "query_text", "answer_text",
    "absence", "assertions", "recall_trace",
  ], "invalid_stored_result");
  if (input["version"] !== RESULT_VERSION
    || typeof input["copied_input_digest"] !== "string" || !DIGEST.test(input["copied_input_digest"])
    || typeof input["input_frontier_digest"] !== "string" || !DIGEST.test(input["input_frontier_digest"])
    || (input["strategy_kind"] !== "retrieval" && input["strategy_kind"] !== "composition")
    || typeof input["strategy_id"] !== "string" || !TOKEN.test(input["strategy_id"])
    || typeof input["execution_contract_digest"] !== "string" || !DIGEST.test(input["execution_contract_digest"])
    || (input["evaluation_role"] !== "baseline" && input["evaluation_role"] !== "candidate")
    || !Number.isSafeInteger(input["repeat_ordinal"])
    || (input["repeat_ordinal"] as number) < 0 || (input["repeat_ordinal"] as number) > MAX_REPEAT) {
    fail("invalid_stored_result");
  }
  const query = boundedText(input["query_text"], MAX_QUERY_CODE_POINTS, "invalid_stored_result");
  const answer = input["answer_text"] === null
    ? null
    : boundedText(input["answer_text"], MAX_ANSWER_CODE_POINTS, "invalid_stored_result");
  const normalizedAssertions = assertions(input["assertions"]);
  let trace: Readonly<ContentSafeRecallTrace>;
  try {
    trace = buildContentSafeRecallTrace(input["recall_trace"]);
  } catch {
    fail("invalid_stored_result");
  }
  const absence = validateAnswerManifest(answer, input["absence"], normalizedAssertions, trace);
  return Object.freeze({
    version: RESULT_VERSION,
    copied_input_digest: input["copied_input_digest"] as string,
    input_frontier_digest: input["input_frontier_digest"] as string,
    strategy_kind: input["strategy_kind"] as "retrieval" | "composition",
    strategy_id: input["strategy_id"] as string,
    execution_contract_digest: input["execution_contract_digest"] as string,
    evaluation_role: input["evaluation_role"] as MemoryEvaluationRole,
    repeat_ordinal: input["repeat_ordinal"] as number,
    query_text: query,
    answer_text: answer,
    absence,
    assertions: normalizedAssertions,
    recall_trace: trace,
  });
};

export const MEMORY_READ_EVALUATION_RESULT_VERSION = RESULT_VERSION;
