import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import {
  agentSpawnJournalReceipt,
  compactRealtimeSpawnToolResult,
  parseAgentSpawnProducerJournalDescriptor,
  stableAgentSpawnTurnId,
} from "../src/runtime/agent-spawn-journal.js";
import { handleAgentControlToolCall } from "../src/runtime/control-tools.js";
import { recordJournalTurn, terminalizeJournalTurn, updateJournalTurn } from "../src/runtime/conversation-journal.js";
import { routeExternalSurfaceTool } from "../src/runtime/external-surface-tool-policy.js";
import { AgentRuntimeKernel, ExternalSurfaceAuthorityError } from "../src/runtime/kernel.js";
import type { AuthorizedRunToolInvocation } from "../src/runtime/run-tool-capability.js";
import { finalizeRelayToolResult } from "../src/runtime/relay-tool-result.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";
import {
  establishRuntimeOwner,
  runRuntimeOwnerRevocationBarrier,
} from "../src/runtime/runtime-owner-authority.js";
import { createKernelHarness, FakeRuntimeAdapter, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("external realtime surface authority", () => {
  it("admits one durable realtime run idempotently and rejects identity or surface drift", () => {
    const fixture = createFixture();
    const first = fixture.kernel.beginExternalSurfaceRun(beginInput(fixture.sessionId));
    const retry = fixture.kernel.beginExternalSurfaceRun({
      ...beginInput(fixture.sessionId),
      requestId: "begin-retry",
    });
    expect(first).toMatchObject({ duplicate: false, sessionId: fixture.sessionId, turnId: "voice-turn-1" });
    expect(retry).toEqual({ ...first, duplicate: true });
    expect(fixture.store.getRow("SELECT status FROM runs WHERE run_id = ?", [first.runId])).toEqual({
      status: "running",
    });
    expect(fixture.store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [first.attemptId])).toEqual({
      status: "running",
    });
    expectCode(() => fixture.kernel.beginExternalSurfaceRun({
      ...beginInput(fixture.sessionId),
      prompt: "Different prompt",
      requestId: "begin-collision",
    }), "external_run_identity_collision");

    const mainSession = fixture.store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });
    expectCode(() => fixture.kernel.beginExternalSurfaceRun(beginInput(mainSession.sessionId)), "invalid_external_surface");
    fixture.store.close();
  });

  it("owner revocation terminalizes externally-owned realtime runs and their pending tools", () => {
    const fixture = createFixture();
    const run = fixture.kernel.beginExternalSurfaceRun(beginInput(fixture.sessionId));
    const invocation = fixture.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "external-owner-revoked-tool",
      toolName: "get_memories",
      toolInput: {},
      activeOwnerId: "owner",
    });
    fixture.kernel.markRunToolInvocationDispatched(invocation);

    expect(fixture.kernel.revokeActiveRunsForOwner("owner", "owner_changed")).toEqual({
      runIds: [run.runId],
    });
    expect(fixture.store.getRow(
      "SELECT status, final_text FROM runs WHERE run_id = ?",
      [run.runId],
    )).toMatchObject({ status: "cancelled", final_text: null });
    expect(fixture.store.getRow(
      "SELECT status FROM run_attempts WHERE attempt_id = ?",
      [run.attemptId],
    ).status).toBe("cancelled");
    expect(readToolInvocation(fixture.store, invocation.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_attempt_terminal",
    });
    expectCode(() => fixture.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      terminalStatus: "completed",
    }), "run_terminal");
    fixture.store.close();
  });

  it("terminalizes a lost-begin-response A run before owner B can become visible", () => {
    const fixture = createFixture();
    // Node committed this begin, but Swift's correlated response is deliberately
    // treated as lost: the transition owns no ExternalSurfaceRunBinding.
    const unknownToSwift = fixture.kernel.beginExternalSurfaceRun(beginInput(fixture.sessionId));
    const pendingInvocation = fixture.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: unknownToSwift.runId,
      attemptId: unknownToSwift.attemptId,
      invocationId: "lost-begin-owner-revoked-tool",
      toolName: "get_memories",
      toolInput: {},
      activeOwnerId: "owner",
    });
    fixture.kernel.markRunToolInvocationDispatched(pendingInvocation);
    let authority = establishRuntimeOwner(
      { ownerId: "desktop-local-user", established: false },
      "owner",
    ).state;

    const barrier = runRuntimeOwnerRevocationBarrier({
      state: authority,
      requestedOwnerId: "owner",
      inertOwnerId: "desktop-local-user",
      lastReceipt: null,
      commitAuthority: (state) => { authority = state; },
      revokeAndClear: (ownerId) => {
        expect(authority).toEqual({ ownerId: "desktop-local-user", established: false });
        // The production handler cannot interleave another stdin message here:
        // every active A run/tool is terminal before this receipt becomes ACK.
        const revoked = fixture.kernel.revokeActiveRunsForOwner(ownerId, "owner_changed");
        const cleared = fixture.kernel.clearOwnerState(ownerId);
        return {
          ownerId,
          revokedRunIds: revoked.runIds,
          invalidatedBindingIds: cleared.invalidatedBindingIds,
        };
      },
    });
    authority = barrier.state;
    expect(barrier.receipt.revokedRunIds).toContain(unknownToSwift.runId);
    expect(fixture.store.getRow(
      "SELECT status, final_text FROM runs WHERE run_id = ?",
      [unknownToSwift.runId],
    )).toMatchObject({ status: "cancelled", final_text: null });
    expect(readToolInvocation(fixture.store, pendingInvocation.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_attempt_terminal",
    });

    authority = establishRuntimeOwner(authority, "owner-b").state;
    expect(authority).toEqual({ ownerId: "owner-b", established: true });
    expectCode(() => fixture.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: unknownToSwift.runId,
      attemptId: unknownToSwift.attemptId,
      terminalStatus: "completed",
    }), "run_terminal");
    expect(fixture.store.getRow(
      "SELECT status, final_text FROM runs WHERE run_id = ?",
      [unknownToSwift.runId],
    )).toMatchObject({ status: "cancelled", final_text: null });
    fixture.store.close();
  });

  it("uses the canonical capability ledger, rejects replay, and revokes on terminal completion", () => {
    const fixture = createFixture();
    const run = fixture.kernel.beginExternalSurfaceRun(beginInput(fixture.sessionId));
    const invocation = fixture.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "voice-tool-1",
      toolName: "get_memories",
      toolInput: { limit: 3 },
      activeOwnerId: "owner",
    });
    expectCode(() => fixture.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      terminalStatus: "completed",
    }), "external_invocations_pending");
    fixture.kernel.markRunToolInvocationDispatched(invocation);
    fixture.kernel.completeRunToolInvocation({
      ...invocationIdentity(invocation),
      capabilityRef: invocation.capabilityRef,
      activeOwnerId: "owner",
      outcome: "succeeded",
      result: "{\"ok\":true}",
    });
    expect(readToolInvocation(fixture.store, invocation.invocationId).status).toBe("succeeded");
    expect(fixture.kernel.getRun({
      ownerId: "owner",
      runId: run.runId,
    }).toolInvocations).toEqual([{
      invocationId: "voice-tool-1",
      runId: run.runId,
      attemptId: run.attemptId,
      toolName: "get_memories",
      status: "succeeded",
      errorCode: null,
      preparedAtMs: expect.any(Number),
      dispatchedAtMs: expect.any(Number),
      completedAtMs: expect.any(Number),
      updatedAtMs: expect.any(Number),
    }]);
    expectCode(() => fixture.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "voice-tool-1",
      toolName: "get_memories",
      toolInput: { limit: 3 },
      activeOwnerId: "owner",
    }), "invocation_replayed");

    expect(fixture.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      terminalStatus: "completed",
    })).toMatchObject({ duplicate: false, terminalStatus: "completed" });
    expect(fixture.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      terminalStatus: "completed",
    })).toMatchObject({ duplicate: true });
    expectCode(() => fixture.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: fixture.sessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "voice-tool-after-terminal",
      toolName: "get_memories",
      toolInput: {},
      activeOwnerId: "owner",
    }), "run_terminal");
    fixture.store.close();
  });

  it("recovers an orphaned external run after daemon restart with a superseding attempt", () => {
    const root = newRoot();
    const databasePath = join(root, "agent.sqlite");
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    const session = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
    }, () => 1);
    let kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
    const before = kernel.beginExternalSurfaceRun(beginInput(session.agentSessionId));
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: true });
    kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [before.runId])).toEqual({ status: "orphaned" });
    const recovered = kernel.beginExternalSurfaceRun({ ...beginInput(session.agentSessionId), requestId: "restart-begin" });
    expect(recovered).toMatchObject({ duplicate: true, runId: before.runId });
    expect(recovered.attemptId).not.toBe(before.attemptId);
    expectCode(() => kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: recovered.runId,
      attemptId: before.attemptId,
      invocationId: "stale-attempt-tool",
      toolName: "get_memories",
      toolInput: {},
      activeOwnerId: "owner",
    }), "attempt_superseded");
    expect(kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: recovered.runId,
      attemptId: recovered.attemptId,
      invocationId: "recovered-tool",
      toolName: "get_memories",
      toolInput: {},
      activeOwnerId: "owner",
    })).toMatchObject({ attemptId: recovered.attemptId, canonicalToolName: "get_memories" });
    store.close();
  });

  it("reroutes permission-like spawn proposals to native tools and rejects external targets", () => {
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Check whether Omi has screen recording permission" },
      originatingPrompt: "Can you check Omi's screen recording permission?",
    })).toEqual({
      action: "execute",
      toolName: "check_permission_status",
      toolInput: { type: "screen_recording" },
      recoveredFromDelegation: true,
    });
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Request microphone permission" },
      originatingPrompt: "Please grant microphone permission",
    })).toMatchObject({ action: "execute", toolName: "request_permission", toolInput: { type: "microphone" } });
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Check Slack's microphone permission" },
      originatingPrompt: "Does Slack have microphone permission?",
    })).toMatchObject({ action: "reject", code: "permission_target_rejected" });
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Fix the screen recording permission somehow" },
      originatingPrompt: "Fix screen recording",
    })).toMatchObject({ action: "reject", code: "permission_route_rejected" });

    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "microphone" },
      originatingPrompt: "Please grant Omi microphone permission",
    })).toMatchObject({
      action: "execute",
      toolName: "request_permission",
      toolInput: { type: "microphone" },
    });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "microphone" },
      originatingPrompt: "Why can you not hear me?",
    })).toMatchObject({ action: "reject", code: "permission_request_not_authorized" });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "microphone" },
      originatingPrompt: "Yes, go ahead",
      precedingAssistantText: "Would you like me to request Omi's microphone permission?",
    })).toMatchObject({ action: "execute", toolName: "request_permission" });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      originatingPrompt: "Request it",
      precedingAssistantText: "I cannot see your screen because Omi needs Screen Recording permission. I can request that permission now.",
    })).toMatchObject({ action: "execute", toolName: "request_permission", toolInput: { type: "screen_recording" } });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      originatingPrompt: "Request permissions",
      precedingAssistantText: "Omi needs microphone and Screen Recording permissions before continuing.",
    })).toMatchObject({ action: "reject", code: "permission_request_not_authorized" });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "microphone" },
      originatingPrompt: "Request it",
      precedingAssistantText: "Omi needs Screen Recording permission before I can see your screen.",
    })).toMatchObject({ action: "reject", code: "permission_request_not_authorized" });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      originatingPrompt: "Request it",
      precedingAssistantText: "Slack needs Screen Recording permission before it can share your screen.",
    })).toMatchObject({ action: "reject", code: "permission_target_rejected" });
    expect(routeExternalSurfaceTool({
      toolName: "check_permission_status",
      toolInput: { type: "microphone" },
      originatingPrompt: "Check Slack's microphone permission",
    })).toMatchObject({ action: "reject", code: "permission_target_rejected" });
  });

  it("canonicalizes screen-share vocabulary to Omi's Screen Recording permission", () => {
    for (const [phrase, inputType] of [
      ["screen share", "screen_share"],
      ["screen sharing", "screen_sharing"],
      ["screen-share", "screen-share"],
    ] as const) {
      expect(routeExternalSurfaceTool({
        toolName: "request_permission",
        toolInput: { type: inputType },
        originatingPrompt: `Please request Omi's ${phrase} permission`,
      })).toEqual({
        action: "execute",
        toolName: "request_permission",
        toolInput: { type: "screen_recording" },
        recoveredFromDelegation: false,
      });
    }

    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Request Omi's screen-sharing permission" },
      originatingPrompt: "Can you request screen share permissions?",
    })).toEqual({
      action: "execute",
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      recoveredFromDelegation: true,
    });
    expect(routeExternalSurfaceTool({
      toolName: "request_permission",
      toolInput: { type: "screen_share" },
      originatingPrompt: "Please request Slack's screen share permission",
    })).toMatchObject({ action: "reject", code: "permission_target_rejected" });
    expect(routeExternalSurfaceTool({
      toolName: "check_permission_status",
      toolInput: { type: "screen_share" },
      originatingPrompt: "Can you check Slack's screen share permission?",
    })).toMatchObject({ action: "reject", code: "permission_target_rejected" });
  });

  it("requires explicit persisted pill-management intent before attention mutation", () => {
    expect(routeExternalSurfaceTool({
      toolName: "set_desktop_attention_override",
      toolInput: { subjectKind: "run", subjectId: "run-1", dismissed: true },
      originatingPrompt: "Research the issue in the background",
    })).toMatchObject({ action: "reject", code: "pill_management_intent_required" });
    expect(routeExternalSurfaceTool({
      toolName: "set_desktop_attention_override",
      toolInput: { subjectKind: "run", subjectId: "run-1", dismissed: true },
      originatingPrompt: "Dismiss that background agent pill",
    })).toMatchObject({ action: "execute", toolName: "set_desktop_attention_override" });
  });

  it("defaults external spawns to Omi unless the current user selects one provider", () => {
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Sleep for five seconds", provider: "hermes" },
      originatingPrompt: "Have an agent sleep for five seconds.",
    })).toEqual({
      action: "execute",
      toolName: "spawn_agent",
      toolInput: { objective: "Sleep for five seconds" },
      recoveredFromDelegation: false,
    });

    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Check X trends", provider: "hermes" },
      originatingPrompt: "Ask OpenCloud what is trending on X.",
    })).toEqual({
      action: "execute",
      toolName: "spawn_agent",
      toolInput: { objective: "Check X trends", provider: "openclaw" },
      recoveredFromDelegation: false,
    });

    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Review the release notes" },
      originatingPrompt: "Run this in Hermes.",
    })).toEqual({
      action: "execute",
      toolName: "spawn_agent",
      toolInput: { objective: "Review the release notes", provider: "hermes" },
      recoveredFromDelegation: false,
    });
  });

  it("applies semantic safety policy from the persisted external run prompt", () => {
    const permissionFixture = createFixture();
    const permissionRun = permissionFixture.kernel.beginExternalSurfaceRun({
      ...beginInput(permissionFixture.sessionId),
      prompt: "Can you check Omi's screen recording permission?",
    });
    expect(permissionFixture.kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: permissionFixture.sessionId,
      runId: permissionRun.runId,
      attemptId: permissionRun.attemptId,
      invocationId: "permission-route",
      toolName: "spawn_agent",
      toolInput: {
        objective: "Check whether Omi has screen recording permission",
      },
    })).toMatchObject({
      toolName: "check_permission_status",
      toolInput: { type: "screen_recording" },
      recoveredFromDelegation: true,
    });
    permissionFixture.store.close();

    const pillFixture = createFixture();
    const pillRun = pillFixture.kernel.beginExternalSurfaceRun({
      ...beginInput(pillFixture.sessionId),
      prompt: "Research the issue in the background",
    });
    expectCode(() => pillFixture.kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: pillFixture.sessionId,
      runId: pillRun.runId,
      attemptId: pillRun.attemptId,
      invocationId: "pill-route",
      toolName: "set_desktop_attention_override",
      toolInput: { subjectKind: "run", subjectId: "run-1", dismissed: true },
    }), "pill_management_intent_required");
    pillFixture.store.close();
  });

  it("routes explicit screen-share permission proposals through one policy for typed and realtime surfaces", async () => {
    const typed = createKernelHarness(join(newRoot(), "typed.sqlite"), "acp");
    typed.adapter.deferResult();
    const typedRunPromise = typed.kernel.executeRun({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "typed-chat",
      requestId: "typed-permission-run",
      prompt: "Can you request screen share permissions?",
      cwd: "/tmp/work",
    });
    await waitUntil(() => typed.adapter.executed.length === 1);
    const typedAttempt = typed.adapter.executed[0];

    const realtime = createFixture();
    const realtimeRun = realtime.kernel.beginExternalSurfaceRun({
      ...beginInput(realtime.sessionId),
      prompt: "Can you request screen share permissions?",
    });
    const proposal = {
      toolName: "spawn_agent",
      toolInput: { objective: "Request Omi's screen-sharing permission" },
    };
    const typedRoute = typed.kernel.routeRelayedRunToolProposal({
      capabilityRef: typedAttempt.toolCapabilityRef,
      activeOwnerId: "owner",
      ...proposal,
    });
    const realtimeRoute = realtime.kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: realtime.sessionId,
      runId: realtimeRun.runId,
      attemptId: realtimeRun.attemptId,
      invocationId: "realtime-permission",
      ...proposal,
    });
    expect(typedRoute).toEqual(realtimeRoute);
    expect(typedRoute).toEqual({
      action: "execute",
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      recoveredFromDelegation: true,
    });

    const typedInvocation = typed.kernel.authorizeRelayedRunToolInvocation({
      capabilityRef: typedAttempt.toolCapabilityRef,
      invocationId: "typed-permission",
      toolName: typedRoute.toolName,
      toolInput: typedRoute.toolInput,
      activeOwnerId: "owner",
    });
    const realtimeInvocation = realtime.kernel.authorizeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: realtime.sessionId,
      runId: realtimeRun.runId,
      attemptId: realtimeRun.attemptId,
      invocationId: "realtime-permission",
      toolName: realtimeRoute.toolName,
      toolInput: realtimeRoute.toolInput,
      activeOwnerId: "owner",
    });
    expect(readToolInvocation(typed.store, typedInvocation.invocationId).toolName).toBe("request_permission");
    expect(readToolInvocation(realtime.store, realtimeInvocation.invocationId).toolName).toBe("request_permission");

    for (const [kernel, invocation] of [
      [typed.kernel, typedInvocation],
      [realtime.kernel, realtimeInvocation],
    ] as const) {
      kernel.markRunToolInvocationDispatched(invocation);
      kernel.completeRunToolInvocation({
        ...invocationIdentity(invocation),
        capabilityRef: invocation.capabilityRef,
        activeOwnerId: "owner",
        outcome: "succeeded",
        result: "{\"ok\":true}",
      });
    }

    const externalProposal = {
      toolName: "spawn_agent",
      toolInput: { objective: "Check Slack's microphone permission" },
    };
    expectCode(() => typed.kernel.routeRelayedRunToolProposal({
      capabilityRef: typedAttempt.toolCapabilityRef,
      activeOwnerId: "owner",
      ...externalProposal,
    }), "permission_target_rejected");
    expectCode(() => realtime.kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: realtime.sessionId,
      runId: realtimeRun.runId,
      attemptId: realtimeRun.attemptId,
      invocationId: "realtime-external-permission",
      ...externalProposal,
    }), "permission_target_rejected");

    const sqlRoute = typed.kernel.routeRelayedRunToolProposal({
      capabilityRef: typedAttempt.toolCapabilityRef,
      activeOwnerId: "owner",
      toolName: "execute_sql",
      toolInput: { query: "SELECT 'DELETE' AS harmless /* UPDATE ignored */" },
    });
    expect(sqlRoute).toMatchObject({
      toolName: "execute_sql",
      toolInput: { query: "SELECT 'DELETE' AS harmless /* UPDATE ignored */", read_only: true },
    });
    const sqlInvocation = typed.kernel.authorizeRelayedRunToolInvocation({
      capabilityRef: typedAttempt.toolCapabilityRef,
      invocationId: "typed-sql-read",
      toolName: sqlRoute.toolName,
      toolInput: sqlRoute.toolInput,
      activeOwnerId: "owner",
    });
    expect(readToolInvocation(typed.store, sqlInvocation.invocationId)).toMatchObject({
      toolName: "execute_sql",
      status: "prepared",
    });
    typed.kernel.markRunToolInvocationDispatched(sqlInvocation);
    typed.kernel.completeRunToolInvocation({
      ...invocationIdentity(sqlInvocation),
      capabilityRef: sqlInvocation.capabilityRef,
      activeOwnerId: "owner",
      outcome: "succeeded",
      result: "[]",
    });
    const beforeRejectedSql = Number(typed.store.getRow(
      "SELECT COUNT(*) AS count FROM tool_invocation_ledger",
    ).count);
    expectCode(() => typed.kernel.routeRelayedRunToolProposal({
      capabilityRef: typedAttempt.toolCapabilityRef,
      activeOwnerId: "owner",
      toolName: "execute_sql",
      toolInput: { query: "WITH target AS (SELECT 1) UPDATE action_items SET completed = 1" },
    }), "sql_write_rejected");
    expect(Number(typed.store.getRow(
      "SELECT COUNT(*) AS count FROM tool_invocation_ledger",
    ).count)).toBe(beforeRejectedSql);

    realtime.kernel.completeExternalSurfaceRun({
      ownerId: "owner",
      sessionId: realtime.sessionId,
      runId: realtimeRun.runId,
      attemptId: realtimeRun.attemptId,
      terminalStatus: "completed",
    });
    realtime.store.close();
    typed.adapter.resolveDeferred();
    await typedRunPromise;
    typed.store.close();
  });

  it("stamps an authorized typed-chat spawn and inherits the exact admitted parent snapshot", async () => {
    const { store, adapter, kernel } = createKernelHarness(join(newRoot(), "typed-spawn.sqlite"), "acp");
    const parentSurface = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "typed-spawn" },
      defaultAdapterId: "acp",
    }, () => 1);
    kernel.updateContextSource({
      ownerId: "owner",
      sessionId: parentSurface.agentSessionId,
      surfaceKind: "main_chat",
      source: "workspace",
      sourceRevision: "typed-workspace@1",
      outcome: "available",
      capturedAtMs: 2,
      payload: { repository: "omi", branch: "typed-spawn" },
    }).snapshot;
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-user",
      role: "user",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "DEFER_TYPED_PARENT_9515 research the release plan",
      contentBlocks: [],
      resources: [],
      createdAtMs: 3,
    });
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-assistant",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "preexisting partial assistant text",
      contentBlocks: [],
      resources: [],
      createdAtMs: 4,
    });
    const admittedSnapshot = kernel.contextSnapshot(parentSurface.agentSessionId, "owner", "main_chat");
    adapter.deferOnlyPromptIncludes = "# User Message\nDEFER_TYPED_PARENT_9515";
    adapter.deferResult();
    const parentPromise = kernel.executeRun({
      ownerId: "owner",
      sessionId: parentSurface.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "typed-spawn",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "typed-chat",
      requestId: "typed-spawn-parent",
      producingTurnId: "typed-spawn-assistant",
      prompt: "DEFER_TYPED_PARENT_9515 research the release plan",
      cwd: "/tmp/work",
    });
    await waitUntil(() => adapter.executed.length === 1);
    const parentAttempt = adapter.executed[0];
    const invocationId = "typed-generated-spawn";
    const routed = kernel.routeRelayedRunToolProposal({
      capabilityRef: parentAttempt.toolCapabilityRef,
      activeOwnerId: "owner",
      toolName: "spawn_agent",
      toolInput: {
        objective: "Research release-plan risks",
        requestedAgentCount: 2,
        metadata: { producerJournal: { forged: true } },
      },
    });
    expect(routed).toMatchObject({
      toolName: "spawn_agent",
      recoveredFromDelegation: false,
      toolInput: { objective: "Research release-plan risks", requestedAgentCount: 2 },
    });
    const authorized = kernel.authorizeRelayedRunToolInvocation({
      capabilityRef: parentAttempt.toolCapabilityRef,
      invocationId,
      toolName: routed.toolName,
      toolInput: routed.toolInput,
      activeOwnerId: "owner",
    });
    const prepared = kernel.prepareAuthorizedSpawnAgentControlInvocation({
      ownerId: authorized.ownerId,
      sessionId: authorized.sessionId,
      runId: authorized.runId,
      attemptId: authorized.attemptId,
      invocationId: authorized.invocationId,
      surfaceKind: authorized.surfaceKind,
      toolInput: { ...routed.toolInput, originSurfaceKind: "realtime" },
    });
    expect(prepared).toMatchObject({
      parentRunId: authorized.runId,
      producerJournal: {
        schemaVersion: 1,
        surface: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "typed-spawn" },
        continuityKey: `agent_spawn:${invocationId}`,
        producerRunId: authorized.runId,
        producerTurnId: "typed-spawn-assistant",
        userText: "DEFER_TYPED_PARENT_9515 research the release plan",
        assistantText: "I started a background agent for that.",
        objective: "Research release-plan risks",
        title: "Delegated: Research release-plan risks",
      },
      toolInput: {
        originSurfaceKind: "main_chat",
        parentRunId: authorized.runId,
        externalRefId: expect.stringMatching(/^[a-f0-9-]{36}$/),
      },
    });
    expect((prepared.toolInput.metadata as any).producerJournal.forged).toBeUndefined();

    kernel.markRunToolInvocationDispatched(authorized);
    const previousArtifactRoot = process.env.OMI_AGENT_ARTIFACTS_DIR;
    process.env.OMI_AGENT_ARTIFACTS_DIR = newRoot();
    let raw: string;
    try {
      raw = await handleAgentControlToolCall({
        kernel,
        callerSessionId: authorized.sessionId,
        executionRole: "coordinator",
        providerBoundary: "local_user:acp",
        defaultAdapterId: "acp",
        authorizedProducerJournal: prepared.producerJournal,
        authorizedCallerRunId: prepared.parentRunId,
        getOwnerId: () => "owner",
      }, authorized.canonicalToolName, prepared.toolInput);
    } finally {
      if (previousArtifactRoot === undefined) delete process.env.OMI_AGENT_ARTIFACTS_DIR;
      else process.env.OMI_AGENT_ARTIFACTS_DIR = previousArtifactRoot;
    }
    kernel.completeRunToolInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "succeeded",
      result: raw,
    });
    const result = JSON.parse(raw) as {
      run: { runId: string };
      session: { sessionId: string };
      agents: Array<{ run: { runId: string }; session: { sessionId: string } }>;
    };
    expect(result.agents).toHaveLength(2);
    const childRunIds = result.agents.map((agent) => agent.run.runId);
    await waitUntil(() => childRunIds.every((runId) => String(store.getRow(
      "SELECT status FROM runs WHERE run_id = ?",
      [runId],
    ).status) === "succeeded"));
    await waitUntil(() => {
      const blocks = JSON.parse(String(store.getRow(
        "SELECT content_blocks_json FROM conversation_turns WHERE turn_id = ?",
        ["typed-spawn-assistant"],
      ).content_blocks_json)) as Array<{ type?: string }>;
      return blocks.filter((block) => block.type === "agentCompletion").length === 2;
    });
    const parentInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE run_id = ?",
      [authorized.runId],
    ).input_json));
    const childInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE run_id = ?",
      [result.run.runId],
    ).input_json));
    expect(childInput.contextSnapshotVersion).toBe(parentInput.contextSnapshotVersion);
    expect(childInput.contextSnapshotGeneration).toBe(parentInput.contextSnapshotGeneration);
    // The immutable source snapshot is inherited exactly, while the renderer
    // and capability fingerprints are intentionally projected for a leaf.
    expect(childInput.contextRendererFingerprint).not.toBe(parentInput.contextRendererFingerprint);
    expect(childInput.contextCapabilityVersion).not.toBe(parentInput.contextCapabilityVersion);
    expect(childInput.contextRendererFingerprint).toBe(childInput.admittedContextSnapshot.rendererFingerprint);
    expect(childInput.contextCapabilityVersion).toBe(childInput.admittedContextSnapshot.capabilityVersion);
    expect(childInput.contextSnapshotVersion).toBe(admittedSnapshot.version);
    expect(childInput.contextSnapshotGeneration).toBe(admittedSnapshot.snapshotGeneration);
    const ensured = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    });
    expect(ensured.userTurn).toBeNull();
    expect(ensured.assistantTurn).toMatchObject({
      turnId: "typed-spawn-assistant",
      content: "preexisting partial assistant text",
      status: "streaming",
      producingRunId: authorized.runId,
      producingAttemptId: authorized.attemptId,
    });
    for (const childRunId of childRunIds) {
      expect(ensured.assistantTurn.contentBlocks).toEqual(expect.arrayContaining([
        expect.objectContaining({ type: "agentSpawn", runId: childRunId }),
        expect.objectContaining({ type: "agentCompletion", runId: childRunId }),
      ]));
    }
    expect(ensured.assistantTurn.contentBlocks.filter((block) => block.type === "agentSpawn")).toHaveLength(2);
    expect(ensured.assistantTurn.contentBlocks.filter((block) => block.type === "agentCompletion")).toHaveLength(2);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [parentSurface.conversationId],
    ).count).toBe(2);

    const writeRunInput = (runId: string, value: Record<string, unknown>) => {
      store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [JSON.stringify(value), runId]);
    };
    const childWithProducerTarget = (
      producerTurnId: string,
      surface = prepared.producerJournal.surface,
    ) => {
      const value = structuredClone(childInput);
      value.metadata.producerJournal.producerTurnId = producerTurnId;
      value.metadata.producerJournal.surface = surface;
      return value;
    };
    writeRunInput(result.run.runId, childWithProducerTarget("forged-producer-turn"));
    expect(() => kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    })).toThrow(/does not match the parent query producing turn/i);
    writeRunInput(result.run.runId, childInput);

    const crossSurface = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "typed-spawn-cross" },
      defaultAdapterId: "acp",
    }, () => 5);
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: crossSurface.conversationId,
      turnId: "cross-session-assistant",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "cross-session target",
      contentBlocks: [],
      resources: [],
      producingRunId: authorized.runId,
      producingAttemptId: authorized.attemptId,
      createdAtMs: 6,
    });
    writeRunInput(authorized.runId, { ...parentInput, producingTurnId: "cross-session-assistant" });
    writeRunInput(result.run.runId, childWithProducerTarget("cross-session-assistant", {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "typed-spawn-cross",
    }));
    expect(() => kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    })).toThrow(/outside the parent session conversation/i);
    writeRunInput(authorized.runId, parentInput);
    writeRunInput(result.run.runId, childInput);

    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-user-target",
      role: "user",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "must not become the producer target",
      contentBlocks: [],
      resources: [],
      producingRunId: authorized.runId,
      producingAttemptId: authorized.attemptId,
      createdAtMs: 7,
    });
    writeRunInput(authorized.runId, { ...parentInput, producingTurnId: "typed-spawn-user-target" });
    writeRunInput(result.run.runId, childWithProducerTarget("typed-spawn-user-target"));
    expect(() => kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    })).toThrow(/must be an assistant turn/i);
    writeRunInput(authorized.runId, parentInput);
    writeRunInput(result.run.runId, childInput);

    updateJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-assistant",
      metadataJson: JSON.stringify({ terminalMarker: "discarded_terminal_projection" }),
    });
    expect(() => kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    })).toThrow(/rejects terminal-marker targets/i);
    updateJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-assistant",
      metadataJson: "{}",
    });

    adapter.resolveDeferred({
      terminalStatus: "succeeded",
      text: "parent response completed",
      adapterSessionId: parentAttempt.binding.adapterNativeSessionId,
    });
    const parentResult = await parentPromise;
    expect(parentResult).toMatchObject({ terminalStatus: "succeeded" });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [authorized.runId])).toEqual({ status: "succeeded" });
    expect(store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [authorized.attemptId])).toEqual({ status: "succeeded" });
    terminalizeJournalTurn(store, {
      ownerId: "owner",
      conversationId: parentSurface.conversationId,
      turnId: "typed-spawn-assistant",
      producingRunId: authorized.runId,
      producingAttemptId: authorized.attemptId,
      disposition: "accept",
      content: "parent response completed",
      replaceContentBlocks: [],
      replaceResources: [],
    });
    const terminalProducer = store.getRow(
      "SELECT status, content_blocks_json FROM conversation_turns WHERE turn_id = ?",
      ["typed-spawn-assistant"],
    );
    expect(terminalProducer.status).toBe("completed");
    const terminalBlocks = JSON.parse(String(terminalProducer.content_blocks_json));
    for (const childRunId of childRunIds) {
      expect(terminalBlocks).toEqual(expect.arrayContaining([
        expect.objectContaining({ type: "agentSpawn", runId: childRunId }),
        expect.objectContaining({ type: "agentCompletion", runId: childRunId }),
      ]));
    }
    store.close();
  });

  it("stamps trusted realtime origin on exact generated spawn payload before the production control parser", async () => {
    const root = newRoot();
    const { store, adapter, kernel } = createKernelHarness(join(root, "agent.sqlite"), "pi-mono");
    const session = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "pi-mono",
    }, () => 1);
    const run = kernel.beginExternalSurfaceRun({
      ...beginInput(session.agentSessionId),
      prompt: "Research the launch plan in the background",
    });

    const routed = kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "generated-spawn-1",
      toolName: "spawn_agent",
      // Exact generated realtime schema: originSurfaceKind is intentionally absent.
      toolInput: {
        objective: "Research the launch plan",
        // This optional alias is advertised by GeneratedRealtimeTools.swift.
        // The external path must accept it through the strict control parser.
        brief: "Checking the launch plan",
      },
    });
    expect(routed.toolInput).toMatchObject({
      objective: "Research the launch plan",
      brief: "Checking the launch plan",
      originSurfaceKind: "realtime",
      parentRunId: run.runId,
      title: "Delegated: Research the launch plan",
      metadata: {
        producerJournal: {
          schemaVersion: 1,
          continuityKey: "voice:voice-turn-1",
          userText: "Research the launch plan in the background",
          assistantText: "I started a background agent for that.",
          objective: "Research the launch plan",
          title: "Delegated: Research the launch plan",
        },
      },
    });
    expect(kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "generated-spawn-override",
      toolName: "spawn_agent",
      toolInput: { objective: "Research safely", originSurfaceKind: "main_chat" },
    }).toolInput).toMatchObject({ originSurfaceKind: "realtime" });

    const previousArtifactRoot = process.env.OMI_AGENT_ARTIFACTS_DIR;
    process.env.OMI_AGENT_ARTIFACTS_DIR = newRoot();
    let resultText: string;
    try {
      resultText = await handleAgentControlToolCall({
        kernel,
        callerSessionId: session.agentSessionId,
        executionRole: "coordinator",
        providerBoundary: "managed_cloud",
        defaultAdapterId: "pi-mono",
        authorizedProducerJournal: parseAgentSpawnProducerJournalDescriptor(
          ((routed.toolInput.metadata as any) ?? {}).producerJournal,
        ),
        authorizedCallerRunId: run.runId,
        getOwnerId: () => "owner",
      }, "spawn_agent", routed.toolInput);
    } finally {
      if (previousArtifactRoot === undefined) delete process.env.OMI_AGENT_ARTIFACTS_DIR;
      else process.env.OMI_AGENT_ARTIFACTS_DIR = previousArtifactRoot;
    }
    const result = JSON.parse(resultText) as Record<string, unknown>;
    expect(result).toMatchObject({
      ok: true,
      requestedAgentCount: 1,
      // The spawn return now snapshots the durable child lifecycle after its
      // first attempt is admitted; this fixture has already crossed queued.
      run: { status: "starting", parentRunId: run.runId },
    });
    await waitUntil(() => adapter.executed.length === 1);
    expect(adapter.executed).toHaveLength(1);
    const child = result.run as { runId: string };
    const childSession = result.session as { sessionId: string };
    await waitUntil(() => String(store.getRow(
      "SELECT status FROM runs WHERE run_id = ?",
      [child.runId],
    ).status) === "succeeded");
    const descriptor = (routed.toolInput.metadata as any).producerJournal;
    const ensured = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: childSession.sessionId,
      runId: child.runId,
    });
    expect(ensured.userTurn).not.toBeNull();
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [ensured.conversationId],
    ).count).toBe(2);
    expect(ensured.assistantTurn.contentBlocks).toEqual([
      expect.objectContaining({
        type: "agentSpawn",
        sessionId: childSession.sessionId,
        runId: child.runId,
        pillId: descriptor.pillId,
      }),
      expect.objectContaining({
        type: "agentCompletion",
        sessionId: childSession.sessionId,
        runId: child.runId,
      }),
    ]);
    const receipt = agentSpawnJournalReceipt(descriptor);
    expect(receipt).toEqual({
      accepted: true,
      continuityKey: "voice:voice-turn-1",
      userTurnId: stableAgentSpawnTurnId("voice:voice-turn-1", "user"),
      assistantTurnId: stableAgentSpawnTurnId("voice:voice-turn-1", "assistant"),
      assistantText: "Delegated: Research the launch plan started and is working in the background.",
    });
    expect(JSON.parse(compactRealtimeSpawnToolResult('{"ok":true}', descriptor))).toMatchObject({
      ok: false,
      error: { code: "realtime_spawn_missing_tool_result_envelope" },
      providerResult: { ok: false, code: "realtime_spawn_missing_tool_result_envelope" },
      toolResultEnvelope: expect.objectContaining({ version: 1, status: "failed" }),
    });

    // Once the spawn receipt commits the exchange, any late provider mutation
    // is a strict identity collision rather than an alternate projection.
    expect(() => recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: ensured.conversationId,
      turnId: receipt.userTurnId!,
      role: "user",
      surfaceKind: "main_chat",
      origin: "realtime_voice",
      status: "completed",
      content: "Research the launch plan in the background",
      contentBlocks: [],
      resources: [],
      metadataJson: JSON.stringify({
        continuityKey: receipt.continuityKey,
        messageSource: "realtime_voice",
      }),
    })).toThrow(/identity collision has different journal content/i);
    expect(() => recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: ensured.conversationId,
      turnId: receipt.assistantTurnId,
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "realtime_voice",
      status: "completed",
      content: "Sure — the background work has started.",
      contentBlocks: [],
      resources: [],
      metadataJson: JSON.stringify({
        continuityKey: receipt.continuityKey,
        messageSource: "realtime_voice",
      }),
    })).toThrow(/identity collision has different journal content/i);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [ensured.conversationId],
    ).count).toBe(2);
    const parentInput = JSON.parse(String(store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [run.runId]).input_json));
    const childInput = JSON.parse(String(store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [child.runId]).input_json));
    expect(childInput.contextSnapshotVersion).toBe(parentInput.contextSnapshotVersion);
    expect(childInput.contextSnapshotGeneration).toBe(parentInput.contextSnapshotGeneration);
    expect(childInput.metadata).toMatchObject({ brief: "Checking the launch plan" });
    store.close();
  });

  it("starts an explicitly requested OpenClaw child independently when its primary producer turn is journaled", async () => {
    const root = newRoot();
    const store = new SqliteAgentStore({ databasePath: join(root, "agent.sqlite"), reconcileOnOpen: false });
    const registry = new AdapterRegistry();
    const piMono = new FakeRuntimeAdapter("pi-mono");
    const openClaw = new FakeRuntimeAdapter("openclaw");
    registry.register("pi-mono", () => piMono);
    registry.register("openclaw", () => openClaw);
    const kernel = new AgentRuntimeKernel({ store, registry });
    const session = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "pi-mono",
    }, () => 1);
    const run = kernel.beginExternalSurfaceRun({
      ...beginInput(session.agentSessionId),
      prompt: "Ask OpenClaw to check the release notes in the background",
    });
    const producerTurnId = "typed-openclaw-producer-turn";
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: session.conversationId,
      turnId: producerTurnId,
      role: "assistant",
      surfaceKind: "realtime_voice",
      origin: "typed_chat",
      status: "streaming",
      content: "Starting OpenClaw.",
      contentBlocks: [],
      resources: [],
      producingRunId: run.runId,
      producingAttemptId: run.attemptId,
      createdAtMs: 2,
    });
    // Production realtime turns can carry the bounded recent-context window
    // back through the accepted spawn result. Keep this fixture deliberately
    // large so the regression proves compaction happens *after* child receipt
    // extraction rather than silently projecting away `agents[0]` first.
    for (let index = 0; index < 24; index += 1) {
      recordJournalTurn(store, {
        ownerId: "owner",
        conversationId: session.conversationId,
        turnId: `realtime-context-${index}`,
        role: index % 2 === 0 ? "user" : "assistant",
        surfaceKind: "realtime_voice",
        origin: "realtime_voice",
        status: "completed",
        content: `Large retained context ${index}: ${"x".repeat(12_000)}`,
        contentBlocks: [],
        resources: [],
        createdAtMs: 10 + index,
      });
    }
    const parentInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE run_id = ?",
      [run.runId],
    ).input_json));
    store.execute(
      "UPDATE runs SET input_json = ? WHERE run_id = ?",
      [JSON.stringify({ ...parentInput, producingTurnId: producerTurnId }), run.runId],
    );
    const routed = kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "realtime-openclaw-spawn",
      toolName: "spawn_agent",
      toolInput: {
        objective: "Check the release notes",
        provider: "openclaw",
        // Gemini sends this optional field because it is present in the
        // realtime schema. It must not reject the OpenClaw admission path.
        brief: "Checking release notes",
      },
    });
    const producerJournal = parseAgentSpawnProducerJournalDescriptor(
      ((routed.toolInput.metadata as Record<string, unknown>).producerJournal),
    );
    expect(producerJournal.producerTurnId).toBe(producerTurnId);
    expect(producerJournal.producerRunId).toBe(run.runId);

    const previousArtifactRoot = process.env.OMI_AGENT_ARTIFACTS_DIR;
    process.env.OMI_AGENT_ARTIFACTS_DIR = newRoot();
    let startedText: string;
    try {
      startedText = await handleAgentControlToolCall({
        kernel,
        callerSessionId: session.agentSessionId,
        executionRole: "coordinator",
        providerBoundary: "managed_cloud",
        defaultAdapterId: "pi-mono",
        authorizedProducerJournal: producerJournal,
        authorizedCallerRunId: run.runId,
        authorizedToolInvocation: {
          invocationId: "realtime-openclaw-spawn",
          runId: run.runId,
          attemptId: run.attemptId,
          toolName: "spawn_agent",
        },
        getOwnerId: () => "owner",
      }, "spawn_agent", routed.toolInput);
    } finally {
      if (previousArtifactRoot === undefined) delete process.env.OMI_AGENT_ARTIFACTS_DIR;
      else process.env.OMI_AGENT_ARTIFACTS_DIR = previousArtifactRoot;
    }
    const started = JSON.parse(startedText) as Record<string, any>;

    expect(Buffer.byteLength(startedText, "utf8")).toBeGreaterThan(8 * 1024);
    expect(started.toolResultEnvelope).toMatchObject({
      version: 1,
      truncated: true,
      fullOutputRef: expect.stringMatching(/^artifact:/),
    });
    const compact = JSON.parse(compactRealtimeSpawnToolResult(startedText, producerJournal)) as Record<string, any>;
    expect(compact).toMatchObject({
      ok: true,
      child: {
        sessionId: expect.any(String),
        runId: expect.any(String),
        attemptId: expect.any(String),
        pillId: producerJournal.pillId,
      },
      providerResult: {
        ok: true,
        child: {
          sessionId: expect.any(String),
          runId: expect.any(String),
          attemptId: expect.any(String),
        },
      },
    });
    expect(compact.toolResultEnvelope.fullOutputRef).toBe(started.toolResultEnvelope.fullOutputRef);

    const finalizedText = finalizeRelayToolResult({
      identity: {
        invocationId: "realtime-openclaw-spawn",
        ownerId: "owner",
        sessionId: session.agentSessionId,
        runId: run.runId,
        attemptId: run.attemptId,
        toolName: "spawn_agent",
      },
      result: JSON.stringify(compact),
      outcome: "succeeded",
      kernel,
      artifactRoot: newRoot(),
    });
    const finalized = JSON.parse(finalizedText) as Record<string, any>;
    expect(Buffer.byteLength(finalizedText, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(finalized).toMatchObject({
      ok: true,
      child: {
        sessionId: compact.child.sessionId,
        runId: compact.child.runId,
        attemptId: compact.child.attemptId,
        pillId: producerJournal.pillId,
      },
      toolResultEnvelope: {
        version: 1,
        status: "succeeded",
        truncated: true,
        fullOutputRef: started.toolResultEnvelope.fullOutputRef,
      },
    });

    expect(started).toMatchObject({
      ok: true,
      run: { parentRunId: null },
      session: {
        defaultAdapterId: "openclaw",
        providerBoundary: "local_user:openclaw",
      },
    });
    await waitUntil(() => openClaw.executed.length === 1);
    expect(piMono.executed).toHaveLength(0);
    const child = started.run as { runId: string };
    const childSession = started.session as { sessionId: string };
    expect(JSON.parse(String(store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [child.runId]).input_json)).metadata)
      .toMatchObject({ brief: "Checking release notes" });
    const ensured = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: childSession.sessionId,
      runId: child.runId,
    });
    expect(ensured.assistantTurn.contentBlocks).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "agentSpawn", runId: child.runId, pillId: producerJournal.pillId }),
    ]));

    // Without the kernel-issued producer-journal authority, the same parent
    // remains a conventional managed delegation and cannot cross providers.
    const ordinaryParentLinked = JSON.parse(await handleAgentControlToolCall({
      kernel,
      callerSessionId: session.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
      getOwnerId: () => "owner",
    }, "spawn_agent", {
      objective: "Must remain inside the parent boundary",
      provider: "openclaw",
      parentRunId: run.runId,
      originSurfaceKind: "realtime",
    })) as Record<string, any>;
    expect(ordinaryParentLinked).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Managed Omi agents can only use Omi cloud routing.",
      },
    });
    store.close();
  });

  it("returns a sanitized structured result when external OpenClaw admission is unavailable", async () => {
    const root = newRoot();
    const store = new SqliteAgentStore({ databasePath: join(root, "agent.sqlite"), reconcileOnOpen: false });
    const registry = new AdapterRegistry();
    registry.register("pi-mono", () => new FakeRuntimeAdapter("pi-mono"));
    const kernel = new AgentRuntimeKernel({ store, registry });
    const session = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "pi-mono",
    }, () => 1);
    const run = kernel.beginExternalSurfaceRun({
      ...beginInput(session.agentSessionId),
      prompt: "Ask OpenClaw to check the release notes in the background",
    });
    const routed = kernel.routeExternalSurfaceToolInvocation({
      ownerId: "owner",
      sessionId: session.agentSessionId,
      runId: run.runId,
      attemptId: run.attemptId,
      invocationId: "realtime-openclaw-unavailable",
      toolName: "spawn_agent",
      toolInput: { objective: "Check the release notes", provider: "openclaw" },
    });
    const producerJournal = parseAgentSpawnProducerJournalDescriptor(
      ((routed.toolInput.metadata as Record<string, unknown>).producerJournal),
    );

    const rejected = JSON.parse(await handleAgentControlToolCall({
      kernel,
      callerSessionId: session.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
      authorizedProducerJournal: producerJournal,
      authorizedCallerRunId: run.runId,
      authorizedToolInvocation: {
        invocationId: "realtime-openclaw-unavailable",
        runId: run.runId,
        attemptId: run.attemptId,
        toolName: "spawn_agent",
      },
      getOwnerId: () => "owner",
    }, "spawn_agent", routed.toolInput));

    expect(rejected).toMatchObject({
      ok: false,
      error: {
        code: "provider_setup_needed",
        message: "OpenClaw needs setup before it can run an agent.",
        provider: "openclaw",
        retryable: true,
      },
      toolResultEnvelope: {
        version: 1,
        status: "failed",
        truncated: false,
        fullOutputRef: null,
        provenance: {
          runId: run.runId,
          toolName: "spawn_agent",
        },
      },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(1);
    store.close();
  });
});

