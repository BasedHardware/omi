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
