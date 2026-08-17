// red-proof: mutate SAFE_WRITE_TOOL_NAME back to "safe.write" and this file fails.
// domain-pending(DIV-CHAT-TOOL-001)

import { describe, expect, test } from "bun:test";

import { GET_ACTION_ITEMS_TOOL_SCHEMA } from "./action-items-tool";
import { createInMemoryAgentRunEventStore } from "./agent-run-events";
import { createAgentToolRegistry, type AgentToolDefinition } from "./agent-tools";
import { PRODUCTION_GATEWAY_TOOL_NAMES } from "./gateway-tool-composition";
import {
  validateGatewayReadOnlyToolLoop,
  type GatewayReadOnlyToolLoopOptions,
  type GatewayReadOnlyToolSchema,
} from "./gateway-tool-loop";
import { createGatewayChatGenerationSource } from "./generation-source";
import { SAFE_WRITE_TOOL_SCHEMA } from "./safe-write-tool";

/** OpenAI function-name charset; a live provider is not required to reject a mismatch. */
const OPENAI_FUNCTION_NAME = /^[a-zA-Z0-9_-]{1,64}$/;

const dottedName = "safe.write";

const dottedSchema = (): GatewayReadOnlyToolSchema => Object.freeze({
  name: dottedName,
  description: "A dotted name the OpenAI tool spec rejects.",
  parameters: Object.freeze({
    type: "object" as const,
    additionalProperties: false as const,
    properties: Object.freeze({}),
    required: Object.freeze([] as readonly string[]),
  }),
});

const dottedDefinition = (): AgentToolDefinition => Object.freeze({
  schemaVersion: 1,
  name: dottedName,
  risk: "safe",
  timeoutMs: 1_000,
  retryable: false,
  displaySummary: "Dotted fixture",
  validateInput: () => true,
  execute: async () => Object.freeze({ summary: "unused", durationMs: 1, retryable: false }),
});

const dottedLoop = (): GatewayReadOnlyToolLoopOptions => Object.freeze({
  registry: createAgentToolRegistry([dottedDefinition()]),
  tool: dottedSchema(),
  agentRunEvents: createInMemoryAgentRunEventStore(),
  nowEpochMilliseconds: () => 1,
});

describe("advertised gateway tool names", () => {
  test("every advertised tool name matches the OpenAI function-name charset", () => {
    expect(PRODUCTION_GATEWAY_TOOL_NAMES).toEqual([
      GET_ACTION_ITEMS_TOOL_SCHEMA.name,
      SAFE_WRITE_TOOL_SCHEMA.name,
    ]);
    for (const name of PRODUCTION_GATEWAY_TOOL_NAMES) {
      expect(name).toMatch(OPENAI_FUNCTION_NAME);
    }
  });

  test("a dotted advertised name fails at configuration time naming the pattern", () => {
    expect(() => validateGatewayReadOnlyToolLoop(dottedLoop())).toThrow(
      `invalid advertised tool name "${dottedName}"; expected a string matching ^[a-zA-Z0-9_-]{1,64}$`,
    );
    expect(() => createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:1",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: dottedLoop(),
    })).toThrow(
      `invalid advertised tool name "${dottedName}"; expected a string matching ^[a-zA-Z0-9_-]{1,64}$`,
    );
  });
});
