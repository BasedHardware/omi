/** Strict, privacy-reducing observation of the Chat agent-run SSE resource. */

import {
  CHAT_AGENT_RUN_STREAM_CHANNEL,
  type BridgePayloadStream,
  type BridgeStreamPort,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";

export type AgentRunCapabilityTier = "deterministic-scripted" | "real-provider" | "unknown";
export type AgentRunStatus =
  | "queued"
  | "gathering_context"
  | "generating"
  | "using_tool"
  | "waiting_approval"
  | "reconnecting"
  | "recovering"
  | "cancelled"
  | "failed"
  | "complete";
export type AgentRunRecoveryAction = "retry" | "reconnect" | "resume" | "manual";

export type AgentRunUiEvent =
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "run_accepted"; readonly safeSummary: string; readonly details: Readonly<Record<string, never>> }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "capability_receipt"; readonly safeSummary: string; readonly details: { readonly tier: AgentRunCapabilityTier; readonly adapter: string; readonly deterministic: boolean } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "context_receipt"; readonly safeSummary: string; readonly details: { readonly sourceKind: string; readonly redactedPreview: string; readonly tokenEstimate: number; readonly inclusionReason: string; readonly policyDecision: "included" | "excluded" | "degraded" } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "status"; readonly safeSummary: string; readonly details: { readonly status: AgentRunStatus; readonly progressPct: number | null } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "tool_request"; readonly safeSummary: string; readonly details: { readonly toolName: string; readonly timeoutMs: number } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "tool_result"; readonly safeSummary: string; readonly details: { readonly toolName: string; readonly resultSummary: string; readonly durationMs: number; readonly retryable: boolean } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "tool_error"; readonly safeSummary: string; readonly details: { readonly toolName: string; readonly errorCode: string; readonly errorSummary: string; readonly retryable: boolean } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "approval_requested"; readonly safeSummary: string; readonly details: { readonly reason: string; readonly expiresAt: number } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "approval_resolved"; readonly safeSummary: string; readonly details: { readonly resolution: "approved" | "denied" | "expired" | "cancelled" } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "usage"; readonly safeSummary: string; readonly details: { readonly inputTokens: number; readonly outputTokens: number; readonly totalTokens: number; readonly durationMs: number } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "recovery"; readonly safeSummary: string; readonly details: { readonly action: AgentRunRecoveryAction; readonly reason: string } }
  | { readonly sequence: number; readonly createdAt: number; readonly kind: "terminal"; readonly safeSummary: string; readonly details: { readonly terminalOutcome: "completed" | "degraded" | "failed" | "cancelled"; readonly terminalCode: string; readonly retryable: boolean; readonly recoveryAction: AgentRunRecoveryAction | null } };

export interface ParsedAgentRunEvent {
  readonly id: string;
  /** Transport-only ownership check; never part of AgentRunUiEvent. */
  readonly runId: string;
  readonly event: AgentRunUiEvent;
}

const EVENT_KINDS = [
  "run_accepted", "capability_receipt", "context_receipt", "status", "tool_request",
  "tool_result", "tool_error", "approval_requested", "approval_resolved", "usage",
  "recovery", "terminal",
] as const;
const STATUS_VALUES = [
  "queued", "gathering_context", "generating", "using_tool", "waiting_approval",
  "reconnecting", "recovering", "cancelled", "failed", "complete",
] as const;
const TERMINAL_CODES = [
  "completed", "cancelled", "generation_provider_failed", "generation_context_failed",
  "generation_attachment_failed", "generation_interrupted", "generation_timeout", "tool_failed",
  "approval_denied", "approval_expired", "recovery_exhausted",
] as const;
const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/u;
const SECRET_LIKE = /(?:Bearer\s+|sk-[A-Za-z0-9]|BEGIN\s+.*PRIVATE\s+KEY|(?:api[_. -]?key|authorization|access[_. -]?token|token|secret|password|attachment|file|opaque|reference)(?:[_. -]?(?:id|ids|ref|refs|reference|references))?\s*[:=]\s*\S+)/iu;
const SENSITIVE_IDENTIFIER = /(?:secret|token|password|authorization|credential|oauth|jwt|bearer)/iu;
const PRIVATE_MARKER = /\b(?:admission|attempt|call|approval|context[_. -]?receipt|event|recovery|run)[_. -]?id\b|\braw[_. -]?(?:arguments?|args?)\b|\b(?:opaque|reference)(?:[_. -]?(?:id|ids|ref|refs|reference|references))?\b/iu;

