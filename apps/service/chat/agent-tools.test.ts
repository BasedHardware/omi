import { describe, expect, test } from "bun:test";

import {
  createAgentToolRegistry,
  createAgentToolRunner,
  type AgentToolDefinition,
  type AgentToolScheduler,
  type AgentToolTraceEvent,
} from "./agent-tools";

class DeterministicToolScheduler implements AgentToolScheduler {
  private nowMs = 0;
  private nextId = 1;
  private readonly timers = new Map<number, { readonly at: number; readonly callback: () => void }>();

  get now(): number { return this.nowMs; }
  setTimeout(callback: () => void, delayMs: number): number {
    const id = this.nextId++;
    this.timers.set(id, { at: this.nowMs + delayMs, callback });
    return id;
  }
  clearTimeout(handle: unknown): void {
    if (typeof handle === "number") this.timers.delete(handle);
  }
  advance(milliseconds: number): void {
    this.nowMs += milliseconds;
    for (;;) {
      const due = [...this.timers.entries()]
        .filter(([, timer]) => timer.at <= this.nowMs)
        .sort(([left], [right]) => left - right)[0];
      if (due === undefined) return;
      this.timers.delete(due[0]);
      due[1].callback();
    }
  }
}

const safeTool = (
  name: string,
  execute: AgentToolDefinition["execute"],
  overrides: Partial<AgentToolDefinition> = {},
): AgentToolDefinition => ({
  schemaVersion: 1,
  name,
  risk: "safe",
  timeoutMs: 100,
  retryable: false,
  displaySummary: `Run ${name}`,
  validateInput: (input): boolean => input !== null && typeof input === "object",
  execute,
  ...overrides,
});

