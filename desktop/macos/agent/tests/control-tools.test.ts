import { mkdtempSync, rmSync } from "node:fs";
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AGENT_CONTROL_TOOL_NAMES,
  agentControlToolDefinitions,
  agentControlToolSchemas,
  handleAgentControlToolCall as rawHandleAgentControlToolCall,
  INTERNAL_AGENT_CONTROL_TOOL_NAMES,
  isAgentControlToolName,
  type AgentControlToolContext,
  withDefaultOwnerGuard,
  withMergedOwnerGuard,
} from "../src/runtime/control-tools.js";
import { agentControlCapabilityManifest, agentControlInputSchema } from "../src/runtime/control-tool-manifest.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { toolNamesForAdapter } from "../src/runtime/omi-tool-manifest.js";
import {
  RunToolCapabilityBroker,
  type AuthorizedRunToolInvocation,
} from "../src/runtime/run-tool-capability.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { baseRunInput, createKernelHarness, FakeRuntimeAdapter, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];
const servers: Array<{ server: Server; sockPath: string }> = [];
const ORIGIN_BOUND_CONTROL_TOOLS = new Set([
  "send_agent_message",
  "spawn_background_agent",
  "spawn_agent",
  "run_agent_and_wait",
]);

function handleAgentControlToolCall(
  context: AgentControlToolContext,
  name: Parameters<typeof rawHandleAgentControlToolCall>[1],
  input: Record<string, unknown>,
): ReturnType<typeof rawHandleAgentControlToolCall> {
  return rawHandleAgentControlToolCall(
    context,
    name,
    ORIGIN_BOUND_CONTROL_TOOLS.has(name)
      ? { originSurfaceKind: "agent_control", ...input }
      : input,
  );
}

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      ({ server, sockPath }) =>
        new Promise<void>((resolve) => {
          server.close(() => {
            rmSync(sockPath, { force: true });
            resolve();
          });
        }),
    ),
  );
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function createCapabilityBroker(store: SqliteAgentStore): RunToolCapabilityBroker {
  return new RunToolCapabilityBroker({
    store,
    profileForSession: (sessionId) => {
      const profile = readSessionExecutionProfile(store, sessionId);
      return {
        generation: profile.generation,
        // These control-tool tests use the kernel's synthetic `fake` adapter;
        // the canonical capability projection they exercise is the stdio lane.
        adapterId: profile.adapterId === "fake" ? "acp" : profile.adapterId,
        executionRole: profile.executionRole,
      };
    },
  });
}

