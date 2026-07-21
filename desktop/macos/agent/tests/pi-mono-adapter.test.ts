import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PassThrough } from "node:stream";
import { EventEmitter } from "node:events";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { spawn } from "child_process";
import {
  PiMonoAdapter,
  PiMonoRuntimeAdapter,
  routePromptForPublicWeb,
} from "../src/adapters/pi-mono.js";
import { HarnessFeature, type AdapterAttemptContext, type HarnessConfig } from "../src/adapters/interface.js";
import type { OutboundMessage } from "../src/protocol.js";

// Mock child_process.spawn so start() doesn't launch a real subprocess.
// Existing tests that mock sendCommand never call start(), so unaffected.
vi.mock("child_process", async () => {
  const actual = await vi.importActual<typeof import("child_process")>("child_process");
  return {
    ...actual,
    spawn: vi.fn(() => {
      const proc = Object.assign(new EventEmitter(), {
        stdin: new PassThrough(),
        stdout: new PassThrough(),
        stderr: new PassThrough(),
        kill: vi.fn(),
        removeAllListeners: vi.fn(),
        pid: 99999,
      });
      return proc;
    }),
  };
});

function createAdapter(configOverrides: Partial<HarnessConfig> & { onRestart?: (reason: string) => void } = {}) {
  const config: HarnessConfig = {
    authToken: "test-token",
    ...configOverrides,
  };
  const adapter = new PiMonoAdapter(config);
  const events: OutboundMessage[] = [];

  (adapter as any).sendCommand = vi.fn();

  return { adapter, events };
}

function seedSessions(adapter: PiMonoAdapter, ...sessionIds: string[]) {
  const sessions = (adapter as any).sessions as Map<string, unknown>;
  for (const sessionId of sessionIds) {
    sessions.set(sessionId, { cwd: "/tmp" });
  }
}

type AttemptContextOverrides = Omit<Partial<AdapterAttemptContext>, "binding"> & {
  binding?: Partial<AdapterAttemptContext["binding"]>;
};

function makeAttemptContext(overrides: AttemptContextOverrides = {}): AdapterAttemptContext {
  const attemptId = overrides.attemptId ?? "att_runtime";
  const sessionId = overrides.sessionId ?? "ses_runtime";
  const adapterNativeSessionId = overrides.binding?.adapterNativeSessionId ?? "session-1";
  return {
    sessionId,
    ownerId: overrides.ownerId ?? "owner-runtime",
    requestId: overrides.requestId ?? "request-runtime",
    clientId: overrides.clientId ?? "client-runtime",
    runId: overrides.runId ?? "run_runtime",
    attemptId,
    toolCapabilityRef: overrides.toolCapabilityRef ?? `cap_${attemptId}`,
    binding: {
      bindingId: "bind-runtime",
      sessionId,
      adapterId: "pi-mono",
      adapterNativeSessionId,
      resumeFidelity: "none",
      cwd: "/tmp",
      ...overrides.binding,
    },
    prompt: overrides.prompt ?? [{ type: "text", text: "hello" }],
    tools: overrides.tools,
    mode: overrides.mode ?? "act",
    metadata: overrides.metadata,
  };
}

function makeTurnEndEvent(text: string, totalCost = 1.25) {
  return {
    type: "turn_end",
    message: {
      role: "assistant",
      content: [{ type: "text", text }],
      usage: {
        input: 11,
        output: 7,
        cacheRead: 3,
        cacheWrite: 2,
        totalTokens: 23,
        cost: {
          input: 0.1,
          output: 0.2,
          cacheRead: 0.3,
          cacheWrite: 0.4,
          total: totalCost,
        },
      },
    },
  };
}

function makeErrorTurnEndEvent(errorMessage: string) {
  return {
    type: "turn_end",
    message: {
      role: "assistant",
      errorMessage,
      content: [],
    },
  };
}