describe("closed agent tool registry and approval seam", () => {
  test("registry is strict, closed, and deterministic", () => {
    const registry = createAgentToolRegistry([
      safeTool("safe.lookup", async () => ({ summary: "lookup ok", durationMs: 1, retryable: false })),
      safeTool("safe.write", async () => ({ summary: "write ok", durationMs: 1, retryable: false }), { risk: "approval-required" }),
    ]);
    expect(registry.names()).toEqual(["safe.lookup", "safe.write"]);
    expect(registry.resolve("unknown.tool")).toBeNull();
    expect(() => createAgentToolRegistry([
      safeTool("safe.lookup", async () => ({ summary: "one", durationMs: 1, retryable: false })),
      safeTool("safe.lookup", async () => ({ summary: "two", durationMs: 1, retryable: false })),
    ])).toThrow("duplicate agent tool name");
    expect(() => createAgentToolRegistry([safeTool("unsafe", async () => ({ summary: "safe", durationMs: 1, retryable: false }), { displaySummary: "api_key=secret" })])).toThrow("invalid agent tool definition");
  });

  test("two safe tools execute in order once and unknown tools never execute", async () => {
    const calls: string[] = [];
    const events: AgentToolTraceEvent[] = [];
    const registry = createAgentToolRegistry([
      safeTool("safe.first", async () => {
        calls.push("first");
        return { summary: "first result", durationMs: 2, retryable: false };
      }),
      safeTool("safe.second", async () => {
        calls.push("second");
        return { summary: "second result", durationMs: 3, retryable: false };
      }),
    ]);
    const runner = createAgentToolRunner({ registry, nowEpochMilliseconds: () => 0, onEvent: (event) => events.push(event) });
    const first = await runner.request({ callId: "call:first", toolName: "safe.first", idempotencyKey: "idem:first", input: { value: 1 } });
    const second = await runner.request({ callId: "call:second", toolName: "safe.second", idempotencyKey: "idem:second", input: { value: 2 } });
    const replay = await runner.request({ callId: "call:replay", toolName: "safe.first", idempotencyKey: "idem:first", input: { value: 1 } });
    const unknown = await runner.request({ callId: "call:unknown", toolName: "unsafe.exec", idempotencyKey: "idem:unknown", input: { api_key: "secret" } });
    expect(calls).toEqual(["first", "second"]);
    expect(first).toMatchObject({ kind: "completed", summary: "first result" });
    expect(second).toMatchObject({ kind: "completed", summary: "second result" });
    expect(replay).toEqual(first);
    expect(unknown).toMatchObject({ kind: "failed", code: "tool_unknown" });
    expect(JSON.stringify(events)).not.toMatch(/api_key|secret/iu);
    expect(events.map((event) => event.kind)).toEqual([
      "tool_request", "tool_progress", "tool_result",
      "tool_request", "tool_progress", "tool_result",
      "tool_error",
    ]);
  });

  test("approval-required tools have zero pre-approval execution and one post-reload execution", async () => {
    let executions = 0;
    const events: AgentToolTraceEvent[] = [];
    const tool = safeTool("safe.write", async () => {
      executions += 1;
      return { summary: "write committed", durationMs: 4, retryable: false };
    }, { risk: "approval-required" });
    const registry = createAgentToolRegistry([tool]);
    const firstRunner = createAgentToolRunner({ registry, nowEpochMilliseconds: () => 10, onEvent: (event) => events.push(event) });
    const call = { callId: "call:approval", toolName: "safe.write", idempotencyKey: "idem:approval", input: { value: "approved" } } as const;
    const pending = await firstRunner.request(call);
    expect(pending).toMatchObject({ kind: "pending_approval", approvalId: "approval:call:approval" });
    expect(executions).toBe(0);
    const secondRunner = createAgentToolRunner({ registry, nowEpochMilliseconds: () => 11, onEvent: (event) => events.push(event) });
    secondRunner.restore(firstRunner.snapshot());
    const completed = await secondRunner.resolveApproval({ approvalId: "approval:call:approval", resolution: "approved", call });
    expect(completed).toMatchObject({ kind: "completed", summary: "write committed" });
    expect(executions).toBe(1);
    expect(events.filter((event) => event.kind === "tool_result")).toHaveLength(1);
  });

  test("denial, expiry, cancellation, timeout, and unsafe results never create a false success", async () => {
    let executions = 0;
    const scheduler = new DeterministicToolScheduler();
    const registry = createAgentToolRegistry([
      safeTool("safe.denied", async () => {
        executions += 1;
        return { summary: "should not run", durationMs: 1, retryable: false };
      }, { risk: "approval-required" }),
      safeTool("safe.hang", () => new Promise(() => {}), { timeoutMs: 5, retryable: true }),
      safeTool("safe.unsafe", async () => ({ summary: "token=secret", durationMs: 1, retryable: false })),
    ]);
    const deny = createAgentToolRunner({
      registry,
      nowEpochMilliseconds: () => scheduler.now,
      scheduler,
      policy: () => ({ kind: "deny", code: "tool_denied", reason: "Not allowed" }),
    });
    expect(await deny.request({ callId: "call:deny", toolName: "safe.denied", idempotencyKey: "idem:deny", input: {} })).toMatchObject({ kind: "failed", code: "tool_denied" });
    expect(executions).toBe(0);

    const expiry = createAgentToolRunner({ registry, nowEpochMilliseconds: () => scheduler.now, scheduler });
    const pending = await expiry.request({ callId: "call:expire", toolName: "safe.denied", idempotencyKey: "idem:expire", input: {} });
    scheduler.advance(60_000);
    expect(await expiry.resolveApproval({ approvalId: "approval:call:expire", resolution: "approved", call: { callId: "call:expire", toolName: "safe.denied", idempotencyKey: "idem:expire", input: {} } })).toMatchObject({ kind: "failed", code: "approval_expired" });
    expect(pending.kind).toBe("pending_approval");
    const cancelled = createAgentToolRunner({ registry, nowEpochMilliseconds: () => scheduler.now, scheduler });
    await cancelled.request({ callId: "call:cancel", toolName: "safe.denied", idempotencyKey: "idem:cancel", input: {} });
    cancelled.cancel("call:cancel");
    expect(await cancelled.request({ callId: "call:cancel", toolName: "safe.denied", idempotencyKey: "idem:cancel", input: {} })).toMatchObject({ kind: "cancelled" });

    const timeout = createAgentToolRunner({ registry, nowEpochMilliseconds: () => scheduler.now, scheduler });
    const timed = timeout.request({ callId: "call:timeout", toolName: "safe.hang", idempotencyKey: "idem:timeout", input: {} });
    scheduler.advance(5);
    expect(await timed).toMatchObject({ kind: "failed", code: "tool_timeout" });
    expect(await timeout.request({ callId: "call:unsafe", toolName: "safe.unsafe", idempotencyKey: "idem:unsafe", input: {} })).toMatchObject({ kind: "failed", code: "tool_result_redaction_failed" });
    const cyclic: { self?: unknown } = {};
    cyclic.self = cyclic;
    expect(await timeout.request({ callId: "call:cyclic", toolName: "safe.hang", idempotencyKey: "idem:cyclic", input: cyclic })).toMatchObject({ kind: "failed", code: "tool_invalid_input" });
  });
});
