// domain-pending(DIV-CHAT-TOOL-001)

import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

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
  if (/(?:Bearer\s+|sk-[A-Za-z0-9]|(?:api[_. -]?keys?|authorizations?|access[_. -]?tokens?|tokens?|secrets?|passwords?)\s*[:=]|(?:attachments?|files?|opaques?|references?)(?:[_. -]?(?:ids?|refs?|references?))?\s*[:=]|BEGIN\s+.*PRIVATE\s+KEY)/iu.test(value)) {
    return null;
  }
  return value;
};

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

const safeExpiry = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const safeToken = (value: unknown): value is string =>
  typeof value === "string" && SAFE_TOKEN.test(value);

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

const parsePolicyDecision = (value: unknown): AgentToolPolicyDecision | null => {
  const record = ownDataRecord(value);
  if (record === null || typeof record.kind !== "string") return null;
  if (record.kind === "allow") {
    return exactKeys(record, ["kind"]) ? { kind: "allow" } : null;
  }
  if (record.kind === "deny") {
    return exactKeys(record, ["code", "kind", "reason"])
      && (record.code === "tool_denied" || record.code === "tool_unknown")
      && safeSummary(record.reason) !== null
      ? { kind: "deny", code: record.code, reason: record.reason as string }
      : null;
  }
  if (record.kind === "approval_required") {
    return exactKeys(record, ["approvalId", "expiresAt", "kind", "reason"])
      && safeToken(record.approvalId) && safeExpiry(record.expiresAt)
      && safeSummary(record.reason) !== null
      ? { kind: "approval_required", approvalId: record.approvalId as string,
          expiresAt: record.expiresAt as number, reason: record.reason as string }
      : null;
  }
  return null;
};

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