type WireRecord = Record<string, unknown> & {
  runId?: unknown; attemptId?: unknown; eventId?: unknown; sequence?: unknown; createdAt?: unknown;
  kind?: unknown; safeSummary?: unknown; details?: unknown; admissionId?: unknown; tier?: unknown;
  adapter?: unknown; deterministic?: unknown; contextReceiptId?: unknown; sourceKind?: unknown;
  redactedPreview?: unknown; tokenEstimate?: unknown; inclusionReason?: unknown;
  policyDecision?: unknown; status?: unknown; progressPct?: unknown; callId?: unknown;
  toolName?: unknown; timeoutMs?: unknown; resultSummary?: unknown; durationMs?: unknown;
  retryable?: unknown; errorCode?: unknown; errorSummary?: unknown; approvalId?: unknown;
  reason?: unknown; expiresAt?: unknown; resolution?: unknown; inputTokens?: unknown;
  outputTokens?: unknown; totalTokens?: unknown; recoveryId?: unknown; action?: unknown;
  terminalOutcome?: unknown; terminalCode?: unknown; recoveryAction?: unknown;
};

function record(input: unknown): WireRecord | null {
  if (input === null || typeof input !== "object" || Array.isArray(input)) return null;
  const prototype = Object.getPrototypeOf(input);
  return prototype === Object.prototype || prototype === null
    ? input as WireRecord
    : null;
}

function exactKeys(value: WireRecord, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function token(value: unknown): value is string {
  return typeof value === "string" && SAFE_TOKEN.test(value);
}

function safeIdentifier(value: unknown): value is string {
  return token(value) && !SENSITIVE_IDENTIFIER.test(value) && !PRIVATE_MARKER.test(value);
}

function summary(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 240 &&
    value.trim().length > 0 && !CONTROL_CHARACTERS.test(value)
    && !SECRET_LIKE.test(value) && !PRIVATE_MARKER.test(value);
}

function integer(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}

function oneOf<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === "string" && values.includes(value as T);
}

function safeDetailsText(value: unknown): value is string {
  return summary(value);
}

