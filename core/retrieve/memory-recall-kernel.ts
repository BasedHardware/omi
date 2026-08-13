import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "./content-digest";
import {
  computeRecallCompleteness,
  type RecallCompletenessInput,
  type RecallCompletenessResult,
  type RecallTraceRef,
} from "./recall-integrity";

export const MEMORY_RECALL_KERNEL_VERSION = "memory-recall-kernel-v1" as const;

export interface MemoryRecallKernelCitation {
  readonly citation_ref: RecallTraceRef;
  readonly assertion_ordinal: number;
}

export interface MemoryRecallKernelAssertion {
  readonly ordinal: number;
  readonly text: string;
  readonly citations: readonly RecallTraceRef[];
}

export interface MemoryRecallKernelRequest {
  readonly version: typeof MEMORY_RECALL_KERNEL_VERSION;
  readonly question_text: string;
  readonly authorization_state_digest: string;
  readonly reader_projection_digest: string;
  readonly projected_content_digest: string;
  readonly input_frontier_digest: string;
}

export interface MemoryRecallKernelResponse {
  readonly version: typeof MEMORY_RECALL_KERNEL_VERSION;
  readonly question_digest: string;
  readonly answer_text: string | null;
  readonly absence: "query_gap" | null;
  readonly assertions: readonly MemoryRecallKernelAssertion[];
  readonly citations: readonly MemoryRecallKernelCitation[];
  readonly completeness: RecallCompletenessResult;
  readonly response_digest: string;
}

const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const MAX_QUERY_CODE_POINTS = 4_096;
const MAX_ANSWER_CODE_POINTS = 65_536;
const MAX_ASSERTIONS = 128;
const MAX_ASSERTION_CODE_POINTS = 8_192;
const MAX_CITATIONS = 32;

