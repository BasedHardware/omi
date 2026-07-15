import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type {
  AuthorizedToolExecutionMessage,
  AuthorizedToolExecutionResultMessage,
  CancelAckMessage,
  ControlToolResultMessage,
  InboundMessage,
  OutboundMessage,
  QueryMessage,
  ExternalSurfaceRunBeginMessage,
  ExternalSurfaceRunBeginResultMessage,
  ExternalSurfaceToolInvokeMessage,
  ExternalSurfaceToolResultMessage,
  ExternalSurfaceRunCompleteMessage,
  ExternalSurfaceRunCompleteResultMessage,
  ImportLegacyMainChatSessionsMessage,
  LegacyMainChatSessionsImportedMessage,
  RevokeOwnerRuntimeMessage,
  OwnerRuntimeRevokedMessage,
  JournalRecordTurnMessage,
  JournalImportRemoteTurnMessage,
  JournalTerminalizeTurnMessage,
  JournalBackendSyncMessage,
} from "../src/protocol.js";
import {
  PROTOCOL_VERSION,
  assertPublicJournalRecordAuthority,
  assertPublicJournalUpdateAuthority,
  isInboundResponseMessage,
  journalTerminalizationDisposition,
} from "../src/protocol.js";
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

    const receipt: ControlToolResultMessage = {
      type: "control_tool_result",
      protocolVersion: PROTOCOL_VERSION,
      requestId: message.requestId,
      clientId: message.clientId,
      ownerId: message.ownerId,
      name: message.name,
      result: JSON.stringify({ ok: false, error: { code: "direct_control_owner_revoked" } }),
    };
    expect((receipt as OutboundMessage).ownerId).toBe(message.ownerId);
  });

  it("types the bounded remote-turn upgrade as an owner-scoped journal request", () => {
    const message: JournalImportRemoteTurnMessage = {
      type: "journal_import_remote_turn",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "import-remote",
      clientId: "main-chat-upgrade",
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      turn: {
        remoteId: "remote-1",
        canonicalTurnId: "turn-1",
        role: "user",
        content: "fixture",
        contentBlocks: [],
        resources: [],
        metadataJson: "{}",
        createdAtMs: 1,
      },
    };
    expect((message as InboundMessage).type).toBe("journal_import_remote_turn");
  });

  it("bootstraps local runtimes with an owner-only handshake before owner-scoped RPCs", () => {
    const message: InboundMessage = {
      type: "refresh_owner",
      ownerId: "signed-owner",
    };
    expect(message).toEqual({ type: "refresh_owner", ownerId: "signed-owner" });
    expect(message).not.toHaveProperty("token");

    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    expect(source).toContain('case "refresh_owner"');
  });

  it("defines a correlated exact-owner runtime revocation barrier", () => {
    const request: RevokeOwnerRuntimeMessage = {
      type: "revoke_owner_runtime",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "revoke-a",
      clientId: "runtime-owner-transition",
      ownerId: "owner-a",
    };
    const receipt: OwnerRuntimeRevokedMessage = {
      type: "owner_runtime_revoked",
      protocolVersion: PROTOCOL_VERSION,
      requestId: request.requestId,
      clientId: request.clientId,
      ownerId: request.ownerId,
      ok: true,
      duplicate: false,
      revokedRunIds: ["run-a"],
      invalidatedBindingIds: [],
    };
    expect((request as InboundMessage).ownerId).toBe("owner-a");
    expect((receipt as OutboundMessage).requestId).toBe(request.requestId);
  });

  it("keeps delivery kernel-owned and terminalizes with exact run-attempt authority", () => {
    const record: JournalRecordTurnMessage = {
      type: "journal_record_turn",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "record-task-turn",
      clientId: "task-chat",
      ownerId: "owner",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      turn: {
        turnId: "turn-task-1",
        role: "assistant",
        content: "Working",
        contentBlocks: [],
      },
    };
    expect(record.turn).not.toHaveProperty("delivery");

    const terminalize: JournalTerminalizeTurnMessage = {
      type: "journal_terminalize_turn",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "terminalize-task-turn",
      clientId: "task-chat",
      ownerId: "owner",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      terminalization: {
        turnId: "turn-task-1",
        producingRunId: "run-task-1",
        producingAttemptId: "att-task-1",
        disposition: "accept",
        content: "Done",
        replaceContentBlocks: [],
        replaceResources: [],
      },
    };
    expect((terminalize as InboundMessage).terminalization).toMatchObject({
      producingRunId: "run-task-1",
      producingAttemptId: "att-task-1",
    });

    const delivery: JournalBackendSyncMessage = {
      type: "journal_backend_sync",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "journal:turn-task-1:2",
      clientId: "kernel-journal",
      ownerId: "owner",
      turnId: "turn-task-1",
      conversationId: "conversation-1",
      conversationGeneration: 1,
      attemptCount: 1,
      deliveryGeneration: 2,
      payloadHash: "sha256:payload",
      clientMessageId: "turn-task-1",
      journalRevision: 3,
      text: "Done",
      sender: "ai",
      appId: null,
      sessionId: null,
      metadata: null,
      messageSource: "desktop_chat",
    };
    expect(delivery).toMatchObject({ clientMessageId: delivery.turnId, journalRevision: 3 });
    expect(delivery).not.toHaveProperty("remoteId");
    expect(() => assertPublicJournalRecordAuthority({ ...record.turn, delivery: "local" })).toThrow(
      /delivery is kernel-owned/i,
    );
    expect(() => assertPublicJournalRecordAuthority({ ...record.turn, producingRunId: "forged" })).toThrow(
      /producingRunId is kernel-owned/i,
    );
    expect(() => assertPublicJournalUpdateAuthority({ turnId: record.turn.turnId, producingAttemptId: "forged" }))
      .toThrow(/producingAttemptId is kernel-owned/i);
    expect(() => journalTerminalizationDisposition({ disposition: "maybe" })).toThrow(
      /explicit accept or discard disposition/i,
    );
    expect(() => journalTerminalizationDisposition({})).toThrow(/explicit accept or discard disposition/i);
  });

  it("acknowledges legacy main-chat aliases only with correlated owner-scoped acceptance", () => {
    const request: ImportLegacyMainChatSessionsMessage = {
      type: "import_legacy_main_chat_sessions",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "legacy-import",
      clientId: "bridge-client",
      ownerId: "owner-1",
      entries: [{ chatId: "default", agentSessionId: "ses_legacy" }],
    };
    const receipt: LegacyMainChatSessionsImportedMessage = {
      type: "legacy_main_chat_sessions_imported",
      protocolVersion: PROTOCOL_VERSION,
      requestId: request.requestId,
      clientId: request.clientId,
      ownerId: "owner-1",
      acceptedEntries: request.entries,
      acceptedCount: 1,
      importedCount: 1,
    };

    expect((request as InboundMessage).ownerId).toBe(receipt.ownerId);
    expect((receipt as OutboundMessage).acceptedEntries).toEqual(request.entries);
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

  it("classifies inbound results as responses that must not receive reflected request errors", () => {
    for (const type of [
      "authorized_tool_execution_result",
      "journal_backend_sync_result",
      "journal_backend_delete_result",
      "journal_backend_reconcile_result",
    ] as const) {
      expect(isInboundResponseMessage({ type })).toBe(true);
    }
    expect(isInboundResponseMessage({ type: "query" })).toBe(false);
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    expect(source).toContain("if (isInboundResponseMessage(msg))");
    expect(source).toContain("Unhandled runtime response error type=");
  });
});