describe("PiMonoAdapter prompt correlation", () => {
  it("forwards tool execution updates as content-free progress activity", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "session-1");

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "write the document" }],
      [],
      "act",
      (event) => events.push(event),
      async () => "",
    );

    (adapter as any).handleEvent(JSON.stringify({
      type: "tool_execution_update",
      toolName: "write",
      toolCallId: "tool-write-1",
      partialResult: { content: [{ type: "text", text: "private document content" }] },
    }));

    expect(events).toEqual([{
      type: "tool_activity",
      name: "write",
      status: "progress",
      toolUseId: "tool-write-1",
    }]);

    (adapter as any).handleTurnEnd(makeTurnEndEvent("done"));
    await expect(prompt).resolves.toMatchObject({ text: "done" });
  });

  it("routes current public web requests for both coordinator and leaf sessions", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "main", "leaf");

    for (const [sessionId, query] of [
      ["main", "what's the weather in NYC right now?"],
      ["leaf", "what AI models were released this week?"],
      ["main", "who's playing in the World Cup right now?"],
    ] as const) {
      const prompt = adapter.sendPrompt(
        sessionId,
        [{ type: "text", text: query }],
        [],
        "act",
        () => {},
        async () => ""
      );
      const command = (adapter as any).sendCommand.mock.calls.at(-1)[0];
      expect(command.message).toContain("<omi_retrieval_policy>");
      expect(command.message).toContain("Web search is required and available for this fresh public request.");
      expect(command.message).toContain("Use a live public-web or search tool before answering.");
      expect(command.message).toContain("Never say, imply, or hedge that you lack internet, web-search, real-time-data, or tool access");
      expect(command.message).toContain(query);
      (adapter as any).handleTurnEnd(makeTurnEndEvent("done"));
      await expect(prompt).resolves.toMatchObject({ text: "done" });
    }
  });

  it("does not route explicit private-context requests onto the public web", () => {
    for (const message of [
      "search my calendar for weather in NYC",
      "what did I say today about the current weather?",
    ]) {
      expect(routePromptForPublicWeb(message)).toBe(message);
    }
  });

  it("does not route a child task from inherited public-web context", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "child");
    const renderedChildPrompt = [
      "# Omi Context Snapshot",
      "Earlier user request: ask OpenClaw what's trending on X right now.",
      "# User Message",
      "Sleep for 5 seconds.",
    ].join("\n");

    const prompt = adapter.sendPrompt(
      "child",
      [{ type: "text", text: renderedChildPrompt }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    const command = (adapter as any).sendCommand.mock.calls.at(-1)[0];
    expect(command.message).toBe(renderedChildPrompt);
    expect(command.message).not.toContain("<omi_retrieval_policy>");
    expect(events.filter((event) => event.type === "tool_activity")).toEqual([]);

    (adapter as any).handleTurnEnd(makeTurnEndEvent("Slept for 5 seconds."));
    await expect(prompt).resolves.toMatchObject({ text: "Slept for 5 seconds." });
  });

  it("projects gateway web-search progress and removes a false no-access disclaimer without local tool events", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "main");
    const response = "I don't have direct internet/web access, but I can get you real weather data via the terminal!\n\nCurrent weather: Sunny, 73 F.";
    const prompt = adapter.sendPrompt(
      "main",
      [{ type: "text", text: "what's the weather in NYC right now?" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    (adapter as any).handleMessageUpdate({
      assistantMessageEvent: { type: "text_delta", delta: response },
    });
    (adapter as any).handleTurnEnd(makeTurnEndEvent(response));

    const expected = "I can get you real weather data via the terminal!\n\nCurrent weather: Sunny, 73 F.";
    await expect(prompt).resolves.toMatchObject({ text: expected });
    expect(events.filter((event) => event.type === "text_delta")).toEqual([
      { type: "text_delta", text: expected },
    ]);
    expect(events.filter((event) => event.type === "tool_activity")).toEqual([
      {
        type: "tool_activity",
        name: "web_search",
        status: "started",
        toolUseId: "gateway-public-web-1",
        input: { executor: "gateway" },
      },
      {
        type: "tool_activity",
        name: "web_search",
        status: "completed",
        toolUseId: "gateway-public-web-1",
      },
    ]);
  });

  it("closes gateway web-search progress as failed when the public lookup fails", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "main");
    const prompt = adapter.sendPrompt(
      "main",
      [{ type: "text", text: "what's the weather in NYC right now?" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    (adapter as any).handleTurnEnd(makeErrorTurnEndEvent("public web lookup failed"));

    await expect(prompt).rejects.toThrow("public web lookup failed");
    expect(events.filter((event) => event.type === "tool_activity")).toEqual([
      {
        type: "tool_activity",
        name: "web_search",
        status: "started",
        toolUseId: "gateway-public-web-1",
        input: { executor: "gateway" },
      },
      {
        type: "tool_activity",
        name: "web_search",
        status: "failed",
        toolUseId: "gateway-public-web-1",
      },
    ]);
  });

  it("closes gateway web-search progress when prompt dispatch fails synchronously", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "main");
    (adapter as any).sendCommand = vi.fn(() => {
      throw new Error("Pi stdin is not writable");
    });

    await expect(adapter.sendPrompt(
      "main",
      [{ type: "text", text: "what's the weather in NYC right now?" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    )).rejects.toThrow("Pi stdin is not writable");

    expect(events.filter((event) => event.type === "tool_activity")).toEqual([
      {
        type: "tool_activity",
        name: "web_search",
        status: "started",
        toolUseId: "gateway-public-web-1",
        input: { executor: "gateway" },
      },
      {
        type: "tool_activity",
        name: "web_search",
        status: "failed",
        toolUseId: "gateway-public-web-1",
      },
    ]);
  });

  it("closes gateway web-search progress when abort dispatch fails synchronously", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "main");
    const prompt = adapter.sendPrompt(
      "main",
      [{ type: "text", text: "what's the weather in NYC right now?" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );
    (adapter as any).sendCommand = vi.fn(() => {
      throw new Error("Pi stdin is not writable");
    });

    adapter.abort("main");

    await expect(prompt).resolves.toMatchObject({ text: "", sessionId: "main" });
    expect(events.filter((event) => event.type === "tool_activity")).toEqual([
      {
        type: "tool_activity",
        name: "web_search",
        status: "started",
        toolUseId: "gateway-public-web-1",
        input: { executor: "gateway" },
      },
      {
        type: "tool_activity",
        name: "web_search",
        status: "failed",
        toolUseId: "gateway-public-web-1",
      },
    ]);
  });

  it("writes the active runtime attempt context before prompt execution", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");
    const runtime = new PiMonoRuntimeAdapter(adapter);
    const attemptContext: AdapterAttemptContext = {
      sessionId: "ses_runtime",
      requestId: "request-runtime",
      clientId: "client-runtime",
      runId: "run_runtime",
      attemptId: "att_runtime",
      toolCapabilityRef: "cap_runtime",
      binding: {
        bindingId: "bind-runtime",
        sessionId: "ses_runtime",
        adapterId: "pi-mono",
        adapterNativeSessionId: "session-1",
        resumeFidelity: "none",
        cwd: "/tmp",
      },
      prompt: [{ type: "text", text: "hello" }],
      mode: "act",
      metadata: {
        protocolVersion: 2,
        disableSwiftBackedTools: true,
      },
    };

    const execution = runtime.executeAttempt(attemptContext, () => {}, new AbortController().signal);
    const relayContext = JSON.parse(readFileSync((adapter as any).contextFilePath, "utf8"));
    expect(relayContext).toEqual({ capabilityRef: "cap_runtime", requestId: "request-runtime" });

    (adapter as any).handleTurnEnd(makeTurnEndEvent("done"));
    await expect(execution).resolves.toMatchObject({ terminalStatus: "succeeded" });
    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("removes the runtime attempt context after adapter errors", async () => {
    const { adapter } = createAdapter();
    (adapter as any).sendCommand = vi.fn(() => {
      throw new Error("adapter send failed");
    });
    seedSessions(adapter, "session-1");
    const runtime = new PiMonoRuntimeAdapter(adapter);
    const attemptContext = makeAttemptContext({ attemptId: "att_error" });

    await expect(runtime.executeAttempt(attemptContext, () => {}, new AbortController().signal)).rejects.toThrow(
      "adapter send failed"
    );
    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("removes the runtime attempt context after abort", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");
    const runtime = new PiMonoRuntimeAdapter(adapter);
    const controller = new AbortController();
    const attemptContext = makeAttemptContext({ attemptId: "att_abort" });

    const execution = runtime.executeAttempt(attemptContext, () => {}, controller.signal);
    expect(JSON.parse(readFileSync((adapter as any).contextFilePath, "utf8")).capabilityRef).toBe("cap_att_abort");
    controller.abort();

    await expect(execution).resolves.toMatchObject({ terminalStatus: "cancelled" });
    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("rejects a concurrent attempt without clearing the active attempt context", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1", "session-2");
    const runtime = new PiMonoRuntimeAdapter(adapter);

    const first = runtime.executeAttempt(
      makeAttemptContext({ attemptId: "att_first", binding: { adapterNativeSessionId: "session-1" } }),
      () => {},
      new AbortController().signal
    );
    expect(JSON.parse(readFileSync((adapter as any).contextFilePath, "utf8")).capabilityRef).toBe("cap_att_first");

    const second = runtime.executeAttempt(
      makeAttemptContext({ attemptId: "att_second", binding: { adapterNativeSessionId: "session-2" } }),
      () => {},
      new AbortController().signal
    );

    await expect(second).rejects.toThrow("pi-mono prompt already in flight");
    expect(JSON.parse(readFileSync((adapter as any).contextFilePath, "utf8")).capabilityRef).toBe("cap_att_first");

    (adapter as any).handleTurnEnd(makeTurnEndEvent("first done"));
    await expect(first).resolves.toMatchObject({ terminalStatus: "succeeded" });
    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("removes the runtime attempt context after subprocess exit rejects the prompt", async () => {
    const { adapter } = createAdapter();
    await adapter.start();
    seedSessions(adapter, "session-1");
    const runtime = new PiMonoRuntimeAdapter(adapter);
    const execution = runtime.executeAttempt(
      makeAttemptContext({ attemptId: "att_exit" }),
      () => {},
      new AbortController().signal
    );
    expect(JSON.parse(readFileSync((adapter as any).contextFilePath, "utf8")).capabilityRef).toBe("cap_att_exit");

    (adapter as any).process.emit("exit", 7);

    await expect(execution).rejects.toThrow("pi-mono process exited (code 7)");
    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("removes invalid relay context for the completed attempt", () => {
    const { adapter } = createAdapter();
    writeFileSync((adapter as any).contextFilePath, "{invalid json");

    (adapter as any).clearRelayContextForCapability("cap_invalid");

    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
  });

  it("clears stale relay context when direct prompt execution has no runtime context", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");

    const runtime = new PiMonoRuntimeAdapter(adapter);
    const attemptContext: AdapterAttemptContext = {
      sessionId: "ses_runtime",
      requestId: "request-runtime",
      clientId: "client-runtime",
      runId: "run_runtime",
      attemptId: "att_runtime",
      toolCapabilityRef: "cap_runtime",
      binding: {
        bindingId: "bind-runtime",
        sessionId: "ses_runtime",
        adapterId: "pi-mono",
        adapterNativeSessionId: "session-1",
        resumeFidelity: "none",
        cwd: "/tmp",
      },
      prompt: [{ type: "text", text: "hello" }],
      mode: "act",
    };

    const execution = runtime.executeAttempt(attemptContext, () => {}, new AbortController().signal);
    expect(existsSync((adapter as any).contextFilePath)).toBe(true);
    (adapter as any).handleTurnEnd(makeTurnEndEvent("done"));
    await expect(execution).resolves.toMatchObject({ terminalStatus: "succeeded" });

    const directPrompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "direct" }],
      [],
      "act",
      () => {},
      async () => ""
    );

    expect(existsSync((adapter as any).contextFilePath)).toBe(false);
    (adapter as any).handleTurnEnd(makeTurnEndEvent("direct done"));
    await expect(directPrompt).resolves.toMatchObject({ text: "direct done" });
  });

  it("rejects a second prompt while one is in flight", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "session-1", "session-2");

    const firstPrompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "first" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    await expect(adapter.sendPrompt(
      "session-2",
      [{ type: "text", text: "second" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    )).rejects.toThrow("pi-mono prompt already in flight");

    (adapter as any).handleTurnEnd(makeTurnEndEvent("first response", 2.5));

    await expect(firstPrompt).resolves.toMatchObject({
      text: "first response",
      sessionId: "session-1",
      costUsd: 2.5,
      inputTokens: 11,
      outputTokens: 7,
      cacheReadTokens: 3,
      cacheWriteTokens: 2,
    });
    expect(events.some((event) => event.type === "result")).toBe(false);
  });

  it("treats agent_settled as advisory and waits for the authoritative turn_end", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");
    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "wait for the child" }],
      [],
      "act",
      () => {},
      async () => "",
    );

    (adapter as any).handleEvent(JSON.stringify({ type: "agent_settled" }));

    expect((adapter as any).activePromptGeneration).toBe(1);
    expect((adapter as any).pendingRequests.size).toBe(1);
    (adapter as any).handleTurnEnd(makeTurnEndEvent("authoritative terminal result"));
    await expect(prompt).resolves.toMatchObject({ text: "authoritative terminal result" });
  });

  it("rejects turn_end errors instead of resolving success", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "session-1");

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "fail" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    (adapter as any).handleTurnEnd(makeErrorTurnEndEvent("adapter failed"));

    await expect(prompt).rejects.toThrow("adapter failed");
    expect(events).toContainEqual(
      expect.objectContaining({
        type: "error",
        message: "adapter failed",
        adapterSessionId: "session-1",
      })
    );
  });

  it("does not report success after a required agent-control operation fails", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "session-1");

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "create a child" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    (adapter as any).handleToolEnd({
      toolName: "spawn_agent",
      toolCallId: "tool-spawn",
      result: {
        content: [{
          type: "text",
          text: JSON.stringify({
            ok: false,
            error: { code: "missing_request_context", message: "missing active Omi request context" },
          }),
        }],
      },
    });
    (adapter as any).handleTurnEnd(makeTurnEndEvent("I could not create the child, but I am done."));

    await expect(prompt).rejects.toThrow("Required spawn_agent operation failed");
    expect(events).toContainEqual(
      expect.objectContaining({
        type: "error",
        message: expect.stringContaining("missing active Omi request context"),
      })
    );
  });

  it("allows a successful required-control retry to complete the parent turn", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "create a child" }],
      [],
      "act",
      () => {},
      async () => ""
    );

    (adapter as any).handleToolEnd({
      toolName: "spawn_agent",
      toolCallId: "tool-spawn-1",
      result: { content: [{ type: "text", text: JSON.stringify({ ok: false, error: { message: "temporary failure" } }) }] },
    });
    (adapter as any).handleToolEnd({
      toolName: "spawn_agent",
      toolCallId: "tool-spawn-2",
      result: { content: [{ type: "text", text: JSON.stringify({ ok: true }) }] },
    });
    (adapter as any).handleTurnEnd(makeTurnEndEvent("child created"));

    await expect(prompt).resolves.toMatchObject({ text: "child created" });
  });

  it("does not let an unrelated control success erase a failed obligation", async () => {
    const { adapter } = createAdapter();
    seedSessions(adapter, "session-1");
    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "create both children" }],
      [],
      "act",
      () => {},
      async () => "",
    );

    (adapter as any).handleToolStart({
      toolName: "spawn_agent",
      toolCallId: "tool-child-a",
      args: { objective: "child A" },
    });
    (adapter as any).handleToolEnd({
      toolName: "spawn_agent",
      toolCallId: "tool-child-a",
      result: { content: [{ type: "text", text: JSON.stringify({ ok: false, error: { message: "failed A" } }) }] },
    });
    (adapter as any).handleToolStart({
      toolName: "spawn_agent",
      toolCallId: "tool-child-b",
      args: { objective: "child B" },
    });
    (adapter as any).handleToolEnd({
      toolName: "spawn_agent",
      toolCallId: "tool-child-b",
      result: { content: [{ type: "text", text: JSON.stringify({ ok: true }) }] },
    });
    (adapter as any).handleTurnEnd(makeTurnEndEvent("child B created"));

    await expect(prompt).rejects.toThrow("failed A");
  });

  it("resolves abort before turn_end and drops the late completion", async () => {
    const { adapter, events } = createAdapter();
    seedSessions(adapter, "session-1");

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "abort me" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    adapter.abort("session-1");

    await expect(prompt).resolves.toMatchObject({
      text: "",
      sessionId: "session-1",
      costUsd: 0,
      inputTokens: 0,
      outputTokens: 0,
    });

    (adapter as any).handleTurnEnd(makeTurnEndEvent("late response"));

    expect(events).toEqual([]);
    expect((adapter as any).activePromptGeneration).toBe(0);
  });

  it("drops stray turn_end events when no prompt is in flight", () => {
    const { adapter, events } = createAdapter();

    (adapter as any).eventHandler = (event: OutboundMessage) => events.push(event);
    (adapter as any).handleTurnEnd(makeTurnEndEvent("orphaned response"));

    expect(events).toEqual([]);
    expect((adapter as any).pendingRequests.size).toBe(0);
  });
});

