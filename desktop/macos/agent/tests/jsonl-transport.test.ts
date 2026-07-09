import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OutboundMessage, QueryMessage } from "../src/protocol.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import {
  JsonlTransport,
  selectAdapterScopedToolCallCorrelation,
  selectUnscopedToolCallCorrelation,
} from "../src/runtime/jsonl-transport.js";
import { AdapterRuntimeError } from "../src/runtime/failures.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { baseRunInput, createKernelHarness, FakeRuntimeAdapter, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("JsonlTransport", () => {
  it("rejects queries without requestId", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await expect(
      facade.handleQuery({
        ...v2Query({ prompt: "missing request id" }),
        requestId: "",
        clientId: "client-v2",
      }),
    ).rejects.toThrow("query requires requestId");
    store.close();
  });

  it("emits structured runtime failures from adapter errors", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    adapter.failNextExecutionError = new AdapterRuntimeError({
      code: "adapter_process_exited",
      source: "adapter_process",
      adapterId: "openclaw",
      provider: "openai",
      retryable: true,
      userMessage: "OpenClaw failed: OpenAI API error: upstream unavailable",
      technicalMessage: "OpenAI API error: upstream unavailable",
    });
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery({
      ...v2Query({ requestId: "request-failed", prompt: "fail" }),
      protocolVersion: 2,
      requestId: "request-failed",
      clientId: "client-failed",
      adapterId: "fake",
    });

    expect(sent).toContainEqual(expect.objectContaining({
      type: "error",
      message: "OpenClaw failed: OpenAI API error: upstream unavailable",
      failure: expect.objectContaining({
        code: "adapter_process_exited",
        adapterId: "openclaw",
        provider: "openai",
      }),
    }));
    store.close();
  });

  it("emits structured runtime failures when binding fails before execution", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    adapter.failNextOpenError = new AdapterRuntimeError({
      code: "adapter_config_invalid",
      source: "adapter_process",
      adapterId: "openclaw",
      retryable: false,
      userMessage:
        "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`.",
      technicalMessage: "OpenClaw config is invalid",
    });
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery({
      ...v2Query({ requestId: "request-binding-failed", prompt: "fail before execution" }),
      protocolVersion: 2,
      requestId: "request-binding-failed",
      clientId: "client-binding-failed",
      adapterId: "fake",
    });

    expect(adapter.executed).toHaveLength(0);
    expect(sent).toContainEqual(expect.objectContaining({
      type: "error",
      message:
        "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`.",
      failure: expect.objectContaining({
        code: "adapter_config_invalid",
        source: "adapter_process",
        adapterId: "openclaw",
        retryable: false,
      }),
    }));
    expect(JSON.parse(store.getRow("SELECT result_json FROM runs").result_json).failure).toMatchObject({
      code: "adapter_config_invalid",
      adapterId: "openclaw",
    });
    store.close();
  });

  it("selects the sole running request for unscoped tool-call correlation", () => {
    expect(
      selectUnscopedToolCallCorrelation([
        {
          protocolVersion: 2,
          requestId: "request-running",
          clientId: "client-running",
          sessionId: "session-running",
          runId: "run-running",
          attemptId: "attempt-running",
          isRunning: true,
        },
        {
          protocolVersion: 2,
          requestId: "request-queued",
          clientId: "client-queued",
        },
      ]),
    ).toMatchObject({
      protocolVersion: 2,
      requestId: "request-running",
      clientId: "client-running",
      sessionId: "session-running",
      runId: "run-running",
      attemptId: "attempt-running",
    });

    expect(
      selectUnscopedToolCallCorrelation([
        {
          protocolVersion: 2,
          requestId: "request-a",
          clientId: "client-a",
          runId: "run-a",
          attemptId: "attempt-a",
          isRunning: true,
        },
        {
          protocolVersion: 2,
          requestId: "request-b",
          clientId: "client-b",
          runId: "run-b",
          attemptId: "attempt-b",
          isRunning: true,
        },
      ]),
    ).toEqual({});
  });

  it("tracks externally-created control runs for Swift-backed tool routing", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      suppressToolUseEvents: false,
    });
    adapter.deferResult();

    facade.registerExternalRequestContext({
      protocolVersion: 2,
      requestId: "control-run-1",
      clientId: "control-client",
      ownerId: "owner",
      adapterId: "fake",
    });
    const running = kernel.executeRun({
      ...baseRunInput,
      requestId: "control-run-1",
      clientId: "control-client",
      prompt: "control-created child",
    });
    await waitUntil(() => adapter.executed.length === 1);
    const attemptId = adapter.executed[0].attemptId;

    adapter.emitLate(attemptId, {
      type: "tool_use",
      callId: "tool-control-1",
      name: "execute_sql",
      input: { query: "select 1" },
    });

    expect(sent.find((message) => message.type === "tool_use")).toMatchObject({
      type: "tool_use",
      requestId: "control-run-1",
      clientId: "control-client",
      runId: adapter.executed[0].runId,
      attemptId,
    });
    expect(facade.toolCallCorrelationForRequest("control-run-1", "control-client")).toMatchObject({
      requestId: "control-run-1",
      clientId: "control-client",
      attemptId,
    });
    expect(facade.toolCallCorrelationForRequest("control-run-1", "other-client")).toEqual({});

    adapter.resolveDeferred({
      text: "done",      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await running;
    expect(facade.toolCallCorrelationForRequest("control-run-1", "control-client")).toEqual({});
    store.close();
  });

  it("requires client id when resolving request-scoped v2 tool-call correlation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 2);
    adapter.deferResult();
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      suppressToolUseEvents: false,
    });

    facade.registerExternalRequestContext({
      protocolVersion: 2,
      requestId: "shared-control-run",
      clientId: "client-a",
      ownerId: "owner",
      adapterId: "fake",
    });
    facade.registerExternalRequestContext({
      protocolVersion: 2,
      requestId: "shared-control-run",
      clientId: "client-b",
      ownerId: "owner",
      adapterId: "fake",
    });
    const first = kernel.executeRun({
      ...baseRunInput,
      requestId: "shared-control-run",
      clientId: "client-a",
      prompt: "control-created child a",
    });
    const second = kernel.executeRun({
      ...baseRunInput,
      requestId: "shared-control-run",
      clientId: "client-b",
      prompt: "control-created child b",
      externalRefId: "task-b",
    });
    await waitUntil(() => adapter.executed.length === 2);

    expect(facade.toolCallCorrelationForRequest("shared-control-run", "client-a")).toMatchObject({
      requestId: "shared-control-run",
      clientId: "client-a",
      runId: adapter.executed[0].runId,
    });
    expect(facade.toolCallCorrelationForRequest("shared-control-run", "client-b")).toMatchObject({
      requestId: "shared-control-run",
      clientId: "client-b",
      runId: adapter.executed[1].runId,
    });
    expect(facade.unscopedToolCallCorrelation("shared-control-run")).toEqual({});

    adapter.resolveDeferred({
      text: "done",      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await Promise.all([first, second]);
    store.close();
  });

  it("routes simultaneous Hermes and OpenClaw relay contexts by clientId plus requestId", async () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const hermes = new FakeRuntimeAdapter("hermes");
    const openclaw = new FakeRuntimeAdapter("openclaw");
    hermes.deferResult();
    openclaw.deferResult();
    const registry = new AdapterRegistry();
    registry.register("hermes", () => hermes, 1);
    registry.register("openclaw", () => openclaw, 1);
    const kernel = new AgentRuntimeKernel({ store, registry });
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "hermes",
      suppressToolUseEvents: false,
    });

    facade.registerExternalRequestContext({
      protocolVersion: 2,
      requestId: "shared-request",
      clientId: "client-hermes",
      ownerId: "owner",
      adapterId: "hermes",
    });
    facade.registerExternalRequestContext({
      protocolVersion: 2,
      requestId: "shared-request",
      clientId: "client-openclaw",
      ownerId: "owner",
      adapterId: "openclaw",
    });

    const hermesRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "hermes",
      defaultAdapterId: "hermes",
      requestId: "shared-request",
      clientId: "client-hermes",
      externalRefId: "task-hermes",
    });
    const openclawRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "openclaw",
      defaultAdapterId: "openclaw",
      requestId: "shared-request",
      clientId: "client-openclaw",
      externalRefId: "task-openclaw",
    });
    await waitUntil(() => hermes.executed.length === 1 && openclaw.executed.length === 1);

    expect(facade.toolCallCorrelationForRequest("shared-request", "client-hermes")).toMatchObject({
      requestId: "shared-request",
      clientId: "client-hermes",
      runId: hermes.executed[0].runId,
      attemptId: hermes.executed[0].attemptId,
    });
    expect(facade.toolCallCorrelationForRequest("shared-request", "client-openclaw")).toMatchObject({
      requestId: "shared-request",
      clientId: "client-openclaw",
      runId: openclaw.executed[0].runId,
      attemptId: openclaw.executed[0].attemptId,
    });
    expect(facade.toolCallCorrelationForAdapter("hermes")).toMatchObject({
      clientId: "client-hermes",
      runId: hermes.executed[0].runId,
    });
    expect(facade.toolCallCorrelationForAdapter("openclaw")).toMatchObject({
      clientId: "client-openclaw",
      runId: openclaw.executed[0].runId,
    });
    expect(facade.unscopedToolCallCorrelation()).toEqual({});

    hermes.resolveDeferred({
      adapterSessionId: hermes.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    openclaw.resolveDeferred({
      adapterSessionId: openclaw.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    });
    await Promise.all([hermesRun, openclawRun]);
    store.close();
  });


  it("selects the sole running adapter context for adapter-scoped tool-call correlation", () => {
    expect(
      selectAdapterScopedToolCallCorrelation([
        {
          protocolVersion: 2,
          adapterId: "acp",
          requestId: "request-acp",
          clientId: "client-acp",
          runId: "run-acp",
          attemptId: "attempt-acp",
          isRunning: true,
        },
        {
          protocolVersion: 2,
          adapterId: "pi-mono",
          requestId: "request-pi",
          clientId: "client-pi",
          runId: "run-pi",
          attemptId: "attempt-pi",
          isRunning: true,
        },
      ], "pi-mono"),
    ).toMatchObject({
      protocolVersion: 2,
      requestId: "request-pi",
      clientId: "client-pi",
      runId: "run-pi",
      attemptId: "attempt-pi",
    });
  });

  it("passes request correlation into MCP server builders", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const buildMcpServers = vi.fn(() => []);
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
      buildMcpServers,
    });

    await facade.handleQuery({
      ...v2Query({ prompt: "mcp context" }),
      protocolVersion: 2,
      ownerId: "owner-firebase-uid",
      requestId: "request-mcp",
      clientId: "client-mcp",
      sessionId: "session-mcp",
      cwd: "/tmp/mcp",
    });

    expect(buildMcpServers).toHaveBeenCalledWith("act", "/tmp/mcp", "task_chat|task|task-1", {
      ownerId: "owner-firebase-uid",
      requestId: "request-mcp",
      clientId: "client-mcp",
      protocolVersion: 2,
      sessionId: "session-mcp",
      adapterId: "fake",
    });
    store.close();
  });



  it("adds v2 request, session, run, attempt, event, and adapter correlation to stream and result messages", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery({
      ...v2Query({ prompt: "hello v2" }),
      protocolVersion: 2,
      requestId: "request-v2",
      clientId: "client-v2",
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
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "cancel me" }),
      protocolVersion: 2,
      requestId: "request-cancel",
      clientId: "client-cancel",
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
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    expect(sent.some((message) => message.type === "result" && message.terminalStatus === "cancelled")).toBe(true);
    store.close();
  });

  it("allows runId-only v2 interrupts to reach kernel cancellation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "cancel by run id" }),
      protocolVersion: 2,
      requestId: "request-run-only-cancel",
      clientId: "client-run-only-cancel",
      ownerId: "owner-run-only-cancel",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      protocolVersion: 2,
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
      ownerId: "owner-run-only-cancel",
    });

    expect(adapter.cancelled).toHaveLength(1);
    expect(adapter.cancelled[0].runId).toBe(adapter.executed[0].runId);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "request-run-only-cancel",
      clientId: "client-run-only-cancel",
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
      accepted: true,
      dispatchAttempted: true,
    });

    adapter.resolveDeferred({
      text: "cancelled by run id",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    await running;
    store.close();
  });

  it("rejects runId-only v2 interrupts without active context or explicit owner guard", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "reject bare run id cancel" }),
      protocolVersion: 2,
      requestId: "request-bare-run-cancel",
      clientId: "client-bare-run-cancel",
      ownerId: "owner-bare-run-cancel",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      protocolVersion: 2,
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
      requestId: "external-cancel-request",
      clientId: "external-client",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> =>
      message.type === "cancel_ack" && message.requestId === "external-cancel-request"
    );
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "external-cancel-request",
      clientId: "external-client",
      runId: adapter.executed[0].runId,
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });

    adapter.resolveDeferred({
      text: "done",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    await running;
    store.close();
  });

  it("rejects v2 interrupt when the supplied owner does not match the active request owner", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "do not cancel cross-owner" }),
      protocolVersion: 2,
      requestId: "request-owner-guard",
      clientId: "client-owner-guard",
      ownerId: "owner-a",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      requestId: "request-owner-guard",
      clientId: "client-owner-guard",
      ownerId: "owner-b",
    });

    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "request-owner-guard",
      clientId: "client-owner-guard",
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });
    expect(adapter.cancelled).toHaveLength(0);

    adapter.resolveDeferred({
      text: "still running",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });

  it("uses the active request owner when request-scoped interrupt omits ownerId", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "cancel firebase owner" }),
      protocolVersion: 2,
      requestId: "request-firebase-owner",
      clientId: "client-firebase-owner",
      ownerId: "firebase-owner",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      requestId: "request-firebase-owner",
      clientId: "client-firebase-owner",
    });

    expect(adapter.cancelled).toHaveLength(1);
    expect(adapter.cancelled[0].runId).toBe(adapter.executed[0].runId);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "request-firebase-owner",
      clientId: "client-firebase-owner",
      accepted: true,
    });

    adapter.resolveDeferred({
      text: "cancelled",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });

  it("rejects protocol v2 request-scoped interrupts that omit clientId", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "cancel without client id" }),
      protocolVersion: 2,
      requestId: "request-without-client",
      clientId: "non-default-client",
      ownerId: "owner-without-client",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      requestId: "request-without-client",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "request-without-client",
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });
    expect(cancelAck).not.toHaveProperty("clientId");

    adapter.resolveDeferred({
      text: "cancelled",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });

  it("ignores request-scoped interrupt context when the client id does not match", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "do not cancel cross-client" }),
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-a",
      ownerId: "owner-a",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-b",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-b",
      accepted: false,
    });

    adapter.resolveDeferred({
      text: "still running",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });

  it("rejects an explicit empty v2 client id instead of using scoped fallback", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "do not cancel with empty explicit client" }),
      protocolVersion: 2,
      requestId: "empty-client-request",
      clientId: "client-a",
      ownerId: "owner-a",
    });
    await waitUntil(() => adapter.executed.length === 1);

    await facade.handleInterrupt({
      protocolVersion: 2,
      requestId: "empty-client-request",
      clientId: "",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "empty-client-request",
      accepted: false,
    });
    expect(cancelAck).not.toHaveProperty("clientId");

    adapter.resolveDeferred({
      text: "still running",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await running;
    store.close();
  });

  it("keeps duplicate request ids isolated by client when interrupting", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 2);
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const first = facade.handleQuery({
      ...v2Query({ prompt: "shared request client a", externalRefId: "task-client-a" }),
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-a",
      ownerId: "owner-shared",
    });
    const second = facade.handleQuery({
      ...v2Query({ prompt: "shared request client b", externalRefId: "task-client-b" }),
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-b",
      ownerId: "owner-shared",
    });
    await waitUntil(() => adapter.executed.length === 2);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-a",
    });

    expect(adapter.cancelled).toHaveLength(1);
    expect(adapter.cancelled[0].runId).toBe(adapter.executed[0].runId);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      requestId: "shared-request-id",
      clientId: "client-a",
      runId: adapter.executed[0].runId,
      accepted: true,
    });

    adapter.resolveDeferred({
      text: "client a cancelled",
      terminalStatus: "cancelled",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await Promise.all([first, second]);
    store.close();
  });

  it("rejects v2 interrupt when requestId is missing", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 2);
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const ownerA = facade.handleQuery({
      ...v2Query({ prompt: "owner a" }),
      protocolVersion: 2,
      requestId: "request-owner-a",
      clientId: "shared-client",
      ownerId: "owner-a",
    });
    const ownerB = facade.handleQuery({
      ...v2Query({ prompt: "owner b" }),
      protocolVersion: 2,
      requestId: "request-owner-b",
      clientId: "shared-client",
      ownerId: "owner-b",
    });
    await waitUntil(() => adapter.executed.length === 2);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2, requestId: "interrupt-owner-a",
      clientId: "shared-client",
      ownerId: "owner-a",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      clientId: "shared-client",
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });
    expect(cancelAck).not.toHaveProperty("runId");

    adapter.resolveDeferred({
      text: "owner a finished",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await Promise.all([ownerA, ownerB]);
    store.close();
  });

  it("does not collide owner/client pairs when selecting latest run for interrupt", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 2);
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const first = facade.handleQuery({
      ...v2Query({ prompt: "first" }),
      protocolVersion: 2,
      requestId: "request-first",
      clientId: "b:c",
      ownerId: "a",
    });
    const second = facade.handleQuery({
      ...v2Query({ prompt: "second" }),
      protocolVersion: 2,
      requestId: "request-second",
      clientId: "c",
      ownerId: "a:b",
    });
    await waitUntil(() => adapter.executed.length === 2);

    await facade.handleInterrupt({
      type: "interrupt",
      protocolVersion: 2,
      clientId: "b:c",
      ownerId: "a",
    });

    expect(adapter.cancelled).toHaveLength(0);
    const cancelAck = sent.find((message): message is Extract<OutboundMessage, { type: "cancel_ack" }> => message.type === "cancel_ack");
    expect(cancelAck).toMatchObject({
      protocolVersion: 2,
      clientId: "b:c",
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });

    adapter.resolveDeferred({
      text: "first finished",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await Promise.all([first, second]);
    store.close();
  });

  it("queues overlapping v2 requests on one worker without mixing request-scoped results", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 1);
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const first = facade.handleQuery({
      ...v2Query({ prompt: "first" }),
      protocolVersion: 2,
      requestId: "request-one",
      clientId: "client-one",
    });
    await waitUntil(() => adapter.executed.length === 1);

    const second = facade.handleQuery({
      ...v2Query({ prompt: "second" }),
      protocolVersion: 2,
      requestId: "request-two",
      clientId: "client-two",
    });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(adapter.executed).toHaveLength(1);
    expect(sent.some((message) => message.type === "error")).toBe(false);
    expect(facade.unscopedToolCallCorrelation()).toMatchObject({
      protocolVersion: 2,
      requestId: "request-one",
      clientId: "client-one",
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
    });

    adapter.resolveDeferred({
      text: "first done",
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,    });
    await first;
    await second;

    expect(adapter.executed).toHaveLength(2);
    const results = sent.filter((message): message is Extract<OutboundMessage, { type: "result" }> => message.type === "result");
    expect(results.map((message) => message.requestId).sort()).toEqual(["request-one", "request-two"]);
    expect(results.find((message) => message.requestId === "request-one")?.text).toBe("first done");
    expect(results.find((message) => message.requestId === "request-two")?.text).toMatch(/^done-att_/);
    expect(new Set(results.map((message) => message.runId)).size).toBe(2);
    expect(store.allRows("SELECT status FROM runs ORDER BY created_at_ms")).toEqual([
      expect.objectContaining({ status: "succeeded" }),
      expect.objectContaining({ status: "succeeded" }),
    ]);
    store.close();
  });

  it("serves acp and pi-mono requests through one facade without adapter conflict", async () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const acpAdapter = new FakeRuntimeAdapter("acp");
    const piMonoAdapter = new FakeRuntimeAdapter("pi-mono");
    const registry = new AdapterRegistry();
    registry.register("acp", () => acpAdapter, 1);
    registry.register("pi-mono", () => piMonoAdapter, 1);
    const kernel = new AgentRuntimeKernel({ store, registry });
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "acp",
      defaultCwd: () => "/tmp/default",
    });

    await Promise.all([
      facade.handleQuery({
        ...v2Query({ prompt: "use acp" }),
        protocolVersion: 2,
        requestId: "request-acp",
        clientId: "client-acp",
        adapterId: "acp",
      }),
      facade.handleQuery({
        ...v2Query({ prompt: "use pi" }),
        protocolVersion: 2,
        requestId: "request-pi",
        clientId: "client-pi",
        adapterId: "pi-mono",
      }),
    ]);

    expect(acpAdapter.executed).toHaveLength(1);
    expect(piMonoAdapter.executed).toHaveLength(1);
    const results = sent.filter((message): message is Extract<OutboundMessage, { type: "result" }> => message.type === "result");
    expect(results.map((message) => message.requestId).sort()).toEqual(["request-acp", "request-pi"]);
    expect(results.find((message) => message.requestId === "request-acp")?.adapterSessionId).toBe("native-1");
    expect(results.find((message) => message.requestId === "request-pi")?.adapterSessionId).toBe("native-1");
    expect(store.allRows("SELECT adapter_id, status FROM adapter_bindings ORDER BY adapter_id")).toEqual([
      expect.objectContaining({ adapter_id: "acp", status: "active" }),
      expect.objectContaining({ adapter_id: "pi-mono", status: "active" }),
    ]);
    store.close();
  });

  it("records warmup as a hint and invalidate_session invalidates bindings without deleting the canonical session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    facade.handleWarmup({
      type: "warmup",
      cwd: "/tmp/warm",
      sessions: [{ key: "task_chat|task|task-1", model: "fake-model", systemPrompt: "warm system" }],
    });
    expect(store.allRows("SELECT * FROM sessions")).toHaveLength(0);

    await facade.handleQuery(v2Query({ requestId: "request-1", cwd: undefined, systemPrompt: "" }));
    expect(adapter.opened[0]).toMatchObject({
      cwd: "/tmp/warm",
      model: "fake-model",
      systemPrompt: "warm system",
    });
    const sessionId = String(store.getRow("SELECT session_id FROM sessions").session_id);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("active");

    facade.handleInvalidateSession({
      type: "invalidate_session",
      protocolVersion: 2,
      requestId: "invalidate-1",
      clientId: "client-invalidate",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
    });

    expect(store.getRow("SELECT session_id FROM sessions").session_id).toBe(sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("invalid");
    store.close();
  });

  it("uses pi-mono default model when configured as the default adapter", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "pi-mono",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery(v2Query({ requestId: "request-1", model: undefined }));

    expect(adapter.opened[0].model).toBe("omi-sonnet");
    expect(store.getRow("SELECT default_adapter_id FROM sessions").default_adapter_id).toBe("pi-mono");
    store.close();
  });

  it("does not apply the process default model to per-query local adapters", async () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const piMonoAdapter = new FakeRuntimeAdapter("pi-mono");
    const openclawAdapter = new FakeRuntimeAdapter("openclaw");
    const registry = new AdapterRegistry();
    registry.register("pi-mono", () => piMonoAdapter, 1);
    registry.register("openclaw", () => openclawAdapter, 1);
    const kernel = new AgentRuntimeKernel({ store, registry });
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "pi-mono",
      defaultCwd: () => "/tmp/default",
    });

    await facade.handleQuery(v2Query({ requestId: "request-openclaw",
      adapterId: "openclaw",
      model: undefined,
    }));

    expect(openclawAdapter.opened[0].model).toBeUndefined();
    expect(openclawAdapter.executed[0].model).toBeUndefined();
    expect(store.getRow("SELECT default_adapter_id FROM sessions").default_adapter_id).toBe("openclaw");
    expect(store.getRow("SELECT adapter_id FROM adapter_bindings").adapter_id).toBe("openclaw");
    store.close();
  });

  it("suppresses pi-mono tool_use events while preserving correlated tool activity", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono");
    adapter.deferResult();
    const sent: OutboundMessage[] = [];
    const facade = new JsonlTransport({
      kernel,
      send: (message) => sent.push(message),
      defaultAdapterId: "pi-mono",
      defaultCwd: () => "/tmp/default",
      suppressToolUseEvents: true,
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "use tools" }),
      protocolVersion: 2,
      requestId: "request-pi",
      clientId: "client-pi",
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
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,      terminalStatus: "succeeded",
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

  it("clears running marker after a terminal run event for unscoped correlation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const facade = new JsonlTransport({
      kernel,
      send: () => {},
      defaultAdapterId: "fake",
      defaultCwd: () => "/tmp/default",
    });

    const running = facade.handleQuery({
      ...v2Query({ prompt: "terminal marker" }),
      protocolVersion: 2,
      requestId: "request-terminal-marker",
      clientId: "client-terminal-marker",
    });
    await waitUntil(() => adapter.executed.length === 1);
    expect(facade.unscopedToolCallCorrelation()).toMatchObject({
      requestId: "request-terminal-marker",
      runId: adapter.executed[0].runId,
    });
    expect(facade.toolCallCorrelationForRequest("request-terminal-marker", "client-terminal-marker")).toMatchObject({
      requestId: "request-terminal-marker",
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
    });
    expect(facade.toolCallCorrelationForRequest("stale-request-from-reused-mcp-process", "client-terminal-marker")).toEqual({});
    expect(facade.toolCallCorrelationForAdapter("fake")).toMatchObject({
      requestId: "request-terminal-marker",
      runId: adapter.executed[0].runId,
      attemptId: adapter.executed[0].attemptId,
    });

    adapter.resolveDeferred({
      text: "done",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,      terminalStatus: "succeeded",
    });
    await running;

    expect(facade.unscopedToolCallCorrelation()).toEqual({});
    store.close();
  });

  it("invokes recoverable auth flow and retries under the same run when binding open requires auth", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const sent: OutboundMessage[] = [];
    let authFlowCalls = 0;
    const authError = Object.assign(new Error("auth required"), { code: -32000 });
    adapter.failNextOpenError = authError;
    const facade = new JsonlTransport({
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

    await facade.handleQuery(v2Query({ requestId: "request-auth"}));

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
    const facade = new JsonlTransport({
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

    await facade.handleQuery(v2Query({ requestId: "request-auth-exec"}));

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
    const facade = new JsonlTransport({
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

    await facade.handleQuery(v2Query({ requestId: "request-auth-fail"}));

    expect(sent.some((message) => message.type === "error")).toBe(true);
    expect(store.getRow("SELECT status FROM runs").status).toBe("failed");
    expect(store.getRow("SELECT status FROM run_attempts").status).toBe("failed");
    expect(store.allRows("SELECT * FROM run_attempts WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')")).toHaveLength(0);
    store.close();
  });
});

function v2Query(overrides: Partial<QueryMessage> = {}): QueryMessage {
  return {
    type: "query",
    protocolVersion: 2,
    requestId: "request",
    clientId: "client",
    surfaceKind: "task_chat",
    externalRefKind: "task",
    externalRefId: "task-1",
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