function parseVisibleAgentRunEvent(input: unknown): AgentRunUiEvent | null {
  const value = record(input);
  if (value === null || !exactKeys(value, [
    "runId", "attemptId", "eventId", "sequence", "createdAt", "kind", "safeSummary", "details",
  ]) || !token(value.runId) || !token(value.attemptId) || !token(value.eventId)
    || !integer(value.sequence) || value.sequence === 0 || !integer(value.createdAt)
    || !oneOf(value.kind, EVENT_KINDS) || !summary(value.safeSummary)) return null;
  const details = record(value.details);
  if (details === null) return null;
  const base = { sequence: value.sequence, createdAt: value.createdAt, safeSummary: value.safeSummary };
  switch (value.kind) {
    case "run_accepted":
      return exactKeys(details, ["admissionId"]) && token(details.admissionId)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({}) }) : null;
    case "capability_receipt":
      return exactKeys(details, ["tier", "adapter", "deterministic"])
        && oneOf(details.tier, ["deterministic-scripted", "real-provider", "unknown"] as const)
        && safeIdentifier(details.adapter) && typeof details.deterministic === "boolean"
        && (details.tier === "deterministic-scripted" ? details.deterministic : !details.deterministic)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ tier: details.tier, adapter: details.adapter, deterministic: details.deterministic }) }) : null;
    case "context_receipt":
      return exactKeys(details, ["contextReceiptId", "sourceKind", "redactedPreview", "tokenEstimate", "inclusionReason", "policyDecision"])
        && token(details.contextReceiptId) && safeIdentifier(details.sourceKind) && safeDetailsText(details.redactedPreview)
        && integer(details.tokenEstimate) && safeDetailsText(details.inclusionReason)
        && oneOf(details.policyDecision, ["included", "excluded", "degraded"] as const)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ sourceKind: details.sourceKind, redactedPreview: details.redactedPreview, tokenEstimate: details.tokenEstimate, inclusionReason: details.inclusionReason, policyDecision: details.policyDecision }) }) : null;
    case "status":
      return exactKeys(details, ["status", "progressPct"]) && oneOf(details.status, STATUS_VALUES)
        && (details.progressPct === null || integer(details.progressPct, 100))
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ status: details.status, progressPct: details.progressPct as number | null }) }) : null;
    case "tool_request":
      return exactKeys(details, ["callId", "toolName", "timeoutMs"]) && token(details.callId)
        && safeIdentifier(details.toolName) && integer(details.timeoutMs, 300_000) && details.timeoutMs > 0
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, timeoutMs: details.timeoutMs }) }) : null;
    case "tool_result":
      return exactKeys(details, ["callId", "toolName", "resultSummary", "durationMs", "retryable"])
        && token(details.callId) && safeIdentifier(details.toolName) && safeDetailsText(details.resultSummary)
        && integer(details.durationMs) && typeof details.retryable === "boolean"
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, resultSummary: details.resultSummary, durationMs: details.durationMs, retryable: details.retryable }) }) : null;
    case "tool_error":
      return exactKeys(details, ["callId", "toolName", "errorCode", "errorSummary", "retryable"])
        && token(details.callId) && safeIdentifier(details.toolName) && safeIdentifier(details.errorCode)
        && safeDetailsText(details.errorSummary) && typeof details.retryable === "boolean"
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, errorCode: details.errorCode, errorSummary: details.errorSummary, retryable: details.retryable }) }) : null;
    case "approval_requested":
      return exactKeys(details, ["approvalId", "callId", "reason", "expiresAt"])
        && token(details.approvalId) && token(details.callId) && safeDetailsText(details.reason)
        && integer(details.expiresAt) && details.expiresAt > value.createdAt
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ reason: details.reason, expiresAt: details.expiresAt }) }) : null;
    case "approval_resolved":
      return exactKeys(details, ["approvalId", "callId", "resolution"])
        && token(details.approvalId) && token(details.callId)
        && oneOf(details.resolution, ["approved", "denied", "expired", "cancelled"] as const)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ resolution: details.resolution }) }) : null;
    case "usage":
      return exactKeys(details, ["inputTokens", "outputTokens", "totalTokens", "durationMs"])
        && integer(details.inputTokens) && integer(details.outputTokens) && integer(details.totalTokens)
        && details.totalTokens === details.inputTokens + details.outputTokens && integer(details.durationMs)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ inputTokens: details.inputTokens, outputTokens: details.outputTokens, totalTokens: details.totalTokens, durationMs: details.durationMs }) }) : null;
    case "recovery":
      return exactKeys(details, ["recoveryId", "action", "reason"]) && token(details.recoveryId)
        && oneOf(details.action, ["retry", "reconnect", "resume", "manual"] as const)
        && safeDetailsText(details.reason)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ action: details.action, reason: details.reason }) }) : null;
    case "terminal":
      return exactKeys(details, ["terminalOutcome", "terminalCode", "retryable", "recoveryAction"])
        && oneOf(details.terminalOutcome, ["completed", "degraded", "failed", "cancelled"] as const)
        && oneOf(details.terminalCode, TERMINAL_CODES) && typeof details.retryable === "boolean"
        && (details.recoveryAction === null || oneOf(details.recoveryAction, ["retry", "reconnect", "resume", "manual"] as const))
        && ((details.terminalOutcome === "completed" && details.terminalCode === "completed" && !details.retryable && details.recoveryAction === null)
          || (details.terminalOutcome === "cancelled" && details.terminalCode === "cancelled" && !details.retryable)
          || ((details.terminalOutcome === "failed" || details.terminalOutcome === "degraded")
            && details.terminalCode !== "completed" && details.terminalCode !== "cancelled"))
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ terminalOutcome: details.terminalOutcome, terminalCode: details.terminalCode, retryable: details.retryable, recoveryAction: details.recoveryAction as AgentRunRecoveryAction | null }) }) : null;
  }
}

