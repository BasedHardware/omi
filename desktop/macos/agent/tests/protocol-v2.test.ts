import { describe, expect, it } from "vitest";
import type { CancelAckMessage, InboundMessage, OutboundMessage, QueryMessage } from "../src/protocol.js";
import { requestIdFor } from "../src/protocol.js";

describe("protocol v2 compatibility", () => {
  it("continues to accept v1 query fields", () => {
    const message: QueryMessage = {
      type: "query",
      id: "legacy-request",
      prompt: "hello",
      systemPrompt: "system",
      sessionKey: "main",
      resume: "acp-native-session",
    };

    expect(requestIdFor(message)).toBe("legacy-request");
  });

  it("accepts v2 query correlation and canonical placeholders", () => {
    const message: InboundMessage = {
      type: "query",
      protocolVersion: 2,
      requestId: "swift-request",
      clientId: "bridge-client",
      adapterId: "acp-claude",
      sessionId: "ses_placeholder",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      legacyClientScope: "task-chat",
      legacySessionKey: "task-1",
      legacyAdapterSessionId: "acp-native-session",
      prompt: "hello",
      systemPrompt: "system",
    };

    expect(message.type).toBe("query");
    expect(requestIdFor(message)).toBe("swift-request");
  });

  it("defines cancel_ack as an outbound message", () => {
    const message: CancelAckMessage = {
      type: "cancel_ack",
      protocolVersion: 2,
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
});
