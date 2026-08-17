import { describe, expect, test } from "bun:test";

import {
  buildMemoryRecallKernelResponse,
  MEMORY_RECALL_KERNEL_VERSION,
} from "../../core/retrieve/memory-recall-kernel";
import {
  defineMemoryQueryTool,
  MEMORY_QUERY_TOOL_NAME,
  MEMORY_QUERY_TOOL_SCOPE,
} from "./memory-query-tool";

const digest = (character: string): string => character.repeat(64);
const trace = (character: string): `tr1_${string}` => `tr1_${digest(character)}`;

const kernelResponse = () => buildMemoryRecallKernelResponse({
  request: {
    version: MEMORY_RECALL_KERNEL_VERSION,
    question_text: "What did we discuss about the Atlas launch?",
    authorization_state_digest: digest("a"),
    reader_projection_digest: digest("b"),
    projected_content_digest: digest("c"),
    input_frontier_digest: digest("d"),
  },
  answer_text: "We planned the Atlas launch for Friday.",
  absence: null,
  assertions: [{
    ordinal: 0,
    text: "We planned the Atlas launch for Friday.",
    citations: [trace("a")],
  }],
  completeness_input: {
    declared_frontier: "frontier:7",
    accepted: { state: "searched", searched_frontier: "frontier:7" },
    stm: { state: "searched", searched_frontier: "frontier:7" },
    projection_freshness: "fresh",
    intentional_bounds: [],
  },
});

describe("dark memory query MCP tool", () => {
  test("shares memories.read over the same kernel and stays unregisterable here", async () => {
    const tool = defineMemoryQueryTool({
      recall: {
        answer: async () => Object.freeze({
          kind: "completed" as const,
          response: kernelResponse(),
          candidates: [],
          identity_expression_labels: [],
          model_calls: 0 as const,
        }),
      } as never,
      authorize: async () => ({ account_id: "account:alice" } as never),
      build_request: async () => ({ question_text: "What did we discuss about the Atlas launch?" } as never),
    });
    expect(tool.name).toBe(MEMORY_QUERY_TOOL_NAME);
    expect(tool.scope).toBe(MEMORY_QUERY_TOOL_SCOPE);
    const completed = await tool.call({}, "What did we discuss about the Atlas launch?");
    expect(completed.kind).toBe("completed");
    const denied = await tool.call({}, "");
    expect(denied.kind).toBe("failed");
  });
});
