import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createLocalDevService } from "../app-facing";
import { createAgentRunEventSupervisor } from "./agent-run-events";
import {
  createGetActionItemsTool,
  createGetActionItemsToolLoop,
} from "./action-items-tool";
import { createChatGenerationContextPacket } from "./generation-context";
import {
  createGatewayChatGenerationSource,
  type ChatGenerationSourceInput,
} from "./generation-source";

const ownerAccountId = "action-items-owner";

const makeService = (): { readonly db: Database; readonly service: ReturnType<typeof createLocalDevService> } => {
  const db = new Database(":memory:");
  return Object.freeze({
    db,
    service: createLocalDevService({
      db,
      ownerAccountId,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "action-items-test-secret",
    }),
  });
};

const addActionItem = async (
  service: ReturnType<typeof createLocalDevService>,
  description: string,
): Promise<Response> => service.app.fetch(new Request("http://omi.local/v1/action-items", {
  method: "POST",
  headers: {
    authorization: `Bearer ${service.devToken}`,
    "content-type": "application/json",
  },
  body: JSON.stringify({ description, source: "manual" }),
}));

const contextFor = createChatGenerationContextPacket({
  accountId: ownerAccountId,
  generationId: "action-items-generation",
  nowEpochMilliseconds: 1,
  candidates: [],
});

const sourceInput = (
  overrides: Partial<ChatGenerationSourceInput> = {},
): ChatGenerationSourceInput => ({
  generationId: "action-items-generation",
  attemptId: "action-items-generation:attempt:1",
  prompt: "What should I do next?",
  context: contextFor,
  attachments: [],
  onDelta() {},
  onComplete() {},
  onError() {},
  ...overrides,
});

const stream = (...events: readonly string[]): Response => new Response(
  new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(new TextEncoder().encode(`data: ${event}\n\n`));
      controller.close();
    },
  }),
  { status: 200, headers: { "content-type": "text/event-stream" } },
);

const toolCallStream = (): Response => stream(
  JSON.stringify({ choices: [{ delta: { tool_calls: [{
    index: 0,
    id: "gateway-call-action-items",
    function: { name: "get_action_items", arguments: "{}" },
  }] } }] }),
  "[DONE]",
);

describe("get_action_items gateway tool", () => {
  test("reads seeded action items through the canonical authenticated tasks route", async () => {
    const { db, service } = makeService();
    try {
      const created = await addActionItem(service, "File the quarterly report");
      expect(created.status).toBe(200);
      let readCalls = 0;
      const tool = createGetActionItemsTool({
        fetch: (request) => {
          readCalls += 1;
          expect(new URL(request.url).pathname).toBe("/v1/tasks");
          expect(new URL(request.url).searchParams.get("limit")).toBe("25");
          return service.app.fetch(request);
        },
        bearerToken: service.devToken,
        ownerAccountId,
        nowEpochMilliseconds: () => 1,
        agentRunEvents: service.writePath.agentRunEvents,
      });
      expect(tool.validateInput({})).toBe(true);
      expect(tool.validateInput({ limit: "1" })).toBe(false);
      const result = await tool.execute({}, { cancelled: false, cancel() {} });
      expect(result.summary).toContain("File the quarterly report");
      expect(result.summary).toContain("open");
      expect(readCalls).toBe(1);
    } finally {
      db.close();
    }
  });

  test("runs through the authenticated gateway loop and records one durable lifecycle", async () => {
    const { db, service } = makeService();
    try {
      await addActionItem(service, "Renew the passport");
      createAgentRunEventSupervisor({
        events: service.writePath.agentRunEvents,
        nowEpochMilliseconds: () => 1,
      }).accepted({
        runId: "action-items-generation",
        attemptId: "action-items-generation:attempt:1",
        admissionId: "action-items-admission",
      });
      const responses = [
        toolCallStream(),
        stream(JSON.stringify({ choices: [{ delta: { content: "I found the action item." } }] }), "[DONE]"),
      ];
      const source = createGatewayChatGenerationSource({
        gatewayUrl: "http://127.0.0.1:8787",
        laneId: "omi:auto:chat-agent",
        serviceToken: "gateway-service-token",
        readOnlyToolLoop: createGetActionItemsToolLoop({
          fetch: (request) => service.app.fetch(request),
          bearerToken: service.devToken,
          ownerAccountId,
          nowEpochMilliseconds: () => 2,
          agentRunEvents: service.writePath.agentRunEvents,
        }),
        fetch: async () => responses.shift()!,
      });
      const answer = await new Promise<string>((resolve, reject) => {
        const text: string[] = [];
        source.start(sourceInput({
          onDelta: (delta) => text.push(delta),
          onComplete: () => resolve(text.join("")),
          onError: reject,
        }));
      });
      expect(answer).toBe("I found the action item.");
      const events = service.writePath.agentRunEvents.list("action-items-generation");
      expect(events.filter((event) => event.kind === "tool_request")).toHaveLength(1);
      expect(events.filter((event) => event.kind === "tool_result")).toHaveLength(1);
      expect(JSON.stringify(events)).not.toContain("gateway-call-action-items");
      expect(JSON.stringify(events)).toContain("Renew the passport");
    } finally {
      db.close();
    }
  });

  test("fails closed when a gateway generation owner is not the bound authenticated owner", async () => {
    const { db, service } = makeService();
    try {
      const source = createGatewayChatGenerationSource({
        gatewayUrl: "http://127.0.0.1:8787",
        laneId: "omi:auto:chat-agent",
        serviceToken: "gateway-service-token",
        readOnlyToolLoopForInput: (input) => {
          if (input.context.ownerAccountId !== ownerAccountId) throw new Error("owner mismatch");
          return createGetActionItemsToolLoop({
            fetch: (request) => service.app.fetch(request),
            bearerToken: service.devToken,
            ownerAccountId,
            nowEpochMilliseconds: () => 2,
            agentRunEvents: service.writePath.agentRunEvents,
          });
        },
        fetch: async () => toolCallStream(),
      });
      const failure = await new Promise<unknown>((resolve) => {
        source.start(sourceInput({
          context: createChatGenerationContextPacket({
            accountId: "different-owner",
            generationId: "action-items-generation",
            nowEpochMilliseconds: 1,
            candidates: [],
          }),
          onError: resolve,
        }));
      });
      expect(failure).toEqual({ code: "generation_provider_failed", retryable: true });
    } finally {
      db.close();
    }
  });
});

