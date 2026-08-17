import { describe, expect, test } from "bun:test";

import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
} from "./agent-run-events";
import { createAgentApprovalCoordinator } from "./agent-approval-coordinator";
import { createSafeWriteTool, createSafeWriteToolRegistry, SAFE_WRITE_TOOL_NAME } from "./safe-write-tool";

describe("agent approval coordinator", () => {
  let executions = 0;

  const boot = (sharedEvents = createInMemoryAgentRunEventStore()) => {
    let now = 10;
    const events = sharedEvents;
    const supervisor = createAgentRunEventSupervisor({
      events,
      nowEpochMilliseconds: () => now++,
      eventId: (runId, sequence, kind) => `${runId}:${sequence}:${kind}`,
    });
    const registry = createSafeWriteToolRegistry();
    const tool = createSafeWriteTool();
    const coordinator = createAgentApprovalCoordinator({
      registry: {
        ...registry,
        resolve: (name) => name === tool.name
          ? {
            ...tool,
            execute: async () => {
              executions += 1;
              return { summary: "Scoped write recorded.", durationMs: 1, retryable: false };
            },
          }
          : registry.resolve(name),
      },
      events: supervisor,
      nowEpochMilliseconds: () => now,
    });
    return { coordinator, events, supervisor, now: () => now };
  };

  test("safe_write has zero pre-approval execution and one post-reload execution", async () => {
    executions = 0;
    const first = boot();
    const call = {
      callId: "call:write",
      toolName: SAFE_WRITE_TOOL_NAME,
      idempotencyKey: "idem:write",
      input: {},
    } as const;
    first.supervisor.accepted({
      runId: "run:approval",
      attemptId: "run:approval:attempt:1",
      admissionId: "message-approval",
    });
    const pending = await first.coordinator.request({
      runId: "run:approval",
      attemptId: "run:approval:attempt:1",
      call,
    });
    expect(pending).toMatchObject({
      kind: "pending_approval",
      approvalId: "approval:call:write",
      reason: "A scoped approval is required.",
    });
    expect(executions).toBe(0);
    expect(first.events.list("run:approval").map((event) => event.kind)).toEqual([
      "run_accepted", "tool_request", "status", "approval_requested",
    ]);

    const snapshot = first.coordinator.snapshot();
    const sharedEvents = first.events;
    const second = boot(sharedEvents);
    second.coordinator.restore(snapshot);
    const completed = await second.coordinator.resolve({
      runId: "run:approval",
      approvalId: "approval:call:write",
      resolution: "approved",
    });
    expect(completed).toMatchObject({ kind: "completed", summary: "Scoped write recorded." });
    expect(executions).toBe(1);
    expect(second.events.list("run:approval").some((event) => event.kind === "tool_result")).toBe(true);
  });

  test("post-reload approve keeps the original safe_write input", async () => {
    executions = 0;
    const first = boot();
    const call = {
      callId: "call:write-note",
      toolName: SAFE_WRITE_TOOL_NAME,
      idempotencyKey: "idem:write-note",
      input: { note: "scoped note" },
    } as const;
    first.supervisor.accepted({
      runId: "run:approval-note",
      attemptId: "run:approval-note:attempt:1",
      admissionId: "message-approval-note",
    });
    const pending = await first.coordinator.request({
      runId: "run:approval-note",
      attemptId: "run:approval-note:attempt:1",
      call,
    });
    expect(pending.kind).toBe("pending_approval");
    expect(executions).toBe(0);
    const snapshot = first.coordinator.snapshot();
    const second = boot(first.events);
    second.coordinator.restore(snapshot);
    const completed = await second.coordinator.resolve({
      runId: "run:approval-note",
      resolution: "approved",
    });
    expect(completed).toMatchObject({ kind: "completed", summary: "Scoped write recorded." });
    expect(executions).toBe(1);
  });

  test("deny and cancel do not execute", async () => {
    for (const resolution of ["denied", "cancelled"] as const) {
      executions = 0;
      const ctx = boot();
      const call = {
        callId: `call:${resolution}`,
        toolName: SAFE_WRITE_TOOL_NAME,
        idempotencyKey: `idem:${resolution}`,
        input: {},
      } as const;
      ctx.supervisor.accepted({
        runId: `run:${resolution}`,
        attemptId: `run:${resolution}:attempt:1`,
        admissionId: `message-${resolution}`,
      });
      const pending = await ctx.coordinator.request({
        runId: `run:${resolution}`,
        attemptId: `run:${resolution}:attempt:1`,
        call,
      });
      expect(pending.kind).toBe("pending_approval");
      const outcome = await ctx.coordinator.resolve({
        runId: `run:${resolution}`,
        approvalId: `approval:call:${resolution}`,
        resolution,
      });
      expect(outcome.kind).not.toBe("completed");
      expect(executions).toBe(0);
      expect(ctx.events.list(`run:${resolution}`).some((event) => event.kind === "tool_result")).toBe(false);
    }
  });
});
