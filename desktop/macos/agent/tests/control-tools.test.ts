import { mkdtempSync, rmSync } from "node:fs";
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  activeControlToolOwnerId,
  AGENT_CONTROL_TOOL_NAMES,
  agentControlToolDefinitions,
  agentControlToolSchemas,
  controlRequestKey,
  handleAgentControlToolCall,
  INTERNAL_AGENT_CONTROL_TOOL_NAMES,
  isAgentControlToolName,
  registerSignedDirectControlOwner,
  resolveControlRequestContext,
  type AgentControlToolContext,
  withDefaultOwnerGuard,
  withMergedOwnerGuard,
} from "../src/runtime/control-tools.js";
import { agentControlCapabilityManifest, agentControlInputSchema } from "../src/runtime/control-tool-manifest.js";
import { toolNamesForAdapter } from "../src/runtime/omi-tool-manifest.js";
import { baseRunInput, createKernelHarness, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];
const servers: Array<{ server: Server; sockPath: string }> = [];

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
        selectedEvents: [{
          eventId: "event-2",
          type: "conversation",
          summary: "Deadline moved to Friday",
          occurredAtMs: 10,
          evidenceRefs: [
            { kind: "conversation", id: "conversation-1", scope: "canonical" },
            { kind: "chat_message", id: "local-turn-1", scope: "device_local", device_id: "test-device" },
          ],
          sensitivityTier: "low",
        }],
        artifactHeads: [],
        provenance: { snapshotVersion: "workstream:2", fetchedAtMs: 20, source: "canonical_backend" },
      },
      artifacts: [{
        logicalKey: "launch-email",
        evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }],
        kind: "markdown",
        role: "result",
        uri: "file:///tmp/launch-email.md",
        contentHash: "sha256:1234567890abcdef",
        sourceArtifactId: "source-artifact-1",
      }, {
        logicalKey: "provider-reference",
        evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }],
        kind: "provider_reference",
        role: "result",
        uri: "adapter://provider/reference-1",
        sourceArtifactId: "source-artifact-local-only",
      }],
    };
    const first = parseToolResult(await handleAgentControlToolCall(context, "persist_workstream_continuity", input));
    const firstDeliveries = first.deliveries as Array<{ deliveryId: string; payload: { kind: string } }>;
    const artifactDelivery = firstDeliveries.find((delivery) => delivery.payload.kind === "artifact_descriptor")!;
    const delivered = parseToolResult(await handleAgentControlToolCall(
      context,
      "resolve_workstream_continuity_delivery",
      { deliveryId: artifactDelivery.deliveryId, status: "delivered", receipt: { artifact_id: "backend-v1" } },
    ));
    const replay = parseToolResult(await handleAgentControlToolCall(context, "persist_workstream_continuity", input));
    const projected = parseToolResult(await handleAgentControlToolCall(context, "project_workstream_continuity", {
      workstreamId: "workstream-1",
    }));
    expect(first.ok).toBe(true);
    expect(firstDeliveries.map((delivery) => delivery.payload.kind).sort()).toEqual([
      "artifact_descriptor",
      "continuation_checkpoint",
    ]);
    expect((delivered.delivery as { status: string }).status).toBe("delivered");
    expect((first.artifactVersions as Array<{ version: number }>)[0]?.version).toBe(1);
    expect((replay.artifactVersions as Array<{ version: number }>)[0]?.version).toBe(1);
    expect(((projected.projection as { artifactVersions: unknown[] }).artifactVersions).length).toBe(2);
    expect((replay.deliveries as Array<{ deliveryId: string }>).some(
      (delivery) => delivery.deliveryId === artifactDelivery.deliveryId,
    )).toBe(false);
    expect((first.checkpoint as { lastEventSequence: number }).lastEventSequence).toBe(2);
    expect((first.checkpoint as { evidenceRefs: Array<{ scope: string }> }).evidenceRefs).toEqual([
      expect.objectContaining({ scope: "canonical" }),
    ]);
    expect(store.getRow("SELECT COUNT(*) AS count FROM workstream_artifact_versions").count).toBe(2);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM desktop_artifact_deliveries WHERE delivery_status = 'cancelled'",
    ).count).toBe(1);
  });

  it("persists prepared artifacts only with a scoped live grant and without replacing context", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const context = ownerContext(kernel);
    const prepared = parseToolResult(await handleAgentControlToolCall(context, "prepare_workstream_continuity", {
      workstreamId: "workstream-prepared",
      taskIds: [],
    }));
    const sessionId = (prepared.session as { agentSessionId: string }).agentSessionId;
    const capability = "desktop.workstream.artifact.prepare";
    const operation = "prepare_artifact";
    const resourceRef = "workstream:workstream-prepared";
    const expiresAtMs = Date.now() + 60_000;
    const created = parseToolResult(await handleAgentControlToolCall(context, "create_desktop_dispatch", {
      kind: "approval",
      priority: 1,
      title: "Prepare artifact",
      decisionPrompt: "Allow this prepared artifact?",
      sourceSessionId: sessionId,
      capability,
      operation,
      resourceRef,
      expiresAtMs,
    }));
    const dispatchId = (created.dispatch as { dispatchId: string }).dispatchId;
    const resolved = parseToolResult(await handleAgentControlToolCall(
      trustedOwnerContext(kernel),
      "resolve_desktop_dispatch",
      {
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
      },
    ));
    const grantId = (resolved.grant as { grantId: string }).grantId;
    const input = {
      workstreamId: "workstream-prepared",
      logicalKey: "investor-email",
      evidenceRefs: [{
        kind: "local_screen",
        id: "sha256:evidence",
        scope: "device_local",
        device_id: "device-1",
      }],
      kind: "email_draft",
      uri: "file:///tmp/investor-email.artifact",
      contentHash: "sha256:1234567890abcdef",
      sourceArtifactId: "prepared-source-1",
      grantId,
    };
    const persisted = parseToolResult(
      await handleAgentControlToolCall(context, "persist_prepared_workstream_artifact", input),
    );
    const rejected = parseToolResult(await handleAgentControlToolCall(
      context,
      "persist_prepared_workstream_artifact",
      { ...input, sourceArtifactId: "prepared-source-2", grantId: "grant_missing" },
    ));

    expect(persisted.ok, JSON.stringify(persisted)).toBe(true);
    expect((persisted.artifactVersion as { version: number }).version).toBe(1);
    expect((persisted.deliveries as unknown[])).toHaveLength(1);
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
    expect(agentControlToolSchemas.spawn_background_agent.safeParse({
      prompt: "",
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
    const created = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "create_desktop_dispatch", {
      kind: "approval",
      priority: 100,
      title: "Approve screenshot",
      decisionPrompt: "Allow screenshot image bytes?",
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      capability: "desktop.context.screenshot_image",
      operation: "get_screenshot",
      resourceRef: "screenshot:42",
    }));

    const resolved = parseToolResult(await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
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
    }));

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
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(1);
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

    const resolved = parseToolResult(await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
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
    }));

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(String(resolved.error.message)).toContain("capability must match");
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(0);
    expect(store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [dispatch.dispatchId]).status).toBe("pending");
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

    const resolved = parseToolResult(await handleAgentControlToolCall(trustedOwnerContext(kernel), "resolve_desktop_dispatch", {
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
    }));

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(String(resolved.error.message)).toContain("Only approval dispatches");
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(0);
    expect(store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [dispatch.dispatchId]).status).toBe("pending");
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

    const resolved = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "resolve_desktop_dispatch", {
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
    }));

    expect(resolved).toMatchObject({
      ok: false,
      error: { code: "policy_denied" },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants WHERE session_id = ?", [session.sessionId]).count).toBe(0);
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

    const unapproved = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "build_desktop_context_packet", {
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
    }));
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

    const approved = parseToolResult(await handleAgentControlToolCall(ownerContext(kernel), "build_desktop_context_packet", {
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
    }));

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

  it("resolves control owners from active request context before mutable global fallback", () => {
    const ownerByRequest = new Map([
      ["request-owner-a", "owner-a"],
      ["request-owner-b", "owner-b"],
    ]);
    const ownerByRun = new Map([["run-owner-c", "owner-c"]]);
    const ownerByAttempt = new Map([["attempt-owner-d", "owner-d"]]);
    let mutableFallbackOwner = "owner-a";

    mutableFallbackOwner = "owner-b";

    expect(
      activeControlToolOwnerId({
        requestKey: "request-owner-a",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-a");
    expect(
      activeControlToolOwnerId({
        requestKey: "request-owner-b",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-b");
    expect(
      activeControlToolOwnerId({
        requestKey: "request-missing",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
        allowFallbackOwner: true,
      }),
    ).toBe("owner-b");
    expect(() =>
      activeControlToolOwnerId({
        requestKey: "request-missing",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toThrow("Owner-scoped control tools require active request, run, or attempt context");
    expect(
      activeControlToolOwnerId({
        requestKey: "request-missing",
        runId: "run-owner-c",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        ownerIdForRun: (runId) => ownerByRun.get(runId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-c");
    expect(
      activeControlToolOwnerId({
        requestKey: "request-missing",
        runId: "run-owner-c",
        attemptId: "attempt-owner-d",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        ownerIdForRun: (runId) => ownerByRun.get(runId),
        ownerIdForAttempt: (attemptId) => ownerByAttempt.get(attemptId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-d");
  });

  it("treats direct control envelope owner as a guard against active owner", () => {
    const resolved = resolveControlRequestContext({
      ownerGuard: " owner-active ",
      activeOwnerId: "owner-active",
      requestId: "request-a",
      clientId: "client-a",
    });

    expect(resolved).toEqual({
      requestKey: JSON.stringify(["client-a", "request-a"]),
      activeOwnerId: "owner-active",
      ownerGuard: "owner-active",
    });
    expect(() =>
      resolveControlRequestContext({
        ownerGuard: "owner-from-envelope",
        activeOwnerId: "fallback-owner",
        requestId: "request-a",
        clientId: "client-a",
      }),
    ).toThrow("ownerId does not match active control owner");
    expect(controlRequestKey({ requestId: "request:a", clientId: "client" })).toBe(JSON.stringify(["client", "request:a"]));
    expect(controlRequestKey({ requestId: "request", clientId: "client:a" })).toBe(JSON.stringify(["client:a", "request"]));
    expect(controlRequestKey({ requestId: "request", clientId: "client" })).toBe(
      JSON.stringify(["client", "request"]),
    );
  });

  it("rejects direct control envelope owners before active owner context is cached", () => {
    expect(() =>
      resolveControlRequestContext({
        ownerGuard: "signed-in-owner",
        activeOwnerId: "desktop-local-user",
        requireActiveOwner: true,
        requireOwnerGuard: true,
        requestId: "cold-control-request",
        clientId: "swift-client",
      }),
    ).toThrow("missing active control owner");
  });

  it("rejects direct control context without active owner authority", () => {
    expect(() =>
      resolveControlRequestContext({
        requireActiveOwner: true,
        requestId: "cold-control-request",
        clientId: "swift-client",
      }),
    ).toThrow("missing active control owner");
  });

  it("registers signed direct control envelopes when no request owner is active", () => {
    const ownersByRequest = new Map<string, string>();
    const requestKey = controlRequestKey({ requestId: "realtime-request", clientId: "realtime-hub" });

    const inserted = registerSignedDirectControlOwner({
      requestKey,
      ownerGuard: " signed-in-owner ",
      ownerIdForRequest: (key) => ownersByRequest.get(key),
      registerOwner: (key, ownerId) => {
        ownersByRequest.set(key, ownerId);
        return true;
      },
    });

    expect(inserted).toBe(true);
    expect(requestKey ? ownersByRequest.get(requestKey) : undefined).toBe("signed-in-owner");
  });

  it("rejects cold direct control calls without active request context", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "signed-in-owner" });
    await kernel.executeRun({
      ...baseRunInput,
      ownerId: "desktop-local-user",
      externalRefId: "local-task",
      requestId: "local-run",
    });

    expect(() =>
      resolveControlRequestContext({
        ownerGuard: "signed-in-owner",
        requireActiveOwner: true,
        requireOwnerGuard: true,
        requestId: "cold-direct-request",
        clientId: "swift-client",
      }),
    ).toThrow("missing active control owner");
    store.close();
  });

  it("rejects blank direct control envelope owners before global fallback", () => {
    expect(() =>
      resolveControlRequestContext({
        ownerGuard: "   ",
        activeOwnerId: "fallback-owner",
        requestId: "request-a",
        clientId: "client-a",
      }),
    ).toThrow("ownerId cannot be empty");
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
    expect(withMergedOwnerGuard({ runId: "run-a", ownerId: " owner-envelope " }, "owner-envelope", "owner-active")).toEqual({
      runId: "run-a",
      ownerId: "owner-envelope",
    });
    expect(() =>
      withMergedOwnerGuard({ runId: "run-a", ownerId: "owner-active" }, "owner-envelope", "owner-active"),
    ).toThrow("Owner guards do not match");
  });

  it("keeps concurrent control tool calls scoped to their active request owners", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "owner-a", requestId: "run-owner-a" });
    await kernel.executeRun({
      ...baseRunInput,
      ownerId: "owner-b",
      externalRefId: "task-owner-b",
      requestId: "run-owner-b",
    });
    const ownerByRequest = new Map([
      ["request-owner-a", "owner-a"],
      ["request-owner-b", "owner-b"],
    ]);
    let mutableFallbackOwner = "owner-a";
    const contextForRequest = (requestId: string): AgentControlToolContext => ({
      kernel,
      getOwnerId: () =>
        activeControlToolOwnerId({
          requestKey: requestId,
          ownerIdForRequest: (id) => ownerByRequest.get(id),
          fallbackOwnerId: mutableFallbackOwner,
          allowFallbackOwner: true,
        }),
    });

    mutableFallbackOwner = "owner-b";
    const [ownerAResult, ownerBResult] = await Promise.all([
      handleAgentControlToolCall(contextForRequest("request-owner-a"), "list_agent_sessions", {}),
      handleAgentControlToolCall(contextForRequest("request-owner-b"), "list_agent_sessions", {}),
    ]);
    const ownerAListed = parseToolResult(ownerAResult);
    const ownerBListed = parseToolResult(ownerBResult);

    expect(ownerAListed.sessions).toHaveLength(1);
    expect(ownerAListed.sessions[0].session.ownerId).toBe("owner-a");
    expect(ownerBListed.sessions).toHaveLength(1);
    expect(ownerBListed.sessions[0].session.ownerId).toBe("owner-b");

    const guarded = parseToolResult(
      await handleAgentControlToolCall(contextForRequest("request-owner-a"), "list_agent_sessions", {
        ownerId: "owner-b",
      }),
    );
    expect(guarded).toMatchObject({
      ok: false,
      error: { code: "control_tool_failed" },
    });
    expect(guarded.error.message).toContain("does not match the active control owner");
    store.close();
  });

  it("rejects owner-scoped adapter-originated tools without active request, run, or attempt context", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    await kernel.executeRun({ ...baseRunInput, ownerId: "signed-in-owner" });
    const result = parseToolResult(
      await handleAgentControlToolCall(
        {
          kernel,
          getOwnerId: () =>
            activeControlToolOwnerId({
              requestKey: controlRequestKey({ requestId: "missing-request" }),
              ownerIdForRequest: () => undefined,
              fallbackOwnerId: "signed-in-owner",
            }),
        },
        "list_agent_sessions",
        {},
      ),
    );

    expect(result).toMatchObject({
      ok: false,
      error: {
        code: "control_tool_failed",
      },
    });
    expect(result.error.message).toContain("Owner-scoped control tools require active request, run, or attempt context");
    store.close();
  });

  it("rejects run inspection, cancellation, and artifact inspection outside the active owner", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const ownerRun = await kernel.executeRun({ ...baseRunInput, ownerId: "owner-from-context" });
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

    const events = kernel.getRun({ runId: result.run.runId, includeEvents: true }).events;
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
    expect(store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [artifact.artifactId]).lifecycle_state).toBe("opened");
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

    const context: AgentControlToolContext = { kernel, getOwnerId: () => "owner" };
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

    expect(store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [ownerArtifact.artifactId]).lifecycle_state).toBe("retained");
    expect(store.getRow("SELECT lifecycle_state FROM artifacts WHERE artifact_id = ?", [otherArtifact.artifactId]).lifecycle_state).toBe("retained");
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
    adapter.nextArtifacts = [{
      kind: "markdown",
      role: "result",
      uri: "adapter://fake/follow-up.md",
      displayName: "follow-up.md",
      mimeType: "text/markdown",
      contentHash: "sha256:abc",
      sizeBytes: 12,
      metadata: { adapterArtifactId: "follow-up" },
    }];

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
    expect(adapter.executed[1].metadata).not.toMatchObject({ disableSwiftBackedTools: true });

    const listed = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "list_agent_sessions", { ownerId: "owner" }),
    );
    expect(listed.sessions).toHaveLength(1);
    expect([first.run.runId, sent.run.runId]).toContain(listed.sessions[0].latestRun.runId);
    store.close();
  });

  it("defaults send_agent_message to the active control context owner", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const first = await kernel.executeRun({ ...baseRunInput, ownerId: "owner-from-context" });

    const sent = parseToolResult(
      await handleAgentControlToolCall(
        { kernel, getOwnerId: () => "owner-from-context" },
        "send_agent_message",
        {
          sessionId: first.session.sessionId,
          prompt: "follow up",
          requestId: "request-context-owner",
        },
      ),
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

  it("lets invalid adapter ids reach kernel adapter-not-registered handling", async () => {
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
      ok: true,
      terminalStatus: "failed",
      run: {
        status: "failed",
        errorCode: "adapter_not_registered",
      },
    });
    expect(failed.run.errorMessage).toContain("Adapter not registered: missing-adapter");
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
      text: "done",      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
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
        externalRefKind: "pill",
        externalRefId: "pill-1",
        requestId: "background-1",
        clientId: "background-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
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
      status: "queued",
    });
    store.close();
  });

  it("inherits the managed adapter for background agents instead of local ACP", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const spawned = parseToolResult(
      await handleAgentControlToolCall(
        { ...ownerContext(kernel), defaultAdapterId: "pi-mono" },
        "spawn_agent",
        {
          objective: "research managed routing",
          visible: true,
          requestId: "spawn-managed-routing-1",
          clientId: "spawn-client",
          ownerId: "owner",
        },
      ),
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
      await handleAgentControlToolCall(
        { ...ownerContext(kernel), defaultAdapterId: "pi-mono" },
        "spawn_agent",
        {
          objective: "do not use local credentials",
          visible: true,
          adapterId: "acp",
          requestId: "spawn-managed-local-acp-1",
          clientId: "spawn-client",
          ownerId: "owner",
        },
      ),
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

  it("keeps every managed control entry point on Omi cloud routing", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const context = { ...ownerContext(kernel), defaultAdapterId: "pi-mono" };
    const parent = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });

    for (const provider of ["hermes", "openclaw"] as const) {
      const spawned = parseToolResult(
        await handleAgentControlToolCall(context, "spawn_agent", {
          objective: `do not route to ${provider}`,
          provider,
          requestId: `managed-provider-${provider}`,
          clientId: "managed-routing",
          ownerId: "owner",
        }),
      );
      expect(spawned).toMatchObject({
        ok: false,
        error: { code: "control_tool_failed", message: "Managed Omi agents can only use Omi cloud routing." },
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
        error: { code: "control_tool_failed", message: "Managed Omi agents can only use Omi cloud routing." },
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
        error: { code: "control_tool_failed", message: "Managed Omi agents can only use Omi cloud routing." },
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
        error: { code: "control_tool_failed", message: "Managed Omi agents can only use Omi cloud routing." },
      });
    }

    expect(store.allRows("SELECT * FROM runs")).toHaveLength(1);
    store.close();
  });

  it("prevents leaf background workers from spawning more agents", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const result = parseToolResult(
      await handleAgentControlToolCall(
        { ...ownerContext(kernel), defaultAdapterId: "pi-mono", canSpawnAgents: false },
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
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", { runId: parent.run.runId, ownerId: "owner" }),
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
        env: [{ name: "OMI_CONTEXT_FILE", value: expect.stringContaining("omi-tools-context") }],
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
    });
    expect(toolNamesForAdapter("omi-tools-stdio", { screenContext: true })).toEqual(
      expect.arrayContaining(["get_work_context", "request_permission", "check_permission_status", "capture_screen"]),
    );
    expect(adapter.opened.at(-1)?.mcpServers).toEqual([
      {
        name: "omi-tools",
        command: "node",
        args: ["omi-tools.js"],
        env: [{ name: "OMI_CONTEXT_FILE", value: expect.stringContaining("omi-tools-context") }],
      },
      {
        name: "playwright",
        command: "node",
        args: ["playwright.js"],
        env: [{ name: "OMI_CONTEXT_FILE", value: expect.stringContaining("omi-tools-context") }],
      },
    ]);
    expect(adapter.executed.at(-1)?.metadata).not.toMatchObject({ disableSwiftBackedTools: true });
    store.close();
  });

  it("routes delegated child runs through the resolved adapter override", async () => {
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

    expect(delegated.ok).toBe(true);
    expect(delegated.session.defaultAdapterId).toBe("openclaw");
    expect(delegated.run).toMatchObject({
      status: "failed",
      errorCode: "adapter_not_registered",
    });
    expect(delegated.run.errorMessage).toContain("Adapter not registered: openclaw");
    expect(buildMcpServers).toHaveBeenCalledWith("ask", undefined, undefined, {
      ownerId: "owner",
      requestId: "delegate-openclaw-1",
      clientId: "delegate-client",
      adapterId: "openclaw",
      protocolVersion: 2,
      includeSwiftBackedTools: true,
      screenContext: true,
    });
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
    expect(spawned.session.externalRefId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
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
    const { store, adapter, kernel } = createKernelHarness(
      newDatabasePath(),
      "acp",
      4,
      undefined,
      (adapterId) =>
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
    expect(store.allRows("SELECT attempt_no, retry_reason, status FROM run_attempts WHERE run_id = ? ORDER BY attempt_no", [
      spawned.run.runId,
    ])).toEqual([
      expect.objectContaining({ attempt_no: 1, retry_reason: null, status: "failed" }),
      expect.objectContaining({ attempt_no: 2, retry_reason: "recoverable_error", status: "succeeded" }),
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
    expect(spawned.run.status).toBe("queued");
    expect(buildMcpServers).toHaveBeenCalledWith("act", undefined, undefined, {
      ownerId: "owner",
      requestId: "delegate-spawn-1",
      clientId: "delegate-client",
      adapterId: "acp",
      protocolVersion: 2,
      surfaceKind: "delegated_agent",
      externalRefKind: undefined,
      externalRefId: undefined,
      includeSwiftBackedTools: true,
      screenContext: true,
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
      text: "spawn complete",      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await waitUntil(() => {
      const row = store.getRow("SELECT status FROM delegations WHERE delegation_id = ?", [spawned.delegation.delegationId]);
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
      const row = store.getRow("SELECT status FROM delegations WHERE delegation_id = ?", [spawned.delegation.delegationId]);
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

    const inspected = parseToolResult((await sendToolUse(sockPath, "get_agent_run", { runId, ownerId: "owner" })).result);
    expect(inspected.run.status).toBe("running");
    expect(inspected.attempts[0].attemptId).toBe(attemptId);

    const artifacts = parseToolResult((await sendToolUse(sockPath, "inspect_agent_artifacts", { runId, ownerId: "owner" })).result);
    expect(artifacts.artifacts[0]).toMatchObject({ artifactId: "art_relay", uri: "omi-artifact://art_relay" });

    const cancelled = parseToolResult((await sendToolUse(sockPath, "cancel_agent_run", { runId, ownerId: "owner" })).result);
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
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });
});

function parseToolResult(result: string): any {
  return JSON.parse(result);
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
            client.write(JSON.stringify({ type: "tool_result", callId: msg.callId, result }) + "\n");
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
