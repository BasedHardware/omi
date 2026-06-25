import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
  activeControlToolOwnerId,
  agentControlToolDefinitions,
  handleAgentControlToolCall,
  isAgentControlToolName,
  type AgentControlToolContext,
} from "../src/runtime/control-tools.js";
import { agentControlCapabilityManifest, agentControlInputSchema } from "../src/runtime/control-tool-manifest.js";
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
  it("owns schemas and definitions for the first kernel-backed tools", () => {
    expect(agentControlToolDefinitions.map((tool) => tool.name)).toEqual([
      "list_agent_sessions",
      "get_agent_run",
      "cancel_agent_run",
      "inspect_agent_artifacts",
      "update_agent_artifact_lifecycle",
      "send_agent_message",
      "delegate_agent",
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

  it("documents delegate_agent as canonical delegation, not floating pill UI", () => {
    const delegateAgent = agentControlCapabilityManifest.find((tool) => tool.name === "delegate_agent");
    expect(delegateAgent?.description).toContain("canonical child handles");
    expect(delegateAgent?.description).toContain("does not create or manage floating pill UI");
    expect(delegateAgent?.promptSnippet).toContain("canonical Omi child agent");
    expect(delegateAgent?.promptGuidelines).toContain(
      "Use spawn_agent instead when the user wants a visible floating-bar background agent pill.",
    );
    expect(delegateAgent?.runtimePreconditions).toContain(
      "Spawn mode returns canonical child handles immediately and does not wait for completion; it does not create floating pill UI.",
    );
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
    expect(list.sessions[0].session.omiSessionId).toBe(result.session.sessionId);
    expect(list.sessions[0].latestRun.runId).toBe(result.run.runId);
    expect(list.sessions[0].adapterBindings[0]).toMatchObject({
      omiSessionId: result.session.sessionId,
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
      omiSessionId: result.session.sessionId,
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
    let mutableFallbackOwner = "owner-a";

    mutableFallbackOwner = "owner-b";

    expect(
      activeControlToolOwnerId({
        requestId: "request-owner-a",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-a");
    expect(
      activeControlToolOwnerId({
        requestId: "request-owner-b",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-b");
    expect(
      activeControlToolOwnerId({
        requestId: "request-missing",
        ownerIdForRequest: (requestId) => ownerByRequest.get(requestId),
        fallbackOwnerId: mutableFallbackOwner,
      }),
    ).toBe("owner-b");
  });

  it("source: direct control_tool ownerId is trimmed guard input, not session authority", () => {
    const indexSrc = readFileSync(fileURLToPath(new URL("../src/index.ts", import.meta.url)), "utf8");
    const controlToolCase = indexSrc.match(/case ["']control_tool["']:[\s\S]*?case ["']interrupt["']:/)?.[0] ?? "";

    expect(controlToolCase).toContain("const trimmedControlOwnerId = control.ownerId?.trim()");
    expect(controlToolCase).toContain("error: { code: \"invalid_owner_id\", message: \"ownerId cannot be empty\" }");
    expect(controlToolCase).toContain("const controlOwnerId = currentOwnerId");
    expect(controlToolCase).toContain("ownerId: trimmedControlOwnerId");
    expect(controlToolCase).toContain("activeControlToolOwnersByRequest.set(controlOwnerKey, controlOwnerId)");
    expect(controlToolCase).not.toContain("currentOwnerId = controlOwnerId");
    expect(controlToolCase).not.toContain("piMonoOwnerId = controlOwnerId");
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
          requestId,
          ownerIdForRequest: (id) => ownerByRequest.get(id),
          fallbackOwnerId: mutableFallbackOwner,
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
        omiSessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "omi-artifact://art_test",
        lifecycleState: "retained",
        lifecycleUpdatedAtMs: null,
        metadata: { source: "test" },
      }),
    ]);

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
        type: "artifact.dismissed",
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
        type: "artifact.opened",
        payload: {
          previousState: "dismissed",
          state: "opened",
        },
      },
    });

    const events = kernel
      .getRun({ runId: result.run.runId, includeEvents: true, eventLimit: 100 })
      .events.filter((event) => event.type.startsWith("artifact."));
    expect(events.map((event) => event.type)).toEqual(["artifact.created", "artifact.dismissed", "artifact.opened"]);
    expect(events[1].eventSeq).toBeLessThan(events[2].eventSeq);
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
      "Inspecting artifacts requires sessionId, runId, or attemptId",
    );
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
        omiSessionId: result.session.sessionId,
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
    expect(sent.session.omiSessionId).toBe(first.session.sessionId);
    expect(sent.run.omiSessionId).toBe(first.session.sessionId);
    expect(sent.run.runId).not.toBe(first.run.runId);
    expect(sent.run.status).toBe("succeeded");
    expect(adapter.executed).toHaveLength(2);
    expect(adapter.executed[1].sessionId).toBe(first.session.sessionId);

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
    expect(sent.run.omiSessionId).toBe(first.session.sessionId);
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
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
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
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
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
    expect(sent.run.omiSessionId).toBe(idleSession.session.sessionId);
    expect(adapter.executed).toHaveLength(3);

    adapter.resolveDeferred({
      text: "done",
      sessionId: adapter.executed[1].binding.adapterNativeSessionId,
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

  it("validates childSessionId before delegate_agent continue mode dispatch", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);

    const invalid = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
        mode: "continue",
        parentRunId: parent.run.runId,
        objective: "continue without a child id",
      }),
    );

    expect(invalid).toMatchObject({
      ok: false,
      error: {
        code: "invalid_tool_input",
      },
    });
    expect(invalid.error.message).toContain("childSessionId");
    store.close();
  });

  it("delegates call mode with distinct parent and child sessions linked by a delegation row", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);

    const delegated = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "delegate_agent", {
        mode: "call",
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
      childSessionId: delegated.childSession.omiSessionId,
      childRunId: delegated.childRun.runId,
      mode: "call",
      status: "succeeded",
      objective: "summarize the child task",
    });
    expect(delegated.childSession.omiSessionId).not.toBe(parent.session.sessionId);
    expect(delegated.childRun.parentRunId).toBe(parent.run.runId);
    expect(delegated.result).toMatchObject({
      summary: expect.stringContaining("done-"),
      verifiedEffects: [],
      openQuestions: [],
      usage: { inputTokens: 1, outputTokens: 2 },
    });

    const row = store.getRow("SELECT * FROM delegations WHERE delegation_id = ?", [delegated.delegation.delegationId]);
    expect(row.parent_run_id).toBe(parent.run.runId);
    expect(row.child_run_id).toBe(delegated.childRun.runId);

    const parentInspect = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", { runId: parent.run.runId, ownerId: "owner" }),
    );
    expect(parentInspect.parentDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    const childInspect = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: delegated.childRun.runId,
        ownerId: "owner",
      }),
    );
    expect(childInspect.childDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    store.close();
  });

  it("delegates spawn mode and returns child handles before the child finishes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    adapter.deferResult();

    const spawned = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "delegate_agent", {
        mode: "spawn",
        parentRunId: parent.run.runId,
        objective: "run in the background",
        requestId: "delegate-spawn-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(spawned.ok).toBe(true);
    expect(spawned.result).toBeNull();
    expect(spawned.childSession.omiSessionId).not.toBe(parent.session.sessionId);
    expect(spawned.childRun.status).toBe("queued");
    await waitUntil(() => adapter.executed.length === 2);

    const running = parseToolResult(
      await handleAgentControlToolCall(ownerContext(kernel), "get_agent_run", {
        runId: spawned.childRun.runId,
        ownerId: "owner",
      }),
    );
    expect(["starting", "running"]).toContain(running.run.status);
    expect(running.childDelegations[0].delegationId).toBe(spawned.delegation.delegationId);

    adapter.resolveDeferred({
      text: "spawn complete",
      sessionId: adapter.executed[1].binding.adapterNativeSessionId,
      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
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
      await handleAgentControlToolCall(ownerContext(kernel), "delegate_agent", {
        mode: "spawn",
        parentRunId: parent.run.runId,
        objective: "fail in the background",
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
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [spawned.childRun.runId]).status).toBe("failed");
    store.close();
  });

  it("delegates continue mode as another run in an existing child session", async () => {
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
      await handleAgentControlToolCall(ownerContext(kernel), "delegate_agent", {
        mode: "continue",
        parentRunId: parent.run.runId,
        childSessionId: firstChild.childSession.sessionId,
        objective: "continue the child",
        requestId: "delegate-continue-1",
        clientId: "delegate-client",
        ownerId: "owner",
      }),
    );

    expect(continued.ok).toBe(true);
    expect(continued.childSession.omiSessionId).toBe(firstChild.childSession.sessionId);
    expect(continued.childRun.runId).not.toBe(firstChild.childRun.runId);
    expect(continued.childRun.parentRunId).toBe(parent.run.runId);
    expect(continued.delegation).toMatchObject({
      parentRunId: parent.run.runId,
      childSessionId: firstChild.childSession.sessionId,
      childRunId: continued.childRun.runId,
      mode: "continue",
      status: "succeeded",
    });
    expect(adapter.resumed.at(-1)?.sessionId).toBe(firstChild.childSession.sessionId);
    store.close();
  });

  it("enforces simple delegation depth and budget constraints", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);

    const invalidBudget = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
        mode: "call",
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
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
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