/** Revalidates a detached UI event before it is restored from durable storage. */
export function parseStoredAgentRunUiEvent(input: unknown): AgentRunUiEvent | null {
  const value = record(input);
  if (value === null || !exactKeys(value, ["sequence", "createdAt", "kind", "safeSummary", "details"])
    || !integer(value.sequence) || value.sequence === 0 || !integer(value.createdAt)
    || !oneOf(value.kind, EVENT_KINDS) || !summary(value.safeSummary)) return null;
  const details = record(value.details);
  if (details === null) return null;
  const base = { sequence: value.sequence, createdAt: value.createdAt, safeSummary: value.safeSummary };
  switch (value.kind) {
    case "run_accepted":
      return exactKeys(details, []) ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({}) }) : null;
    case "capability_receipt":
      return exactKeys(details, ["tier", "adapter", "deterministic"])
        && oneOf(details.tier, ["deterministic-scripted", "real-provider", "unknown"] as const)
        && safeIdentifier(details.adapter) && typeof details.deterministic === "boolean"
        && (details.tier === "deterministic-scripted" ? details.deterministic : !details.deterministic)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ tier: details.tier, adapter: details.adapter, deterministic: details.deterministic }) }) : null;
    case "context_receipt":
      return exactKeys(details, ["sourceKind", "redactedPreview", "tokenEstimate", "inclusionReason", "policyDecision"])
        && safeIdentifier(details.sourceKind) && safeDetailsText(details.redactedPreview) && integer(details.tokenEstimate)
        && safeDetailsText(details.inclusionReason) && oneOf(details.policyDecision, ["included", "excluded", "degraded"] as const)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ sourceKind: details.sourceKind, redactedPreview: details.redactedPreview, tokenEstimate: details.tokenEstimate, inclusionReason: details.inclusionReason, policyDecision: details.policyDecision }) }) : null;
    case "status":
      return exactKeys(details, ["status", "progressPct"]) && oneOf(details.status, STATUS_VALUES)
        && (details.progressPct === null || integer(details.progressPct, 100))
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ status: details.status, progressPct: details.progressPct as number | null }) }) : null;
    case "tool_request":
      return exactKeys(details, ["toolName", "timeoutMs"]) && safeIdentifier(details.toolName)
        && integer(details.timeoutMs, 300_000) && details.timeoutMs > 0
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, timeoutMs: details.timeoutMs }) }) : null;
    case "tool_result":
      return exactKeys(details, ["toolName", "resultSummary", "durationMs", "retryable"])
        && safeIdentifier(details.toolName) && safeDetailsText(details.resultSummary) && integer(details.durationMs)
        && typeof details.retryable === "boolean"
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, resultSummary: details.resultSummary, durationMs: details.durationMs, retryable: details.retryable }) }) : null;
    case "tool_error":
      return exactKeys(details, ["toolName", "errorCode", "errorSummary", "retryable"])
        && safeIdentifier(details.toolName) && safeIdentifier(details.errorCode) && safeDetailsText(details.errorSummary)
        && typeof details.retryable === "boolean"
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ toolName: details.toolName, errorCode: details.errorCode, errorSummary: details.errorSummary, retryable: details.retryable }) }) : null;
    case "approval_requested":
      return exactKeys(details, ["reason", "expiresAt"]) && safeDetailsText(details.reason)
        && integer(details.expiresAt) && details.expiresAt > value.createdAt
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ reason: details.reason, expiresAt: details.expiresAt }) }) : null;
    case "approval_resolved":
      return exactKeys(details, ["resolution"]) && oneOf(details.resolution, ["approved", "denied", "expired", "cancelled"] as const)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ resolution: details.resolution }) }) : null;
    case "usage":
      return exactKeys(details, ["inputTokens", "outputTokens", "totalTokens", "durationMs"])
        && integer(details.inputTokens) && integer(details.outputTokens) && integer(details.totalTokens)
        && details.totalTokens === details.inputTokens + details.outputTokens && integer(details.durationMs)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ inputTokens: details.inputTokens, outputTokens: details.outputTokens, totalTokens: details.totalTokens, durationMs: details.durationMs }) }) : null;
    case "recovery":
      return exactKeys(details, ["action", "reason"]) && oneOf(details.action, ["retry", "reconnect", "resume", "manual"] as const)
        && safeDetailsText(details.reason)
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ action: details.action, reason: details.reason }) }) : null;
    case "terminal":
      return exactKeys(details, ["terminalOutcome", "terminalCode", "retryable", "recoveryAction"])
        && oneOf(details.terminalOutcome, ["completed", "degraded", "failed", "cancelled"] as const)
        && oneOf(details.terminalCode, TERMINAL_CODES) && typeof details.retryable === "boolean"
        && (details.recoveryAction === null || oneOf(details.recoveryAction, ["retry", "reconnect", "resume", "manual"] as const))
        && ((details.terminalOutcome === "completed" && details.terminalCode === "completed" && !details.retryable && details.recoveryAction === null)
          || (details.terminalOutcome === "cancelled" && details.terminalCode === "cancelled" && !details.retryable)
          || ((details.terminalOutcome === "failed" || details.terminalOutcome === "degraded")
            && details.terminalCode !== "completed" && details.terminalCode !== "cancelled"))
        ? Object.freeze({ ...base, kind: value.kind, details: Object.freeze({ terminalOutcome: details.terminalOutcome, terminalCode: details.terminalCode, retryable: details.retryable, recoveryAction: details.recoveryAction as AgentRunRecoveryAction | null }) }) : null;
  }
}

