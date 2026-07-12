import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import {
  agentSpawnJournalReceipt,
  attachAgentSpawnJournalReceipt,
  parseAgentSpawnProducerJournalDescriptor,
  stableAgentSpawnTurnId,
} from "../src/runtime/agent-spawn-journal.js";
import { handleAgentControlToolCall } from "../src/runtime/control-tools.js";
import { recordJournalTurn } from "../src/runtime/conversation-journal.js";
import { routeExternalSurfaceTool } from "../src/runtime/external-surface-tool-policy.js";
import { AgentRuntimeKernel, ExternalSurfaceAuthorityError } from "../src/runtime/kernel.js";
import type { AuthorizedRunToolInvocation } from "../src/runtime/run-tool-capability.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

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
      toolName: "check_permission_status",
      toolInput: { type: "microphone" },
      originatingPrompt: "Check Slack's microphone permission",
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

  it("routes identical permission proposals through one policy for typed and realtime surfaces", async () => {
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
      prompt: "Can you check Omi's screen recording permission?",
      cwd: "/tmp/work",
    });
    await waitUntil(() => typed.adapter.executed.length === 1);
    const typedAttempt = typed.adapter.executed[0];

    const realtime = createFixture();
    const realtimeRun = realtime.kernel.beginExternalSurfaceRun({
      ...beginInput(realtime.sessionId),
      prompt: "Can you check Omi's screen recording permission?",
    });
    const proposal = {
      toolName: "spawn_agent",
      toolInput: { objective: "Check whether Omi has screen recording permission" },
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
      toolName: "check_permission_status",
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
    expect(readToolInvocation(typed.store, typedInvocation.invocationId).toolName).toBe("check_permission_status");
    expect(readToolInvocation(realtime.store, realtimeInvocation.invocationId).toolName).toBe("check_permission_status");

    for (const [kernel, invocation] of [
      [typed.kernel, typedInvocation],
      [realtime.kernel, realtimeInvocation],
    ] as const) {
      kernel.markRunToolInvocationDispatched(invocation);
      kernel.completeRunToolInvocation({
        ...invocationIdentity(invocation),
        capabilityRef: invocation.capabilityRef,
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
    const sourceSnapshot = kernel.updateContextSource({
      ownerId: "owner",
      sessionId: parentSurface.agentSessionId,
      surfaceKind: "main_chat",
      source: "workspace",
      sourceRevision: "typed-workspace@1",
      outcome: "available",
      capturedAtMs: 2,
      payload: { repository: "omi", branch: "typed-spawn" },
    }).snapshot;
    adapter.deferOnlyPromptIncludes = "DEFER_TYPED_PARENT_9515";
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
        metadata: { producerJournal: { forged: true } },
      },
    });
    expect(routed).toMatchObject({
      toolName: "spawn_agent",
      recoveredFromDelegation: false,
      toolInput: { objective: "Research release-plan risks" },
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
      toolInput: routed.toolInput,
    });
    expect(prepared).toMatchObject({
      parentRunId: authorized.runId,
      producerJournal: {
        schemaVersion: 1,
        surface: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "typed-spawn" },
        continuityKey: `agent_spawn:${invocationId}`,
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
    const raw = await handleAgentControlToolCall({
      kernel,
      callerSessionId: authorized.sessionId,
      executionRole: "coordinator",
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      authorizedProducerJournal: prepared.producerJournal,
      authorizedCallerRunId: prepared.parentRunId,
      getOwnerId: () => "owner",
    }, authorized.canonicalToolName, prepared.toolInput);
    kernel.completeRunToolInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      outcome: "succeeded",
      result: raw,
    });
    const result = JSON.parse(raw) as { run: { runId: string }; session: { sessionId: string } };
    await waitUntil(() => String(store.getRow(
      "SELECT status FROM runs WHERE run_id = ?",
      [result.run.runId],
    ).status) === "succeeded");
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
    expect(childInput.contextSnapshotVersion).toBe(sourceSnapshot.version);
    expect(childInput.contextSnapshotGeneration).toBe(sourceSnapshot.snapshotGeneration);
    const ensured = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    });
    expect(ensured.assistantTurn.contentBlocks).toEqual([
      expect.objectContaining({ type: "agentSpawn", runId: result.run.runId }),
      expect.objectContaining({ type: "agentCompletion", runId: result.run.runId }),
    ]);

    adapter.resolveDeferred();
    await parentPromise;
    store.close();
  });

  it("stamps trusted realtime origin on exact generated spawn payload before the production control parser", async () => {
    const root = newRoot();
    const { store, adapter, kernel } = createKernelHarness(join(root, "agent.sqlite"), "acp");
    const session = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
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
      toolInput: { objective: "Research the launch plan" },
    });
    expect(routed.toolInput).toMatchObject({
      objective: "Research the launch plan",
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

    const result = JSON.parse(await handleAgentControlToolCall({
      kernel,
      callerSessionId: session.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      authorizedProducerJournal: parseAgentSpawnProducerJournalDescriptor(
        ((routed.toolInput.metadata as any) ?? {}).producerJournal,
      ),
      authorizedCallerRunId: run.runId,
      getOwnerId: () => "owner",
    }, "spawn_agent", routed.toolInput)) as Record<string, unknown>;
    expect(result).toMatchObject({
      ok: true,
      requestedAgentCount: 1,
      run: { status: "queued", parentRunId: run.runId },
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
      assistantText: "I started a background agent for that.",
    });
    expect(JSON.parse(attachAgentSpawnJournalReceipt('{"ok":true}', descriptor))).toEqual({
      ok: true,
      journalReceipt: receipt,
    });

    // The provider still emits turn_done after the spawn tool result. Its
    // ordinary main-chat projection must acknowledge, not overwrite or collide
    // with, the already committed canonical voice spawn exchange.
    const lateUser = recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: ensured.conversationId,
      turnId: receipt.userTurnId,
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
      delivery: "backend",
    });
    const lateAssistant = recordJournalTurn(store, {
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
      delivery: "backend",
    });
    expect(lateUser).toMatchObject({ created: false, duplicate: true });
    expect(lateAssistant).toMatchObject({ created: false, duplicate: true });
    expect(lateAssistant.turn.content).toBe(receipt.assistantText);
    expect(lateAssistant.turn.contentBlocks.filter((block) => block.type === "agentSpawn")).toHaveLength(1);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [ensured.conversationId],
    ).count).toBe(2);
    const parentInput = JSON.parse(String(store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [run.runId]).input_json));
    const childInput = JSON.parse(String(store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [child.runId]).input_json));
    expect(childInput.contextSnapshotVersion).toBe(parentInput.contextSnapshotVersion);
    expect(childInput.contextSnapshotGeneration).toBe(parentInput.contextSnapshotGeneration);
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
