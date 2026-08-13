import { describe, expect, test } from "bun:test";

import {
  buildMemoryRecallKernelResponse,
  memoryRecallKernelQuestionDigest,
  parseMemoryRecallKernelRequest,
  parseMemoryRecallKernelResponse,
  MEMORY_RECALL_KERNEL_VERSION,
} from "./memory-recall-kernel";

const digest = (character: string): string => character.repeat(64);
const trace = (character: string): string => `tr1_${digest(character)}`;

const request = () => ({
  version: MEMORY_RECALL_KERNEL_VERSION,
  question_text: "What did we discuss about the Atlas launch?",
  authorization_state_digest: digest("a"),
  reader_projection_digest: digest("b"),
  projected_content_digest: digest("c"),
  input_frontier_digest: digest("d"),
});

const completenessInput = () => ({
  declared_frontier: "frontier:7",
  accepted: { state: "searched" as const, searched_frontier: "frontier:7" },
  stm: { state: "searched" as const, searched_frontier: "frontier:7" },
  projection_freshness: "fresh" as const,
  intentional_bounds: [] as const,
});

describe("memory recall kernel", () => {
  test("builds a grounded response with citations and typed completeness", () => {
    const built = buildMemoryRecallKernelResponse({
      request: request(),
      answer_text: "We planned the Atlas launch for Friday.",
      absence: null,
      assertions: [{
        ordinal: 0,
        text: "We planned the Atlas launch for Friday.",
        citations: [trace("a")],
      }],
      completeness_input: completenessInput(),
    });

    expect(built.question_digest).toBe(memoryRecallKernelQuestionDigest(request().question_text));
    expect(built.completeness.status).toBe("complete");
    expect(built.citations).toEqual([{
      citation_ref: trace("a"),
      assertion_ordinal: 0,
    }]);
    expect(parseMemoryRecallKernelResponse(JSON.parse(JSON.stringify(built)))).toEqual(built);
  });

  test("honest query gaps remain typed incomplete answers, not empty success", () => {
    const built = buildMemoryRecallKernelResponse({
      request: request(),
      answer_text: null,
      absence: "query_gap",
      assertions: [],
      completeness_input: {
        ...completenessInput(),
        accepted: { state: "pending", searched_frontier: null },
      },
    });
    expect(built.absence).toBe("query_gap");
    expect(built.completeness.status).toBe("incomplete");
    expect(() => parseMemoryRecallKernelRequest({ ...request(), version: "other" }))
      .toThrow("invalid_request");
  });
});