describe("agent control tools", () => {
  it("bridges workstream migration, artifact versioning, checkpointing, and idempotent replay", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const context = ownerContext(kernel);
    const prepared = parseToolResult(
      await handleAgentControlToolCall(context, "prepare_workstream_continuity", {
        workstreamId: "workstream-1",
        taskIds: [],
      }),
    );
    expect(prepared.ok).toBe(true);
    expect((prepared.session as { agentSessionId: string }).agentSessionId).toMatch(/^ses_/);

    const input = {
      workstreamId: "workstream-1",
      context: {
        canonicalSummary: "Draft ready for review",
        redactedCanonicalSummary: "Draft ready for review",
        summarySensitivityTier: "low",
        latestEventSequence: 2,
        selectedEvents: [
          {
            eventId: "event-2",
            type: "conversation",
            summary: "Deadline moved to Friday",
            occurredAtMs: 10,
            evidenceRefs: [
              {
                kind: "conversation",
                id: "conversation-1",
                scope: "canonical",
              },
              {
                kind: "chat_message",
                id: "local-turn-1",
                scope: "device_local",
                device_id: "test-device",
              },
            ],
            sensitivityTier: "low",
          },
        ],
        artifactHeads: [],
        provenance: {
          snapshotVersion: "workstream:2",
          fetchedAtMs: 20,
          source: "canonical_backend",
        },
      },
      artifacts: [
        {
          logicalKey: "launch-email",
          evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }],
          kind: "markdown",
          role: "result",
          uri: "file:///tmp/launch-email.md",
          contentHash: "sha256:1234567890abcdef",
          sourceArtifactId: "source-artifact-1",
        },
        {
          logicalKey: "provider-reference",
          evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }],
          kind: "provider_reference",
          role: "result",
          uri: "adapter://provider/reference-1",
          sourceArtifactId: "source-artifact-local-only",
        },
      ],
    };
    const first = parseToolResult(await handleAgentControlToolCall(context, "persist_workstream_continuity", input));
    const firstDeliveries = first.deliveries as Array<{
      deliveryId: string;
      payload: { kind: string };
    }>;
    const artifactDelivery = firstDeliveries.find((delivery) => delivery.payload.kind === "artifact_descriptor")!;
    const delivered = parseToolResult(
      await handleAgentControlToolCall(context, "resolve_workstream_continuity_delivery", {
        deliveryId: artifactDelivery.deliveryId,
        status: "delivered",
        receipt: { artifact_id: "backend-v1" },
      }),
    );
    const replay = parseToolResult(await handleAgentControlToolCall(context, "persist_workstream_continuity", input));
    const projected = parseToolResult(
      await handleAgentControlToolCall(context, "project_workstream_continuity", {
        workstreamId: "workstream-1",
      }),
    );
    expect(first.ok).toBe(true);
    expect(firstDeliveries.map((delivery) => delivery.payload.kind).sort()).toEqual([
      "artifact_descriptor",
      "continuation_checkpoint",
    ]);
    expect((delivered.delivery as { status: string }).status).toBe("delivered");
    expect((first.artifactVersions as Array<{ version: number }>)[0]?.version).toBe(1);
    expect((replay.artifactVersions as Array<{ version: number }>)[0]?.version).toBe(1);
    expect((projected.projection as { artifactVersions: unknown[] }).artifactVersions.length).toBe(2);
    expect(
      (replay.deliveries as Array<{ deliveryId: string }>).some(
        (delivery) => delivery.deliveryId === artifactDelivery.deliveryId,
      ),
    ).toBe(false);
    expect((first.checkpoint as { lastEventSequence: number }).lastEventSequence).toBe(2);
    expect((first.checkpoint as { evidenceRefs: Array<{ scope: string }> }).evidenceRefs).toEqual([
      expect.objectContaining({ scope: "canonical" }),
    ]);
    expect(store.getRow("SELECT COUNT(*) AS count FROM workstream_artifact_versions").count).toBe(2);
    expect(
      store.getRow("SELECT COUNT(*) AS count FROM desktop_artifact_deliveries WHERE delivery_status = 'cancelled'")
        .count,
    ).toBe(1);
  });

  it("revalidates workstream authority between commits and ledgers revocation without later writes", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const caller = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
      executionRole: "coordinator",
    });
    const parent = store.insertRun({
      sessionId: caller.sessionId,
      clientId: "workstream-lease-client",
      requestId: "workstream-lease-parent",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: parent.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "workstream-lease-worker",
    });
    const broker = createCapabilityBroker(store);
    const capability = broker.register({
      ownerId: "owner",
      sessionId: caller.sessionId,
      runId: parent.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "lease-workstream-commits",
      runId: parent.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: "owner",
      toolName: "spawn_agent",
      toolInput: { objective: "persist guarded workstream state" },
    });
    broker.markInvocationDispatched(authorized);
    const lease = broker.acquireExecutionLease(authorized, () => "owner");
    let assertionCount = 0;
    let entered!: () => void;
    let resume!: () => void;
    const enteredSecondCommit = new Promise<void>((resolve) => { entered = resolve; });
    const resumeSecondCommit = new Promise<void>((resolve) => { resume = resolve; });
    const resultPromise = handleAgentControlToolCall({
      ...ownerContext(kernel),
      callerSessionId: caller.sessionId,
      executionLease: {
        signal: lease.signal,
        assertCurrentAuthority: async () => {
          assertionCount += 1;
          if (assertionCount === 3) {
            entered();
            await resumeSecondCommit;
          }
          lease.assertCurrentAuthority();
        },
      },
    }, "persist_workstream_continuity", {
      workstreamId: "guarded-workstream",
      context: {
        canonicalSummary: "Guard each durable write",
        latestEventSequence: 1,
        selectedEvents: [],
        artifactHeads: [],
        provenance: {
          snapshotVersion: "guarded:1",
          fetchedAtMs: 10,
          source: "canonical_backend",
        },
      },
      artifacts: [{
        logicalKey: "guarded-report",
        evidenceRefs: [{ kind: "conversation", id: "conversation-guarded", scope: "canonical" }],
        kind: "markdown",
        role: "result",
        uri: "file:///tmp/guarded-report.md",
        contentHash: "sha256:guarded-report",
        sourceArtifactId: "source-guarded-report",
      }],
    });

    await enteredSecondCommit;
    broker.revokeForOwner("owner", "owner_changed");
    const atRevocation = workstreamWriteSnapshot(store);
    resume();
    const result = parseToolResult(await resultPromise);
    expect(result).toMatchObject({ ok: false, error: { code: "owner_mismatch" } });
    expect(workstreamWriteSnapshot(store)).toEqual(atRevocation);
    expect(atRevocation.contextPackets).toHaveLength(1);
    expect(atRevocation.artifactVersions).toHaveLength(0);
    expect(atRevocation.deliveries).toHaveLength(0);
    lease.release();
    expect(() => broker.completeInvocation({
      ...invocationIdentityForTest(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "failed",
      result: JSON.stringify(result),
    })).toThrow(/completion authority was revoked/);
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_owner_changed",
    });
    store.close();
  });

  it("persists prepared artifacts only with a scoped live grant and without replacing context", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const context = ownerContext(kernel);
    const prepared = parseToolResult(
      await handleAgentControlToolCall(context, "prepare_workstream_continuity", {
        workstreamId: "workstream-prepared",
        taskIds: [],
      }),
    );
    const sessionId = (prepared.session as { agentSessionId: string }).agentSessionId;
    const capability = "desktop.workstream.artifact.prepare";
    const operation = "prepare_artifact";
    const resourceRef = "workstream:workstream-prepared";
    const expiresAtMs = Date.now() + 60_000;
    const created = parseToolResult(
      await handleAgentControlToolCall(context, "create_desktop_dispatch", {
        kind: "approval",
        priority: 1,
        title: "Prepare artifact",
        decisionPrompt: "Allow this prepared artifact?",
        sourceSessionId: sessionId,
        capability,
        operation,
        resourceRef,
        expiresAtMs,
      }),
    );
    const dispatchId = (created.dispatch as { dispatchId: string }).dispatchId;
    const resolved = parseToolResult(
      await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
        dispatchId,
        status: "resolved",
        resolution: { decision: "allow" },
        grant: {
          sessionId,
          capability,
          operation,
          resourcePattern: resourceRef,
          effect: "allow",
          source: "user",
          expiresAtMs,
        },
      }),
    );
    const grantId = (resolved.grant as { grantId: string }).grantId;
    const input = {
      workstreamId: "workstream-prepared",
      logicalKey: "investor-email",
      evidenceRefs: [
        {
          kind: "local_screen",
          id: "sha256:evidence",
          scope: "device_local",
          device_id: "device-1",
        },
      ],
      kind: "email_draft",
      uri: "file:///tmp/investor-email.artifact",
      contentHash: "sha256:1234567890abcdef",
      sourceArtifactId: "prepared-source-1",
      grantId,
    };
    const persisted = parseToolResult(
      await handleAgentControlToolCall(context, "persist_prepared_workstream_artifact", input),
    );
    const rejected = parseToolResult(
      await handleAgentControlToolCall(context, "persist_prepared_workstream_artifact", {
        ...input,
        sourceArtifactId: "prepared-source-2",
        grantId: "grant_missing",
      }),
    );

    expect(persisted.ok, JSON.stringify(persisted)).toBe(true);
    expect((persisted.artifactVersion as { version: number }).version).toBe(1);
    expect(persisted.deliveries as unknown[]).toHaveLength(1);
    expect(rejected.ok).toBe(false);
    expect(store.getRow("SELECT COUNT(*) AS count FROM workstream_continuation_checkpoints").count).toBe(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM desktop_context_packets").count).toBe(0);
    store.close();
  });

  it("owns schemas and definitions for the first kernel-backed tools", () => {
    expect(agentControlToolDefinitions.map((tool) => tool.name)).toEqual([
      "list_agent_sessions",
      "get_agent_run",
      "build_desktop_awareness_snapshot",
      "list_desktop_action_queue",
      "get_desktop_open_loops",
      "build_desktop_context_packet",
      "route_desktop_intent",
      "evaluate_desktop_tool_policy",
      "create_desktop_dispatch",
      "resolve_desktop_dispatch",
      "cancel_agent_run",
      "inspect_agent_artifacts",
      "read_tool_output",
      "search_tool_output",
      "update_agent_artifact_lifecycle",
      "send_agent_message",
      "spawn_background_agent",
      "spawn_agent",
      "run_agent_and_wait",
      "set_desktop_attention_override",
    ]);
    for (const tool of agentControlToolDefinitions) {
      expect(isAgentControlToolName(tool.name)).toBe(true);
      expect(tool.inputSchema).toMatchObject({ type: "object" });
    }
  });

  it("validates structured route proposals against kernel-owned targets and adapters", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const existing = await kernel.executeRun(baseRunInput);

    const continued = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "route_desktop_intent", {
        utterance: "continue the referenced run",
        surfaceKind: "floating_bar",
        snapshotVersion: "snapshot:control-1",
        proposal: { intent: "continue_run" },
        syntaxFacts: {
          explicitSessionId: existing.session.sessionId,
          explicitRunId: existing.run.runId,
        },
      }),
    );
    const unavailable = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "route_desktop_intent", {
        utterance: "use an unavailable provider",
        surfaceKind: "realtime",
        snapshotVersion: "snapshot:control-2",
        proposal: { intent: "spawn_agent" },
        syntaxFacts: { explicitProvider: "openclaw" },
      }),
    );

    expect(continued.route).toMatchObject({
      intent: "continue_run",
      sessionId: existing.session.sessionId,
      runId: existing.run.runId,
      snapshotVersion: "snapshot:control-1",
    });
    expect(unavailable.route).toMatchObject({
      intent: "reject",
      code: "provider_unavailable",
      snapshotVersion: "snapshot:control-2",
    });
    store.close();
  });

  it("generates ACP/MCP tool definitions from the canonical manifest", () => {
    expect(agentControlToolDefinitions).toEqual(
      agentControlCapabilityManifest.map((tool) => ({
        name: tool.name,
        description: tool.description,
        inputSchema: agentControlInputSchema(tool),
      })),
    );
  });

  it("keeps agent-control registry, manifest, and schemas in parity", () => {
    expect(new Set(agentControlCapabilityManifest.map((tool) => tool.name))).toEqual(new Set(AGENT_CONTROL_TOOL_NAMES));
    expect(new Set([...AGENT_CONTROL_TOOL_NAMES, ...INTERNAL_AGENT_CONTROL_TOOL_NAMES])).toEqual(
      new Set(Object.keys(agentControlToolSchemas)),
    );
  });

  it("validates the canonical Swift background-agent spawn payload", () => {
    const parsed = agentControlToolSchemas.spawn_background_agent.safeParse({
      prompt: "Search my recent memories and write a short story.",
      originSurfaceKind: "floating_bar",
      title: "Create Memory Story",
      surfaceKind: "background_agent",
      externalRefKind: "pill",
      externalRefId: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
      clientId: "desktop-floating-pill",
      mode: "act",
      adapterId: "pi-mono",
      cwd: "/tmp/omi-test",
      metadata: {
        uiProjection: "floating_pill",
        pillId: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
      },
    });

    expect(parsed.success).toBe(true);
    expect(
      agentControlToolSchemas.spawn_background_agent.safeParse({
        prompt: "valid",
      }).success,
    ).toBe(false);
  });

  it("accepts objective-only public spawn_agent input and rejects caller-supplied routing authority", () => {
    expect(agentControlToolSchemas.spawn_agent.safeParse({
      objective: "Research the release plan",
    }).success).toBe(true);
    expect(agentControlToolSchemas.spawn_agent.safeParse({
      objective: "Research the release plan",
      originSurfaceKind: "main_chat",
    }).success).toBe(false);
  });

  it("declares coordinator policy metadata for every control tool", () => {
    for (const tool of agentControlCapabilityManifest) {
      expect(tool.riskTier).toMatch(/^(low|medium|high)$/);
      expect(tool.privacyTier).toMatch(/^(low|local_private|sensitive)$/);
      expect(tool.approvalPolicy).toMatch(/^(allow|user_approval|policy_grant)$/);
      expect(tool.bundles.length).toBeGreaterThan(0);
      if (tool.name !== "spawn_background_agent" && tool.name !== "resolve_desktop_dispatch") {
        expect(tool.allowedSurfaces.length).toBeGreaterThan(0);
      }
    }

    expect(agentControlCapabilityManifest.find((tool) => tool.name === "list_agent_sessions")).toMatchObject({
      riskTier: "low",
      approvalPolicy: "allow",
      bundles: ["desktop.agent_control.read"],
    });
    expect(agentControlCapabilityManifest.find((tool) => tool.name === "cancel_agent_run")).toMatchObject({
      riskTier: "medium",
      approvalPolicy: "policy_grant",
      bundles: ["desktop.agent_control.manage"],
    });
  });

  it("constrains canonical list surfaceKind to known surfaces", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const invalid = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        ownerId: "owner",
        surfaceKind: "surprise_surface",
      }),
    );
    const valid = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        ownerId: "owner",
        surfaceKind: "realtime",
      }),
    );

    expect(invalid).toMatchObject({
      ok: false,
      error: { code: "invalid_tool_input" },
    });
    expect(valid.ok).toBe(true);
    store.close();
  });

  it.each(["background_agent", "delegated_agent"])(
    "treats semantic %s surface hints as cross-surface child discovery",
    async (surfaceKind) => {
      const { store, kernel } = createKernelHarness(newDatabasePath());
      const child = await kernel.executeRun({
        ...baseRunInput,
        requestId: `request-${surfaceKind}`,
        surfaceKind: "floating_bar",
        executionRole: "leaf",
        externalRefKind: "pill",
        externalRefId: `child-${surfaceKind}`,
      });
      const coordinator = await kernel.executeRun({
        ...baseRunInput,
        requestId: `request-${surfaceKind}-coordinator`,
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefId: `coordinator-${surfaceKind}`,
      });

      expect(coordinator.session.executionRole).toBe("coordinator");

      const listed = parseToolResult(
        await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
          ownerId: "owner",
          surfaceKind,
          limit: 1,
        }),
      );

      expect(listed.ok).toBe(true);
      expect(listed.sessions).toHaveLength(1);
      expect(listed.sessions[0].session.surfaceKind).toBe("floating_bar");
      expect(listed.sessions[0].latestRun.runId).toBe(child.run.runId);
      expect(listed.sessions[0].latestRun.finalText).toBe(child.run.finalText);
      store.close();
    },
  );

  it("rejects unknown coordinator bundles at the control-tool boundary", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "evaluate_desktop_tool_policy", {
        selectedBundles: ["desktop.context.local_read", "desktop.context.magic_root"],
      }),
    );

    expect(result).toMatchObject({
      ok: false,
      error: { code: "invalid_tool_input" },
    });
    store.close();
  });

  it("accepts a signed direct-control owner guard when evaluating policy", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "evaluate_desktop_tool_policy", {
        ownerId: "scenario-13-automation-owner",
        selectedBundles: ["external.write_send"],
        requestedBundles: ["external.write_send"],
        externalSend: true,
      }),
    );

    expect(result).toMatchObject({
      ok: true,
      policy: { decision: "dispatch_required" },
    });
    store.close();
  });

  it("documents run_agent_and_wait as synchronous parent-linked delegation", () => {
    const runAndWait = agentControlCapabilityManifest.find((tool) => tool.name === "run_agent_and_wait");
    expect(runAndWait?.description).toContain("synchronously");
    expect(runAndWait?.runtimePreconditions).toContain("Requires parentRunId.");
    expect(runAndWait?.promptGuidelines?.join("\n")).not.toMatch(/send_agent_message|instead of/i);
  });

  it("documents send_agent_message as session continuation only", () => {
    const sendMessage = agentControlCapabilityManifest.find((tool) => tool.name === "send_agent_message");
    expect(sendMessage?.runtimePreconditions).toContain(
      "Requires an existing sessionId from list_agent_sessions; cannot create a new session.",
    );
    expect(sendMessage?.promptGuidelines?.join("\n")).not.toMatch(/do not|instead of|delegated child/i);
  });

  it("resolves desktop approval dispatches with a scoped grant and event evidence", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "waiting_approval",
      mode: "act",
    });
    const created = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "create_desktop_dispatch", {
        kind: "approval",
        priority: 100,
        title: "Approve screenshot",
        decisionPrompt: "Allow screenshot image bytes?",
        sourceSessionId: session.sessionId,
        sourceRunId: run.runId,
        capability: "desktop.context.screenshot_image",
        operation: "get_screenshot",
        resourceRef: "screenshot:42",
      }),
    );

    const resolved = parseToolResult(
      await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
        dispatchId: created.dispatch.dispatchId,
        status: "resolved",
        resolution: { decision: "allow" },
        grant: {
          capability: "desktop.context.screenshot_image",
          operation: "get_screenshot",
          resourcePattern: "screenshot:42",
          effect: "allow",
          expiresAtMs: Date.now() + 60_000,
        },
      }),
    );

    expect(resolved).toMatchObject({
      ok: true,
      dispatch: { status: "resolved" },
      grant: {
        sessionId: session.sessionId,
        runId: run.runId,
        capability: "desktop.context.screenshot_image",
        operation: "get_screenshot",
        resourcePattern: "screenshot:42",
        effect: "allow",
        source: "user",
      },
      event: { type: "approval.resolved" },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(
      1,
    );
    expect(store.getRow("SELECT COUNT(*) AS count FROM events WHERE type = ?", ["approval.resolved"]).count).toBe(1);
    store.close();
  });

  it("rejects desktop dispatch grants that do not match the approval request", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
    });
    const dispatch = kernel.createDesktopDispatch({
      ownerId: "owner",
      kind: "approval",
      priority: 100,
      title: "Approve screenshot",
      decisionPrompt: "Allow screenshot image bytes?",
      sourceSessionId: session.sessionId,
      capability: "desktop.context.screenshot_image",
      operation: "get_screenshot",
      resourceRef: "screenshot:42",
    });

    const resolved = parseToolResult(
      await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
        dispatchId: dispatch.dispatchId,
        status: "resolved",
        resolution: { decision: "allow" },
        grant: {
          capability: "desktop.context.local_read",
          operation: "get_screenshot",
          resourcePattern: "screenshot:42",
          effect: "allow",
          expiresAtMs: Date.now() + 60_000,
        },
      }),
    );

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(String(resolved.error.message)).toContain("capability must match");
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(
      0,
    );
    expect(
      store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [dispatch.dispatchId]).status,
    ).toBe("pending");
    store.close();
  });

  it("rejects grant creation for non-approval desktop dispatches", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
    });
    const dispatch = kernel.createDesktopDispatch({
      ownerId: "owner",
      kind: "routing_choice",
      priority: 10,
      title: "Choose route",
      decisionPrompt: "Resume or fork?",
      sourceSessionId: session.sessionId,
      capability: "desktop.agent_control.manage",
      operation: "route_desktop_intent",
      resourceRef: "route:1",
    });

    const resolved = parseToolResult(
      await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
        dispatchId: dispatch.dispatchId,
        status: "resolved",
        resolution: { decision: "allow" },
        grant: {
          capability: "desktop.agent_control.manage",
          operation: "route_desktop_intent",
          resourcePattern: "route:1",
          effect: "allow",
          expiresAtMs: Date.now() + 60_000,
        },
      }),
    );

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(String(resolved.error.message)).toContain("Only approval dispatches");
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(
      0,
    );
    expect(
      store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [dispatch.dispatchId]).status,
    ).toBe("pending");
    store.close();
  });

  it("denies desktop dispatch resolution from untrusted tool callers", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
    });
    const dispatch = kernel.createDesktopDispatch({
      ownerId: "owner",
      kind: "approval",
      priority: 100,
      title: "Approve screenshot",
      decisionPrompt: "Allow screenshot image bytes?",
      sourceSessionId: session.sessionId,
      capability: "desktop.context.screenshot_image",
      operation: "get_screenshot",
      resourceRef: "screenshot:42",
    });

    const resolved = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "resolve_desktop_dispatch", {
        dispatchId: dispatch.dispatchId,
        status: "resolved",
        resolution: { decision: "allow" },
        grant: {
          capability: "desktop.context.screenshot_image",
          operation: "get_screenshot",
          resourcePattern: "screenshot:42",
          effect: "allow",
          expiresAtMs: Date.now() + 60_000,
        },
      }),
    );

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "policy_denied" },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(
      0,
    );
    store.close();
  });

  it("requires verified approved dispatches for sensitive context packet snippets", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const dispatch = kernel.createDesktopDispatch({
      ownerId: "owner",
      kind: "screen_context",
      priority: 100,
      title: "Approve current screen",
      decisionPrompt: "Allow current screen summary?",
      capability: "desktop.context.screen_summary",
      operation: "get_work_context",
      resourceRef: "screen:current",
    });

    const unapproved = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "build_desktop_context_packet", {
        surfaceKind: "main_chat",
        objective: "Inspect screen",
        ttlMs: 60_000,
        retentionClass: "ephemeral",
        packetJson: {
          snippets: [
            {
              snippetId: "screen",
              sourceKind: "screen_current",
              operation: "get_work_context",
              provenance: { scope: "current" },
              content: "Visible app title",
              sensitivityTier: "sensitive",
              policyDecision: "dispatch_created",
              dispatchId: dispatch.dispatchId,
            },
          ],
        },
      }),
    );
    expect(unapproved).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(String(unapproved.error.message)).toContain("not approved");

    store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });

    const approved = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "build_desktop_context_packet", {
        surfaceKind: "main_chat",
        objective: "Inspect screen",
        ttlMs: 60_000,
        retentionClass: "ephemeral",
        packetJson: {
          snippets: [
            {
              snippetId: "screen",
              sourceKind: "screen_current",
              operation: "get_work_context",
              provenance: { scope: "current" },
              content: "Visible app title",
              sensitivityTier: "sensitive",
              policyDecision: "dispatch_created",
              dispatchId: dispatch.dispatchId,
            },
          ],
        },
      }),
    );

    expect(approved.ok).toBe(true);
    expect(approved.accessLogs[0]).toMatchObject({
      sourceKind: "screen_current",
      dispatchId: dispatch.dispatchId,
      policyDecision: "dispatch_created",
    });
    store.close();
  });

  it("lists sessions and inspects runs using canonical runtime ids", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);

    const list = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        ownerId: "owner",
      }),
    );
    expect(list.ok).toBe(true);
    expect(list.sessions).toHaveLength(1);
    expect(list.sessions[0].session.sessionId).toBe(result.session.sessionId);
    expect(list.sessions[0].latestRun.runId).toBe(result.run.runId);
    expect(list.sessions[0].adapterBindings[0]).toMatchObject({
      sessionId: result.session.sessionId,
      adapterId: "fake",
      adapterNativeSessionId: "native-1",
    });

    const inspected = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: result.run.runId,
        ownerId: "owner",
      }),
    );
    expect(inspected.run).toMatchObject({
      runId: result.run.runId,
      sessionId: result.session.sessionId,
      status: "succeeded",
    });
    expect(inspected.attempts[0].attemptId).toBe(result.attempt.attemptId);
    expect(inspected.events.map((event: any) => event.type)).toContain("run.succeeded");
    store.close();
  });

  it("keeps a 620 KiB session listing bounded and makes the full output artifact-readable", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const surfaceContextSentinel = "SENSITIVE_CONTEXT_SENTINEL".repeat(26_000);
    const result = await kernel.executeRun({
      ...baseRunInput,
      surfaceContextJson: JSON.stringify({ rendered: surfaceContextSentinel }),
      prompt: "p".repeat(4_000),
    });
    // Simulate the historical regression shape: a persisted run input that
    // contains a 620 KiB surface payload. The production projection must stay
    // bounded while the canonical full result remains artifact-readable.
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({ prompt: "p".repeat(4_000), surfaceContextJson: surfaceContextSentinel }),
      result.run.runId,
    ]);

    const raw = await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
      ownerId: "owner",
    });
    const listed = parseToolResult(raw);

    expect(Buffer.byteLength(raw, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(raw).not.toContain("SENSITIVE_CONTEXT_SENTINEL");
    expect(listed.sessions[0].latestRun.input.prompt).toContain("[truncated]");
    expect(listed.sessions[0].latestRun.input).not.toHaveProperty("surfaceContextJson");
    expect(listed.toolResultEnvelope).toMatchObject({
      version: 1,
      truncated: true,
      originalBytes: expect.any(Number),
      projectedBytes: expect.any(Number),
    });
    expect(listed.toolResultEnvelope.originalBytes).toBeGreaterThanOrEqual(620 * 1024);
    const artifactId = String(listed.toolResultEnvelope.fullOutputRef);
    const recovered = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "search_tool_output", {
      ownerId: "owner",
      artifactId,
      query: "SENSITIVE_CONTEXT_SENTINEL",
    }));
    expect(recovered.ok).toBe(true);
    expect(recovered.matches).toHaveLength(1);
    store.close();
  });

  it("returns a typed failure when a 620 KiB session listing cannot persist its full output", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const surfaceContextSentinel = "UNSAVED_CONTEXT_SENTINEL".repeat(26_000);
    const result = await kernel.executeRun({
      ...baseRunInput,
      surfaceContextJson: JSON.stringify({ rendered: surfaceContextSentinel }),
      prompt: "p".repeat(4_000),
    });
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({ prompt: "p".repeat(4_000), surfaceContextJson: surfaceContextSentinel }),
      result.run.runId,
    ]);
    vi.spyOn(kernel, "persistArtifact").mockImplementation(() => {
      throw new Error("deterministic artifact persistence failure");
    });

    const raw = await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
      ownerId: "owner",
    });
    const failed = parseToolResult(raw);

    expect(Buffer.byteLength(raw, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(raw).not.toContain("UNSAVED_CONTEXT_SENTINEL");
    expect(failed).toMatchObject({
      ok: false,
      error: { code: "tool_result_exceeded_provider_budget" },
      toolResultEnvelope: {
        status: "failed",
        truncated: false,
        fullOutputRef: null,
      },
    });
    store.close();
  });

  it("finalizes oversized awareness snapshots through the same recoverable envelope", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const sentinel = "AWARENESS_CONTEXT_SENTINEL".repeat(26_000);
    const result = await kernel.executeRun({
      ...baseRunInput,
      surfaceContextJson: JSON.stringify({ rendered: sentinel }),
    });
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({ prompt: "awareness", surfaceContextJson: sentinel }),
      result.run.runId,
    ]);

    const raw = await handleAgentControlToolCall(ownerContext(kernel), "build_desktop_awareness_snapshot", {
      ownerId: "owner",
    });
    const projected = parseToolResult(raw);

    expect(Buffer.byteLength(raw, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(raw).not.toContain("AWARENESS_CONTEXT_SENTINEL");
    expect(projected).toMatchObject({ ok: true, toolResultEnvelope: {
      version: 1,
      status: "succeeded",
      truncated: true,
      originalBytes: expect.any(Number),
      fullOutputRef: expect.stringMatching(/^artifact:/),
    } });
    expect(projected.toolResultEnvelope.originalBytes).toBeGreaterThan(620 * 1024);
    const recovered = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "search_tool_output", {
      ownerId: "owner",
      artifactId: projected.toolResultEnvelope.fullOutputRef,
      query: "AWARENESS_CONTEXT_SENTINEL",
    }));
    expect(recovered.matches).toHaveLength(1);
    store.close();
  });

  it("envelopes unknown and invalid control-tool errors", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const unknown = parseToolResult(await rawHandleAgentControlToolCall(ownerContext(kernel), "not_a_real_tool", {}));
    const invalid = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {}));

    for (const result of [unknown, invalid]) {
      expect(result).toMatchObject({
        ok: false,
        error: { code: expect.any(String) },
        toolResultEnvelope: {
          version: 1,
          status: "failed",
          truncated: false,
          fullOutputRef: null,
        },
      });
    }
    expect(unknown.error.code).toBe("unknown_control_tool");
    expect(invalid.error.code).toBe("invalid_tool_input");
    store.close();
  });

  it("binds direct realtime control output and validation failures to the authorized invocation", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const invocation = {
      invocationId: "invocation-realtime-control",
      runId: "run-realtime-control",
      attemptId: "attempt-realtime-control",
      toolName: "list_agent_sessions",
    };
    const context = {
      ...ownerContext(kernel),
      authorizedToolInvocation: invocation,
    };

    const success = parseToolResult(await handleAgentControlToolCall(context, "list_agent_sessions", {
      ownerId: "owner",
    }));
    expect(success.toolResultEnvelope.provenance).toEqual(invocation);

    const failedInvocation = {
      ...invocation,
      invocationId: "invocation-realtime-invalid",
      toolName: "get_agent_run",
    };
    const failure = parseToolResult(await handleAgentControlToolCall({
      ...context,
      authorizedToolInvocation: failedInvocation,
    }, "get_agent_run", {}));
    expect(failure).toMatchObject({ ok: false, error: { code: "invalid_tool_input" } });
    expect(failure.toolResultEnvelope.provenance).toEqual(failedInvocation);
    store.close();
  });

  it("bounds get_agent_run and accepts its fullOutputRef verbatim", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const sentinel = "RUN_DETAIL_SENTINEL".repeat(35_000);
    const result = await kernel.executeRun({
      ...baseRunInput,
      surfaceContextJson: JSON.stringify({ rendered: sentinel }),
    });
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({ prompt: "detail", surfaceContextJson: sentinel }),
      result.run.runId,
    ]);

    const raw = await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
      ownerId: "owner",
      runId: result.run.runId,
    });
    const projected = parseToolResult(raw);

    expect(Buffer.byteLength(raw, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(raw).not.toContain("RUN_DETAIL_SENTINEL");
    expect(projected.toolResultEnvelope).toMatchObject({
      truncated: true,
      fullOutputRef: expect.stringMatching(/^artifact:/),
    });
    const recovered = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "search_tool_output", {
      ownerId: "owner",
      artifactId: projected.toolResultEnvelope.fullOutputRef,
      query: "RUN_DETAIL_SENTINEL",
    }));
    expect(recovered.matches).toHaveLength(1);
    store.close();
  });

  it("keeps the aggregate default session list within the realtime provider budget", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    for (let index = 0; index < 60; index += 1) {
      await kernel.executeRun({
        ...baseRunInput,
        externalRefId: `task-${index}`,
        requestId: `request-${index}`,
        prompt: `${index}-${"p".repeat(4_000)}`,
      });
    }

    const raw = await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
      ownerId: "owner",
    });
    const listed = parseToolResult(raw);

    expect(Buffer.byteLength(raw, "utf8")).toBeLessThanOrEqual(8 * 1024);
    expect(listed.fetched_session_count).toBe(50);
    expect(listed.returned_session_count).toBeLessThan(listed.fetched_session_count);
    expect(listed.truncated).toBe(true);
    expect(listed.sessions).toHaveLength(listed.returned_session_count);
    expect(listed.task_agents).toHaveLength(listed.returned_session_count);
    store.close();
  });

  it("defaults owner-scoped tools to the active control context owner", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "owner-from-context" });
    await kernel.executeRun({
      ...baseRunInput,
      ownerId: "other-owner",
      externalRefId: "task-other",
      requestId: "request-other",
    });

    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner-from-context",
    };
    const listed = parseToolResult(await handleAgentControlToolCall(context, "list_agent_sessions", {}));

    expect(listed.ok).toBe(true);
    expect(listed.sessions).toHaveLength(1);
    expect(listed.sessions[0].session.ownerId).toBe("owner-from-context");
    store.close();
  });

  it("injects the active owner as a default guard without overriding tool-supplied guards", () => {
    expect(withDefaultOwnerGuard({ runId: "run-a" }, "owner-active")).toEqual({
      runId: "run-a",
      ownerId: "owner-active",
    });
    expect(withDefaultOwnerGuard({ runId: "run-a", ownerId: "owner-guard" }, "owner-active")).toEqual({
      runId: "run-a",
      ownerId: "owner-guard",
    });
  });

  it("requires envelope and input owner guards to agree before control dispatch", () => {
    expect(withMergedOwnerGuard({ runId: "run-a" }, "owner-envelope", "owner-active")).toEqual({
      runId: "run-a",
      ownerId: "owner-envelope",
    });
    expect(
      withMergedOwnerGuard({ runId: "run-a", ownerId: " owner-envelope " }, "owner-envelope", "owner-active"),
    ).toEqual({
      runId: "run-a",
      ownerId: "owner-envelope",
    });
    expect(() =>
      withMergedOwnerGuard({ runId: "run-a", ownerId: "owner-active" }, "owner-envelope", "owner-active"),
    ).toThrow("Owner guards do not match");
  });

  it("rejects run inspection, cancellation, and artifact inspection outside the active owner", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const ownerRun = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "owner-from-context",
    });
    const otherRun = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "other-owner",
      externalRefId: "task-other",
      requestId: "request-other",
    });
    kernel.persistArtifact({
      attemptId: otherRun.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://other-owner-result",
    });

    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner-from-context",
    };

    const inspected = parseToolResult(
      await handleAgentControlToolCall(context, "get_agent_run", {
        runId: otherRun.run.runId,
      }),
    );
    expect(inspected).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(inspected.error.message).toContain("not visible to the active owner");

    const cancelled = parseToolResult(
      await handleAgentControlToolCall(context, "cancel_agent_run", {
        runId: otherRun.run.runId,
      }),
    );
    expect(cancelled).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(cancelled.error.message).toContain("not visible to the active owner");

    const artifacts = parseToolResult(
      await handleAgentControlToolCall(context, "inspect_agent_artifacts", {
        attemptId: otherRun.attempt.attemptId,
      }),
    );
    expect(artifacts).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(artifacts.error.message).toContain("not visible to the active owner");

    const ownInspected = parseToolResult(
      await handleAgentControlToolCall(context, "get_agent_run", {
        runId: ownerRun.run.runId,
      }),
    );
    expect(ownInspected.ok).toBe(true);
    expect(ownInspected.run.runId).toBe(ownerRun.run.runId);
    store.close();
  });

  it("rejects caller-provided owner ids that differ from the active owner", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const otherRun = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "other-owner",
      externalRefId: "task-other-owner",
      requestId: "request-other-owner",
    });
    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner-from-context",
    };

    const listed = parseToolResult(
      await handleAgentControlToolCall(context, "list_agent_sessions", {
        ownerId: "other-owner",
      }),
    );
    expect(listed).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(listed.error.message).toContain("does not match the active control owner");

    const inspected = parseToolResult(
      await handleAgentControlToolCall(context, "get_agent_run", {
        runId: otherRun.run.runId,
        ownerId: "other-owner",
      }),
    );
    expect(inspected).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(inspected.error.message).toContain("does not match the active control owner");

    const sent = parseToolResult(
      await handleAgentControlToolCall(context, "send_agent_message", {
        sessionId: otherRun.session.sessionId,
        ownerId: "other-owner",
        prompt: "try to cross owners",
      }),
    );
    expect(sent).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(sent.error.message).toContain("does not match the active control owner");
    store.close();
  });

  it("treats caller-provided owner ids as trimmed guards", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "owner-from-context" });
    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner-from-context",
    };

    const trimmed = parseToolResult(
      await handleAgentControlToolCall(context, "list_agent_sessions", {
        ownerId: " owner-from-context ",
      }),
    );
    expect(trimmed.ok).toBe(true);
    expect(trimmed.sessions).toHaveLength(1);

    const blank = parseToolResult(
      await handleAgentControlToolCall(context, "list_agent_sessions", {
        ownerId: "   ",
      }),
    );
    expect(blank).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(blank.error.message).toContain("cannot be empty");
    store.close();
  });

  it("returns canonical artifact references without reading artifact contents", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);
    kernel.persistArtifact({
      artifactId: "art_test",
      attemptId: result.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://art_test",
      displayName: "result.json",
      mimeType: "application/json",
      contentHash: "sha256:test",
      sizeBytes: 42,
      metadata: { source: "test" },
    });

    const inspected = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {
        runId: result.run.runId,
        ownerId: "owner",
      }),
    );
    expect(inspected.artifacts).toEqual([
      expect.objectContaining({
        artifactId: "art_test",
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "omi-artifact://art_test",
        lifecycleState: "retained",
        lifecycleUpdatedAtMs: null,
        metadata: { source: "test" },
      }),
    ]);

    const inspectedByArtifact = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {
        artifactId: "art_test",
        ownerId: "owner",
      }),
    );
    expect(inspectedByArtifact.artifacts).toHaveLength(1);
    expect(inspectedByArtifact.artifacts[0]).toMatchObject({
      artifactId: "art_test",
      sessionId: result.session.sessionId,
    });

    const events = kernel.getRun({
      runId: result.run.runId,
      includeEvents: true,
    }).events;
    expect(events.find((event: any) => event.type === "artifact.created")).toMatchObject({
      sessionId: result.session.sessionId,
      runId: result.run.runId,
      attemptId: result.attempt.attemptId,
    });
    store.close();
  });

  it("updates artifact lifecycle metadata idempotently and appends ordered events", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);
    const artifact = kernel.persistArtifact({
      artifactId: "art_lifecycle",
      attemptId: result.attempt.attemptId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://art_lifecycle",
    });

    const dismissed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "update_agent_artifact_lifecycle", {
        artifactId: artifact.artifactId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        state: "dismissed",
        reason: "not useful",
        metadata: { source: "test" },
      }),
    );
    expect(dismissed).toMatchObject({
      ok: true,
      changed: true,
      artifact: {
        artifactId: artifact.artifactId,
        lifecycleState: "dismissed",
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
      },
      event: {
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        type: "artifact.lifecycle_updated",
        payload: {
          artifactId: artifact.artifactId,
          previousState: "retained",
          state: "dismissed",
          reason: "not useful",
          metadata: { source: "test" },
        },
      },
    });
    expect(dismissed.artifact.lifecycleUpdatedAtMs).toEqual(expect.any(Number));
    expect(dismissed.event.payload.lifecycleUpdatedAtMs).toEqual(dismissed.artifact.lifecycleUpdatedAtMs);

    const idempotent = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "update_agent_artifact_lifecycle", {
        artifactId: artifact.artifactId,
        sessionId: result.session.sessionId,
        state: "dismissed",
      }),
    );
    expect(idempotent).toMatchObject({
      ok: true,
      changed: false,
      event: null,
      artifact: {
        artifactId: artifact.artifactId,
        lifecycleState: "dismissed",
      },
    });

    const opened = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "update_agent_artifact_lifecycle", {
        artifactId: artifact.artifactId,
        state: "opened",
      }),
    );
    expect(opened).toMatchObject({
      ok: true,
      changed: true,
      artifact: {
        artifactId: artifact.artifactId,
        lifecycleState: "opened",
      },
      event: {
        type: "artifact.lifecycle_updated",
        payload: {
          artifactId: artifact.artifactId,
          previousState: "dismissed",
          state: "opened",
        },
      },
    });

    const events = kernel
      .getRun({ runId: result.run.runId, includeEvents: true, eventLimit: 100 })
      .events.filter((event) => event.type.startsWith("artifact."));
    expect(events.map((event) => event.type)).toEqual([
      "artifact.created",
      "artifact.lifecycle_updated",
      "artifact.lifecycle_updated",
    ]);
    expect(
      store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [artifact.artifactId])
        .lifecycle_state,
    ).toBe("opened");
    store.close();
  });

  it("rejects artifact lifecycle updates outside owner visibility or scope", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const ownerRun = await kernel.executeRun(baseRunInput);
    const otherRun = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "other-owner",
      externalRefId: "task-other-lifecycle",
      requestId: "request-other-lifecycle",
    });
    const ownerArtifact = kernel.persistArtifact({
      artifactId: "art_owner_scope",
      attemptId: ownerRun.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://owner-scope",
    });
    const otherArtifact = kernel.persistArtifact({
      artifactId: "art_other_scope",
      attemptId: otherRun.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://other-scope",
    });

    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner",
    };
    const wrongOwner = parseToolResult(
      await handleAgentControlToolCall(context, "update_agent_artifact_lifecycle", {
        artifactId: otherArtifact.artifactId,
        state: "dismissed",
      }),
    );
    expect(wrongOwner).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(wrongOwner.error.message).toContain("not visible to the active owner");

    const wrongScope = parseToolResult(
      await handleAgentControlToolCall(context, "update_agent_artifact_lifecycle", {
        artifactId: ownerArtifact.artifactId,
        runId: otherRun.run.runId,
        state: "dismissed",
      }),
    );
    expect(wrongScope).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(wrongScope.error.message).toContain("belongs to run");

    expect(
      store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [ownerArtifact.artifactId])
        .lifecycle_state,
    ).toBe("retained");
    expect(
      store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [otherArtifact.artifactId])
        .lifecycle_state,
    ).toBe("retained");
    store.close();
  });

  it("rejects unscoped direct kernel artifact inspection", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    expect(() => kernel.inspectArtifacts({ ownerId: "owner" })).toThrow(
      "Inspecting artifacts requires artifactId, sessionId, runId, or attemptId",
    );
    store.close();
  });

  it("validates artifact inspection selectors before control tool dispatch", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const invalid = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {}),
    );

    expect(invalid).toMatchObject({
      ok: false,
      error: {
        code: "invalid_tool_input",
      },
    });
    expect(invalid.error.message).toContain("artifactId, sessionId, runId, or attemptId");
    store.close();
  });

  it("rejects extra top-level control tool keys to match advertised schemas", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const invalid = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        unexpected: "drift",
      }),
    );

    expect(invalid).toMatchObject({
      ok: false,
      error: {
        code: "invalid_tool_input",
      },
    });
    expect(invalid.error.message).toContain("Unrecognized key");
    store.close();
  });

  it("filters persisted artifacts by session, run, attempt, and role", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const first = await kernel.executeRun(baseRunInput);
    const second = await kernel.executeRun({
      ...baseRunInput,
      externalRefId: "task-2",
      requestId: "request-2",
    });

    kernel.persistArtifact({
      attemptId: first.attempt.attemptId,
      kind: "log",
      role: "log",
      uri: "omi-artifact://first-log",
    });
    kernel.persistArtifact({
      attemptId: first.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://first-result",
    });
    kernel.persistArtifact({
      attemptId: second.attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "omi-artifact://second-result",
    });

    const runFiltered = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {
        runId: first.run.runId,
        ownerId: "owner",
        role: "result",
      }),
    );
    expect(runFiltered.artifacts.map((artifact: any) => artifact.uri)).toEqual(["omi-artifact://first-result"]);

    const attemptFiltered = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {
        sessionId: first.session.sessionId,
        attemptId: first.attempt.attemptId,
        ownerId: "owner",
        role: "log",
      }),
    );
    expect(attemptFiltered.artifacts.map((artifact: any) => artifact.uri)).toEqual(["omi-artifact://first-log"]);
    store.close();
  });

  it("persists adapter result artifacts as artifact refs with native ids in metadata", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.nextArtifacts = [
      {
        kind: "markdown",
        role: "result",
        uri: "adapter://fake/native-summary",
        displayName: "summary.md",
        mimeType: "text/markdown",
        contentHash: "sha256:native-summary",
        sizeBytes: 128,
        metadata: { adapterArtifactId: "native-summary" },
      },
    ];

    const result = await kernel.executeRun(baseRunInput);
    const inspected = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "inspect_agent_artifacts", {
        attemptId: result.attempt.attemptId,
        ownerId: "owner",
      }),
    );

    expect(inspected.artifacts).toEqual([
      expect.objectContaining({
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "adapter://fake/native-summary",
        metadata: { adapterArtifactId: "native-summary" },
      }),
    ]);
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings").count).toBe(1);
    store.close();
  });

  it("sends a follow-up message as a new run in an existing canonical session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const first = await kernel.executeRun(baseRunInput);
    adapter.nextArtifacts = [
      {
        kind: "markdown",
        role: "result",
        uri: "adapter://fake/follow-up.md",
        displayName: "follow-up.md",
        mimeType: "text/markdown",
        contentHash: "sha256:abc",
        sizeBytes: 12,
        metadata: { adapterArtifactId: "follow-up" },
      },
    ];

    const sent = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        ownerId: "owner",
        sessionId: first.session.sessionId,
        prompt: "follow up",
        requestId: "request-follow-up",
        clientId: "client-follow-up",
      }),
    );

    expect(sent.ok).toBe(true);
    expect(sent.routeDecision).toMatchObject({
      intent: "continue_run",
      sessionId: first.session.sessionId,
    });
    expect(sent.session.sessionId).toBe(first.session.sessionId);
    expect(sent.run.sessionId).toBe(first.session.sessionId);
    expect(sent.run.runId).not.toBe(first.run.runId);
    expect(sent.run.status).toBe("succeeded");
    expect(sent.artifacts).toEqual([
      expect.objectContaining({
        sessionId: first.session.sessionId,
        runId: sent.run.runId,
        uri: "adapter://fake/follow-up.md",
        displayName: "follow-up.md",
      }),
    ]);
    expect(adapter.executed).toHaveLength(2);
    expect(adapter.executed[1].sessionId).toBe(first.session.sessionId);
    expect(adapter.executed[1].metadata).not.toMatchObject({
      disableSwiftBackedTools: true,
    });

    const listed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", { ownerId: "owner" }),
    );
    expect(listed.sessions).toHaveLength(1);
    expect([first.run.runId, sent.run.runId]).toContain(listed.sessions[0].latestRun.runId);
    store.close();
  });

  it("defaults send_agent_message to the active control context owner", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const first = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "owner-from-context",
    });

    const sent = parseToolResult(
      await handleAgentControlToolCall({ kernel, getOwnerId: () => "owner-from-context" }, "send_agent_message", {
        sessionId: first.session.sessionId,
        prompt: "follow up",
        requestId: "request-context-owner",
      }),
    );

    expect(sent.ok).toBe(true);
    expect(adapter.executed).toHaveLength(2);
    expect(sent.run.sessionId).toBe(first.session.sessionId);
    store.close();
  });

  it("rejects synchronous nested ACP control runs while the single ACP worker is busy", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp", 1);
    adapter.deferResult();
    const running = kernel.executeRun({
      ...baseRunInput,
      adapterId: "acp",
      defaultAdapterId: "acp",
    });
    await waitUntil(() => adapter.executed.length === 1);

    const blocked = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        ownerId: "owner",
        sessionId: adapter.executed[0].sessionId,
        prompt: "nested follow up",
        requestId: "nested-send",
      }),
    );

    expect(blocked).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
      },
    });
    expect(blocked.error.message).toContain("Synchronous acp control-tool runs are unavailable");

    adapter.resolveDeferred({
      text: "done",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await running;
    store.close();
  });

  it("fails closed for an unknown adapter before starting a control run", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "fake", 1);
    const first = await kernel.executeRun(baseRunInput);

    const failed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        ownerId: "owner",
        sessionId: first.session.sessionId,
        prompt: "use missing adapter",
        adapterId: "missing-adapter",
        requestId: "missing-adapter-request",
      }),
    );

    expect(failed).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Desktop intent effect rejected by canonical route policy (provider_unavailable).",
      },
    });
    store.close();
  });

  it("rejects synchronous nested pi-mono control runs while pi-mono is busy", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    adapter.deferResult();
    const running = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    await waitUntil(() => adapter.executed.length === 1);

    const blocked = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        ownerId: "owner",
        sessionId: adapter.executed[0].sessionId,
        prompt: "nested follow up",
        requestId: "nested-send-pi",
      }),
    );

    expect(blocked).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
      },
    });
    expect(blocked.error.message).toContain("Synchronous pi-mono control-tool runs are unavailable");

    adapter.resolveDeferred({
      text: "done",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await running;
    store.close();
  });

  it("allows synchronous control runs for a different session when adapter capacity remains", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "multi", 2);
    const idleSession = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "multi",
      defaultAdapterId: "multi",
      externalRefId: "idle-task",
      requestId: "idle-request",
    });

    adapter.deferResult();
    adapter.deferOnlyPromptIncludes = "busy";
    const running = kernel.executeRun({
      ...baseRunInput,
      adapterId: "multi",
      defaultAdapterId: "multi",
      prompt: "busy prompt",
      externalRefId: "busy-task",
      requestId: "busy-request",
    });
    await waitUntil(() => adapter.executed.length === 2);

    const sent = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        ownerId: "owner",
        sessionId: idleSession.session.sessionId,
        prompt: "follow up on idle session",
        requestId: "nested-send-multi",
      }),
    );

    expect(sent.ok).toBe(true);
    expect(sent.run.sessionId).toBe(idleSession.session.sessionId);
    expect(adapter.executed).toHaveLength(3);

    adapter.resolveDeferred({
      text: "done",
      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await running;
    store.close();
  });

  it("falls back when the active owner getter returns an empty string", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "desktop-local-user" });
    await kernel.executeRun({
      ...baseRunInput,
      ownerId: "other-owner",
      externalRefId: "other-task",
      requestId: "other-request",
    });

    const listed = parseToolResult(
      await handleAgentControlToolCall({ kernel, getOwnerId: () => "   " }, "list_agent_sessions", {}),
    );

    expect(listed.ok).toBe(true);
    expect(listed.sessions).toHaveLength(1);
    expect(listed.sessions[0].session.ownerId).toBe("desktop-local-user");
    store.close();
  });

  it("spawns a canonical top-level background agent without a parent run", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const spawned = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "spawn_background_agent", {
        prompt: "draft a story idea",
        title: "Story Idea",
        adapterId: "fake",
        externalRefKind: "pill",
        externalRefId: "pill-1",
        requestId: "background-1",
        clientId: "background-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
    expect(spawned.routeDecision).toMatchObject({
      intent: "spawn_agent",
      requestedProvider: "fake",
      requestedAgentCount: 1,
    });
    expect(spawned.session).toMatchObject({
      ownerId: "owner",
      title: "Story Idea",
      surfaceKind: "floating_bar",
      externalRefKind: "pill",
      externalRefId: "pill-1",
    });
    expect(spawned.run).toMatchObject({
      sessionId: spawned.session.sessionId,
      parentRunId: null,
      mode: "act",
      status: "starting",
    });
    store.close();
  });

  it("binds every direct-control origin surface through the same route owner", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    for (const [index, originSurfaceKind] of [
      "main_chat",
      "floating_bar",
      "realtime",
      "task_chat",
      "agent_control",
    ].entries()) {
      const spawned = parseToolResult(
        await handleAgentControlToolCall(ownerContext(kernel), "spawn_background_agent", {
          prompt: `origin ${originSurfaceKind}`,
          originSurfaceKind,
          adapterId: "fake",
          externalRefKind: "pill",
          externalRefId: `origin-${index}`,
          requestId: `origin-${index}`,
          ownerId: "owner",
        }),
      );
      expect(spawned.ok).toBe(true);
      expect(spawned.routeDecision).toMatchObject({
        intent: "spawn_agent",
        surfaceKind: originSurfaceKind,
      });
      expect(spawned.session.surfaceKind).toBe("floating_bar");
    }
    store.close();
  });

  it("creates a requested sibling set under one route decision", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const spawned = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "spawn_agent", {
      objective: "parallel bounded research",
      originSurfaceKind: "main_chat",
      requestedAgentCount: 3,
      visible: true,
      externalRefId: "sibling-set",
      adapterId: "fake",
      requestId: "sibling-set",
    }));

    expect(spawned.routeDecision).toMatchObject({ intent: "spawn_agent", requestedAgentCount: 3 });
    expect(spawned.requestedAgentCount).toBe(3);
    expect(spawned.agents).toHaveLength(3);
    const siblingExternalRefIds = spawned.agents.map((agent: any) => agent.session.externalRefId);
    expect(new Set(siblingExternalRefIds).size).toBe(3);
    for (const externalRefId of siblingExternalRefIds) {
      expect(externalRefId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
    }
    for (const row of store.allRows(
      `SELECT s.external_ref_id, r.input_json
       FROM sessions s JOIN runs r ON r.session_id = s.session_id
       WHERE s.external_ref_id IN (?, ?, ?)`,
      siblingExternalRefIds,
    )) {
      expect(JSON.parse(String(row.input_json)).metadata).toMatchObject({
        pillId: row.external_ref_id,
        siblingGroupExternalRefId: "sibling-set",
      });
    }
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(3);
    await waitUntil(() => store.allRows("SELECT status FROM runs").every((row) => row.status === "succeeded"));
    store.close();
  });

  it("leases authority before the first control effect and fails the invocation with zero effects after revocation", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const caller = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
      executionRole: "coordinator",
    });
    const parent = store.insertRun({
      sessionId: caller.sessionId,
      clientId: "lease-client",
      requestId: "lease-parent",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: parent.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "lease-worker",
    });
    const broker = createCapabilityBroker(store);
    const capability = broker.register({
      ownerId: "owner",
      sessionId: caller.sessionId,
      runId: parent.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "lease-before-first-effect",
      runId: parent.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: "owner",
      toolName: "spawn_agent",
      toolInput: { objective: "must not start" },
    });
    broker.markInvocationDispatched(authorized);
    const lease = broker.acquireExecutionLease(authorized, () => "owner");
    let entered!: () => void;
    let resume!: () => void;
    const enteredEffectBoundary = new Promise<void>((resolve) => { entered = resolve; });
    const resumeEffectBoundary = new Promise<void>((resolve) => { resume = resolve; });
    const resultPromise = handleAgentControlToolCall({
      ...ownerContext(kernel),
      callerSessionId: caller.sessionId,
      executionLease: {
        signal: lease.signal,
        assertCurrentAuthority: async () => {
          entered();
          await resumeEffectBoundary;
          lease.assertCurrentAuthority();
        },
      },
    }, "spawn_agent", {
      objective: "must not start",
      requestedAgentCount: 1,
      visible: true,
      adapterId: "fake",
      requestId: "lease-before-first-effect",
    });
    await enteredEffectBoundary;
    broker.revokeForOwner("owner", "owner_changed");
    resume();
    const result = parseToolResult(await resultPromise);
    expect(result).toMatchObject({ ok: false, error: { code: "owner_mismatch" } });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(1);
    lease.release();
    expect(() => broker.completeInvocation({
      ...invocationIdentityForTest(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "failed",
      result: JSON.stringify(result),
    })).toThrow(/completion authority was revoked/);
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_owner_changed",
    });
    store.close();
  });

  it("revalidates the lease between sibling effects and records the partial invocation as failed", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const caller = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
      executionRole: "coordinator",
    });
    const parent = store.insertRun({
      sessionId: caller.sessionId,
      clientId: "sibling-lease-client",
      requestId: "sibling-lease-parent",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: parent.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "sibling-lease-worker",
    });
    const broker = createCapabilityBroker(store);
    const capability = broker.register({
      ownerId: "owner",
      sessionId: caller.sessionId,
      runId: parent.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "lease-between-siblings",
      runId: parent.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: "owner",
      toolName: "spawn_agent",
      toolInput: { objective: "start one only", requestedAgentCount: 2 },
    });
    broker.markInvocationDispatched(authorized);
    const lease = broker.acquireExecutionLease(authorized, () => "owner");
    let assertionCount = 0;
    let entered!: () => void;
    let resume!: () => void;
    const enteredSecondSibling = new Promise<void>((resolve) => { entered = resolve; });
    const resumeSecondSibling = new Promise<void>((resolve) => { resume = resolve; });
    const resultPromise = handleAgentControlToolCall({
      ...ownerContext(kernel),
      callerSessionId: caller.sessionId,
      executionLease: {
        signal: lease.signal,
        assertCurrentAuthority: async () => {
          assertionCount += 1;
          if (assertionCount === 3) {
            entered();
            await resumeSecondSibling;
          }
          lease.assertCurrentAuthority();
        },
      },
    }, "spawn_agent", {
      objective: "start one only",
      requestedAgentCount: 2,
      visible: true,
      adapterId: "fake",
      requestId: "lease-between-siblings",
    });
    await enteredSecondSibling;
    broker.revokeForOwner("owner", "owner_changed");
    resume();
    const result = parseToolResult(await resultPromise);
    expect(result).toMatchObject({ ok: false, error: { code: "owner_mismatch" } });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(2);
    lease.release();
    expect(() => broker.completeInvocation({
      ...invocationIdentityForTest(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "failed",
      result: JSON.stringify(result),
    })).toThrow(/completion authority was revoked/);
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_owner_changed",
    });
    store.close();
  });

  it("aborts an in-flight send when its parent invocation authority is revoked", async () => {
    const { store, kernel, adapter } = createKernelHarness(newDatabasePath());
    const caller = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "fake",
      executionRole: "coordinator",
    });
    const parent = store.insertRun({
      sessionId: caller.sessionId,
      clientId: "send-lease-client",
      requestId: "send-lease-parent",
      status: "running",
      mode: "act",
    });
    const parentAttempt = store.insertAttempt({
      runId: parent.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "send-lease-worker",
    });
    const target = store.insertSession({
      ownerId: "owner",
      surfaceKind: "background_agent",
      defaultAdapterId: "fake",
      executionRole: "leaf",
    });
    const broker = createCapabilityBroker(store);
    const capability = broker.register({
      ownerId: "owner",
      sessionId: caller.sessionId,
      runId: parent.runId,
      attemptId: parentAttempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "lease-inflight-send",
      runId: parent.runId,
      attemptId: parentAttempt.attemptId,
      activeOwnerId: "owner",
      toolName: "send_agent_message",
      toolInput: { sessionId: target.sessionId, prompt: "continue" },
    });
    broker.markInvocationDispatched(authorized);
    const lease = broker.acquireExecutionLease(authorized, () => "owner");
    adapter.deferResult();
    const resultPromise = handleAgentControlToolCall({
      ...ownerContext(kernel),
      callerSessionId: caller.sessionId,
      executionLease: lease,
    }, "send_agent_message", {
      sessionId: target.sessionId,
      prompt: "continue only while authorized",
      mode: "act",
      requestId: "lease-inflight-send",
      clientId: "send-lease-client",
    });
    await waitUntil(() => adapter.executed.length === 1);
    broker.revokeForOwner("owner", "owner_changed");
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late result" });
    const result = parseToolResult(await resultPromise);
    expect(result).toMatchObject({ ok: false, error: { code: "owner_mismatch" } });
    expect(store.getRow(
      "SELECT status FROM runs WHERE session_id = ? ORDER BY created_at_ms DESC LIMIT 1",
      [target.sessionId],
    ).status).toBe("cancelled");
    lease.release();
    expect(() => broker.completeInvocation({
      ...invocationIdentityForTest(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "failed",
      result: JSON.stringify(result),
    })).toThrow(/completion authority was revoked/);
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_owner_changed",
    });
    store.close();
  });

  it("cannot promote a persisted leaf caller with a coordinator origin surface", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const leaf = store.insertSession({
      ownerId: "owner",
      surfaceKind: "delegated_agent",
      externalRefKind: "agent",
      externalRefId: "leaf-origin-guard",
      defaultAdapterId: "fake",
      executionRole: "leaf",
    });
    const result = parseToolResult(
      await handleAgentControlToolCall(
        { ...ownerContext(kernel), callerSessionId: leaf.sessionId },
        "spawn_background_agent",
        {
          prompt: "try to promote me",
          originSurfaceKind: "main_chat",
          adapterId: "fake",
          externalRefKind: "pill",
          externalRefId: "must-not-exist",
          requestId: "leaf-origin-promotion",
          ownerId: "owner",
        },
      ),
    );
    expect(result).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(result.error.message).toMatch(/caller_role_forbidden|Leaf workers/i);
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("uses the owner default only for new direct sessions and preserves caller inheritance", async () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const registry = new AdapterRegistry();
    registry.register("acp", () => new FakeRuntimeAdapter("acp"), 2);
    registry.register("pi-mono", () => new FakeRuntimeAdapter("pi-mono"), 2);
    const kernel = new AgentRuntimeKernel({ store, registry });
    const existing = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "existing-old-profile",
      defaultAdapterId: "acp",
      modelProfile: "old-model",
      defaultCwd: "/tmp/old-profile",
      executionRole: "coordinator",
    });
    kernel.configureDefaultExecutionProfile({
      ownerId: "owner",
      adapterId: "pi-mono",
      modelProfile: "new-model",
      workingDirectory: "/tmp/new-profile",
      expectedPreferenceGeneration: 0,
    });

    const direct = parseToolResult(await handleAgentControlToolCall(
      trustedOwnerContext(kernel),
      "spawn_agent",
      {
        objective: "new direct pill",
        originSurfaceKind: "main_chat",
        visible: true,
        externalRefId: "new-direct-pill",
        requestId: "new-direct-pill",
      },
    ));
    const inherited = parseToolResult(await handleAgentControlToolCall(
      { ...ownerContext(kernel), callerSessionId: existing.sessionId },
      "spawn_background_agent",
      {
        prompt: "child of old session",
        originSurfaceKind: "main_chat",
        externalRefKind: "pill",
        externalRefId: "old-session-child",
        requestId: "old-session-child",
      },
    ));

    expect(direct.session).toMatchObject({
      defaultAdapterId: "pi-mono",
      modelProfile: "new-model",
      defaultCwd: "/tmp/new-profile",
    });
    expect(inherited.session).toMatchObject({
      defaultAdapterId: "acp",
      modelProfile: "old-model",
      defaultCwd: "/tmp/old-profile",
    });
    expect(kernel.sessionExecutionProfile(existing.sessionId, "owner")).toMatchObject({
      adapterId: "acp",
      modelProfile: "old-model",
      workingDirectory: "/tmp/old-profile",
    });
    await waitUntil(() => store.allRows(
      "SELECT status FROM runs WHERE run_id IN (?, ?)",
      [direct.run.runId, inherited.run.runId],
    ).every((row) => row.status === "succeeded"));
    store.close();
  });

  it("inherits the managed adapter for background agents instead of local ACP", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const spawned = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), defaultAdapterId: "pi-mono" }, "spawn_agent", {
        objective: "research managed routing",
        visible: true,
        requestId: "spawn-managed-routing-1",
        clientId: "spawn-client",
        ownerId: "owner",
      }),
    );

    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]);
      return row.status === "succeeded";
    });
    expect(spawned.session.defaultAdapterId).toBe("pi-mono");
    expect(adapter.executed).toHaveLength(1);
    store.close();
  });

  it("rejects an explicit local ACP override from a managed agent", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const result = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), defaultAdapterId: "pi-mono" }, "spawn_agent", {
        objective: "do not use local credentials",
        visible: true,
        adapterId: "acp",
        requestId: "spawn-managed-local-acp-1",
        clientId: "spawn-client",
        ownerId: "owner",
      }),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Local Claude is available only when the User Claude mode is selected.",
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("lets signed desktop control start Hermes and OpenClaw as top-level local sessions", async () => {
    for (const provider of ["hermes", "openclaw"] as const) {
      const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), provider);
      const spawned = parseToolResult(
        await handleAgentControlToolCall(
          {
            ...ownerContext(kernel),
            defaultAdapterId: "pi-mono",
            providerBoundary: "managed_cloud",
            trustedUserControl: true,
          },
          "spawn_agent",
          {
            objective: `run this with ${provider}`,
            provider,
            visible: true,
            requestId: `direct-${provider}-spawn`,
            clientId: "desktop-floating-pill",
            ownerId: "owner",
          },
        ),
      );

      await waitUntil(() => {
        const row = store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]);
        return row.status === "succeeded";
      });
      expect(spawned.session).toMatchObject({
        defaultAdapterId: provider,
        providerBoundary: `local_user:${provider}`,
      });
      const listed = parseToolResult(
        await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", { ownerId: "owner" }),
      );
      expect(listed.floating_agent_pills).toContainEqual(
        expect.objectContaining({
          sessionId: spawned.session.sessionId,
          runId: spawned.run.runId,
          provider,
        }),
      );
      expect(adapter.executed).toHaveLength(1);
      store.close();
    }
  });

  it("lets the canonical directed-provider tool start Hermes and OpenClaw from an Omi coordinator", async () => {
    for (const provider of ["hermes", "openclaw"] as const) {
      const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), provider);
      const spawned = parseToolResult(
        await handleAgentControlToolCall(
          {
            ...ownerContext(kernel),
            defaultAdapterId: "pi-mono",
            providerBoundary: "managed_cloud",
          },
          "spawn_agent",
          {
            objective: `run this with ${provider}`,
            provider,
            visible: true,
            requestId: `managed-directed-${provider}-spawn`,
            clientId: "main-chat",
            ownerId: "owner",
          },
        ),
      );

      await waitUntil(() => {
        const row = store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]);
        return row.status === "succeeded";
      });
      expect(spawned.session).toMatchObject({
        defaultAdapterId: provider,
        providerBoundary: `local_user:${provider}`,
      });
      expect(adapter.executed).toHaveLength(1);
      store.close();
    }
  });

  it("keeps an explicit realtime local provider on its own adapter and model profile", async () => {
    for (const provider of ["hermes", "openclaw"] as const) {
      const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), provider);
      const surface = {
        surfaceKind: "realtime_voice",
        externalRefKind: "chat",
        externalRefId: `voice-${provider}`,
      };
      const coordinator = kernel.resolveSurfaceSession({
        ownerId: "owner",
        surfaceRef: surface,
        defaultAdapterId: "pi-mono",
        modelProfile: "omi-sonnet",
        providerBoundary: "managed_cloud",
        executionRole: "coordinator",
      });
      const parentRun = store.insertRun({
        sessionId: coordinator.agentSessionId,
        clientId: "realtime",
        requestId: `voice-parent-${provider}`,
        status: "running",
        mode: "act",
      });
      const spawned = parseToolResult(
        await handleAgentControlToolCall(
          {
            ...ownerContext(kernel),
            defaultAdapterId: "pi-mono",
            providerBoundary: "managed_cloud",
            callerSessionId: coordinator.agentSessionId,
            executionRole: "coordinator",
            authorizedCallerRunId: parentRun.runId,
            authorizedProducerJournal: {
              schemaVersion: 1,
              surface,
              continuityKey: `voice-provider-model-${provider}`,
              pillId: `pill-provider-model-${provider}`,
              userText: `Ask ${provider} for a summary`,
              assistantText: `Starting ${provider}`,
              objective: `Run this with ${provider}`,
              title: `Ask ${provider}`,
            },
          },
          "spawn_agent",
          {
            objective: `Run this with ${provider}`,
            provider,
            visible: true,
            externalRefId: `pill-provider-model-${provider}`,
            requestId: `voice-${provider}-spawn`,
            clientId: "realtime",
            ownerId: "owner",
          },
        ),
      );

      await waitUntil(() => store.getRow(
        "SELECT status FROM runs WHERE run_id = ?",
        [spawned.run.runId],
      ).status === "succeeded");
      expect(spawned.session).toMatchObject({
        defaultAdapterId: provider,
        providerBoundary: `local_user:${provider}`,
        modelProfile: null,
      });
      expect(kernel.sessionExecutionProfile(spawned.session.sessionId, "owner")).toMatchObject({
        adapterId: provider,
        credentialScope: "local_user",
        modelProfile: null,
      });
      expect(adapter.opened.at(-1)?.model).toBeUndefined();
      store.close();
    }
  });

  it("rejects a mismatched directed provider and adapter override", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const result = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), defaultAdapterId: "pi-mono" }, "spawn_agent", {
        objective: "do not create an ambiguous provider session",
        provider: "openclaw",
        adapterId: "pi-mono",
        requestId: "managed-mismatched-provider-spawn",
        clientId: "main-chat",
        ownerId: "owner",
      }),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "provider and adapterId must match when both are supplied",
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("lets signed desktop control continue a local provider session through the Omi cloud bridge", async () => {
    for (const provider of ["hermes", "openclaw"] as const) {
      const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), provider);
      const initial = await kernel.executeRun({
        ...baseRunInput,
        adapterId: provider,
        defaultAdapterId: provider,
      });

      const continued = parseToolResult(
        await handleAgentControlToolCall(
          {
            ...ownerContext(kernel),
            defaultAdapterId: "pi-mono",
            providerBoundary: "managed_cloud",
            trustedUserControl: true,
          },
          "send_agent_message",
          {
            sessionId: initial.session.sessionId,
            prompt: "Say how it's going.",
            requestId: `direct-${provider}-continue`,
            clientId: "desktop-floating-pill",
            ownerId: "owner",
          },
        ),
      );

      expect(continued).toMatchObject({
        ok: true,
        session: {
          sessionId: initial.session.sessionId,
          defaultAdapterId: provider,
          providerBoundary: `local_user:${provider}`,
        },
      });
      expect(adapter.executed).toHaveLength(2);
      store.close();
    }
  });

  it("returns a typed setup-needed result when an authorized realtime spawn selects an unavailable provider", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const surface = {
      surfaceKind: "realtime_voice",
      externalRefKind: "chat",
      externalRefId: "voice-unavailable-provider",
    };
    const coordinator = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: surface,
      defaultAdapterId: "pi-mono",
      modelProfile: "omi-sonnet",
      providerBoundary: "managed_cloud",
      executionRole: "coordinator",
    });
    const parentRun = store.insertRun({
      sessionId: coordinator.agentSessionId,
      clientId: "realtime",
      requestId: "voice-parent-unavailable-provider",
      status: "running",
      mode: "act",
    });

    const result = parseToolResult(
      await handleAgentControlToolCall(
        {
          ...ownerContext(kernel),
          defaultAdapterId: "pi-mono",
          providerBoundary: "managed_cloud",
          callerSessionId: coordinator.agentSessionId,
          executionRole: "coordinator",
          authorizedCallerRunId: parentRun.runId,
          authorizedProducerJournal: {
            schemaVersion: 1,
            surface,
            continuityKey: "voice-provider-setup-needed",
            pillId: "pill-provider-setup-needed",
            userText: "Ask OpenClaw for a summary",
            assistantText: "Starting OpenClaw",
            objective: "Run this with OpenClaw",
            title: "Ask OpenClaw",
          },
        },
        "spawn_agent",
        {
          objective: "Run this with OpenClaw",
          provider: "openclaw",
          visible: true,
          externalRefId: "pill-provider-setup-needed",
          requestId: "voice-openclaw-unavailable",
          clientId: "realtime",
          ownerId: "owner",
        },
      ),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "provider_setup_needed",
        provider: "openclaw",
        retryable: true,
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("does not let signed desktop control cross a managed parent run into a local provider", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const parent = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });

    const result = parseToolResult(
      await handleAgentControlToolCall(
        {
          ...ownerContext(kernel),
          defaultAdapterId: "pi-mono",
          providerBoundary: "managed_cloud",
          trustedUserControl: true,
        },
        "spawn_agent",
        {
          objective: "do not cross into OpenClaw",
          provider: "openclaw",
          parentRunId: parent.run.runId,
          requestId: "direct-managed-parent-openclaw",
          clientId: "desktop-floating-pill",
          ownerId: "owner",
        },
      ),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Managed Omi agents can only use Omi cloud routing.",
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("fails closed for an unknown adapter even from signed desktop control", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const result = parseToolResult(
      await handleAgentControlToolCall(
        {
          ...ownerContext(kernel),
          defaultAdapterId: "pi-mono",
          providerBoundary: "managed_cloud",
          trustedUserControl: true,
        },
        "spawn_agent",
        {
          objective: "do not create an unknown provider session",
          adapterId: "unknown-adapter",
          requestId: "direct-unknown-provider",
          clientId: "desktop-floating-pill",
          ownerId: "owner",
        },
      ),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Unknown production adapter: unknown-adapter",
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("keeps every managed control entry point on Omi cloud routing", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const context = { ...ownerContext(kernel), defaultAdapterId: "pi-mono" };
    const parent = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });

    for (const provider of ["acp", "hermes", "openclaw", "unknown-adapter"] as const) {
      const expectedMessage =
        provider === "acp"
          ? "Local Claude is available only when the User Claude mode is selected."
          : provider === "unknown-adapter"
            ? "Unknown production adapter: unknown-adapter"
            : "Managed Omi agents can only use Omi cloud routing.";
      const spawned = parseToolResult(
        await handleAgentControlToolCall(context, "spawn_agent", {
          objective: `do not route to ${provider}`,
          adapterId: provider,
          requestId: `managed-provider-${provider}`,
          clientId: "managed-routing",
          ownerId: "owner",
        }),
      );
      expect(spawned).toMatchObject({
        ok: false,
        error: { code: "control_tool_failed", message: expectedMessage },
      });

      const background = parseToolResult(
        await handleAgentControlToolCall(context, "spawn_background_agent", {
          prompt: `do not route to ${provider}`,
          adapterId: provider,
          requestId: `managed-background-${provider}`,
          clientId: "managed-routing",
          ownerId: "owner",
        }),
      );
      expect(background).toMatchObject({
        ok: false,
        error: { code: "control_tool_failed", message: expectedMessage },
      });

      const continued = parseToolResult(
        await handleAgentControlToolCall(context, "send_agent_message", {
          sessionId: parent.session.sessionId,
          prompt: `do not route to ${provider}`,
          adapterId: provider,
          requestId: `managed-continue-${provider}`,
          clientId: "managed-routing",
          ownerId: "owner",
        }),
      );
      expect(continued).toMatchObject({
        ok: false,
        error: { code: "control_tool_failed", message: expectedMessage },
      });

      const delegated = parseToolResult(
        await handleAgentControlToolCall(context, "run_agent_and_wait", {
          parentRunId: parent.run.runId,
          objective: `do not route to ${provider}`,
          adapterId: provider,
          requestId: `managed-delegate-${provider}`,
          clientId: "managed-routing",
          ownerId: "owner",
        }),
      );
      expect(delegated).toMatchObject({
        ok: false,
        error: { code: "control_tool_failed", message: expectedMessage },
      });
    }

    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("prevents leaf background workers from spawning more agents", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const result = parseToolResult(
      await handleAgentControlToolCall(
        {
          ...ownerContext(kernel),
          defaultAdapterId: "pi-mono",
          executionRole: "leaf",
        },
        "spawn_agent",
        {
          objective: "fan out more work",
          visible: true,
          requestId: "leaf-worker-spawn-1",
          clientId: "spawn-client",
          ownerId: "owner",
        },
      ),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Background agents are leaf workers and cannot start additional agents.",
      },
    });
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("denies every nested-agent creation entry point for a leaf role", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const parent = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const context = {
      ...ownerContext(kernel),
      defaultAdapterId: "pi-mono",
      providerBoundary: "managed_cloud" as const,
      executionRole: "leaf" as const,
      callerSessionId: parent.session.sessionId,
    };
    const calls = [
      [
        "spawn_agent",
        { objective: "nested", visible: false },
        "Background agents are leaf workers and cannot start additional agents.",
      ],
      [
        "spawn_background_agent",
        { prompt: "nested" },
        "Background agents are leaf workers and cannot start additional agents.",
      ],
      [
        "run_agent_and_wait",
        { objective: "nested", parentRunId: parent.run.runId },
        "Background agents are leaf workers and cannot start additional agents.",
      ],
      [
        "send_agent_message",
        { sessionId: parent.session.sessionId, prompt: "continue" },
        "Leaf workers cannot continue agent sessions.",
      ],
    ] as const;

    for (const [name, input, message] of calls) {
      const result = parseToolResult(await handleAgentControlToolCall(context, name, input));
      expect(result).toMatchObject({
        ok: false,
        error: {
          code: "control_tool_failed",
          message,
        },
      });
    }
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("rejects kernel background spawns from leaf callers without trusted authority", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const leaf = store.insertSession({
      ownerId: "owner",
      surfaceKind: "background_agent",
      executionRole: "leaf",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
    });

    await expect(
      kernel.spawnBackgroundAgent({
        ownerId: "owner",
        clientId: "client",
        requestId: "leaf-bypass",
        prompt: "should fail",
        adapterId: "pi-mono",
        defaultAdapterId: "pi-mono",
        callerSessionId: leaf.sessionId,
      }),
    ).rejects.toThrow("Leaf workers cannot create background agents.");

    await expect(
      kernel.spawnBackgroundAgent({
        ownerId: "owner",
        clientId: "client",
        requestId: "unscoped-bypass",
        prompt: "should fail",
        adapterId: "pi-mono",
        defaultAdapterId: "pi-mono",
      }),
    ).rejects.toThrow("Background agent spawn requires a coordinator caller session.");

    expect(store.allRows("SELECT * FROM runs")).toHaveLength(0);
    store.close();
  });

  it("loads owned session execution policy by id instead of a bounded list", () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const leaf = store.insertSession({
      ownerId: "owner",
      surfaceKind: "background_agent",
      executionRole: "leaf",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
    });

    expect(kernel.executionPolicyForOwnedSession(leaf.sessionId, "owner")).toEqual({
      executionRole: "leaf",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
    });
    expect(() => kernel.executionPolicyForOwnedSession(leaf.sessionId, "other-owner")).toThrow(
      "Agent session is not visible to the active owner",
    );
    store.close();
  });

  it("delegates call mode with distinct parent and child sessions linked by a delegation row", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);

    const delegated = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "run_agent_and_wait", {
        parentRunId: parent.run.runId,
        objective: "summarize the child task",
        context: "only concise parent context",
        requestId: "delegate-call-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(delegated.ok).toBe(true);
    expect(delegated.delegation).toMatchObject({
      parentSessionId: parent.session.sessionId,
      parentRunId: parent.run.runId,
      childSessionId: delegated.session.sessionId,
      childRunId: delegated.run.runId,
      mode: "call",
      status: "succeeded",
      objective: "summarize the child task",
    });
    expect(delegated.session.sessionId).not.toBe(parent.session.sessionId);
    expect(delegated.run.parentRunId).toBe(parent.run.runId);
    expect(delegated.result).toMatchObject({
      summary: expect.stringContaining("done-"),
      verifiedEffects: [],
      openQuestions: [],
      usage: { inputTokens: 1, outputTokens: 2 },
    });

    const row = store.getRow("SELECT * FROM delegations WHERE delegation_id = ?", [delegated.delegation.delegationId]);
    expect(row.parent_run_id).toBe(parent.run.runId);
    expect(row.child_run_id).toBe(delegated.run.runId);

    const parentInspect = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: parent.run.runId,
        ownerId: "owner",
      }),
    );
    expect(parentInspect.parentDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    const childInspect = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: delegated.run.runId,
        ownerId: "owner",
      }),
    );
    expect(childInspect.childDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    store.close();
  });

  it("keeps Swift-backed MCP tools available in delegated child bindings", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    const buildMcpServers = vi.fn(() => [
      {
        name: "omi-tools",
        command: "node",
        args: ["omi-tools.js"],
        env: [
          {
            name: "OMI_CONTEXT_FILE",
            value: expect.stringContaining("omi-tools-context"),
          },
        ],
      },
      { name: "playwright", command: "node", args: ["playwright.js"], env: [] },
    ]);

    const delegated = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), buildMcpServers }, "run_agent_and_wait", {
        parentRunId: parent.run.runId,
        objective: "use browser tools if needed",
        requestId: "delegate-tools-1",
        clientId: "delegate-client",
        ownerId: "owner",
        cwd: "/tmp/delegate-cwd",
        runMode: "act",
      }),
    );

    expect(delegated.ok).toBe(true);
    expect(buildMcpServers).toHaveBeenCalledWith("act", "/tmp/delegate-cwd", undefined, {
      ownerId: "owner",
      requestId: "delegate-tools-1",
      clientId: "delegate-client",
      adapterId: "fake",
      protocolVersion: 2,
      includeSwiftBackedTools: true,
      screenContext: true,
      executionRole: "leaf",
      surfaceKind: undefined,
      externalRefKind: undefined,
      externalRefId: undefined,
    });
    expect(toolNamesForAdapter("omi-tools-stdio", { screenContext: true })).toEqual(
      expect.arrayContaining(["get_work_context", "request_permission", "check_permission_status", "capture_screen"]),
    );
    expect(adapter.opened.at(-1)?.mcpServers).toEqual([
      {
        name: "omi-tools",
        command: "node",
        args: ["omi-tools.js"],
        env: [
          {
            name: "OMI_CONTEXT_FILE",
            value: expect.stringContaining("omi-tools-context"),
          },
        ],
      },
      {
        name: "playwright",
        command: "node",
        args: ["playwright.js"],
        env: [
          {
            name: "OMI_CONTEXT_FILE",
            value: expect.stringContaining("omi-tools-context"),
          },
        ],
      },
    ]);
    expect(adapter.executed.at(-1)?.metadata).not.toMatchObject({
      disableSwiftBackedTools: true,
    });
    store.close();
  });

  it("rejects delegated child runs when the requested adapter is unavailable", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    const buildMcpServers = vi.fn(() => []);

    const delegated = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), buildMcpServers }, "run_agent_and_wait", {
        parentRunId: parent.run.runId,
        objective: "use OpenClaw for this child",
        adapterId: "openclaw",
        requestId: "delegate-openclaw-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(delegated).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
        message: "Desktop intent effect rejected by canonical route policy (provider_unavailable).",
      },
    });
    expect(buildMcpServers).not.toHaveBeenCalled();
    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("rejects non-run parent ids before creating delegated child work", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const delegated = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "run_agent_and_wait", {
        parentRunId: "ctx_73609606effbbf6d",
        objective: "try the invalid parent id",
        requestId: "delegate-invalid-parent-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(delegated.ok).toBe(false);
    expect(delegated.error.code).toBe("control_tool_failed");
    expect(delegated.error.message).toContain("parentRunId must be a canonical Omi run_id");
    store.close();
  });

  it("spawn_agent generates a pill external ref when visible without externalRefId", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const spawnedRaw = await handleAgentControlToolCall(ownerContext(kernel), "spawn_agent", {
      objective: "summarize inbox",
      visible: true,
      adapterId: "fake",
      requestId: "spawn-visible-pill-1",
      clientId: "spawn-client",
      ownerId: "owner",
    });
    const spawned = parseToolResult(spawnedRaw);

    expect(spawned.ok).toBe(true);
    expect(spawnedRaw).not.toMatch(/errorCode|errorMessage/);
    expect(spawned.session).toMatchObject({
      ownerId: "owner",
      surfaceKind: "floating_bar",
      externalRefKind: "pill",
    });
    expect(spawned.session.externalRefId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
    const row = store.getRow("SELECT external_ref_kind, external_ref_id FROM sessions WHERE session_id = ?", [
      spawned.session.sessionId,
    ]);
    expect(row.external_ref_kind).toBe("pill");
    expect(row.external_ref_id).toBe(spawned.session.externalRefId);

    const listed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        ownerId: "owner",
      }),
    );
    expect(listed.ok).toBe(true);
    expect(listed.floating_agent_pills).toContainEqual(
      expect.objectContaining({
        id: spawned.session.externalRefId,
        sessionId: spawned.session.sessionId,
        runId: spawned.run.runId,
        status: expect.any(String),
        query: "summarize inbox",
      }),
    );
    store.close();
  });

  it("projects typed failure details for accepted visible spawned agents", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    adapter.failNextExecutionError = new Error("spawn bridge failed after acceptance");

    const spawned = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "spawn_agent", {
        objective: "summarize inbox",
        visible: true,
        externalRefId: "11111111-2222-4333-8444-555555555555",
        requestId: "spawn-visible-failure-1",
        clientId: "spawn-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]);
      return row.status === "failed";
    });

    const listed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", {
        ownerId: "owner",
      }),
    );
    expect(listed.floating_agent_pills).toContainEqual(
      expect.objectContaining({
        id: "11111111-2222-4333-8444-555555555555",
        runId: spawned.run.runId,
        status: "failed",
        errorCode: "adapter_execution_failed",
        errorMessage: expect.stringContaining("spawn bridge failed after acceptance"),
        latestActivity: expect.stringContaining("spawn bridge failed after acceptance"),
      }),
    );
    store.close();
  });

  it("retries an accepted ACP spawn after control-tool credential recovery", async () => {
    const authError = new Error("Invalid authentication credentials");
    let recoveries = 0;
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp", 4, undefined, (adapterId) =>
      adapterId === "acp"
        ? {
            maxAttempts: 2,
            recoverAfterError: async (error) => {
              recoveries += 1;
              return error === authError;
            },
          }
        : {},
    );
    adapter.failNextExecutionError = authError;

    const spawned = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "spawn_agent", {
        objective: "research PXMX",
        visible: true,
        requestId: "spawn-auth-recovery-1",
        clientId: "spawn-client",
        ownerId: "owner",
      }),
    );

    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]);
      return row.status === "succeeded";
    });
    expect(recoveries).toBe(1);
    expect(
      store.allRows("SELECT attempt_no, retry_reason, status FROM run_attempts WHERE run_id = ? ORDER BY attempt_no", [
        spawned.run.runId,
      ]),
    ).toEqual([
      expect.objectContaining({
        attempt_no: 1,
        retry_reason: null,
        status: "failed",
      }),
      expect.objectContaining({
        attempt_no: 2,
        retry_reason: "recoverable_error",
        status: "succeeded",
      }),
    ]);
    store.close();
  });

  it("spawn_agent with parentRunId returns child handles before the child finishes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    adapter.deferResult();
    const buildMcpServers = vi.fn(() => []);

    const spawned = parseToolResult(
      await handleAgentControlToolCall({ ...ownerContext(kernel), buildMcpServers }, "spawn_agent", {
        parentRunId: parent.run.runId,
        objective: "run in the background",
        visible: false,
        requestId: "delegate-spawn-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
    expect(spawned.result).toBeUndefined();
    expect(spawned.session.sessionId).not.toBe(parent.session.sessionId);
    expect(spawned.run.status).toBe("starting");
    expect(buildMcpServers).toHaveBeenCalledWith("act", undefined, undefined, {
      ownerId: "owner",
      requestId: "delegate-spawn-1",
      clientId: "delegate-client",
      adapterId: "fake",
      protocolVersion: 2,
      surfaceKind: "delegated_agent",
      externalRefKind: undefined,
      externalRefId: undefined,
      includeSwiftBackedTools: true,
      screenContext: true,
      executionRole: "leaf",
    });
    await waitUntil(() => adapter.executed.length === 2);

    const running = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: spawned.run.runId,
        ownerId: "owner",
      }),
    );
    expect(["starting", "running"]).toContain(running.run.status);
    expect(running.childDelegations[0].delegationId).toBe(spawned.delegation.delegationId);

    adapter.resolveDeferred({
      text: "spawn complete",
      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM delegations WHERE delegation_id = ?", [
        spawned.delegation.delegationId,
      ]);
      return row.status === "succeeded";
    });
    store.close();
  });

  it("marks spawned delegations failed when child execution fails", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    adapter.failNextExecutionError = new Error("spawn failed");

    const spawned = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "spawn_agent", {
        parentRunId: parent.run.runId,
        objective: "fail in the background",
        visible: false,
        requestId: "delegate-spawn-failure",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM delegations WHERE delegation_id = ?", [
        spawned.delegation.delegationId,
      ]);
      return row.status === "failed";
    });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.run.runId]).status).toBe("failed");
    store.close();
  });

  it("send_agent_message continues an existing child session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    const firstChild = await kernel.delegateAgent({
      mode: "call",
      parentRunId: parent.run.runId,
      objective: "first child objective",
      ownerId: "owner",
      clientId: "delegate-client",
      requestId: "delegate-call-seed",
    });

    const continued = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
        sessionId: firstChild.childSession.sessionId,
        prompt: "continue the child",
        requestId: "delegate-continue-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(continued.ok).toBe(true);
    expect(continued.session.sessionId).toBe(firstChild.childSession.sessionId);
    expect(continued.run.runId).not.toBe(firstChild.childRun.runId);
    expect(continued.run.parentRunId).toBeNull();
    expect(adapter.executed).toHaveLength(3);
    expect(adapter.executed[2].sessionId).toBe(firstChild.childSession.sessionId);
    store.close();
  });

  it("enforces simple delegation depth and budget constraints", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);

    const invalidBudget = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "run_agent_and_wait", {
        parentRunId: parent.run.runId,
        objective: "too expensive",
        maxBudgetUsd: 11,
      }),
    );
    expect(invalidBudget.ok).toBe(false);
    expect(invalidBudget.error.code).toBe("invalid_tool_input");

    const child = await kernel.delegateAgent({
      mode: "call",
      parentRunId: parent.run.runId,
      objective: "depth one",
      ownerId: "owner",
      clientId: "delegate-client",
      requestId: "delegate-depth-one",
      maxDepth: 1,
    });
    const tooDeep = await kernel
      .delegateAgent({
        mode: "call",
        parentRunId: child.childRun.runId,
        objective: "depth two",
        ownerId: "owner",
        clientId: "delegate-client",
        requestId: "delegate-depth-two",
        maxDepth: 1,
      })
      .then(
        () => undefined,
        (error) => error,
      );
    expect(tooDeep).toBeInstanceOf(Error);
    expect(String(tooDeep.message)).toContain("exceeds maxDepth");
    store.close();
  });

  it("runs list, inspect, artifact, and cancel through the relay-style tool path", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const running = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);

    const runId = adapter.executed[0].runId;
    const attemptId = adapter.executed[0].attemptId;
    kernel.persistArtifact({
      artifactId: "art_relay",
      attemptId,
      kind: "log",
      role: "log",
      uri: "omi-artifact://art_relay",
      displayName: "relay.log",
      mimeType: "text/plain",
      sizeBytes: 9,
    });
    const sockPath = await startControlRelay(ownerContext(kernel));

    const listed = parseToolResult((await sendToolUse(sockPath, "list_agent_sessions", { ownerId: "owner" })).result);
    expect(listed.sessions[0].activeRun.runId).toBe(runId);

    const inspected = parseToolResult(
      (
        await sendToolUse(sockPath, "get_agent_run", {
          runId,
          ownerId: "owner",
        })
      ).result,
    );
    expect(inspected.run.status).toBe("running");
    expect(inspected.attempts[0].attemptId).toBe(attemptId);

    const artifacts = parseToolResult(
      (
        await sendToolUse(sockPath, "inspect_agent_artifacts", {
          runId,
          ownerId: "owner",
        })
      ).result,
    );
    expect(artifacts.artifacts[0]).toMatchObject({
      artifactId: "art_relay",
      uri: "omi-artifact://art_relay",
    });

    const cancelled = parseToolResult(
      (
        await sendToolUse(sockPath, "cancel_agent_run", {
          runId,
          ownerId: "owner",
        })
      ).result,
    );
    expect(cancelled.cancellation).toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
      runId,
      attemptId,
    });

    adapter.resolveDeferred({
      text: "relay cancelled",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    await running;
    store.close();
  });
});