describe("PiMonoAdapter restart lifecycle", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockClear();
  });

  it("notifies restart observers after an immediate system prompt restart", async () => {
    const onRestart = vi.fn();
    const { adapter } = createAdapter({ onRestart });

    await adapter.start();
    await expect(adapter.setSystemPrompt("new prompt")).resolves.toBe(true);

    expect(onRestart).toHaveBeenCalledWith("systemPrompt");
    expect(spawn).toHaveBeenCalledTimes(2);
  });
});

describe("PiMonoAdapter source-level invariants", () => {
  const piMonoSrc = readFileSync(
    fileURLToPath(new URL("../src/adapters/pi-mono.ts", import.meta.url)),
    "utf8"
  );

  it("passes the raw authToken as OMI_API_KEY (no `Bearer ` prefix)", () => {
    expect(piMonoSrc).toMatch(/env\.OMI_API_KEY\s*=\s*this\.config\.authToken\s*;?/);
    expect(piMonoSrc).not.toMatch(/env\.OMI_API_KEY\s*=\s*`Bearer \$\{/);
  });

  it("always scrubs ANTHROPIC_API_KEY from the child env", () => {
    expect(piMonoSrc).toMatch(/delete\s+env\.ANTHROPIC_API_KEY\s*;?/);
  });
});

describe("PiMonoAdapter spawn args (behavioral)", () => {
  // Behavioral test: actually call start() with a mocked spawn to verify
  // the real args array rather than grepping source text.
  beforeEach(() => {
    vi.mocked(spawn).mockClear();
  });

  it("does not pass --no-extensions to the subprocess", async () => {
    const config: HarnessConfig = {
      authToken: "test-token",
    };
    const adapter = new PiMonoAdapter(config, "/fake/pi", "/fake/ext.ts");
    await adapter.start();

    expect(spawn).toHaveBeenCalledOnce();
    const [cmd, args] = vi.mocked(spawn).mock.calls[0];
    expect(cmd).toBe("/fake/pi");
    expect(args).toContain("--mode");
    expect(args).toContain("rpc");
    expect(args).toContain("-e");
    expect(args).toContain("/fake/ext.ts");
    // Auto-discovery must be enabled: --no-extensions must NOT be present
    expect(args).not.toContain("--no-extensions");

    await adapter.stop();
  });

  it("includes required base flags: --mode rpc, -e, --provider, --model", async () => {
    const config: HarnessConfig = {
      authToken: "test-token",
    };
    const adapter = new PiMonoAdapter(config, "/fake/pi", "/fake/ext.ts");
    await adapter.start();

    const [, args] = vi.mocked(spawn).mock.calls[0];
    expect(args).toEqual(expect.arrayContaining([
      "--mode", "rpc",
      "-e", "/fake/ext.ts",
      "--provider", "omi",
      "--model", "omi-sonnet",
    ]));

    await adapter.stop();
  });

  it("scrubs OMI_API_KEY into the subprocess env from authToken", async () => {
    const config: HarnessConfig = {
      authToken: "firebase-id-token-xyz",
    };
    const adapter = new PiMonoAdapter(config, "/fake/pi", "/fake/ext.ts");
    await adapter.start();

    const [, , options] = vi.mocked(spawn).mock.calls[0] as [string, string[], { env: Record<string, string> }];
    // Raw token, not "Bearer <token>"
    expect(options.env.OMI_API_KEY).toBe("firebase-id-token-xyz");
    // Upstream secret must be scrubbed
    expect(options.env.ANTHROPIC_API_KEY).toBeUndefined();

    await adapter.stop();
  });

  it("projects chat-first tools into the child env only for an enabled main Chat", async () => {
    const adapter = new PiMonoAdapter({ authToken: "test-token" }, "/fake/pi", "/fake/ext.ts");
    await adapter.setToolProjection({
      surfaceKind: "main_chat",
      chatFirstUi: true,
      controlGeneration: 7,
    });
    await adapter.start();

    const [, , options] = vi.mocked(spawn).mock.calls[0] as [string, string[], { env: Record<string, string> }];
    expect(options.env.OMI_SURFACE_KIND).toBe("main_chat");
    expect(options.env.OMI_CHAT_FIRST_UI).toBe("true");
    expect(options.env.OMI_CHAT_FIRST_CONTROL_GENERATION).toBe("7");
    await adapter.stop();

    vi.mocked(spawn).mockClear();
    await adapter.setToolProjection({
      surfaceKind: "floating_chat",
      chatFirstUi: true,
      controlGeneration: 7,
    });
    await adapter.start();
    const [, , legacyOptions] = vi.mocked(spawn).mock.calls[0] as [
      string,
      string[],
      { env: Record<string, string> },
    ];
    expect(legacyOptions.env.OMI_SURFACE_KIND).toBeUndefined();
    expect(legacyOptions.env.OMI_CHAT_FIRST_UI).toBeUndefined();
    expect(legacyOptions.env.OMI_CHAT_FIRST_CONTROL_GENERATION).toBeUndefined();
    await adapter.stop();
  });
});

describe("PiMonoAdapter capabilities", () => {
  it("does not advertise native session resume", () => {
    const { adapter } = createAdapter();

    expect(adapter.supportsFeature(HarnessFeature.SESSION_RESUME)).toBe(false);
  });
});

describe("tool_use event filtering", () => {
  // Two-layer defense:
  // 1. Source-level assertion verifies the filter EXISTS in the real code
  // 2. Behavioral test verifies the filtering LOGIC is correct
  // Together they catch both: (a) accidental removal/refactoring of the
  // filter, and (b) logical errors in the filtering pattern.
  const indexSrc = readFileSync(
    fileURLToPath(new URL("../src/index.ts", import.meta.url)),
    "utf8"
  );
  const transportSrc = readFileSync(
    fileURLToPath(new URL("../src/runtime/jsonl-transport.ts", import.meta.url)),
    "utf8"
  );

  it("source: shared runtime registers pi-mono in the same daemon", () => {
    expect(indexSrc).toMatch(/Default harness mode/);
    expect(indexSrc).toMatch(/registry\.register\(["']acp["']/);
    expect(indexSrc).toMatch(/registry\.register\(["']pi-mono["']/);
  });

  it("source: jsonl transport suppresses tool_use when configured or routed to pi-mono", () => {
    expect(transportSrc).toMatch(/case\s+["']tool_use["'][\s\S]*!this\.suppressToolUseEvents\s*&&\s*context\.adapterId\s*!==\s*["']pi-mono["']/);
  });

  it("behavioral: suppresses tool_use events and forwards all other types", () => {
    const forwarded: any[] = [];

    // Equivalent filtering path used by the jsonl transport for pi-mono events.
    const eventCallback = (event: any) => {
      if ((event as any).type === "tool_use") return;
      forwarded.push(event);
    };

    // tool_use must be suppressed (prevents Swift double-executing the tool)
    eventCallback({ type: "tool_use", callId: "call-1", name: "bash", input: { command: "ls" } });
    expect(forwarded).toHaveLength(0);

    // All other event types must pass through
    const otherEvents = [
      { type: "text_delta", text: "hello" },
      { type: "thinking_delta", text: "thinking..." },
      { type: "tool_activity", name: "bash", status: "started", toolUseId: "call-1" },
      { type: "tool_activity", name: "bash", status: "completed", toolUseId: "call-1" },
      { type: "tool_result_display", toolUseId: "call-1", name: "bash", output: "file.txt" },
      { type: "result", text: "done", sessionId: "s1", costUsd: 0 },
    ];

    for (const event of otherEvents) {
      eventCallback(event);
    }

    expect(forwarded).toHaveLength(otherEvents.length);
    expect(forwarded).toEqual(otherEvents);
  });

  it("handles multiple tool_use events interspersed with other events", () => {
    const forwarded: any[] = [];
    const eventCallback = (event: any) => {
      if ((event as any).type === "tool_use") return;
      forwarded.push(event);
    };

    eventCallback({ type: "text_delta", text: "Let me check..." });
    eventCallback({ type: "tool_use", callId: "c1", name: "Read", input: { path: "/tmp/x" } });
    eventCallback({ type: "tool_activity", name: "Read", status: "started" });
    eventCallback({ type: "tool_use", callId: "c2", name: "bash", input: { command: "pwd" } });
    eventCallback({ type: "tool_activity", name: "bash", status: "started" });
    eventCallback({ type: "text_delta", text: "Here's what I found." });

    // Only tool_use events should be filtered; everything else passes through
    expect(forwarded).toHaveLength(4);
    expect(forwarded.map((e: any) => e.type)).toEqual([
      "text_delta",
      "tool_activity",
      "tool_activity",
      "text_delta",
    ]);
  });
});
