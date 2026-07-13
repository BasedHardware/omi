import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, waitUntil } from "./kernel-fakes.js";
import { OmiArtifactStorage } from "../src/runtime/artifact-storage.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("AgentRuntimeKernel run and attempt lifecycle", () => {
  it("creates one run per accepted query and one attempt per adapter execution", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    const first = await kernel.executeRun(baseRunInput);
    const second = await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-2",
      prompt: "follow up",
    });

    expect(first.session.sessionId).toBe(second.session.sessionId);
    expect(first.run.runId).not.toBe(second.run.runId);
    expect(adapter.executed).toHaveLength(2);
    expect(store.allRows("SELECT run_id, status FROM runs ORDER BY created_at_ms")).toHaveLength(2);
    expect(store.allRows("SELECT attempt_id, run_id, attempt_no, status FROM run_attempts ORDER BY created_at_ms, attempt_id")).toEqual([
      expect.objectContaining({ run_id: first.run.runId, attempt_no: 1, status: "succeeded" }),
      expect.objectContaining({ run_id: second.run.runId, attempt_no: 1, status: "succeeded" }),
    ]);
    expect(store.allRows("SELECT * FROM run_attempts WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')")).toHaveLength(0);
    store.close();
  });

  it("keeps the session binding pinned when a legacy follow-up supplies a different cwd", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({ ...baseRunInput, cwd: "/tmp/project-a" });
    await kernel.executeRun({ ...baseRunInput, requestId: "request-cwd-b", cwd: "/tmp/project-b" });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, cwd FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toEqual([
      expect.objectContaining({ binding_generation: 1, status: "active", cwd: "/tmp/project-a" }),
    ]);
    store.close();
  });

  it("ignores legacy per-query system prompt changes and reuses the kernel policy binding", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({ ...baseRunInput, systemPrompt: "prompt-a" });
    await kernel.executeRun({ ...baseRunInput, requestId: "request-system-prompt-b", systemPrompt: "prompt-b" });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, system_prompt_hash FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toEqual([expect.objectContaining({ binding_generation: 1, status: "active" })]);
    expect(adapter.opened[0].systemPrompt).toContain("desktop kernel is the authority");
    store.close();
  });

  it("reuses an active binding when only request-scoped MCP env changes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({
      ...baseRunInput,
      mcpServers: [
        {
          name: "omi-tools",
          command: "node",
          args: ["tools.js"],
          env: [
            { name: "OMI_REQUEST_ID", value: "request-1" },
            { name: "OMI_CLIENT_ID", value: "client-a" },
            { name: "OMI_CONTEXT_FILE", value: "/tmp/stale-request-path-a.json" },
            { name: "OMI_QUERY_MODE", value: "act" },
          ],
        },
      ],
    });
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-2",
      clientId: "client-b",
      mcpServers: [
        {
          command: "node",
          name: "omi-tools",
          env: [
            { value: "request-2", name: "OMI_REQUEST_ID" },
            { value: "client-b", name: "OMI_CLIENT_ID" },
            { value: "canonical-session-1", name: "OMI_SESSION_ID" },
            { value: "/tmp/omi-tools-999.sock", name: "OMI_BRIDGE_PIPE" },
            { value: "/tmp/stale-request-path-b.json", name: "OMI_CONTEXT_FILE" },
            { value: "act", name: "OMI_QUERY_MODE" },
          ],
          args: ["tools.js"],
        },
      ],
    });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, metadata_json FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toHaveLength(1);
    expect(bindings[0]).toMatchObject({ binding_generation: 1, status: "active" });
    const openedContextFile = mcpEnvValue(adapter.opened[0].mcpServers, "OMI_CONTEXT_FILE");
    const resumedContextFile = mcpEnvValue(adapter.resumed[0].mcpServers, "OMI_CONTEXT_FILE");
    expect(openedContextFile).toBeTruthy();
    expect(resumedContextFile).toBe(openedContextFile);
    expect(openedContextFile).not.toContain("stale-request-path");
    expect(JSON.parse(readFileSync(openedContextFile!, "utf8"))).toEqual({
      capabilityRef: adapter.executed[1].toolCapabilityRef,
    });
    store.close();
  });

  it("preserves legacy active bindings without MCP metadata hashes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({
      ...baseRunInput,
      mcpServers: [{ name: "omi-tools", command: "node", args: ["tools.js"] }],
    });
    store.execute("UPDATE adapter_bindings SET metadata_json = '{}' WHERE binding_generation = 1", []);
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-legacy-binding",
      mcpServers: [{ name: "omi-tools", command: "node", args: ["tools.js"] }],
    });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, metadata_json FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toHaveLength(1);
    expect(bindings[0]).toMatchObject({ binding_generation: 1, status: "active" });
    expect(JSON.parse(String(bindings[0].metadata_json)).mcpServersHash).toBeDefined();
    store.close();
  });

  it("preserves legacy active bindings without system prompt hashes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun(baseRunInput);
    store.execute("UPDATE adapter_bindings SET system_prompt_hash = NULL WHERE binding_generation = 1", []);
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-legacy-system-prompt",
      systemPrompt: "post-upgrade prompt",
    });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, system_prompt_hash FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toHaveLength(1);
    expect(bindings[0]).toMatchObject({ binding_generation: 1, status: "active" });
    expect(bindings[0].system_prompt_hash).not.toBeNull();
    store.close();
  });

  it("replaces an active binding when stable MCP server configuration changes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({
      ...baseRunInput,
      mcpServers: [{ name: "omi-tools", command: "node", args: ["tools-a.js"] }],
    });
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-mcp-b",
      mcpServers: [{ name: "omi-tools", command: "node", args: ["tools-b.js"] }],
    });

    expect(adapter.opened).toHaveLength(2);
    expect(adapter.resumed).toHaveLength(0);
    const bindings = store.allRows("SELECT binding_generation, status, metadata_json FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings[0]).toMatchObject({ binding_generation: 1, status: "stale" });
    expect(bindings[1]).toMatchObject({ binding_generation: 2, status: "active" });
    expect(JSON.parse(bindings[0].metadata_json).mcpServersHash).not.toBe(JSON.parse(bindings[1].metadata_json).mcpServersHash);
    store.close();
  });

  it("preserves binding when adapter strips MCP servers and only query-mode env changes", async () => {
    // Regression: OpenClaw (sessionMcpServersMode: "empty") always passes []
    // to its session, so switching Ask/Act must not invalidate the binding.
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.effectiveMcpServersOverride = [];

    await kernel.executeRun({
      ...baseRunInput,
      mcpServers: [
        {
          name: "omi-tools",
          command: "node",
          args: ["tools.js"],
          env: [{ name: "OMI_QUERY_MODE", value: "ask" }],
        },
      ],
    });
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-mode-switch",
      mcpServers: [
        {
          name: "omi-tools",
          command: "node",
          args: ["tools.js"],
          env: [{ name: "OMI_QUERY_MODE", value: "act" }],
        },
      ],
    });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    const bindings = store.allRows("SELECT binding_generation, status, metadata_json FROM adapter_bindings ORDER BY binding_generation");
    expect(bindings).toHaveLength(1);
    expect(bindings[0]).toMatchObject({ binding_generation: 1, status: "active" });
    store.close();
  });

  it("does not allow another non-terminal attempt for the same run", () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "fake",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "ask",
    });
    store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "worker",
    });

    expect(() => (kernel as any).createAttempt({
      runId: run.runId,
      attemptNo: 2,
      adapterId: "fake",
      retryReason: null,
      resumeFromAttemptId: null,
    })).toThrow(/already has active attempt/);
    store.close();
  });

  it("creates separate sessions for distinct external refs", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const first = await kernel.executeRun({
      ...baseRunInput,
      requestId: "chat-1",
      externalRefKind: "chat",
      externalRefId: "backend-chat-1",
    });
    const second = await kernel.executeRun({
      ...baseRunInput,
      requestId: "chat-2",
      externalRefKind: "chat",
      externalRefId: "backend-chat-2",
    });

    expect(second.session.sessionId).not.toBe(first.session.sessionId);
    expect(store.allRows("SELECT session_id FROM sessions ORDER BY created_at_ms")).toHaveLength(2);
    store.close();
  });

  it("persists adapter-emitted artifacts under canonical run and attempt ids", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.nextArtifacts = [{
      kind: "markdown",
      role: "result",
      uri: "adapter://fake/native-report",
      displayName: "report.md",
      mimeType: "text/markdown",
      contentHash: "sha256:def",
      sizeBytes: 42,
      metadata: { adapterArtifactId: "native-report" },
    }];

    const result = await kernel.executeRun(baseRunInput);
    const artifacts = kernel.inspectArtifacts({ runId: result.run.runId });

    expect(artifacts).toEqual([
      expect.objectContaining({
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "adapter://fake/native-report",
        role: "result",
      }),
    ]);
    expect(JSON.parse(artifacts[0].metadataJson)).toEqual({ adapterArtifactId: "native-report" });
    expect(store.allRows("SELECT type FROM events WHERE type = 'artifact.created'")).toHaveLength(1);
    store.close();
  });

  it("uses a managed run directory and discovers files written there as artifacts", async () => {
    const artifactRoot = mkdtempTracked("omi-agent-artifacts-");
    const artifactStorage = new OmiArtifactStorage({ rootDir: artifactRoot });
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 4, artifactStorage);
    adapter.writeFileOnExecute = { name: "omi-artifact-smoke.txt", contents: "hello from smoke test" };

    const result = await kernel.executeRun({ ...baseRunInput, cwd: artifactRoot });
    const artifacts = kernel.inspectArtifacts({ runId: result.run.runId });

    expect(adapter.opened[0].cwd).toContain(result.run.runId);
    expect(adapter.executed[0].binding.cwd).toBe(adapter.opened[0].cwd);
    expect(artifacts).toEqual([
      expect.objectContaining({
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: expect.stringContaining("omi-artifact-smoke.txt"),
        displayName: "omi-artifact-smoke.txt",
        role: "result",
        mimeType: "text/plain",
        sizeBytes: 21,
      }),
    ]);
    expect(readFileSync(new URL(artifacts[0].uri), "utf8")).toBe("hello from smoke test");
    expect(JSON.parse(artifacts[0].metadataJson)).toMatchObject({
      omiManaged: true,
      discoveredFromRunDirectory: true,
    });
    store.close();
  });

  it("stales all active process-local bindings for an adapter across owners and surfaces", () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const firstSession = store.insertSession({
      ownerId: "owner-a",
      surfaceKind: "legacy_jsonl",
      defaultAdapterId: "pi-mono",
    });
    const secondSession = store.insertSession({
      ownerId: "owner-b",
      surfaceKind: "delegated_agent",
      defaultAdapterId: "pi-mono",
    });
    const acpSession = store.insertSession({
      ownerId: "owner-a",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const firstPiBinding = store.insertAdapterBinding({
      sessionId: firstSession.sessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterNativeSessionId: "pi-native-a",
      resumeFidelity: "none",
      status: "active",
    });
    const secondPiBinding = store.insertAdapterBinding({
      sessionId: secondSession.sessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterNativeSessionId: "pi-native-b",
      resumeFidelity: "none",
      status: "active",
    });
    const nativeAcpBinding = store.insertAdapterBinding({
      sessionId: acpSession.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "acp-native",
      resumeFidelity: "native",
      status: "active",
    });

    const result = kernel.staleProcessLocalBindings({
      adapterId: "pi-mono",
      reason: "pi_mono_restart_test",
    });

    expect(new Set(result.staleBindingIds)).toEqual(new Set([firstPiBinding.bindingId, secondPiBinding.bindingId]));
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstPiBinding.bindingId]).status).toBe("stale");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [secondPiBinding.bindingId]).status).toBe("stale");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [nativeAcpBinding.bindingId]).status).toBe("active");
    expect(
      store
        .allRows("SELECT type, payload_json FROM events WHERE type = ? ORDER BY event_seq", ["binding.stale"])
        .map((row) => JSON.parse(String(row.payload_json))),
    ).toEqual(expect.arrayContaining([
      expect.objectContaining({ bindingId: firstPiBinding.bindingId, reason: "pi_mono_restart_test" }),
      expect.objectContaining({ bindingId: secondPiBinding.bindingId, reason: "pi_mono_restart_test" }),
    ]));
    store.close();
  });

  it("replaces a stale process-local pinned binding through the pinned worker", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id, binding_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? ORDER BY binding_generation DESC LIMIT 1",
      [first.session.sessionId, "pi-mono"],
    );
    const firstBindingId = firstBinding.binding_id;
    store.execute("UPDATE adapter_bindings SET status = 'stale', invalidated_at_ms = ?, updated_at_ms = ? WHERE binding_id = ?", [
      Date.now(),
      Date.now(),
      firstBindingId,
    ]);

    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-replace-stale",
    });

    expect(second.run.status).toBe("succeeded");
    const secondBinding = store.getRow(
      "SELECT binding_id, binding_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [second.session.sessionId, "pi-mono"],
    );
    expect(secondBinding.binding_id).not.toBe(firstBindingId);
    expect(secondBinding.binding_generation).toBe(firstBinding.binding_generation + 1);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBindingId]).status).toBe("stale");
    expect(JSON.parse(store.getRow("SELECT payload_json FROM events WHERE type = 'binding.replaced'").payload_json)).toMatchObject({
      bindingId: secondBinding.binding_id,
      replacesBindingId: firstBindingId,
    });
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });

  it("closes a stale binding when a restarted process reuses the native session id", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );
    store.execute("UPDATE adapter_bindings SET status = 'stale', invalidated_at_ms = ?, updated_at_ms = ? WHERE binding_id = ?", [
      Date.now(),
      Date.now(),
      firstBinding.binding_id,
    ]);
    (adapter as unknown as { nextNativeSession: number }).nextNativeSession = 1;

    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-reused-native-session",
    });

    expect(second.run.status).toBe("succeeded");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("closed");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND adapter_native_session_id = ? AND status = 'active'", ["pi-mono", "native-1"]).count).toBe(1);
    expect(JSON.parse(store.getRow("SELECT payload_json FROM events WHERE type = 'binding.stale' AND payload_json LIKE '%native_session_reused%'").payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      reason: "native_session_reused",
    });
    store.close();
  });

  it("reassigns an idle pinned pi-mono worker to a different session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );

    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-other-session",
      externalRefId: "task-other-session",
    });

    expect(second.run.status).toBe("succeeded");
    expect(second.session.sessionId).not.toBe(first.session.sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'", ["pi-mono"]).count).toBe(1);
    const staleEvent = store.getRow("SELECT session_id, run_id, attempt_id, payload_json FROM events WHERE type = 'binding.stale' ORDER BY event_seq DESC LIMIT 1");
    expect(staleEvent).toMatchObject({
      session_id: first.session.sessionId,
      run_id: null,
      attempt_id: null,
    });
    expect(JSON.parse(staleEvent.payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      reason: "pinned_worker_reassigned",
    });
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });

  it("marks an evicted pi-mono binding stale even when replacement open fails", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );
    adapter.failNextOpenError = new Error("replacement open failed");

    const failed = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-replacement-open-fails",
      externalRefId: "task-replacement-open-fails",
      maxAttempts: 1,
    });

    expect(failed.run.status).toBe("failed");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'", ["pi-mono"]).count).toBe(0);
    const staleEvent = store.getRow("SELECT payload_json FROM events WHERE type = 'binding.stale' ORDER BY event_seq DESC LIMIT 1");
    expect(JSON.parse(staleEvent.payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      reason: "pinned_worker_reassigned",
    });
    store.close();
  });

  it("queues a new pi-mono binding while the only pinned worker is busy", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });
    adapter.deferOnlyPromptIncludes = "hold worker";
    adapter.deferResult();

    const firstRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-hold-worker",
      prompt: "hold worker",
    });
    await waitUntil(() => adapter.executed.length === 1);
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'",
      ["pi-mono"],
    );

    const secondRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-queued-saturation",
      externalRefId: "task-queued-saturation",
      prompt: "queued after saturation",
    });
    await Promise.resolve();
    expect(adapter.opened).toHaveLength(1);

    adapter.resolveDeferred({
      terminalStatus: "succeeded",
      text: "first done",      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    const [first, second] = await Promise.all([firstRun, secondRun]);

    expect(first.run.status).toBe("succeeded");
    expect(second.run.status).toBe("succeeded");
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    const staleEvent = store.getRow("SELECT payload_json FROM events WHERE type = 'binding.stale' ORDER BY event_seq DESC LIMIT 1");
    expect(JSON.parse(staleEvent.payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      reason: "pinned_worker_reassigned",
    });
    store.close();
  });

  it("does not evict a newly opened pi-mono binding before its execution lease", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });
    adapter.deferOnlyPromptIncludes = "first concurrent";
    adapter.deferResult();

    const firstRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-first-concurrent",
      externalRefId: "task-first-concurrent",
      prompt: "first concurrent",
    });
    const secondRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-second-concurrent",
      externalRefId: "task-second-concurrent",
      prompt: "second concurrent",
    });

    await waitUntil(() => adapter.executed.length === 1);
    expect(adapter.opened).toHaveLength(1);
    adapter.resolveDeferred({
      terminalStatus: "succeeded",
      text: "first done",      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    const [first, second] = await Promise.all([firstRun, secondRun]);

    expect(first.run.status).toBe("succeeded");
    expect(second.run.status).toBe("succeeded");
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });

  it("does not evict an existing pi-mono binding before its execution lease", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const initial = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    adapter.deferOnlyPromptIncludes = "existing concurrent";
    adapter.deferResult();

    const existingBindingRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      sessionId: initial.session.sessionId,
      requestId: "request-existing-concurrent",
      externalRefId: "task-existing-concurrent",
      prompt: "existing concurrent",
    });
    const newBindingRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-new-during-existing",
      externalRefId: "task-new-during-existing",
      prompt: "new during existing",
    });

    await waitUntil(() => adapter.executed.length === 2);
    adapter.resolveDeferred({
      terminalStatus: "succeeded",
      text: "existing done",      adapterSessionId: adapter.executed[1].binding.adapterNativeSessionId,
    });
    const [existing, next] = await Promise.all([existingBindingRun, newBindingRun]);

    expect(existing.run.status).toBe("succeeded");
    expect(next.run.status).toBe("succeeded");
    expect(adapter.executed.map((execution) => execution.prompt[0]?.text)).toEqual([
      expect.stringContaining("hello"),
      expect.stringContaining("existing concurrent"),
      expect.stringContaining("new during existing"),
    ]);
    store.close();
  });

  it("does not leak pinned protection when existing pi-mono resume is stale", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "native",
      supportsNativeResume: true,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const initial = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    adapter.failNextResume = true;

    const retried = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      sessionId: initial.session.sessionId,
      requestId: "request-stale-resume-retry",
      externalRefId: "task-stale-resume-retry",
      prompt: "retry stale resume",
    });

    expect(retried.run.status).toBe("succeeded");
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed.map((execution) => execution.prompt[0]?.text)).toEqual([
      expect.stringContaining("hello"),
      expect.stringContaining("retry stale resume"),
    ]);
    store.close();
  });

  it("releases an idle stale pi-mono pin before replacing an invalid latest binding", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );
    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-invalid-target",
      externalRefId: "task-invalid-target",
    });
    const secondBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [second.session.sessionId, "pi-mono"],
    );
    store.execute("UPDATE adapter_bindings SET status = 'invalid', invalidated_at_ms = ?, updated_at_ms = ? WHERE binding_id = ?", [
      Date.now(),
      Date.now(),
      secondBinding.binding_id,
    ]);

    const third = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-invalid-target-retry",
      externalRefId: "task-invalid-target",
    });

    expect(third.run.status).toBe("succeeded");
    expect(third.session.sessionId).toBe(second.session.sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'", ["pi-mono"]).count).toBe(1);
    expect(adapter.opened).toHaveLength(3);
    expect(adapter.executed).toHaveLength(3);
    store.close();
  });

  it("reconciles active attempts as orphaned and keeps restart semantics adapter-scoped", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => now });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "task_chat",
      defaultAdapterId: "acp",
    });
    const nativeBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-session",
      adapterInstanceId: "worker-acp",
      resumeFidelity: "native",
      status: "active",
    });
    const processLocalBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterNativeSessionId: "pi-session",
      adapterInstanceId: "worker-pi",
      resumeFidelity: "none",
      status: "active",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "restart-active",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "worker-acp",
      bindingId: nativeBinding.bindingId,
    });
    store.close();

    now = 200;
    store = new SqliteAgentStore({ databasePath, nowMs: () => now });

    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [run.runId]).status).toBe("orphaned");
    expect(store.getRow("SELECT status, adapter_instance_id FROM run_attempts WHERE attempt_id = ?", [attempt.attemptId])).toMatchObject({
      status: "orphaned",
      adapter_instance_id: "",
    });
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [nativeBinding.bindingId]).status).toBe("active");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [processLocalBinding.bindingId]).status).toBe("stale");
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toEqual([
      "attempt.orphaned",
      "run.orphaned",
      "binding.stale",
    ]);
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempTracked("omi-agent-kernel-");
  return join(dir, "omi-agentd.sqlite3");
}

function mkdtempTracked(prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  createdDirs.push(dir);
  return dir;
}

function mcpEnvValue(mcpServers: Record<string, unknown>[] | undefined, name: string): string | undefined {
  const env = mcpServers?.[0]?.env;
  if (!Array.isArray(env)) return undefined;
  const entry = env.find((candidate) =>
    candidate &&
    typeof candidate === "object" &&
    !Array.isArray(candidate) &&
    (candidate as Record<string, unknown>).name === name
  );
  return entry && typeof entry === "object" && !Array.isArray(entry)
    ? String((entry as Record<string, unknown>).value ?? "")
    : undefined;
}
