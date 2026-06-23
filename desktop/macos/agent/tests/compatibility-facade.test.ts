import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { OutboundMessage, QueryMessage } from "../src/protocol.js";
import { JsonlCompatibilityFacade } from "../src/runtime/compatibility-facade.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("JsonlCompatibilityFacade", () => {
  it("maps v1 sessionKey to a legacy alias and returns adapter-native sessionId compatibility", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery(v1Query({ id: "request-1", sessionKey: "task-1" }));
    await facade.handleQuery(v1Query({ id: "request-2", sessionKey: "task-1" }));

    const sessions = store.allRows("SELECT session_id, legacy_session_key FROM sessions");
    expect(sessions).toHaveLength(1);
    expect(sessions[0].legacy_session_key).toBe("task-1");
    expect(sessions[0].session_id).not.toBe("native-1");
    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.resumed[0].adapterNativeSessionId).toBe("native-1");

    const results = sent.filter((message): message is Extract<OutboundMessage, { type: "result" }> => message.type === "result");
    expect(results).toHaveLength(2);
    expect(results[0].sessionId).toBe("native-1");
    expect(results[0].protocolVersion).toBeUndefined();
    store.close();
  });

  it("maps v1 resume only as a legacy adapter-native session id", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery(v1Query({ id: "request-1", sessionKey: "task-1", resume: "legacy-native" }));

    const session = store.getRow("SELECT session_id FROM sessions");
    expect(session.session_id).not.toBe("legacy-native");
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.resumed[0].adapterNativeSessionId).toBe("legacy-native");
    store.close();
  });

  it("adds v2 request, session, run, attempt, event, and adapter correlation to stream and result messages", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery({
      ...v1Query({ prompt: "hello v2" }),
      protocolVersion: 2,
      requestId: "request-v2",
      clientId: "client-v2",
      legacyClientScope: "task-chat",
      legacySessionKey: "task-2",
    });

    const textDelta = sent.find((message): message is Extract<OutboundMessage, { type: "text_delta" }> => message.type === "text_delta");
    const result = sent.find((message): message is Extract<OutboundMessage, { type: "result" }> => message.type === "result");
    expect(textDelta).toMatchObject({
      protocolVersion: 2,
      requestId: "request-v2",
      clientId: "client-v2",
      text: expect.stringContaining("delta-att_"),
      adapterSessionId: "native-1",
    });
    expect(textDelta?.sessionId).toMatch(/^ses_/);
    expect(textDelta?.runId).toMatch(/^run_/);
    expect(textDelta?.attemptId).toMatch(/^att_/);
    expect(textDelta?.eventId).toMatch(/^evt_/);
    expect(result).toMatchObject({
      protocolVersion: 2,
      requestId: "request-v2",
      clientId: "client-v2",
      terminalStatus: "succeeded",
      adapterSessionId: "native-1",
    });
    expect(result?.sessionId).toBe(textDelta?.sessionId);
    expect(result?.sessionId).not.toBe("native-1");
    store.close();
  });

  it("translates v2 interrupt to kernel cancellation with truthful ack", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v1Query({ prompt: "cancel me" }),
      protocolVersion: 2,
      requestId: "request-cancel",
      clientId: "client-cancel",
      legacySessionKey: "cancel-key",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      requestId: "request-cancel",
      clientId: "client-cancel",
    });

    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "request-cancel",
      clientId: "client-cancel",
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    });
    expect(cancelAck?.sessionId).toMatch(/^ses_/);
    expect(cancelAck?.runId).toMatch(/^run_/);
    expect(cancelAck?.attemptId).toMatch(/^att_/);

    adapter.resolveDeferred({
      text: "partial",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    await running;
    expect(sent.some((message) => message.type === "result" && message.terminalStatus === "cancelled")).toBe(true);
    store.close();
  });

  it("records warmup as a hint and invalidate_session invalidates bindings without deleting the canonical session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    facade.handleWarmup({
      type: "warmup",
      cwd: "/tmp/warm",
      sessions: [{ key: "main", model: "fake-model", systemPrompt: "warm system" }],
    });
    expect(store.allRows("SELECT * FROM sessions")).toHaveLength(0);

    await facade.handleQuery(v1Query({ id: "request-1", sessionKey: "main", cwd: undefined, systemPrompt: "" }));
    expect(adapter.opened[0]).toMatchObject({
      cwd: "/tmp/warm",
      model: "fake-model",
      systemPrompt: "warm system",
    });
    const sessionId = String(store.getRow("SELECT session_id FROM sessions").session_id);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("active");

    facade.handleInvalidateSession({ type: "invalidate_session", sessionKey: "main" });

    expect(store.getRow("SELECT session_id FROM sessions").session_id).toBe(sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("invalid");
    store.close();
  });

  it("uses pi-mono default model when configured as the default adapter", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: () => {},
      defaultAdapterId: "pi-mono",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery(v1Query({ id: "request-1", sessionKey: undefined, model: undefined }));

    expect(adapter.opened[0].model).toBe("omi-sonnet");
    expect(store.getRow("SELECT default_adapter_id FROM sessions").default_adapter_id).toBe("pi-mono");
    store.close();
  });

  it("suppresses pi-mono tool_use events while preserving correlated tool activity", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "pi-mono",
      defaultCwd: () => "/tmp/default",
      suppressToolUseEvents: true,
    });

    const running = facade.handleQuery({
      ...v1Query({ prompt: "use tools" }),
      protocolVersion: 2,
      requestId: "request-pi",
      clientId: "client-pi",
      legacySessionKey: "pi-key",
    });
    await waitUntil(() => adapter.executed.length === 1);
    const attemptId = adapter.executed[0].attemptId;
    adapter.emitLate(attemptId, {
      type: "tool_activity",
      name: "Read",
      status: "started",
      toolUseId: "tool-1",
    });
    adapter.emitLate(attemptId, {
      type: "tool_use",
      callId: "tool-1",
      name: "Read",
      input: { file: "README.md" },
    });
    adapter.resolveDeferred({
      text: "done",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await running;

    expect(sent.some((message) => message.type === "tool_use")).toBe(false);
    const activity = sent.find((message): message is Extract<OutboundMessage, { type: "tool_activity" }> => message.type === "tool_activity");
    expect(activity).toMatchObject({
      protocolVersion: 2,
      requestId: "request-pi",
      clientId: "client-pi",
      name: "Read",
      status: "started",
    });
    expect(activity?.runId).toMatch(/^run_/);
    store.close();
  });

  it("invokes recoverable auth flow and retries under the same run when binding open requires auth", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    let authFlowCalls = 0;
    const authError = Object.assign(new Error("auth required"), { code: -32000 });
    adapter.failNextOpenError = authError;
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
      isRecoverableError: (error) => error === authError,
      onRecoverableError: async () => {
        authFlowCalls += 1;
      },
      maxRecoverableRetries: 2,
    });

    await facade.handleQuery(v1Query({ id: "request-auth", sessionKey: "auth-key" }));

    expect(authFlowCalls).toBe(1);
    expect(sent.some((message) => message.type === "error")).toBe(false);
    expect(sent.some((message) => message.type === "result" && message.terminalStatus === "succeeded")).toBe(true);
    const runs = store.allRows("SELECT run_id, status FROM runs");
    expect(runs).toHaveLength(1);
    expect(runs[0].status).toBe("succeeded");
    expect(store.allRows("SELECT attempt_no, retry_reason, status FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "failed" }),
      expect.objectContaining({ attempt_no: 2, retry_reason: "recoverable_error", status: "succeeded" }),
    ]);
    store.close();
  });

  it("invokes recoverable auth flow and retries when execution requires auth", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    let authFlowCalls = 0;
    const authError = Object.assign(new Error("auth required during prompt"), { code: -32000 });
    adapter.failNextExecutionError = authError;
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
      isRecoverableError: (error) => error === authError,
      onRecoverableError: async () => {
        authFlowCalls += 1;
      },
      maxRecoverableRetries: 2,
    });

    await facade.handleQuery(v1Query({ id: "request-auth-exec", sessionKey: "auth-exec-key" }));

    expect(authFlowCalls).toBe(1);
    const runIds = new Set(store.allRows("SELECT run_id FROM run_attempts").map((row) => row.run_id));
    expect(runIds.size).toBe(1);
    expect(adapter.executed).toHaveLength(2);
    expect(store.allRows("SELECT attempt_no, retry_reason, status FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "failed" }),
      expect.objectContaining({ attempt_no: 2, retry_reason: "recoverable_error", status: "succeeded" }),
    ]);
    store.close();
  });

  it("fails terminally when recoverable error handling fails", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    const authError = Object.assign(new Error("auth required"), { code: -32000 });
    adapter.failNextOpenError = authError;
    const facade = new JsonlCompatibilityFacade({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
      isRecoverableError: (error) => error === authError,
      onRecoverableError: async () => {
        throw new Error("oauth failed");
      },
      maxRecoverableRetries: 2,
    });

    await facade.handleQuery(v1Query({ id: "request-auth-fail", sessionKey: "auth-fail-key" }));

    expect(sent.some((message) => message.type === "error")).toBe(true);
    expect(store.getRow("SELECT status FROM runs").status).toBe("failed");
    expect(store.getRow("SELECT status FROM run_attempts").status).toBe("failed");
    expect(store.allRows("SELECT * FROM run_attempts WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')")).toHaveLength(0);
    store.close();
  });
});

function v1Query(overrides: Partial<QueryMessage> = {}): QueryMessage {
  return {
    type: "query",
    id: "request",
    prompt: "hello",
    systemPrompt: "system",
    cwd: "/tmp/work",
    mode: "act",
    ...overrides,
  };
}

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-facade-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
