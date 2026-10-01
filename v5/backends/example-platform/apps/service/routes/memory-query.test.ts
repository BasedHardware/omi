import { describe, expect, test } from "bun:test";

import {
  buildMemoryRecallKernelResponse,
  MEMORY_RECALL_KERNEL_VERSION,
} from "../../../core/retrieve/memory-recall-kernel";
import { MEMORY_QUERY_PATH, MEMORY_QUERY_ROUTE_VERSION, registerMemoryQueryRoute } from "./memory-query";

const digest = (character: string): string => character.repeat(64);
const trace = (character: string): `tr1_${string}` => `tr1_${digest(character)}`;

const response = () => buildMemoryRecallKernelResponse({
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

const register = () => {
  let handler: ((context: {
    req: { header: (name: string) => string | undefined; query: (name: string) => string | undefined };
  }) => Promise<Response>) | undefined;
  registerMemoryQueryRoute({
    get(_path: string, next: typeof handler) { handler = next; },
  } as never, {
    recall: {
      answer: async () => Object.freeze({
        kind: "completed" as const,
        response: response(),
        candidates: [],
        identity_expression_labels: [],
        model_calls: 0 as const,
      }),
    } as never,
    authorize: async (token: string) => token === "token" ? ({ account_id: "account:alice" } as never) : null,
    now_epoch_seconds: () => 100,
    build_request: async () => ({ question_text: "What did we discuss about the Atlas launch?" } as never),
  });
  if (handler === undefined) throw new Error("route was not registered");
  return handler;
};

const request = (
  query: Record<string, string | undefined>,
  authorization?: string,
) => ({
  req: {
    header: (name: string) => name === "authorization" ? authorization : undefined,
    query: (name: string) => query[name],
  },
});

describe("dark memory query HTTP route", () => {
  test("answers question= over derived-group recall and rejects ?q=", async () => {
    const handler = register();
    const ok = await handler(request(
      { question: "What did we discuss about the Atlas launch?" },
      "Bearer token",
    ));
    expect(ok.status).toBe(200);
    const body = await ok.json() as { version: string; answer_text: string };
    expect(body.version).toBe(MEMORY_QUERY_ROUTE_VERSION);
    expect(body.answer_text).toBe("We planned the Atlas launch for Friday.");
    expect(MEMORY_QUERY_PATH).toBe("/v1/memories/query");

    const q = await handler(request({ q: "hello" }, "Bearer token"));
    expect(q.status).toBe(400);
  });
});