function parseToolResult(result: string): any {
  return JSON.parse(result);
}

function invocationIdentityForTest(invocation: AuthorizedRunToolInvocation) {
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

function workstreamWriteSnapshot(store: SqliteAgentStore) {
  return {
    sessions: store.allRows("SELECT * FROM sessions ORDER BY session_id"),
    surfaceConversations: store.allRows(
      "SELECT * FROM surface_conversations ORDER BY owner_id, surface_kind, external_ref_kind, external_ref_id",
    ),
    contextPackets: store.allRows("SELECT * FROM desktop_context_packets ORDER BY packet_id"),
    contextAccessLogs: store.allRows("SELECT * FROM desktop_context_access_log ORDER BY access_id"),
    artifactVersions: store.allRows(
      "SELECT * FROM workstream_artifact_versions ORDER BY session_id, logical_key, version",
    ),
    artifacts: store.allRows("SELECT * FROM artifacts ORDER BY artifact_id"),
    checkpoints: store.allRows(
      "SELECT * FROM workstream_continuation_checkpoints ORDER BY owner_id, workstream_id",
    ),
    deliveries: store.allRows("SELECT * FROM desktop_artifact_deliveries ORDER BY delivery_id"),
    events: store.allRows("SELECT * FROM events ORDER BY event_id"),
  };
}

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-control-tools-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}

