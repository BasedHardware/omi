import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { CancelAckMessage, InboundMessage, OutboundMessage, QueryMessage } from "../src/protocol.js";
import { PROTOCOL_VERSION } from "../src/protocol.js";
import { AGENT_CONTROL_TOOL_NAMES, SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES } from "../src/runtime/control-tools.js";

describe("protocol v2", () => {
  it("requires v2 correlation fields on queries", () => {
    const message: QueryMessage = {
      type: "query",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "swift-request",
      clientId: "bridge-client",
      adapterId: "acp-claude",
      sessionId: "ses_placeholder",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      prompt: "hello",
      systemPrompt: "system",
    };

    expect(message.type).toBe("query");
    expect(message.requestId).toBe("swift-request");
    expect(message.protocolVersion).toBe(2);
  });

  it("defines cancel_ack as an outbound message", () => {
    const message: CancelAckMessage = {
      type: "cancel_ack",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "swift-request",
      sessionId: "ses_placeholder",
      runId: "run_placeholder",
      attemptId: "att_placeholder",
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };

    const outbound: OutboundMessage = message;
    expect(outbound.type).toBe("cancel_ack");
  });

  it("announces canonical agent-control tools in the init handshake", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    const initSendStart = source.indexOf('send({ type: "init"');

    expect(initSendStart).toBeGreaterThanOrEqual(0);
    expect(AGENT_CONTROL_TOOL_NAMES).toContain("spawn_background_agent");
    expect(SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES).not.toContain("spawn_background_agent");
    expect(source).toContain("agentControlTools: SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES");
  });

  it("defines direct app control as an owner-guarded inbound message", () => {
    const message: InboundMessage = {
      type: "direct_control_tool",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "control-request",
      clientId: "realtime-hub",
      ownerId: "owner-1",
      name: "list_agent_sessions",
      input: { limit: 10 },
    };

    expect(message.type).toBe("direct_control_tool");
    expect(message.requestId).toBe("control-request");
  });

  it("keeps signed direct-control owner registration out of control_tool dispatch", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    const controlStart = source.indexOf('case "control_tool"');
    const directStart = source.indexOf('case "direct_control_tool"');
    const controlBlock = source.slice(controlStart, directStart);
    const directBlock = source.slice(directStart);

    expect(controlStart).toBeGreaterThanOrEqual(0);
    expect(directStart).toBeGreaterThan(controlStart);
    expect(source).toContain("direct control requires clientId");
    expect(source).toContain("direct control requires requestId");
    expect(controlBlock).not.toContain("registerSignedDirectControlOwner");
    expect(directBlock).toContain("registerSignedDirectControlOwner");
    expect(directBlock).toContain("releaseDirectControlOwner");
  });

  it("routes direct app control through the canonical agent-control registry", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    const directStart = source.indexOf('case "direct_control_tool"');
    const directBlock = source.slice(directStart, source.indexOf('case "interrupt"'));

    expect(directStart).toBeGreaterThanOrEqual(0);
    expect(directBlock).toContain("if (!isAgentControlToolName(control.name))");
    expect(directBlock).not.toContain("DIRECT_CONTROL_TOOL_NAMES");
    expect(directBlock).toContain("handleAgentControlToolCall");
  });

  it("treats top-level background-agent spawn as a long-lived correlated control run", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    const correlationStart = source.indexOf("function withControlRunCorrelation");
    const adapterStart = source.indexOf("function controlRunAdapterId");
    const longLivedStart = source.indexOf("function isLongLivedControlRun");
    const correlationBlock = source.slice(correlationStart, adapterStart);
    const adapterBlock = source.slice(adapterStart, longLivedStart);
    const longLivedBlock = source.slice(longLivedStart, source.indexOf("function controlToolResultOk"));

    expect(correlationBlock).toContain('"spawn_background_agent"');
    expect(adapterBlock).toContain('"spawn_background_agent"');
    expect(longLivedBlock).toContain('name === "spawn_background_agent"');
  });
});