const fail = (code: string): never => { throw new TypeError(`memory recall kernel ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const boundedText = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > maximum || /[\p{Cc}\p{Cs}]/u.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

export const memoryRecallKernelQuestionDigest = (questionText: string): string =>
  sha256CanonicalContent({
    contract_version: MEMORY_RECALL_KERNEL_VERSION,
    question_text: questionText,
  });

export const parseMemoryRecallKernelRequest = (
  value: unknown,
): Readonly<MemoryRecallKernelRequest> => {
  const input = exactRecord(value, [
    "version", "question_text", "authorization_state_digest",
    "reader_projection_digest", "projected_content_digest", "input_frontier_digest",
  ], "invalid_request");
  if (input["version"] !== MEMORY_RECALL_KERNEL_VERSION) fail("invalid_request");
  return Object.freeze({
    version: MEMORY_RECALL_KERNEL_VERSION,
    question_text: boundedText(input["question_text"], MAX_QUERY_CODE_POINTS, "invalid_request"),
    authorization_state_digest: digest(input["authorization_state_digest"], "invalid_request"),
    reader_projection_digest: digest(input["reader_projection_digest"], "invalid_request"),
    projected_content_digest: digest(input["projected_content_digest"], "invalid_request"),
    input_frontier_digest: digest(input["input_frontier_digest"], "invalid_request"),
  });
};

const assertions = (
  value: readonly Readonly<{ ordinal: number; text: string; citations: readonly string[] }>[],
): readonly MemoryRecallKernelAssertion[] => Object.freeze(value.map((item, index) => {
  if (item.ordinal !== index) fail("invalid_assertions");
  const citations = [...item.citations];
  if (citations.length === 0 || citations.length > MAX_CITATIONS
    || citations.some((citation) => !TRACE_REF.test(citation))
    || new Set(citations).size !== citations.length) fail("invalid_assertions");
  const sorted = [...citations].sort();
  if (citations.some((citation, citationIndex) => citation !== sorted[citationIndex])) fail("invalid_assertions");
  return Object.freeze({
    ordinal: index,
    text: boundedText(item.text, MAX_ASSERTION_CODE_POINTS, "invalid_assertions"),
    citations: Object.freeze(citations as RecallTraceRef[]),
  });
}));

export const buildMemoryRecallKernelResponse = (inputValue: Readonly<{
  request: MemoryRecallKernelRequest;
  answer_text: string | null;
  absence: "query_gap" | null;
  assertions: readonly Readonly<{ ordinal: number; text: string; citations: readonly string[] }>[];
  completeness_input: RecallCompletenessInput;
}>): Readonly<MemoryRecallKernelResponse> => {
  const request = parseMemoryRecallKernelRequest(inputValue.request);
  const normalizedAssertions = assertions(inputValue.assertions);
  const answer = inputValue.answer_text === null
    ? null
    : boundedText(inputValue.answer_text, MAX_ANSWER_CODE_POINTS, "invalid_answer");
  if (answer === null) {
    if (inputValue.absence !== "query_gap" || normalizedAssertions.length !== 0) fail("invalid_no_answer");
  } else if (inputValue.absence !== null
    || normalizedAssertions.length === 0
    || normalizedAssertions.map((item) => item.text).join(" ") !== answer) {
    fail("invalid_grounded_answer");
  }
  const completeness = computeRecallCompleteness(inputValue.completeness_input);
  const citations = Object.freeze(normalizedAssertions.flatMap((assertion) =>
    assertion.citations.map((citationRef) => Object.freeze({
      citation_ref: citationRef,
      assertion_ordinal: assertion.ordinal,
    }))));
  const withoutDigest = {
    version: MEMORY_RECALL_KERNEL_VERSION,
    question_digest: memoryRecallKernelQuestionDigest(request.question_text),
    answer_text: answer,
    absence: answer === null ? "query_gap" as const : null,
    assertions: normalizedAssertions,
    citations,
    completeness,
  };
  return Object.freeze({
    ...withoutDigest,
    response_digest: sha256CanonicalContent({
      contract_version: MEMORY_RECALL_KERNEL_VERSION,
      authorization_state_digest: request.authorization_state_digest,
      reader_projection_digest: request.reader_projection_digest,
      projected_content_digest: request.projected_content_digest,
      input_frontier_digest: request.input_frontier_digest,
      ...withoutDigest,
    }),
  });
};

const parseCompletenessResult = (value: unknown): RecallCompletenessResult => {
  const input = exactRecord(value, ["version", "status", "reasons", "frontiers"], "invalid_response");
  if (input["version"] !== "recall-completeness-v1") fail("invalid_response");
  const status = input["status"];
  if (status !== "complete" && status !== "incomplete" && status !== "degraded" && status !== "partial") {
    fail("invalid_response");
  }
  const frontiers = input["frontiers"];
  if (frontiers === null || typeof frontiers !== "object" || Array.isArray(frontiers)) fail("invalid_response");
  return Object.freeze({
    version: "recall-completeness-v1",
    status,
    reasons: Array.isArray(input["reasons"]) ? Object.freeze([...input["reasons"]]) as RecallCompletenessResult["reasons"] : fail("invalid_response"),
    frontiers: frontiers as RecallCompletenessResult["frontiers"],
  });
};

export const parseMemoryRecallKernelResponse = (
  value: unknown,
): Readonly<MemoryRecallKernelResponse> => {
  const input = exactRecord(value, [
    "version", "question_digest", "answer_text", "absence", "assertions",
    "citations", "completeness", "response_digest",
  ], "invalid_response");
  if (input["version"] !== MEMORY_RECALL_KERNEL_VERSION) fail("invalid_response");
  const completeness = input["completeness"];
  if (completeness === null || typeof completeness !== "object" || Array.isArray(completeness)) fail("invalid_response");
  const parsedCompleteness = parseCompletenessResult(completeness);
  const parsedAssertions = assertions((Array.isArray(input["assertions"]) ? input["assertions"] : fail("invalid_response"))
    .map((item) => {
      const assertion = exactRecord(item, ["ordinal", "text", "citations"], "invalid_response");
      return {
        ordinal: assertion["ordinal"] as number,
        text: assertion["text"] as string,
        citations: assertion["citations"] as readonly string[],
      };
    }));
  const answer = input["answer_text"] === null
    ? null
    : boundedText(input["answer_text"], MAX_ANSWER_CODE_POINTS, "invalid_response");
  const absence = input["absence"] === null ? null : input["absence"] === "query_gap" ? "query_gap" : fail("invalid_response");
  if (answer === null) {
    if (absence !== "query_gap" || parsedAssertions.length !== 0) fail("invalid_no_answer");
  } else if (absence !== null || parsedAssertions.length === 0
    || parsedAssertions.map((item) => item.text).join(" ") !== answer) {
    fail("invalid_grounded_answer");
  }
  const citations = Object.freeze((Array.isArray(input["citations"]) ? input["citations"] : fail("invalid_response"))
    .map((item) => {
      const citation = exactRecord(item, ["citation_ref", "assertion_ordinal"], "invalid_response");
      const citationRef = citation["citation_ref"];
      if (typeof citationRef !== "string" || !TRACE_REF.test(citationRef)) fail("invalid_response");
      const assertionOrdinal = citation["assertion_ordinal"];
      if (!Number.isSafeInteger(assertionOrdinal)) fail("invalid_response");
      return Object.freeze({
        citation_ref: citationRef as RecallTraceRef,
        assertion_ordinal: assertionOrdinal as number,
      });
    }));
  return Object.freeze({
    version: MEMORY_RECALL_KERNEL_VERSION,
    question_digest: digest(input["question_digest"], "invalid_response"),
    answer_text: answer,
    absence,
    assertions: parsedAssertions,
    citations,
    completeness: parsedCompleteness,
    response_digest: digest(input["response_digest"], "invalid_response"),
  });
};