function createFixture() {
  const store = new SqliteAgentStore({ stateDir: newRoot(), reconcileOnOpen: false });
  const session = resolveSurfaceSession(store, {
    ownerId: "owner",
    surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
    defaultAdapterId: "acp",
  }, () => 1);
  return {
    store,
    sessionId: session.agentSessionId,
    kernel: new AgentRuntimeKernel({ store, registry: new AdapterRegistry() }),
  };
}

function beginInput(sessionId: string) {
  return {
    ownerId: "owner",
    sessionId,
    turnId: "voice-turn-1",
    prompt: "Remember my latest request",
    mode: "act" as const,
    clientId: "realtime-hub",
    requestId: "begin-1",
  };
}

function invocationIdentity(invocation: AuthorizedRunToolInvocation) {
  return {
    invocationId: invocation.invocationId,
    ownerId: invocation.ownerId,
    sessionId: invocation.sessionId,
    runId: invocation.runId,
    attemptId: invocation.attemptId,
    profileGeneration: invocation.profileGeneration,
    manifestVersion: invocation.manifestVersion,
    manifestDigest: invocation.manifestDigest,
    daemonBootEpoch: invocation.daemonBootEpoch,
    executionGeneration: invocation.executionGeneration,
    inputHash: invocation.inputHash,
  };
}

function expectCode(work: () => unknown, code: string): void {
  try {
    work();
    throw new Error("Expected external authority rejection");
  } catch (error) {
    if (error instanceof ExternalSurfaceAuthorityError) {
      expect(error.code).toBe(code);
      return;
    }
    expect(error).toMatchObject({ code });
  }
}

function newRoot(): string {
  const root = mkdtempSync(join(tmpdir(), "omi-external-surface-"));
  roots.push(root);
  return root;
}
