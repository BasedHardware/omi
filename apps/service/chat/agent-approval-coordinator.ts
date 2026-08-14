// domain-pending(DIV-CHAT-TOOL-001)

import { isProxy } from "node:util/types";

import type { AgentRunEventSupervisor } from "./agent-run-events";
import {
  createAgentToolRunner,
  type AgentToolCallInput,
  type AgentToolOutcome,
  type AgentToolRegistry,
  type AgentToolRunner,
  type AgentToolRunnerSnapshot,
  type AgentToolScheduler,
  type AgentToolTraceEvent,
  realtimeAgentToolScheduler,
} from "./agent-tools";

const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;

export type AgentApprovalResolution = "approved" | "denied" | "cancelled";

export interface AgentApprovalCoordinatorRequest {
  readonly runId: string;
  readonly attemptId: string;
  readonly call: AgentToolCallInput;
}

export interface AgentApprovalCoordinatorResolve {
  readonly runId: string;
  readonly approvalId: string;
  readonly resolution: AgentApprovalResolution;
}

export interface AgentApprovalCoordinatorSnapshot {
  readonly runner: AgentToolRunnerSnapshot;
  readonly pending: readonly {
    readonly runId: string;
    readonly attemptId: string;
    readonly callId: string;
    readonly approvalId: string;
    readonly toolName: string;
    readonly idempotencyKey: string;
    readonly inputHash: string;
  }[];
}

export interface AgentApprovalCoordinator {
  request(input: AgentApprovalCoordinatorRequest): Promise<AgentToolOutcome>;
  resolve(input: AgentApprovalCoordinatorResolve): Promise<AgentToolOutcome>;
  snapshot(): AgentApprovalCoordinatorSnapshot;
  restore(snapshot: unknown): void;
}

export interface AgentApprovalCoordinatorOptions {
  readonly registry: AgentToolRegistry;
  readonly events: AgentRunEventSupervisor;
  readonly nowEpochMilliseconds: () => number;
  readonly scheduler?: AgentToolScheduler;
}

interface PendingApproval {
  readonly runId: string;
  readonly attemptId: string;
  readonly call: AgentToolCallInput;
  readonly approvalId: string;
}

const ownDataRecord = (value: unknown): Record<string, unknown> | null => {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) return null;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const keys = Reflect.ownKeys(value);
    if (keys.some((key) => typeof key !== "string")) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const record = Object.create(null) as Record<string, unknown>;
    for (const key of keys) {
      const descriptor = descriptors[key as string];
      if (descriptor === undefined || !("value" in descriptor)) return null;
      record[key as string] = descriptor.value;
    }
    return record;
  } catch {
    return null;
  }
};

