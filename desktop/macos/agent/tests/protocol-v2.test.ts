import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type {
  AuthorizedToolExecutionMessage,
  AuthorizedToolExecutionResultMessage,
  CancelAckMessage,
  InboundMessage,
  OutboundMessage,
  QueryMessage,
  ExternalSurfaceRunBeginMessage,
  ExternalSurfaceRunBeginResultMessage,
  ExternalSurfaceToolInvokeMessage,
  ExternalSurfaceToolResultMessage,
  ExternalSurfaceRunCompleteMessage,
  ExternalSurfaceRunCompleteResultMessage,
} from "../src/protocol.js";
import { PROTOCOL_VERSION } from "../src/protocol.js";
import {
  AGENT_CONTROL_TOOL_NAMES,
  SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES,
} from "../src/runtime/control-tools.js";

describe("protocol v2", () => {
  it("makes canonical session identity the only query execution selector", () => {
    const message: QueryMessage = {
      type: "query",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "swift-request",
      clientId: "bridge-client",
      ownerId: "owner",
      sessionId: "ses_placeholder",
      surfaceKind: "main_chat",
      prompt: "hello",
      expectedContextSnapshotVersion: "sha256:snapshot",
      expectedContextSnapshotGeneration: 3,
      expectedContextRendererFingerprint: "sha256:renderer",
      expectedCapabilityVersion: "sha256:capability",
    };
    expect(message).toMatchObject({
      type: "query",
      protocolVersion: 2,
      sessionId: "ses_placeholder",
    });
    expect(message).not.toHaveProperty("adapterId");
    expect(message).not.toHaveProperty("model");
    expect(message).not.toHaveProperty("cwd");
    expect(message).not.toHaveProperty("systemPrompt");
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
  });

  it("binds every physical command/result to the exact manifest and ledger tuple", () => {
    const command: AuthorizedToolExecutionMessage = {
      type: "authorized_tool_execution",
      protocolVersion: 2,
      invocationId: "invoke-1",
      ownerId: "owner",
      sessionId: "session",
      runId: "run",
      attemptId: "attempt",
      profileGeneration: 2,
      manifestVersion: 1,
      manifestDigest: "sha256:manifest",
      daemonBootEpoch: "boot",
      executionGeneration: 4,
      toolName: "get_memories",
      input: {},
      inputHash: "sha256:input",
      effectClass: "read_only",
      retryPolicy: "safe_retry",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      originatingUserText: "remember",
      precedingAssistantText: null,
      runMode: "act",
      chatMode: null,
    };
    const result: AuthorizedToolExecutionResultMessage = {
      type: "authorized_tool_execution_result",
      protocolVersion: 2,
      invocationId: command.invocationId,
      ownerId: command.ownerId,
      sessionId: command.sessionId,
      runId: command.runId,
      attemptId: command.attemptId,
      profileGeneration: command.profileGeneration,
      manifestVersion: command.manifestVersion,
      manifestDigest: command.manifestDigest,
      daemonBootEpoch: command.daemonBootEpoch,
      executionGeneration: command.executionGeneration,
      inputHash: command.inputHash,
      outcome: "succeeded",
      result: "ok",
    };
    expect((command as OutboundMessage).type).toBe("authorized_tool_execution");
    expect((result as InboundMessage).manifestDigest).toBe(command.manifestDigest);
    const recovered: AuthorizedToolExecutionMessage = {
      ...command,
      toolName: "request_permission",
      policyRecovery: "permission_delegation_to_native",
    };
    expect(recovered.policyRecovery).toBe("permission_delegation_to_native");
  });

  it("defines the correlated three-step external surface authority wire", () => {
    const begin: ExternalSurfaceRunBeginMessage = {
      type: "external_surface_run_begin",
      protocolVersion: 2,
      requestId: "begin",
      clientId: "realtime-hub",
      ownerId: "owner",
      sessionId: "voice-session",
      turnId: "voice-turn",
      prompt: "Do the thing",
      mode: "act",
    };
    const began: ExternalSurfaceRunBeginResultMessage = {
      type: "external_surface_run_begin_result",
      protocolVersion: 2,
      requestId: begin.requestId,
      clientId: begin.clientId,
      ownerId: begin.ownerId,
      sessionId: begin.sessionId,
      turnId: begin.turnId,
      ok: true,
      runId: "run",
      attemptId: "attempt",
      duplicate: false,
    };
    const invoke: ExternalSurfaceToolInvokeMessage = {
      type: "external_surface_tool_invoke",
      protocolVersion: 2,
      requestId: "invoke",
      clientId: begin.clientId,
      ownerId: begin.ownerId,
      sessionId: begin.sessionId,
      runId: began.runId!,
      attemptId: began.attemptId!,
      invocationId: "invocation",
      toolName: "get_memories",
      input: {},
    };
    const invoked: ExternalSurfaceToolResultMessage = {
      type: "external_surface_tool_result",
      protocolVersion: 2,
      requestId: invoke.requestId,
      clientId: invoke.clientId,
      ownerId: invoke.ownerId,
      sessionId: invoke.sessionId,
      runId: invoke.runId,
      attemptId: invoke.attemptId,
      invocationId: invoke.invocationId,
      ok: true,
      result: "ok",
    };
    const complete: ExternalSurfaceRunCompleteMessage = {
      type: "external_surface_run_complete",
      protocolVersion: 2,
      requestId: "complete",
      clientId: begin.clientId,
      ownerId: begin.ownerId,
      sessionId: begin.sessionId,
      runId: invoke.runId,
      attemptId: invoke.attemptId,
      terminalStatus: "completed",
    };
    const completed: ExternalSurfaceRunCompleteResultMessage = {
      type: "external_surface_run_complete_result",
      protocolVersion: 2,
      requestId: complete.requestId,
      clientId: complete.clientId,
      ownerId: complete.ownerId,
      sessionId: complete.sessionId,
      runId: complete.runId,
      attemptId: complete.attemptId,
      ok: true,
      terminalStatus: "completed",
      duplicate: false,
    };
    expect([begin, invoke, complete] satisfies InboundMessage[]).toHaveLength(3);
    expect([began, invoked, completed] satisfies OutboundMessage[]).toHaveLength(3);
  });

  it("keeps removed capability and dual-writer wire names absent", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const protocol = readFileSync(join(here, "../src/protocol.ts"), "utf8");
    expect(protocol).not.toMatch(/tool_capability_(?:register|revoke)/);
    expect(protocol).not.toMatch(/record_surface_turn|project_cross_surface_turn|turn_recorded/);
  });
});