const parseOutcome = (
  raw: unknown,
  callId: string,
): AgentToolOutcome | null => {
  const record = ownDataRecord(raw);
  if (record === null || record.callId !== callId || typeof record.kind !== "string") return null;
  if (record.kind === "completed") {
    if (!exactKeys(record, ["callId", "durationMs", "kind", "retryable", "summary"])
      || !safeSummary(record.summary) || !Number.isSafeInteger(record.durationMs)
      || (record.durationMs as number) < 0 || typeof record.retryable !== "boolean") return null;
    return Object.freeze({ kind: "completed", callId, summary: record.summary, durationMs: record.durationMs, retryable: record.retryable });
  }
  if (record.kind === "failed") {
    if (!exactKeys(record, ["callId", "code", "kind", "retryable", "summary"])
      || !safeToken(record.code) || !safeSummary(record.summary) || typeof record.retryable !== "boolean") return null;
    return Object.freeze({ kind: "failed", callId, code: record.code, summary: record.summary, retryable: record.retryable });
  }
  if (record.kind === "cancelled") {
    if (!exactKeys(record, ["callId", "kind", "summary"]) || !safeSummary(record.summary)) return null;
    return Object.freeze({ kind: "cancelled", callId, summary: record.summary });
  }
  if (record.kind === "pending_approval") {
    if (!exactKeys(record, ["approvalId", "callId", "expiresAt", "kind", "reason"])
      || !safeToken(record.approvalId) || !safeExpiry(record.expiresAt) || !safeSummary(record.reason)) return null;
    return Object.freeze({
      kind: "pending_approval", callId, approvalId: record.approvalId,
      expiresAt: record.expiresAt, reason: record.reason,
    });
  }
  return null;
};

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
  cancelRequested: boolean;
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
    if (state.outcome !== null || state.cancelRequested || state.state === "cancelled") {
      return state.outcome ?? { kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." };
    }
    const input = state.input;
    const control: AgentToolExecutionControl = {
      get cancelled(): boolean { return state.cancelRequested || state.state === "cancelled"; },
      cancel(): void {
        state.cancelRequested = true;
        state.state = "cancelled";
      },
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
      if (state.cancelRequested || state.state === "cancelled") {
        settle({ kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." });
        return;
      }
      const timeout = scheduler.setTimeout(() => {
        state.cancelRequested = true;
        state.state = "failed";
        control.cancel();
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
      cancelRequested: false, control: null, finish: null,
    };
    states.set(state.callId, state);
    idempotency.set(state.idempotencyKey, state.callId);
    emit({ kind: "tool_request", callId: state.callId, toolName: state.toolName, inputHash, timeoutMs: definition.timeoutMs, displaySummary: definition.displaySummary });
    if (state.outcome !== null || state.cancelRequested || state.state === "cancelled") {
      return state.outcome ?? { kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." };
    }
    let decision: AgentToolPolicyDecision | null;
    try {
      decision = parsePolicyDecision((options.policy ?? defaultPolicy)({
        callId: state.callId, toolName: definition.name, risk: definition.risk,
        timeoutMs: definition.timeoutMs, nowEpochMilliseconds: options.nowEpochMilliseconds(),
      }));
    } catch {
      decision = null;
    }
    if (decision === null) {
      const outcome: AgentToolOutcome = {
        kind: "failed", callId: state.callId, code: "tool_policy_failed",
        summary: "The tool policy was unavailable.", retryable: true,
      };
      emit({ kind: "tool_error", callId: state.callId, toolName: state.toolName,
        code: outcome.code, summary: outcome.summary, retryable: outcome.retryable });
      finish(state, outcome);
      return outcome;
    }
    if (state.outcome !== null || state.cancelRequested || state.state === "cancelled") {
      return state.outcome ?? { kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." };
    }
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
      if (state.outcome !== null || state.cancelRequested || state.state === "cancelled") {
        return state.outcome ?? { kind: "cancelled", callId: state.callId, summary: "The tool call was cancelled." };
      }
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
    if (input.call.toolName !== state.toolName || input.call.idempotencyKey !== state.idempotencyKey) {
      const outcome: AgentToolOutcome = {
        kind: "failed", callId: state.callId, code: "tool_input_conflict",
        summary: "The approved tool identity changed.", retryable: false,
      };
      finish(state, outcome);
      return outcome;
    }
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
    if (definition === null) {
      const outcome = unknownOutcome(state.callId);
      emit({ kind: "tool_error", callId: state.callId, toolName: state.toolName,
        code: outcome.kind === "failed" ? outcome.code : "tool_unknown",
        summary: outcome.kind === "failed" ? outcome.summary : "The requested tool is unavailable.",
        retryable: false });
      finish(state, outcome);
      return outcome;
    }
    state.input = input.call.input;
    return await execute(state, definition);
  };
  const cancel = (callId: string): void => {
    const state = states.get(callId);
    if (state === undefined || (state.outcome !== null && state.outcome.kind !== "pending_approval")) return;
    state.cancelRequested = true;
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
    } else {
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
    const snapshot = ownDataRecord(raw);
    if (snapshot === null || !exactKeys(snapshot, ["calls"]) || !Array.isArray(snapshot.calls)) {
      throw new TypeError("invalid tool runner snapshot");
    }
    const next = new Map<string, MutableCallState>();
    const nextIdempotency = new Map<string, string>();
    let now: number;
    try { now = options.nowEpochMilliseconds(); } catch { throw new TypeError("invalid tool runner snapshot clock"); }
    if (!Number.isSafeInteger(now) || now < 0) throw new TypeError("invalid tool runner snapshot clock");
    for (const value of snapshot.calls) {
      const item = ownDataRecord(value);
      if (item === null || !exactKeys(item, ["approvalId", "callId", "expiresAt", "idempotencyKey", "inputHash", "outcome", "state", "toolName"])
        || !safeToken(item.callId) || !safeToken(item.toolName) || !safeToken(item.idempotencyKey)
        || typeof item.inputHash !== "string" || !SAFE_HASH.test(item.inputHash)
        || (item.state !== "pending_approval" && item.state !== "completed" && item.state !== "failed" && item.state !== "cancelled")
        || next.has(item.callId) || nextIdempotency.has(item.idempotencyKey)) {
        throw new TypeError("invalid tool runner call snapshot");
      }
      const toolName = item.toolName;
      const definition = options.registry.resolve(toolName);
      const approvalId = item.approvalId === null ? null : item.approvalId;
      const expiresAt = item.expiresAt === null ? null : item.expiresAt;
      if ((approvalId !== null && !safeToken(approvalId))
        || (expiresAt !== null && !safeExpiry(expiresAt))
        || (approvalId === null) !== (expiresAt === null)) {
        throw new TypeError("invalid tool runner approval snapshot");
      }
      let outcome = parseOutcome(item.outcome, item.callId);
      if (outcome === null) throw new TypeError("invalid tool runner outcome snapshot");
      let parsedState = item.state as MutableCallState["state"];
      if (definition === null) {
        outcome = unknownOutcome(item.callId);
        parsedState = "failed";
      } else if (parsedState === "pending_approval") {
        if (outcome.kind !== "pending_approval" || approvalId !== outcome.approvalId || expiresAt !== outcome.expiresAt) {
          throw new TypeError("invalid tool runner approval snapshot");
        }
        if (now >= outcome.expiresAt) {
          outcome = { kind: "failed", callId: item.callId, code: "approval_expired", summary: "Approval expired before execution.", retryable: false };
          parsedState = "failed";
        }
      } else if ((parsedState === "completed" && outcome.kind !== "completed")
        || (parsedState === "failed" && outcome.kind !== "failed")
        || (parsedState === "cancelled" && outcome.kind !== "cancelled")) {
        throw new TypeError("invalid tool runner outcome state");
      }
      const state: MutableCallState = {
        callId: item.callId, toolName, idempotencyKey: item.idempotencyKey,
        inputHash: item.inputHash, state: parsedState, approvalId, expiresAt,
        outcome, input: undefined, cancelRequested: false, control: null, finish: null,
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
