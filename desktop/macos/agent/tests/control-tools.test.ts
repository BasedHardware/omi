import { mkdtempSync, rmSync } from "node:fs";
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  agentControlToolDefinitions,
  handleAgentControlToolCall,
  isAgentControlToolName,
  type AgentControlToolContext,
} from "../src/runtime/control-tools.js";
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
      "send_agent_message",
      "delegate_agent",
    ]);
    for (const tool of agentControlToolDefinitions) {
      expect(isAgentControlToolName(tool.name)).toBe(true);
      expect(tool.inputSchema).toMatchObject({ type: "object" });
    }
  });

  it("lists sessions and inspects runs using canonical runtime ids", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);

    const list = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "list_agent_sessions", {
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
      await handleAgentControlToolCall({ kernel }, "get_agent_run", {
        runId: result.run.runId,
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

  it("returns canonical artifact references without reading artifact contents", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);
    store.execute(
      `INSERT INTO artifacts (
        artifact_id, session_id, run_id, attempt_id, kind, role, uri,
        display_name, mime_type, content_hash, size_bytes, metadata_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        "art_test",
        result.session.sessionId,
        result.run.runId,
        result.attempt.attemptId,
        "json",
        "result",
        "omi-artifact://art_test",
        "result.json",
        "application/json",
        "sha256:test",
        42,
        JSON.stringify({ source: "test" }),
        Date.now(),
      ],
    );

    const inspected = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "inspect_agent_artifacts", {
        runId: result.run.runId,
      }),
    );
    expect(inspected.artifacts).toEqual([
      expect.objectContaining({
        artifactId: "art_test",
        omiSessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "omi-artifact://art_test",
        metadata: { source: "test" },
      }),
    ]);
    store.close();
  });

  it("sends a follow-up message as a new run in an existing canonical session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const first = await kernel.executeRun(baseRunInput);

    const sent = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "send_agent_message", {
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

    const listed = parseToolResult(await handleAgentControlToolCall({ kernel }, "list_agent_sessions", { ownerId: "owner" }));
    expect(listed.sessions).toHaveLength(1);
    expect(listed.sessions[0].latestRun.runId).toBe(sent.run.runId);
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
      await handleAgentControlToolCall({ kernel }, "send_agent_message", {
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
      await handleAgentControlToolCall({ kernel }, "send_agent_message", {
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
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
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

    const parentInspect = parseToolResult(await handleAgentControlToolCall({ kernel }, "get_agent_run", { runId: parent.run.runId }));
    expect(parentInspect.parentDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    const childInspect = parseToolResult(await handleAgentControlToolCall({ kernel }, "get_agent_run", { runId: delegated.childRun.runId }));
    expect(childInspect.childDelegations[0].delegationId).toBe(delegated.delegation.delegationId);
    store.close();
  });

  it("delegates spawn mode and returns child handles before the child finishes", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const parent = await kernel.executeRun(baseRunInput);
    adapter.deferResult();

    const spawned = parseToolResult(
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
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

    const running = parseToolResult(await handleAgentControlToolCall({ kernel }, "get_agent_run", { runId: spawned.childRun.runId }));
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
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
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
      await handleAgentControlToolCall({ kernel }, "delegate_agent", {
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
    store.execute(
      `INSERT INTO artifacts (
        artifact_id, session_id, run_id, attempt_id, kind, role, uri,
        display_name, mime_type, content_hash, size_bytes, metadata_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        "art_relay",
        adapter.executed[0].sessionId,
        runId,
        attemptId,
        "log",
        "log",
        "omi-artifact://art_relay",
        "relay.log",
        "text/plain",
        null,
        9,
        "{}",
        Date.now(),
      ],
    );
    const sockPath = await startControlRelay({ kernel });

    const listed = parseToolResult((await sendToolUse(sockPath, "list_agent_sessions", { ownerId: "owner" })).result);
    expect(listed.sessions[0].activeRun.runId).toBe(runId);

    const inspected = parseToolResult((await sendToolUse(sockPath, "get_agent_run", { runId })).result);
    expect(inspected.run.status).toBe("running");
    expect(inspected.attempts[0].attemptId).toBe(attemptId);

    const artifacts = parseToolResult((await sendToolUse(sockPath, "inspect_agent_artifacts", { runId })).result);
    expect(artifacts.artifacts[0]).toMatchObject({ artifactId: "art_relay", uri: "omi-artifact://art_relay" });

    const cancelled = parseToolResult((await sendToolUse(sockPath, "cancel_agent_run", { runId })).result);
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