function ownerContext(kernel: AgentControlToolContext["kernel"]): AgentControlToolContext {
  return { kernel, getOwnerId: () => "owner" };
}

function trustedOwnerContext(kernel: AgentControlToolContext["kernel"]): AgentControlToolContext {
  return { kernel, trustedUserControl: true, getOwnerId: () => "owner" };
}

function startControlRelay(context: AgentControlToolContext): Promise<string> {
  const sockPath = join(tmpdir(), `omi-control-tools-${process.pid}-${Date.now()}.sock`);
  rmSync(sockPath, { force: true });
  return new Promise((resolve) => {
    const server = createServer((client: Socket) => {
      let buffer = "";
      client.on("data", (data: Buffer) => {
        buffer += data.toString();
        let idx;
        while ((idx = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 1);
          if (!line.trim()) continue;
          const msg = JSON.parse(line) as {
            type: string;
            callId: string;
            name: string;
            input: Record<string, unknown>;
          };
          if (msg.type !== "tool_use" || !isAgentControlToolName(msg.name)) continue;
          void handleAgentControlToolCall(context, msg.name, msg.input).then((result) => {
            client.write(
              JSON.stringify({
                type: "tool_result",
                callId: msg.callId,
                result,
              }) + "\n",
            );
          });
        }
      });
    });
    servers.push({ server, sockPath });
    server.listen(sockPath, () => resolve(sockPath));
  });
}

function sendToolUse(
  sockPath: string,
  name: string,
  input: Record<string, unknown>,
): Promise<{ type: string; callId: string; result: string }> {
  const callId = `call-${name}-${Date.now()}-${Math.random()}`;
  return new Promise((resolve, reject) => {
    const client = createConnection(sockPath, () => {
      client.write(JSON.stringify({ type: "tool_use", callId, name, input }) + "\n");
    });
    let buffer = "";
    client.on("data", (data: Buffer) => {
      buffer += data.toString();
      const idx = buffer.indexOf("\n");
      if (idx < 0) return;
      const response = JSON.parse(buffer.slice(0, idx));
      client.end();
      resolve(response);
    });
    client.on("error", reject);
  });
}