const exactKeys = (record: Record<string, unknown>, expected: readonly string[]): boolean => {
  const actual = Object.keys(record).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

export const createAgentApprovalCoordinator = (
  options: AgentApprovalCoordinatorOptions,
): AgentApprovalCoordinator => {
  const scheduler = options.scheduler ?? realtimeAgentToolScheduler;
  const pendingByRun = new Map<string, PendingApproval>();
  let runner: AgentToolRunner = createRunner();

  function createRunner(): AgentToolRunner {
    return createAgentToolRunner({
      registry: options.registry,
      nowEpochMilliseconds: options.nowEpochMilliseconds,
      scheduler,
      onEvent: (event: AgentToolTraceEvent): void => {
        const call = [...pendingByRun.values()].find((entry) => entry.call.callId === event.callId);
        if (call === undefined) return;
        try {
          if (event.kind === "approval_requested") {
            options.events.status({
              runId: call.runId,
              attemptId: call.attemptId,
              status: "waiting_approval",
              progressPct: null,
            });
            options.events.approvalRequested({
              runId: call.runId,
              attemptId: call.attemptId,
              approvalId: event.approvalId,
              callId: event.callId,
              reason: event.reason,
              expiresAt: event.expiresAt,
            });
          }
          if (event.kind === "approval_resolved") {
            options.events.approvalResolved({
              runId: call.runId,
              attemptId: call.attemptId,
              approvalId: event.approvalId,
              callId: event.callId,
              resolution: event.resolution,
            });
          }
          if (event.kind === "tool_request") {
            options.events.toolRequest({
              runId: call.runId,
              attemptId: call.attemptId,
              callId: event.callId,
              toolName: event.toolName,
              timeoutMs: event.timeoutMs,
              idempotencyKey: call.call.idempotencyKey,
            });
          }
          if (event.kind === "tool_result") {
            options.events.toolResult({
              runId: call.runId,
              attemptId: call.attemptId,
              callId: event.callId,
              toolName: event.toolName,
              resultSummary: event.summary,
              durationMs: event.durationMs,
              retryable: event.retryable,
            });
          }
          if (event.kind === "tool_error") {
            options.events.toolError({
              runId: call.runId,
              attemptId: call.attemptId,
              callId: event.callId,
              toolName: event.toolName,
              errorCode: event.code,
              errorSummary: event.summary,
              retryable: event.retryable,
            });
          }
        } catch {
          // Observability must not strand tool execution.
        }
      },
    });
  }

  const request = async (input: AgentApprovalCoordinatorRequest): Promise<AgentToolOutcome> => {
    if (!SAFE_TOKEN.test(input.runId) || !SAFE_TOKEN.test(input.attemptId)
      || !SAFE_TOKEN.test(input.call.callId) || !SAFE_TOKEN.test(input.call.toolName)
      || !SAFE_TOKEN.test(input.call.idempotencyKey)) {
      return { kind: "failed", callId: input.call.callId, code: "tool_invalid_request",
        summary: "The tool request is invalid.", retryable: false };
    }
    const provisional: PendingApproval = {
      runId: input.runId,
      attemptId: input.attemptId,
      call: input.call,
      approvalId: `approval:${input.call.callId}`,
    };
    pendingByRun.set(input.runId, provisional);
    const outcome = await runner.request(input.call);
    if (outcome.kind === "pending_approval") {
      if (provisional.approvalId !== outcome.approvalId) {
        pendingByRun.set(input.runId, { ...provisional, approvalId: outcome.approvalId });
      }
    } else {
      pendingByRun.delete(input.runId);
    }
    return outcome;
  };

  const resolve = async (input: AgentApprovalCoordinatorResolve): Promise<AgentToolOutcome> => {
    const pending = pendingByRun.get(input.runId);
    if (pending === undefined || pending.approvalId !== input.approvalId) {
      return { kind: "failed", callId: pending?.call.callId ?? "call:unknown",
        code: "approval_unknown", summary: "The approval request is unavailable.", retryable: false };
    }
    const outcome = await runner.resolveApproval({
      approvalId: input.approvalId,
      resolution: input.resolution,
      call: pending.call,
    });
    if (outcome.kind !== "pending_approval") pendingByRun.delete(input.runId);
    return outcome;
  };

  const snapshot = (): AgentApprovalCoordinatorSnapshot => Object.freeze({
    runner: runner.snapshot(),
    pending: Object.freeze([...pendingByRun.values()].map((entry) => Object.freeze({
      runId: entry.runId,
      attemptId: entry.attemptId,
      callId: entry.call.callId,
      approvalId: entry.approvalId,
      toolName: entry.call.toolName,
      idempotencyKey: entry.call.idempotencyKey,
      inputHash: runner.snapshot().calls.find((call) => call.callId === entry.call.callId)?.inputHash ?? "",
    }))),
  });

  const restore = (raw: unknown): void => {
    const record = ownDataRecord(raw);
    if (record === null || !exactKeys(record, ["pending", "runner"])) {
      throw new TypeError("invalid agent approval coordinator snapshot");
    }
    if (!Array.isArray(record.pending)) throw new TypeError("invalid agent approval coordinator snapshot");
    runner = createRunner();
    runner.restore(record.runner);
    pendingByRun.clear();
    for (const value of record.pending) {
      const item = ownDataRecord(value);
      if (item === null || !exactKeys(item, ["approvalId", "attemptId", "callId", "idempotencyKey",
        "inputHash", "runId", "toolName"])
        || !SAFE_TOKEN.test(item.runId) || !SAFE_TOKEN.test(item.attemptId)
        || !SAFE_TOKEN.test(item.callId) || !SAFE_TOKEN.test(item.approvalId)
        || !SAFE_TOKEN.test(item.toolName) || !SAFE_TOKEN.test(item.idempotencyKey)) {
        throw new TypeError("invalid agent approval coordinator pending snapshot");
      }
      const callState = runner.snapshot().calls.find((call) => call.callId === item.callId);
      if (callState === undefined || callState.state !== "pending_approval") {
        throw new TypeError("invalid agent approval coordinator pending snapshot");
      }
      pendingByRun.set(item.runId, {
        runId: item.runId,
        attemptId: item.attemptId,
        approvalId: item.approvalId,
        call: {
          callId: item.callId,
          toolName: item.toolName,
          idempotencyKey: item.idempotencyKey,
          input: {},
        },
      });
    }
  };

  return Object.freeze({ request, resolve, snapshot, restore });
};