/** Stateful UTF-8 SSE parser. Every field and Unicode scalar may be split. */
export class IncrementalAgentRunParser {
  private readonly decoder = new TextDecoder("utf-8", { fatal: true });
  private text = "";
  private eventName: string | null = null;
  private eventId: string | null = null;
  private data: string[] = [];

  push(chunk: Uint8Array | string): readonly ParsedAgentRunEvent[] {
    this.text += typeof chunk === "string" ? chunk : this.decoder.decode(chunk, { stream: true });
    return this.drain(false);
  }

  finish(): readonly ParsedAgentRunEvent[] {
    this.text += this.decoder.decode();
    const events = this.drain(true);
    if (this.eventName !== null || this.eventId !== null || this.data.length > 0) {
      throw new Error("truncated agent-run SSE event at stream end");
    }
    return events;
  }

  private drain(finishing: boolean): ParsedAgentRunEvent[] {
    const events: ParsedAgentRunEvent[] = [];
    while (this.text.length > 0) {
      let end = -1;
      let width = 0;
      for (let index = 0; index < this.text.length; index += 1) {
        if (this.text[index] === "\n") { end = index; width = 1; break; }
        if (this.text[index] === "\r") {
          if (index === this.text.length - 1 && !finishing) return events;
          end = index; width = this.text[index + 1] === "\n" ? 2 : 1; break;
        }
      }
      if (end < 0) {
        if (!finishing) return events;
        const line = this.text; this.text = ""; this.consume(line, events); return events;
      }
      const line = this.text.slice(0, end);
      this.text = this.text.slice(end + width);
      this.consume(line, events);
    }
    return events;
  }

