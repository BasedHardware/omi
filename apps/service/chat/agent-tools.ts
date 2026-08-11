// domain-pending(DIV-CHAT-TOOL-001)

import { createHash } from "node:crypto";

export const AGENT_TOOL_SCHEMA_VERSION = 1 as const;
const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const SAFE_HASH = /^sha256:[0-9a-f]{64}$/u;
const CONTROL = /[\u0000-\u001f\u007f]/u;
const SUMMARY_MAX = 240;

const canonicalJson = (value: unknown, seen = new WeakSet<object>()): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (seen.has(value)) throw new TypeError("cyclic tool input");
  seen.add(value);
  if (Array.isArray(value)) {
    const result = `[${value.map((entry) => canonicalJson(entry, seen)).join(",")}]`;
    seen.delete(value);
    return result;
  }
  const result = `{${Object.keys(value as Record<string, unknown>).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key], seen)}`).join(",")}}`;
  seen.delete(value);
  return result;
};

const hashInput = (input: unknown): string | null => {
  try {
    return `sha256:${createHash("sha256").update(canonicalJson(input), "utf8").digest("hex")}`;
  } catch {
    return null;
  }
};

const safeSummary = (value: unknown): string | null => {
  if (typeof value !== "string" || value.length === 0 || value.length > SUMMARY_MAX
    || value.trim().length === 0 || CONTROL.test(value)) return null;
  if (/(?:Bearer\s+|sk-[A-Za-z0-9]|(?:api[_. -]?key|authorization|access[_. -]?token|token|secret|password)\s*[:=]|(?:attachment|file|opaque|reference)(?:[_. -]?id)?\s*[:=]|BEGIN\s+.*PRIVATE\s+KEY)/iu.test(value)) {
    return null;
  }
  return value;
};

export type AgentToolRisk = "safe" | "approval-required";

export interface AgentToolExecutionControl {
  readonly cancelled: boolean;
  cancel(): void;
}

export interface AgentToolExecutionResult {
  readonly summary: string;
  readonly durationMs: number;
  readonly retryable: boolean;
}

export interface AgentToolDefinition {
  readonly schemaVersion: typeof AGENT_TOOL_SCHEMA_VERSION;
  readonly name: string;
  readonly risk: AgentToolRisk;
  readonly timeoutMs: number;
  readonly retryable: boolean;
  readonly displaySummary: string;
  readonly validateInput: (input: unknown) => boolean;
  readonly execute: (input: unknown, control: AgentToolExecutionControl) => Promise<AgentToolExecutionResult>;
}

export interface AgentToolRegistry {
  resolve(name: string): AgentToolDefinition | null;
  names(): readonly string[];
}

const validateDefinition = (definition: AgentToolDefinition): void => {
  if (definition.schemaVersion !== AGENT_TOOL_SCHEMA_VERSION || !SAFE_TOKEN.test(definition.name)
    || (definition.risk !== "safe" && definition.risk !== "approval-required")
    || !Number.isSafeInteger(definition.timeoutMs) || definition.timeoutMs <= 0 || definition.timeoutMs > 300_000
    || typeof definition.retryable !== "boolean" || safeSummary(definition.displaySummary) === null
    || typeof definition.validateInput !== "function" || typeof definition.execute !== "function") {
    throw new TypeError("invalid agent tool definition");
  }
};

export const createAgentToolRegistry = (
  definitions: readonly AgentToolDefinition[],
): AgentToolRegistry => {
  const byName = new Map<string, AgentToolDefinition>();
  for (const definition of definitions) {
    validateDefinition(definition);
    if (byName.has(definition.name)) throw new TypeError("duplicate agent tool name");
    byName.set(definition.name, Object.freeze({ ...definition }));
  }
  const names = Object.freeze([...byName.keys()].sort());
  return Object.freeze({
    resolve(name: string): AgentToolDefinition | null {
      return byName.get(name) ?? null;
    },
    names(): readonly string[] {
      return names;
    },
  });
};

export interface AgentToolScheduler {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const realtimeAgentToolScheduler: AgentToolScheduler = Object.freeze({
  setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
});

export type AgentToolPolicyDecision =
  | { readonly kind: "allow" }
  | { readonly kind: "deny"; readonly code: "tool_denied" | "tool_unknown"; readonly reason: string }
  | { readonly kind: "approval_required"; readonly approvalId: string; readonly expiresAt: number; readonly reason: string };

export interface AgentToolPolicyInput {
  readonly callId: string;
  readonly toolName: string;
  readonly risk: AgentToolRisk;
  readonly timeoutMs: number;
  readonly nowEpochMilliseconds: number;
}

export interface AgentToolCallInput {
  readonly callId: string;
  readonly toolName: string;
  readonly idempotencyKey: string;
  readonly input: unknown;
}

export type AgentToolOutcome =
  | { readonly kind: "completed"; readonly callId: string; readonly summary: string; readonly durationMs: number; readonly retryable: boolean }
  | { readonly kind: "pending_approval"; readonly callId: string; readonly approvalId: string; readonly expiresAt: number; readonly reason: string }
  | { readonly kind: "failed"; readonly callId: string; readonly code: string; readonly summary: string; readonly retryable: boolean }
  | { readonly kind: "cancelled"; readonly callId: string; readonly summary: string };

export type AgentToolTraceEvent =
  | { readonly kind: "tool_request"; readonly callId: string; readonly toolName: string; readonly inputHash: string; readonly timeoutMs: number; readonly displaySummary: string }
  | { readonly kind: "tool_progress"; readonly callId: string; readonly toolName: string; readonly status: "running" }
  | { readonly kind: "approval_requested"; readonly callId: string; readonly approvalId: string; readonly expiresAt: number; readonly reason: string }
  | { readonly kind: "approval_resolved"; readonly callId: string; readonly approvalId: string; readonly resolution: "approved" | "denied" | "expired" | "cancelled" }
  | { readonly kind: "tool_result"; readonly callId: string; readonly toolName: string; readonly summary: string; readonly durationMs: number; readonly retryable: boolean }
  | { readonly kind: "tool_error"; readonly callId: string; readonly toolName: string; readonly code: string; readonly summary: string; readonly retryable: boolean };

export interface AgentToolRunnerSnapshot {
  readonly calls: readonly {
    readonly callId: string;
    readonly toolName: string;
    readonly idempotencyKey: string;
    readonly inputHash: string;
    readonly state: "pending_approval" | "completed" | "failed" | "cancelled";
    readonly approvalId: string | null;
    readonly expiresAt: number | null;
    readonly outcome: AgentToolOutcome;
  }[];
}

export interface AgentToolRunner {
  request(input: AgentToolCallInput): Promise<AgentToolOutcome>;
  resolveApproval(input: { readonly approvalId: string; readonly resolution: "approved" | "denied" | "cancelled"; readonly call: AgentToolCallInput }): Promise<AgentToolOutcome>;
  cancel(callId: string): void;
  snapshot(): AgentToolRunnerSnapshot;
  restore(snapshot: unknown): void;
}

interface MutableCallState {
  readonly callId: string;
  readonly toolName: string;
  readonly idempotencyKey: string;
  readonly inputHash: string;
  state: "pending_approval" | "running" | "completed" | "failed" | "cancelled";
  approvalId: string | null;
  expiresAt: number | null;
  outcome: AgentToolOutcome | null;
  input: unknown;
  control: AgentToolExecutionControl | null;
  finish: ((outcome: AgentToolOutcome) => void) | null;
}

export interface AgentToolRunnerOptions {
  readonly registry: AgentToolRegistry;
  readonly nowEpochMilliseconds: () => number;
  readonly scheduler?: AgentToolScheduler;
  readonly policy?: (input: AgentToolPolicyInput) => AgentToolPolicyDecision;
  readonly onEvent?: (event: AgentToolTraceEvent) => void;
}

const unknownOutcome = (callId: string): AgentToolOutcome => ({
  kind: "failed", callId, code: "tool_unknown", summary: "The requested tool is unavailable.", retryable: false,
});

export const createAgentToolRunner = (options: AgentToolRunnerOptions): AgentToolRunner => {
  const states = new Map<string, MutableCallState>();
  const idempotency = new Map<string, string>();
  const scheduler = options.scheduler ?? realtimeAgentToolScheduler;
  const emit = (event: AgentToolTraceEvent): void => {
    try { options.onEvent?.(Object.freeze(event)); } catch { /* tracing cannot strand execution */ }
  };
  const defaultPolicy = (input: AgentToolPolicyInput): AgentToolPolicyDecision => input.risk === "safe"
    ? { kind: "allow" }
    : { kind: "approval_required", approvalId: `approval:${input.callId}`, expiresAt: input.nowEpochMilliseconds + 60_000, reason: "A scoped approval is required." };
  const finish = (state: MutableCallState, outcome: AgentToolOutcome): void => {
    if (state.outcome !== null) return;
    state.outcome = Object.freeze(outcome);
    state.state = outcome.kind === "completed" ? "completed"
      : outcome.kind === "cancelled" ? "cancelled" : outcome.kind === "pending_approval" ? "pending_approval" : "failed";
    state.input = undefined;
    state.control = null;
    state.finish?.(state.outcome);
    state.finish = null;
  };
  const execute = async (state: MutableCallState, definition: AgentToolDefinition): Promise<AgentToolOutcome> => {
    state.state = "running";
    emit({ kind: "tool_progress", callId: state.callId, toolName: state.toolName, status: "running" });
    const input = state.input;
    const control: AgentToolExecutionControl = {
      get cancelled(): boolean { return state.state === "cancelled"; },
      cancel(): void { /* state transition is owned by cancel() */ },
    };
    state.control = control;
    return await new Promise<AgentToolOutcome>((resolve) => {
      state.finish = resolve;
      let settled = false;
      const settle = (outcome: AgentToolOutcome): void => {
        if (settled || state.outcome !== null) return;
        settled = true;
        if (outcome.kind === "completed") {
          emit({ kind: "tool_result", callId: state.callId, toolName: state.toolName, summary: outcome.summary, durationMs: outcome.durationMs, retryable: outcome.retryable });
        } else if (outcome.kind === "failed") {
          emit({ kind: "tool_error", callId: state.callId, toolName: state.toolName, code: outcome.code, summary: outcome.summary, retryable: outcome.retryable });
        }
        finish(state, outcome);
      };
      const timeout = scheduler.setTimeout(() => {
        state.state = "failed";
        settle({ kind: "failed", callId: state.callId, code: "tool_timeout", summary: "The tool timed out.", retryable: definition.retryable });
      }, definition.timeoutMs);
      Promise.resolve().then(() => definition.execute(input, control)).then((result) => {
        if (safeSummary(result.summary) === null || !Number.isSafeInteger(result.durationMs) || result.durationMs < 0
          || typeof result.retryable !== "boolean") {
          settle({ kind: "failed", callId: state.callId, code: "tool_result_redaction_failed", summary: "The tool returned an unsafe result.", retryable: false });
          return;
        }
        settle({ kind: "completed", callId: state.callId, summary: result.summary, durationMs: result.durationMs, retryable: result.retryable });
      }).catch(() => settle({ kind: "failed", callId: state.callId, code: "tool_failed", summary: "The tool failed.", retryable: definition.retryable }))
        .finally(() => scheduler.clearTimeout(timeout));
    });
  };
  const request = async (input: AgentToolCallInput): Promise<AgentToolOutcome> => {
    if (!SAFE_TOKEN.test(input.callId) || !SAFE_TOKEN.test(input.toolName) || !SAFE_TOKEN.test(input.idempotencyKey)) {
      return { kind: "failed", callId: input.callId, code: "tool_invalid_request", summary: "The tool request is invalid.", retryable: false };
    }
    const inputHash = hashInput(input.input);
    if (inputHash === null) {
      return { kind: "failed", callId: input.callId, code: "tool_invalid_input", summary: "The tool request is invalid.", retryable: false };
    }
    const existingId = idempotency.get(input.idempotencyKey);
    if (existingId !== undefined) {
      const existing = states.get(existingId)!;
      return existing.inputHash === inputHash && existing.toolName === input.toolName
        ? existing.outcome ?? { kind: "pending_approval", callId: existing.callId, approvalId: existing.approvalId!, expiresAt: existing.expiresAt!, reason: "Approval is pending." }
        : { kind: "failed", callId: input.callId, code: "tool_idempotency_conflict", summary: "The idempotency key conflicts with another request.", retryable: false };
    }
    const previous = states.get(input.callId);
    if (previous !== undefined) return previous.outcome ?? { kind: "failed", callId: input.callId, code: "tool_in_progress", summary: "The tool call is already in progress.", retryable: false };
    const definition = options.registry.resolve(input.toolName);
    if (definition === null) {
      const outcome = unknownOutcome(input.callId);
      emit({ kind: "tool_error", callId: input.callId, toolName: input.toolName, code: outcome.kind === "failed" ? outcome.code : "tool_unknown", summary: outcome.kind === "failed" ? outcome.summary : "The requested tool is unavailable.", retryable: false });
      return outcome;
    }
    let valid = false;
    try { valid = definition.validateInput(input.input); } catch { valid = false; }
    if (!valid) return { kind: "failed", callId: input.callId, code: "tool_invalid_input", summary: "The tool request is invalid.", retryable: false };
    const state: MutableCallState = {
      callId: input.callId, toolName: input.toolName, idempotencyKey: input.idempotencyKey, inputHash,
      state: "pending_approval", approvalId: null, expiresAt: null, outcome: null, input: input.input,
      control: null, finish: null,
    };
    states.set(state.callId, state);
    idempotency.set(state.idempotencyKey, state.callId);
    emit({ kind: "tool_request", callId: state.callId, toolName: state.toolName, inputHash, timeoutMs: definition.timeoutMs, displaySummary: definition.displaySummary });
    const decision = (options.policy ?? defaultPolicy)({
      callId: state.callId, toolName: definition.name, risk: definition.risk,
      timeoutMs: definition.timeoutMs, nowEpochMilliseconds: options.nowEpochMilliseconds(),
    });
    if (decision.kind === "deny") {
      const outcome: AgentToolOutcome = { kind: "failed", callId: state.callId, code: decision.code, summary: safeSummary(decision.reason) ?? "The tool was denied.", retryable: false };
      emit({ kind: "tool_error", callId: state.callId, toolName: state.toolName, code: outcome.code, summary: outcome.summary, retryable: false });
      finish(state, outcome);
      return outcome;
    }
    if (decision.kind === "approval_required") {
      if (!SAFE_TOKEN.test(decision.approvalId) || !Number.isSafeInteger(decision.expiresAt)
        || decision.expiresAt <= options.nowEpochMilliseconds() || safeSummary(decision.reason) === null) {
        const outcome: AgentToolOutcome = { kind: "failed", callId: state.callId, code: "approval_invalid", summary: "Approval policy was invalid.", retryable: false };
        finish(state, outcome);
        return outcome;
      }
      state.approvalId = decision.approvalId;
      state.expiresAt = decision.expiresAt;
      const outcome: AgentToolOutcome = { kind: "pending_approval", callId: state.callId, approvalId: decision.approvalId, expiresAt: decision.expiresAt, reason: decision.reason };
      emit({ kind: "approval_requested", callId: state.callId, approvalId: decision.approvalId, expiresAt: decision.expiresAt, reason: decision.reason });
      state.outcome = Object.freeze(outcome);
      return outcome;
    }
    state.outcome = null;
    return await execute(state, definition);
  };
  const resolveApproval = async (input: { readonly approvalId: string; readonly resolution: "approved" | "denied" | "cancelled"; readonly call: AgentToolCallInput }): Promise<AgentToolOutcome> => {
    const state = states.get(input.call.callId);
    if (state === undefined || state.state !== "pending_approval" || state.approvalId !== input.approvalId) {
      return { kind: "failed", callId: input.call.callId, code: "approval_unknown", summary: "The approval request is unavailable.", retryable: false };
    }
    state.outcome = null;
    const resolution = input.resolution;
    if (resolution !== "approved") {
      emit({ kind: "approval_resolved", callId: state.callId, approvalId: input.approvalId, resolution });
      const outcome: AgentToolOutcome = resolution === "cancelled"
        ? { kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." }
        : { kind: "failed", callId: state.callId, code: "approval_denied", summary: "Approval was denied.", retryable: false };
      finish(state, outcome);
      return outcome;
    }
    if (state.expiresAt === null || options.nowEpochMilliseconds() >= state.expiresAt) {
      const outcome: AgentToolOutcome = { kind: "failed", callId: state.callId, code: "approval_expired", summary: "Approval expired before execution.", retryable: false };
      emit({ kind: "approval_resolved", callId: state.callId, approvalId: input.approvalId, resolution: "expired" });
      finish(state, outcome);
      return outcome;
    }
    emit({ kind: "approval_resolved", callId: state.callId, approvalId: input.approvalId, resolution });
    if (hashInput(input.call.input) !== state.inputHash) {
      const outcome: AgentToolOutcome = { kind: "failed", callId: state.callId, code: "tool_input_conflict", summary: "The approved input changed.", retryable: false };
      finish(state, outcome);
      return outcome;
    }
    const definition = options.registry.resolve(state.toolName);
    if (definition === null) return unknownOutcome(state.callId);
    state.input = input.call.input;
    return await execute(state, definition);
  };
  const cancel = (callId: string): void => {
    const state = states.get(callId);
    if (state === undefined || (state.outcome !== null && state.outcome.kind !== "pending_approval")) return;
    state.state = "cancelled";
    state.outcome = null;
    state.control?.cancel();
    if (state.finish !== null) {
      const outcome: AgentToolOutcome = { kind: "cancelled", callId, summary: "The tool call was cancelled." };
      emit({ kind: "tool_error", callId, toolName: state.toolName, code: "tool_cancelled", summary: outcome.summary, retryable: false });
      finish(state, outcome);
    } else if (state.approvalId !== null) {
      emit({ kind: "approval_resolved", callId, approvalId: state.approvalId, resolution: "cancelled" });
      finish(state, { kind: "cancelled", callId, summary: "The tool call was cancelled." });
    }
  };
  const snapshot = (): AgentToolRunnerSnapshot => Object.freeze({
    calls: Object.freeze([...states.values()].map((state) => Object.freeze({
      callId: state.callId, toolName: state.toolName, idempotencyKey: state.idempotencyKey,
      inputHash: state.inputHash, state: state.state === "running" ? "failed" : state.state,
      approvalId: state.approvalId, expiresAt: state.expiresAt,
      outcome: state.outcome ?? { kind: "failed", callId: state.callId, code: "tool_recovery_required", summary: "The tool requires recovery.", retryable: true },
    }))),
  });
  const restore = (raw: unknown): void => {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new TypeError("invalid tool runner snapshot");
    const calls = (raw as { calls?: unknown }).calls;
    if (!Array.isArray(calls)) throw new TypeError("invalid tool runner snapshot");
    const next = new Map<string, MutableCallState>();
    const nextIdempotency = new Map<string, string>();
    for (const value of calls) {
      if (value === null || typeof value !== "object") throw new TypeError("invalid tool runner call snapshot");
      const item = value as Partial<AgentToolRunnerSnapshot["calls"][number]>;
      if (typeof item.callId !== "string" || !SAFE_TOKEN.test(item.callId) || typeof item.toolName !== "string"
        || !SAFE_TOKEN.test(item.toolName) || typeof item.idempotencyKey !== "string" || !SAFE_TOKEN.test(item.idempotencyKey)
        || typeof item.inputHash !== "string" || !SAFE_HASH.test(item.inputHash)
        || (item.state !== "pending_approval" && item.state !== "completed" && item.state !== "failed" && item.state !== "cancelled")
        || next.has(item.callId) || nextIdempotency.has(item.idempotencyKey) || item.outcome === undefined) {
        throw new TypeError("invalid tool runner call snapshot");
      }
      const state: MutableCallState = {
        callId: item.callId, toolName: item.toolName, idempotencyKey: item.idempotencyKey,
        inputHash: item.inputHash, state: item.state, approvalId: item.approvalId ?? null,
        expiresAt: item.expiresAt ?? null, outcome: item.outcome, input: undefined, control: null, finish: null,
      };
      next.set(state.callId, state);
      nextIdempotency.set(state.idempotencyKey, state.callId);
    }
    states.clear();
    idempotency.clear();
    for (const [key, value] of next) states.set(key, value);
    for (const [key, value] of nextIdempotency) idempotency.set(key, value);
  };
  return Object.freeze({ request, resolveApproval, cancel, snapshot, restore });
};