  private consume(line: string, events: ParsedAgentRunEvent[]): void {
    if (line === "") {
      const event = this.dispatch();
      if (event !== null) events.push(event);
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventName = value;
    else if (field === "id") {
      if (value.includes("\u0000")) throw new Error("agent-run SSE id contains NUL");
      this.eventId = value;
    } else if (field === "data") this.data.push(value);
  }

  private dispatch(): ParsedAgentRunEvent | null {
    if (this.data.length === 0) { this.reset(); return null; }
    const name = this.eventName;
    const id = this.eventId;
    const data = this.data.join("\n");
    this.reset();
    if (name === null || name === "" || id === null || id === "") {
      throw new Error("agent-run SSE event requires opaque id and event name");
    }
    let raw: unknown;
    try { raw = JSON.parse(data) as unknown; } catch { throw new Error("agent-run SSE data is not JSON"); }
    const parsed = parseVisibleAgentRunEvent(raw);
    if (parsed === null || parsed.kind !== name) throw new Error("invalid agent-run SSE event");
    const wire = record(raw);
    if (wire?.eventId !== id) throw new Error("agent-run SSE id does not match its event");
    return Object.freeze({ id, runId: wire.runId as string, event: parsed });
  }

  private reset(): void {
    this.eventName = null;
    this.eventId = null;
    this.data = [];
  }
}

export type AgentRunObservationEvent =
  | { readonly kind: "event"; readonly id: string; readonly event: AgentRunUiEvent }
  | { readonly kind: "error"; readonly failure: string };

export interface AgentRunObservation {
  readonly events: AsyncIterable<AgentRunObservationEvent>;
  cancel(reason?: string): void;
}

const RECONNECT_DELAYS_MS = [250, 500, 1_000, 2_000, 4_000] as const;

/** Observe one run by exact opaque cursor; observation never mutates the run. */
export function observeAgentRun(
  streamPort: BridgeStreamPort,
  generationId: string,
  env: Env,
  resumeAfterEventId?: string,
): AgentRunObservation {
  let cancelled = false;
  let active: BridgePayloadStream | null = null;
  let cancelDelay: (() => void) | null = null;
  let cursor = resumeAfterEventId;
  let lastSequence: number | null = null;
  const seen = new Set<string>();

  const cancel = (reason?: string): void => {
    if (cancelled) return;
    cancelled = true;
    active?.cancel(reason ?? "agent-run-observation-cancelled");
    cancelDelay?.();
  };
  const delay = async (milliseconds: number): Promise<void> => {
    await new Promise<void>((resolve) => {
      let settled = false;
      let clear = (): void => undefined;
      const finish = (): void => {
        if (settled) return;
        settled = true;
        clear();
        cancelDelay = null;
        resolve();
      };
      clear = env.delay(milliseconds, finish);
      cancelDelay = finish;
      if (cancelled) finish();
    });
  };

  const events = (async function* (): AsyncGenerator<AgentRunObservationEvent> {
    if (!token(generationId)) { yield { kind: "error", failure: "generation id is invalid" }; return; }
    let reconnect = 0;
    while (!cancelled) {
      let replayedCursor = cursor;
      try {
        active = streamPort.open({
          channel: CHAT_AGENT_RUN_STREAM_CHANNEL,
          params: JSON.stringify({ generationId, ...(cursor === undefined ? {} : { lastEventId: cursor }) }),
          initialCredit: 4,
        });
      } catch (error) {
        yield { kind: "error", failure: String(error) };
        return;
      }
      const parser = new IncrementalAgentRunParser();
      let advanced = false;
      try {
        const consume = function* (parsed: readonly ParsedAgentRunEvent[]): Generator<ParsedAgentRunEvent> {
          for (const item of parsed) {
            if (item.runId !== generationId) throw new Error("agent-run event belongs to another generation");
            // Some transports echo the reconnect cursor once. It is already
            // durable and must not be surfaced twice; any later reuse remains
            // corruption and fails closed.
            if (replayedCursor !== undefined && item.id === replayedCursor) {
              replayedCursor = undefined;
              continue;
            }
            if (seen.has(item.id)) throw new Error("agent-run event cursor was reused");
            if (lastSequence !== null && item.event.sequence <= lastSequence) {
              throw new Error("agent-run event sequence did not advance");
            }
            if (cursor === undefined && lastSequence === null && item.event.kind !== "run_accepted") {
              throw new Error("agent-run connection omitted run acceptance");
            }
            seen.add(item.id);
            cursor = item.id;
            lastSequence = item.event.sequence;
            advanced = true;
            yield item;
          }
        };
        for await (const chunk of active) {
          for (const item of consume(parser.push(chunk))) {
            yield { kind: "event", id: item.id, event: item.event };
            if (item.event.kind === "terminal") { cancel("agent-run-terminal-observed"); return; }
          }
        }
        for (const item of consume(parser.finish())) {
          yield { kind: "event", id: item.id, event: item.event };
          if (item.event.kind === "terminal") { cancel("agent-run-terminal-observed"); return; }
        }
      } catch (error) {
        active?.cancel("agent-run-observation-error");
        yield { kind: "error", failure: String(error) };
        return;
      } finally {
        active = null;
      }
      if (cancelled) return;
      if (cursor === undefined) { yield { kind: "error", failure: "agent run disconnected before its first event" }; return; }
      if (advanced) reconnect = 0;
      if (reconnect >= RECONNECT_DELAYS_MS.length) {
        yield { kind: "error", failure: "agent-run observation reconnect limit reached" };
        return;
      }
      await delay(RECONNECT_DELAYS_MS[reconnect++]!);
    }
  })();
  return Object.freeze({ events, cancel });
}
