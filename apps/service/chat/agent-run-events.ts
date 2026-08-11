// domain-pending(DIV-CHAT-SOURCE-001)

/**
 * Versioned, append-only agent-run events. This is deliberately a separate
 * ledger from the existing text-generation frames: old text frames retain
 * their wire shape while agent state gets a strict, privacy-safe contract.
 */

export const CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION = 1 as const;
export const PREVIOUS_AGENT_RUN_EVENT_SCHEMA_VERSION = 0 as const;
/**
 * Version 0 is the initial compatibility encoding. Its field set is
 * intentionally identical to v1; parsing v0 detaches it into the current v1
 * in-memory representation before it can enter a store or projection.
 */
export const SUPPORTED_AGENT_RUN_EVENT_SCHEMA_VERSIONS = Object.freeze([
  PREVIOUS_AGENT_RUN_EVENT_SCHEMA_VERSION,
  CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
] as const);

export type AgentRunEventSchemaVersion =
  | typeof PREVIOUS_AGENT_RUN_EVENT_SCHEMA_VERSION
  | typeof CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION;
export type AgentRunEventVisibility = "ui" | "internal";

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

export type AgentRunTerminalOutcome = "completed" | "degraded" | "failed" | "cancelled";
export type AgentRunTerminalCode =
  | "completed"
  | "cancelled"
  | "generation_provider_failed"
  | "generation_context_failed"
  | "generation_attachment_failed"
  | "generation_interrupted"
  | "generation_timeout"
  | "tool_failed"
  | "approval_denied"
  | "approval_expired"
  | "recovery_exhausted";
export type AgentRunApprovalResolution = "approved" | "denied" | "expired" | "cancelled";
export type AgentRunRecoveryAction = "retry" | "reconnect" | "resume" | "manual";

interface AgentRunEventBase {
  readonly schemaVersion: AgentRunEventSchemaVersion;
  readonly runId: string;
  readonly attemptId: string;
  readonly eventId: string;
  readonly sequence: number;
  readonly visibility: AgentRunEventVisibility;
  readonly createdAt: number;
  readonly safeSummary: string;
}

export type AgentRunAcceptedEvent = AgentRunEventBase & {
  readonly kind: "run_accepted";
  readonly admissionId: string;
};

export type AgentRunCapabilityEvent = AgentRunEventBase & {
  readonly kind: "capability_receipt";
  readonly capabilityId: string;
  readonly tier: "deterministic-scripted" | "real-provider" | "unknown";
  readonly adapter: string;
  readonly deterministic: boolean;
};

export type AgentRunContextReceiptEvent = AgentRunEventBase & {
  readonly kind: "context_receipt";
  readonly contextReceiptId: string;
  readonly sourceKind: string;
  readonly sourceRef: string;
  readonly sourceHash: string;
  readonly ownerRef: string;
  readonly expiresAt: number | null;
  readonly redactedPreview: string;
  readonly tokenEstimate: number;
  readonly inclusionReason: string;
  readonly policyDecision: "included" | "excluded" | "degraded";
};

export type AgentRunStatusEvent = AgentRunEventBase & {
  readonly kind: "status";
  readonly status: AgentRunStatus;
  readonly progressPct: number | null;
};

export type AgentRunToolRequestEvent = AgentRunEventBase & {
  readonly kind: "tool_request";
  readonly callId: string;
  readonly toolName: string;
  readonly timeoutMs: number;
  readonly idempotencyKey: string;
};

export type AgentRunToolResultEvent = AgentRunEventBase & {
  readonly kind: "tool_result";
  readonly callId: string;
  readonly toolName: string;
  readonly resultSummary: string;
  readonly durationMs: number;
  readonly retryable: boolean;
};

export type AgentRunToolErrorEvent = AgentRunEventBase & {
  readonly kind: "tool_error";
  readonly callId: string;
  readonly toolName: string;
  readonly errorCode: string;
  readonly errorSummary: string;
  readonly retryable: boolean;
};

export type AgentRunApprovalRequestedEvent = AgentRunEventBase & {
  readonly kind: "approval_requested";
  readonly approvalId: string;
  readonly callId: string;
  readonly reason: string;
  readonly expiresAt: number;
};

export type AgentRunApprovalResolvedEvent = AgentRunEventBase & {
  readonly kind: "approval_resolved";
  readonly approvalId: string;
  readonly callId: string;
  readonly resolution: AgentRunApprovalResolution;
};

export type AgentRunUsageEvent = AgentRunEventBase & {
  readonly kind: "usage";
  readonly usageId: string;
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly totalTokens: number;
  readonly durationMs: number;
};

export type AgentRunRecoveryEvent = AgentRunEventBase & {
  readonly kind: "recovery";
  readonly recoveryId: string;
  readonly action: AgentRunRecoveryAction;
  readonly reason: string;
  readonly fromAttemptId: string;
  readonly toAttemptId: string;
};

export type AgentRunTerminalEvent = AgentRunEventBase & {
  readonly kind: "terminal";
  readonly terminalOutcome: AgentRunTerminalOutcome;
  readonly terminalCode: AgentRunTerminalCode;
  readonly retryable: boolean;
  readonly recoveryAction: AgentRunRecoveryAction | null;
};

export type AgentRunEvent =
  | AgentRunAcceptedEvent
  | AgentRunCapabilityEvent
  | AgentRunContextReceiptEvent
  | AgentRunStatusEvent
  | AgentRunToolRequestEvent
  | AgentRunToolResultEvent
  | AgentRunToolErrorEvent
  | AgentRunApprovalRequestedEvent
  | AgentRunApprovalResolvedEvent
  | AgentRunUsageEvent
  | AgentRunRecoveryEvent
  | AgentRunTerminalEvent;

export type AgentRunEventKind = AgentRunEvent["kind"];

export type AgentRunEventParseFailure =
  | "not_object"
  | "accessor_or_proxy"
  | "extra_or_missing_field"
  | "invalid_common_field"
  | "invalid_payload"
  | "unsupported_schema_version";

export interface AgentRunEventParseResult {
  readonly ok: true;
  readonly event: AgentRunEvent;
}

export interface AgentRunEventParseFailureResult {
  readonly ok: false;
  readonly reason: AgentRunEventParseFailure;
}

export type ParsedAgentRunEvent = AgentRunEventParseResult | AgentRunEventParseFailureResult;

const EVENT_KINDS = Object.freeze([
  "run_accepted",
  "capability_receipt",
  "context_receipt",
  "status",
  "tool_request",
  "tool_result",
  "tool_error",
  "approval_requested",
  "approval_resolved",
  "usage",
  "recovery",
  "terminal",
] as const);

const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const SAFE_HASH = /^sha256:[0-9a-f]{64}$/u;
const SAFE_SUMMARY_MAX = 240;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/u;

const commonKeys = Object.freeze([
  "attemptId",
  "createdAt",
  "eventId",
  "kind",
  "runId",
  "safeSummary",
  "schemaVersion",
  "sequence",
  "visibility",
]);

const payloadKeys: Readonly<Record<AgentRunEventKind, readonly string[]>> = Object.freeze({
  run_accepted: ["admissionId"],
  capability_receipt: ["adapter", "capabilityId", "deterministic", "tier"],
  context_receipt: [
    "contextReceiptId", "expiresAt", "inclusionReason", "ownerRef", "policyDecision",
    "redactedPreview", "sourceHash", "sourceKind", "sourceRef", "tokenEstimate",
  ],
  status: ["progressPct", "status"],
  tool_request: ["callId", "idempotencyKey", "timeoutMs", "toolName"],
  tool_result: ["callId", "durationMs", "resultSummary", "retryable", "toolName"],
  tool_error: ["callId", "errorCode", "errorSummary", "retryable", "toolName"],
  approval_requested: ["approvalId", "callId", "expiresAt", "reason"],
  approval_resolved: ["approvalId", "callId", "resolution"],
  usage: ["durationMs", "inputTokens", "outputTokens", "totalTokens", "usageId"],
  recovery: ["action", "fromAttemptId", "reason", "recoveryId", "toAttemptId"],
  terminal: ["recoveryAction", "retryable", "terminalCode", "terminalOutcome"],
});

const allKeys = (kind: AgentRunEventKind): readonly string[] => Object.freeze([
  ...commonKeys,
  ...payloadKeys[kind],
]);

const ownDataRecord = (
  input: unknown,
): { readonly value: Record<string, unknown>; readonly reason?: never } | {
  readonly value?: never;
  readonly reason: "not_object" | "accessor_or_proxy";
} => {
  // This reflective boundary catches malformed objects and accessor/proxy
  // failures. It does not promise zero Proxy trap execution; callers needing
  // side-effect-free parsing must supply raw JSON/plain data.
  try {
    if (input === null || typeof input !== "object" || Array.isArray(input)) {
      return { reason: "not_object" };
    }
    const prototype = Object.getPrototypeOf(input);
    if (prototype !== Object.prototype && prototype !== null) return { reason: "not_object" };
    const keys = Reflect.ownKeys(input);
    if (keys.some((key) => typeof key !== "string")) return { reason: "accessor_or_proxy" };
    const descriptors = Object.getOwnPropertyDescriptors(input);
    const values: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    for (const key of keys) {
      const descriptor = descriptors[key as string];
      if (descriptor === undefined || !("value" in descriptor)) return { reason: "accessor_or_proxy" };
      values[key as string] = descriptor.value;
    }
    return { value: values };
  } catch {
    return { reason: "accessor_or_proxy" };
  }
};

const exactKeys = (record: Record<string, unknown>, expected: readonly string[]): boolean => {
  const actual = Object.keys(record).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const isSafeToken = (value: unknown): value is string =>
  typeof value === "string" && SAFE_TOKEN.test(value);

const isSafeSummary = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= SAFE_SUMMARY_MAX
  && !CONTROL_CHARACTERS.test(value) && value.trim().length > 0;

const isSafeEpoch = (value: unknown, allowNull = false): value is number | null =>
  (allowNull && value === null) || (typeof value === "number"
    && Number.isSafeInteger(value) && value >= 0);

const isSafeNonNegativeInt = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const includesString = (values: readonly string[], value: unknown): value is string =>
  typeof value === "string" && values.includes(value);

const asEvent = (record: Record<string, unknown>, kind: AgentRunEventKind): AgentRunEvent | null => {
  const common = {
    schemaVersion: record.schemaVersion,
    runId: record.runId,
    attemptId: record.attemptId,
    eventId: record.eventId,
    sequence: record.sequence,
    visibility: record.visibility,
    createdAt: record.createdAt,
    safeSummary: record.safeSummary,
  };
  if (!SUPPORTED_AGENT_RUN_EVENT_SCHEMA_VERSIONS.includes(common.schemaVersion as AgentRunEventSchemaVersion)
    || !isSafeToken(common.runId) || !isSafeToken(common.attemptId) || !isSafeToken(common.eventId)
    || !isSafeNonNegativeInt(common.sequence) || common.sequence === 0
    || (common.visibility !== "ui" && common.visibility !== "internal")
    || !isSafeEpoch(common.createdAt) || !isSafeSummary(common.safeSummary)) return null;

  const base = Object.freeze({
    ...common,
    // v0 and v1 have the same field set; normalize the accepted compatibility
    // form to the current schema before storing or projecting it.
    schemaVersion: CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
  }) as AgentRunEventBase;
  switch (kind) {
    case "run_accepted":
      return isSafeToken(record.admissionId)
        ? Object.freeze({ ...base, kind, admissionId: record.admissionId })
        : null;
    case "capability_receipt":
      return isSafeToken(record.capabilityId) && isSafeToken(record.adapter)
        && isBoolean(record.deterministic)
        && (record.tier === "deterministic-scripted" || record.tier === "real-provider" || record.tier === "unknown")
        && (record.tier === "deterministic-scripted" ? record.deterministic === true : record.deterministic === false)
        ? Object.freeze({ ...base, kind, capabilityId: record.capabilityId, tier: record.tier,
          adapter: record.adapter, deterministic: record.deterministic })
        : null;
    case "context_receipt":
      return isSafeToken(record.contextReceiptId) && isSafeToken(record.sourceKind)
        && isSafeToken(record.sourceRef) && typeof record.sourceHash === "string"
        && SAFE_HASH.test(record.sourceHash) && isSafeToken(record.ownerRef)
        && isSafeEpoch(record.expiresAt, true) && isSafeSummary(record.redactedPreview)
        && isSafeNonNegativeInt(record.tokenEstimate) && isSafeSummary(record.inclusionReason)
        && (record.policyDecision === "included" || record.policyDecision === "excluded"
          || record.policyDecision === "degraded")
        ? Object.freeze({ ...base, kind, contextReceiptId: record.contextReceiptId,
          sourceKind: record.sourceKind, sourceRef: record.sourceRef, sourceHash: record.sourceHash,
          ownerRef: record.ownerRef, expiresAt: record.expiresAt, redactedPreview: record.redactedPreview,
          tokenEstimate: record.tokenEstimate, inclusionReason: record.inclusionReason,
          policyDecision: record.policyDecision })
        : null;
    case "status":
      return EVENT_KINDS.includes(kind) && typeof record.status === "string"
        && (["queued", "gathering_context", "generating", "using_tool", "waiting_approval",
          "reconnecting", "recovering", "cancelled", "failed", "complete"] as readonly string[])
          .includes(record.status)
        && isSafeEpoch(record.progressPct, true)
        && (record.progressPct === null || record.progressPct <= 100)
        ? Object.freeze({ ...base, kind, status: record.status as AgentRunStatus,
          progressPct: record.progressPct })
        : null;
    case "tool_request":
      return isSafeToken(record.callId) && isSafeToken(record.toolName)
        && isSafeNonNegativeInt(record.timeoutMs) && record.timeoutMs > 0 && record.timeoutMs <= 300_000
        && isSafeToken(record.idempotencyKey)
        ? Object.freeze({ ...base, kind, callId: record.callId, toolName: record.toolName,
          timeoutMs: record.timeoutMs, idempotencyKey: record.idempotencyKey })
        : null;
    case "tool_result":
      return isSafeToken(record.callId) && isSafeToken(record.toolName)
        && isSafeSummary(record.resultSummary) && isSafeNonNegativeInt(record.durationMs)
        && isBoolean(record.retryable)
        ? Object.freeze({ ...base, kind, callId: record.callId, toolName: record.toolName,
          resultSummary: record.resultSummary, durationMs: record.durationMs, retryable: record.retryable })
        : null;
    case "tool_error":
      return isSafeToken(record.callId) && isSafeToken(record.toolName) && isSafeToken(record.errorCode)
        && isSafeSummary(record.errorSummary) && isBoolean(record.retryable)
        ? Object.freeze({ ...base, kind, callId: record.callId, toolName: record.toolName,
          errorCode: record.errorCode, errorSummary: record.errorSummary, retryable: record.retryable })
        : null;
    case "approval_requested": {
      const expiresAt = record.expiresAt;
      const createdAt = common.createdAt;
      if (!isSafeToken(record.approvalId) || !isSafeToken(record.callId) || !isSafeSummary(record.reason)
        || !isSafeEpoch(expiresAt) || !isSafeEpoch(createdAt)
        || expiresAt === null || createdAt === null || expiresAt <= createdAt) return null;
      return Object.freeze({ ...base, kind, approvalId: record.approvalId, callId: record.callId,
        reason: record.reason, expiresAt });
    }
    case "approval_resolved":
      return isSafeToken(record.approvalId) && isSafeToken(record.callId)
        && includesString(["approved", "denied", "expired", "cancelled"], record.resolution)
        ? Object.freeze({ ...base, kind, approvalId: record.approvalId, callId: record.callId,
          resolution: record.resolution as AgentRunApprovalResolution })
        : null;
    case "usage":
      return isSafeToken(record.usageId) && isSafeNonNegativeInt(record.inputTokens)
        && isSafeNonNegativeInt(record.outputTokens) && isSafeNonNegativeInt(record.totalTokens)
        && record.totalTokens === (record.inputTokens as number) + (record.outputTokens as number)
        && isSafeNonNegativeInt(record.durationMs)
        ? Object.freeze({ ...base, kind, usageId: record.usageId, inputTokens: record.inputTokens,
          outputTokens: record.outputTokens, totalTokens: record.totalTokens, durationMs: record.durationMs })
        : null;
    case "recovery":
      return isSafeToken(record.recoveryId) && isSafeToken(record.fromAttemptId)
        && isSafeToken(record.toAttemptId) && isSafeSummary(record.reason)
        && includesString(["retry", "reconnect", "resume", "manual"], record.action)
        ? Object.freeze({ ...base, kind, recoveryId: record.recoveryId,
          action: record.action as AgentRunRecoveryAction, reason: record.reason,
          fromAttemptId: record.fromAttemptId, toAttemptId: record.toAttemptId })
        : null;
    case "terminal":
      return includesString(["completed", "degraded", "failed", "cancelled"], record.terminalOutcome)
        && includesString(["completed", "cancelled", "generation_provider_failed", "generation_context_failed",
          "generation_attachment_failed", "generation_interrupted", "generation_timeout", "tool_failed",
          "approval_denied", "approval_expired", "recovery_exhausted"], record.terminalCode)
        && isBoolean(record.retryable)
        && (record.recoveryAction === null
          || includesString(["retry", "reconnect", "resume", "manual"], record.recoveryAction))
        && ((record.terminalOutcome === "completed" && record.terminalCode === "completed"
          && record.retryable === false && record.recoveryAction === null)
          || (record.terminalOutcome === "cancelled" && record.terminalCode === "cancelled"
            && record.retryable === false)
          || ((record.terminalOutcome === "failed" || record.terminalOutcome === "degraded")
            && record.terminalCode !== "completed" && record.terminalCode !== "cancelled"))
        ? Object.freeze({ ...base, kind, terminalOutcome: record.terminalOutcome as AgentRunTerminalOutcome,
          terminalCode: record.terminalCode as AgentRunTerminalCode, retryable: record.retryable,
          recoveryAction: record.recoveryAction as AgentRunRecoveryAction | null })
        : null;
  }
};

/** Parses and strictly detaches an event; malformed input fails closed. */
export const parseAgentRunEvent = (input: unknown): ParsedAgentRunEvent => {
  const recordResult = ownDataRecord(input);
  if (recordResult.value === undefined) return { ok: false, reason: recordResult.reason };
  const record = recordResult.value;
  if (!isSafeToken(record.kind) || !EVENT_KINDS.includes(record.kind as AgentRunEventKind)) {
    return { ok: false, reason: "invalid_payload" };
  }
  const kind = record.kind as AgentRunEventKind;
  if (!exactKeys(record, allKeys(kind))) return { ok: false, reason: "extra_or_missing_field" };
  if (!SUPPORTED_AGENT_RUN_EVENT_SCHEMA_VERSIONS.includes(record.schemaVersion as AgentRunEventSchemaVersion)) {
    return { ok: false, reason: "unsupported_schema_version" };
  }
  const event = asEvent(record, kind);
  return event === null ? { ok: false, reason: "invalid_payload" } : { ok: true, event };
};

export const assertAgentRunEvent = (input: unknown): AgentRunEvent => {
  const result = parseAgentRunEvent(input);
  if (!result.ok) throw new TypeError(`invalid agent run event: ${result.reason}`);
  return result.event;
};

export type AppendAgentRunEventOutcome =
  | { readonly kind: "appended"; readonly event: AgentRunEvent }
  | { readonly kind: "replay"; readonly event: AgentRunEvent }
  | { readonly kind: "conflict" }
  | { readonly kind: "rejected"; readonly reason: AgentRunEventParseFailure | "sequence" | "terminal" | "ordering" };

interface AgentRunLog {
  readonly runId: string;
  readonly events: AgentRunEvent[];
  readonly byId: Map<string, AgentRunEvent>;
  terminal: boolean;
}

const eventBytes = (event: AgentRunEvent): string => JSON.stringify(event);
const detachEvent = (event: AgentRunEvent): AgentRunEvent => Object.freeze({ ...event });

export interface AgentRunEventStoreSnapshot {
  readonly runs: readonly {
    readonly runId: string;
    readonly events: readonly AgentRunEvent[];
  }[];
}

export interface AgentRunEventStore {
  append(input: unknown): AppendAgentRunEventOutcome;
  list(runId: string): readonly AgentRunEvent[];
  snapshot(): AgentRunEventStoreSnapshot;
  restore(snapshot: unknown): void;
  reset(): void;
}

const canonicalSnapshot = (logs: Map<string, AgentRunLog>): AgentRunEventStoreSnapshot => Object.freeze({
  runs: Object.freeze([...logs.values()]
    .sort((left, right) => left.runId < right.runId ? -1 : left.runId > right.runId ? 1 : 0)
    .map((log) => Object.freeze({
      runId: log.runId,
      events: Object.freeze(log.events.map(detachEvent)),
    }))),
});

export const createInMemoryAgentRunEventStore = (): AgentRunEventStore => {
  const logs = new Map<string, AgentRunLog>();
  const list = (runId: string): readonly AgentRunEvent[] => {
    const log = logs.get(runId);
    return Object.freeze(log === undefined ? [] : log.events.map(detachEvent));
  };

  return Object.freeze({
    append(input: unknown): AppendAgentRunEventOutcome {
      const parsed = parseAgentRunEvent(input);
      if (!parsed.ok) return { kind: "rejected", reason: parsed.reason };
      const event = parsed.event;
      const log = logs.get(event.runId);
      if (log === undefined) {
        if (event.sequence !== 1 || event.kind !== "run_accepted") return { kind: "rejected", reason: "sequence" };
        const next: AgentRunLog = {
          runId: event.runId,
          events: [event],
          byId: new Map([[event.eventId, event]]),
          terminal: false,
        };
        logs.set(event.runId, next);
        return { kind: "appended", event: detachEvent(event) };
      }
      const existing = log.byId.get(event.eventId);
      if (existing !== undefined) {
        return eventBytes(existing) === eventBytes(event)
          ? { kind: "replay", event: detachEvent(existing) }
          : { kind: "conflict" };
      }
      if (log.terminal) return { kind: "rejected", reason: "terminal" };
      if (event.sequence !== log.events.length + 1) return { kind: "rejected", reason: "sequence" };
      if (event.kind === "run_accepted") return { kind: "rejected", reason: "ordering" };
      if ((event.kind === "tool_result" || event.kind === "tool_error")
        && !log.events.some((prior) => prior.kind === "tool_request" && prior.callId === event.callId)) {
        return { kind: "rejected", reason: "ordering" };
      }
      if ((event.kind === "tool_result" || event.kind === "tool_error")
        && log.events.some((prior) => (prior.kind === "tool_result" || prior.kind === "tool_error")
          && prior.callId === event.callId)) {
        return { kind: "rejected", reason: "ordering" };
      }
      if (event.kind === "approval_resolved"
        && !log.events.some((prior) => prior.kind === "approval_requested"
          && prior.approvalId === event.approvalId && prior.callId === event.callId)) {
        return { kind: "rejected", reason: "ordering" };
      }
      if (event.kind === "approval_resolved"
        && log.events.some((prior) => prior.kind === "approval_resolved"
          && prior.approvalId === event.approvalId && prior.callId === event.callId)) {
        return { kind: "rejected", reason: "ordering" };
      }
      log.events.push(event);
      log.byId.set(event.eventId, event);
      if (event.kind === "terminal") log.terminal = true;
      return { kind: "appended", event: detachEvent(event) };
    },

    list,

    snapshot(): AgentRunEventStoreSnapshot {
      return canonicalSnapshot(logs);
    },

    restore(snapshot: unknown): void {
      const recordResult = ownDataRecord(snapshot);
      if (recordResult.value === undefined || !exactKeys(recordResult.value, ["runs"])
        || !Array.isArray(recordResult.value.runs)) throw new TypeError("invalid agent run snapshot");
      const next = new Map<string, AgentRunLog>();
      for (const rawRun of recordResult.value.runs) {
        const run = ownDataRecord(rawRun);
        if (run.value === undefined || !exactKeys(run.value, ["events", "runId"])
          || !isSafeToken(run.value.runId) || !Array.isArray(run.value.events)) {
          throw new TypeError("invalid agent run snapshot row");
        }
        const events: AgentRunEvent[] = [];
        const eventIds = new Set<string>();
        for (const rawEvent of run.value.events) {
          const parsed = parseAgentRunEvent(rawEvent);
          if (!parsed.ok || parsed.event.runId !== run.value.runId
            || parsed.event.sequence !== events.length + 1 || eventIds.has(parsed.event.eventId)) {
            throw new TypeError("invalid agent run snapshot event");
          }
          eventIds.add(parsed.event.eventId);
          events.push(parsed.event);
        }
        if (events.length === 0 || events[0]!.kind !== "run_accepted"
          || next.has(run.value.runId)) throw new TypeError("invalid agent run snapshot ordering");
        const terminalIndices = events.flatMap((event, index) => event.kind === "terminal" ? [index] : []);
        const terminal = terminalIndices.length > 0;
        if (terminal && (terminalIndices.length > 1 || terminalIndices[0] !== events.length - 1)) {
          throw new TypeError("invalid agent run snapshot terminal");
        }
        for (const [index, event] of events.entries()) {
          if ((event.kind === "tool_result" || event.kind === "tool_error")
            && !events.slice(0, index).some((prior) => prior.kind === "tool_request" && prior.callId === event.callId)) {
            throw new TypeError("invalid agent run snapshot tool ordering");
          }
          if ((event.kind === "tool_result" || event.kind === "tool_error")
            && events.slice(0, index).some((prior) => (prior.kind === "tool_result" || prior.kind === "tool_error")
              && prior.callId === event.callId)) {
            throw new TypeError("invalid agent run snapshot tool ordering");
          }
          if (event.kind === "approval_resolved"
            && !events.slice(0, index).some((prior) => prior.kind === "approval_requested"
              && prior.approvalId === event.approvalId && prior.callId === event.callId)) {
            throw new TypeError("invalid agent run snapshot approval ordering");
          }
          if (event.kind === "approval_resolved"
            && events.slice(0, index).some((prior) => prior.kind === "approval_resolved"
              && prior.approvalId === event.approvalId && prior.callId === event.callId)) {
            throw new TypeError("invalid agent run snapshot approval ordering");
          }
        }
        next.set(run.value.runId, {
          runId: run.value.runId,
          events,
          byId: new Map(events.map((event) => [event.eventId, event])),
          terminal,
        });
      }
      logs.clear();
      for (const [runId, log] of next) logs.set(runId, log);
    },

    reset(): void {
      logs.clear();
    },
  });
};

export interface AgentRunVisibleTimelineEvent {
  readonly runId: string;
  readonly attemptId: string;
  readonly eventId: string;
  readonly sequence: number;
  readonly createdAt: number;
  readonly kind: AgentRunEventKind;
  readonly safeSummary: string;
  readonly details: Readonly<Record<string, unknown>>;
}

export interface AgentRunVisibleTimeline {
  readonly runId: string;
  readonly events: readonly AgentRunVisibleTimelineEvent[];
}

const REDACTED_KEYS = new Set([
  "prompt", "rawprompt", "args", "arguments", "rawarguments", "attachment", "attachments",
  "attachmentid", "attachmentids", "attachmentref", "attachmentrefs", "attachmentreference", "attachmentreferences",
  "fileid", "fileids", "fileref", "filerefs", "filereference", "filereferences",
  "opaque", "opaqueid", "opaqueids", "opaqueref", "opaquerefs", "opaquereference", "opaquereferences",
  "referenceid", "referenceids", "referenceref", "referencerefs", "reference",
  "credential", "credentials", "accesstoken", "password",
  "secret", "token", "apikey", "authorization", "auth", "reasoning", "chainofthought", "hiddenreasoning",
]);
const REDACTED_STRING = /(?:Bearer\s+|sk-[A-Za-z0-9]|BEGIN\s+.*PRIVATE\s+KEY)/iu;
const REDACTED_VALUE_STRING = /(?:api[_. -]?key|authorization|access[_. -]?token|token|secret|password)\s*[:=]\s*\S+/iu;
const REDACTED_ATTACHMENT_STRING = /(?:attachment|file|opaque|reference)(?:[_. -]?(?:id|ids|ref|refs|reference|references))?\s*[:=]\s*[A-Za-z0-9._:@+-]+/iu;
const normalizedRedactionKey = (key: string): string => key.replace(/[^A-Za-z0-9]/gu, "").toLowerCase();

/** Returns scanner findings rather than exposing sensitive values. */
export const scanAgentRunRedactions = (value: unknown): readonly string[] => {
  const findings: string[] = [];
  const seen = new Set<object>();
  const visit = (current: unknown, path: string): void => {
    if (typeof current === "string") {
      if (REDACTED_STRING.test(current) || REDACTED_VALUE_STRING.test(current)
        || REDACTED_ATTACHMENT_STRING.test(current)) findings.push(path || "value");
      return;
    }
    if (current === null || typeof current !== "object") return;
    if (seen.has(current)) return;
    seen.add(current);
    if (Array.isArray(current)) {
      current.forEach((item, index) => visit(item, `${path}[${index}]`));
      return;
    }
    const recordResult = ownDataRecord(current);
    if (recordResult.value === undefined) {
      findings.push(path || "value");
      return;
    }
    for (const [key, nested] of Object.entries(recordResult.value)) {
      const nestedPath = path === "" ? key : `${path}.${key}`;
      if (REDACTED_KEYS.has(normalizedRedactionKey(key))) findings.push(nestedPath);
      else visit(nested, nestedPath);
    }
  };
  visit(value, "");
  return Object.freeze(findings);
};

const visibleDetails = (event: AgentRunEvent): Readonly<Record<string, unknown>> => {
  switch (event.kind) {
    case "run_accepted": return Object.freeze({ admissionId: event.admissionId });
    case "capability_receipt": return Object.freeze({ tier: event.tier, adapter: event.adapter,
      deterministic: event.deterministic });
    case "context_receipt": return Object.freeze({ contextReceiptId: event.contextReceiptId,
      sourceKind: event.sourceKind, redactedPreview: event.redactedPreview,
      tokenEstimate: event.tokenEstimate, inclusionReason: event.inclusionReason,
      policyDecision: event.policyDecision });
    case "status": return Object.freeze({ status: event.status, progressPct: event.progressPct });
    case "tool_request": return Object.freeze({ callId: event.callId, toolName: event.toolName,
      timeoutMs: event.timeoutMs });
    case "tool_result": return Object.freeze({ callId: event.callId, toolName: event.toolName,
      resultSummary: event.resultSummary, durationMs: event.durationMs, retryable: event.retryable });
    case "tool_error": return Object.freeze({ callId: event.callId, toolName: event.toolName,
      errorCode: event.errorCode, errorSummary: event.errorSummary, retryable: event.retryable });
    case "approval_requested": return Object.freeze({ approvalId: event.approvalId, callId: event.callId,
      reason: event.reason, expiresAt: event.expiresAt });
    case "approval_resolved": return Object.freeze({ approvalId: event.approvalId, callId: event.callId,
      resolution: event.resolution });
    case "usage": return Object.freeze({ inputTokens: event.inputTokens, outputTokens: event.outputTokens,
      totalTokens: event.totalTokens, durationMs: event.durationMs });
    case "recovery": return Object.freeze({ recoveryId: event.recoveryId, action: event.action,
      reason: event.reason });
    case "terminal": return Object.freeze({ terminalOutcome: event.terminalOutcome,
      terminalCode: event.terminalCode, retryable: event.retryable, recoveryAction: event.recoveryAction });
  }
};

/** Projects only UI-visible fields and fails closed on any malformed event. */
export const projectAgentRunTimeline = (
  input: readonly unknown[],
): AgentRunVisibleTimeline | null => {
  const parsed: AgentRunEvent[] = [];
  const eventIds = new Set<string>();
  for (const raw of input) {
    const result = parseAgentRunEvent(raw);
    if (!result.ok) return null;
    if (eventIds.has(result.event.eventId)) return null;
    eventIds.add(result.event.eventId);
    parsed.push(result.event);
  }
  if (parsed.length === 0) return null;
  const runId = parsed[0]!.runId;
  if (parsed[0]!.kind !== "run_accepted"
    || parsed.some((event, index) => event.runId !== runId || event.sequence !== index + 1
      || (index > 0 && event.kind === "run_accepted"))) return null;
  let terminalSeen = false;
  for (const [index, event] of parsed.entries()) {
    if (terminalSeen) return null;
    if (event.kind === "terminal") {
      if (index !== parsed.length - 1) return null;
      terminalSeen = true;
    }
    if ((event.kind === "tool_result" || event.kind === "tool_error")
      && !parsed.slice(0, index).some((prior) => prior.kind === "tool_request" && prior.callId === event.callId)) {
      return null;
    }
    if (event.kind === "approval_resolved"
      && !parsed.slice(0, index).some((prior) => prior.kind === "approval_requested"
        && prior.approvalId === event.approvalId && prior.callId === event.callId)) {
      return null;
    }
  }
  const visible = parsed.filter((event) => event.visibility === "ui").map((event) => Object.freeze({
    runId: event.runId,
    attemptId: event.attemptId,
    eventId: event.eventId,
    sequence: event.sequence,
    createdAt: event.createdAt,
    kind: event.kind,
    safeSummary: event.safeSummary,
    details: visibleDetails(event),
  }));
  const projection = Object.freeze({ runId, events: Object.freeze(visible) });
  return scanAgentRunRedactions(projection).length === 0 ? projection : null;
};

export interface AgentRunEventSupervisorDependencies {
  readonly events: AgentRunEventStore;
  readonly nowEpochMilliseconds: () => number;
  readonly eventId?: (runId: string, sequence: number, kind: AgentRunEventKind) => string;
}

export interface AgentRunEventSupervisor {
  accepted(input: { readonly runId: string; readonly attemptId: string; readonly admissionId: string }): AgentRunEvent;
  capability(input: { readonly runId: string; readonly attemptId: string; readonly capabilityId: string;
    readonly tier: AgentRunCapabilityEvent["tier"]; readonly adapter: string; readonly deterministic: boolean }): AgentRunEvent;
  context(input: { readonly runId: string; readonly attemptId: string; readonly contextReceiptId: string;
    readonly sourceKind: string; readonly sourceRef: string; readonly sourceHash: string; readonly ownerRef: string;
    readonly expiresAt: number | null; readonly redactedPreview: string; readonly tokenEstimate: number;
    readonly inclusionReason: string; readonly policyDecision: AgentRunContextReceiptEvent["policyDecision"] }): AgentRunEvent;
  status(input: { readonly runId: string; readonly attemptId: string; readonly status: AgentRunStatus;
    readonly progressPct: number | null }): AgentRunEvent;
  toolRequest(input: { readonly runId: string; readonly attemptId: string; readonly callId: string;
    readonly toolName: string; readonly timeoutMs: number; readonly idempotencyKey: string }): AgentRunEvent;
  toolResult(input: { readonly runId: string; readonly attemptId: string; readonly callId: string;
    readonly toolName: string; readonly resultSummary: string; readonly durationMs: number; readonly retryable: boolean }): AgentRunEvent;
  toolError(input: { readonly runId: string; readonly attemptId: string; readonly callId: string;
    readonly toolName: string; readonly errorCode: string; readonly errorSummary: string; readonly retryable: boolean }): AgentRunEvent;
  approvalRequested(input: { readonly runId: string; readonly attemptId: string; readonly approvalId: string;
    readonly callId: string; readonly reason: string; readonly expiresAt: number }): AgentRunEvent;
  approvalResolved(input: { readonly runId: string; readonly attemptId: string; readonly approvalId: string;
    readonly callId: string; readonly resolution: AgentRunApprovalResolution }): AgentRunEvent;
  usage(input: { readonly runId: string; readonly attemptId: string; readonly usageId: string;
    readonly inputTokens: number; readonly outputTokens: number; readonly totalTokens: number; readonly durationMs: number }): AgentRunEvent;
  recovery(input: { readonly runId: string; readonly attemptId: string; readonly recoveryId: string;
    readonly action: AgentRunRecoveryAction; readonly reason: string; readonly fromAttemptId: string;
    readonly toAttemptId: string }): AgentRunEvent;
  terminal(input: { readonly runId: string; readonly attemptId: string; readonly terminalOutcome: AgentRunTerminalOutcome;
    readonly terminalCode: AgentRunTerminalCode; readonly retryable: boolean;
    readonly recoveryAction: AgentRunRecoveryAction | null }): AgentRunEvent;
}

const defaultSummary = (kind: AgentRunEventKind): string => kind.replace(/_/gu, " ");

export const createAgentRunEventSupervisor = (
  deps: AgentRunEventSupervisorDependencies,
): AgentRunEventSupervisor => {
  const append = (
    kind: AgentRunEventKind,
    input: Record<string, unknown>,
  ): AgentRunEvent => {
    const runId = input.runId;
    if (typeof runId !== "string") throw new TypeError("agent run event missing run id");
    const prior = deps.events.list(runId);
    const sequence = prior.length + 1;
    const attemptId = input.attemptId;
    if (typeof attemptId !== "string") throw new TypeError("agent run event missing attempt id");
    const eventId = deps.eventId?.(runId, sequence, kind) ?? `${runId}:${sequence}:${kind}`;
    const payload = { ...input };
    for (const reserved of ["schemaVersion", "runId", "attemptId", "eventId", "sequence",
      "visibility", "createdAt", "safeSummary", "kind"]) delete payload[reserved];
    const candidate = {
      schemaVersion: CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
      runId,
      attemptId,
      eventId,
      sequence,
      visibility: input.visibility ?? "ui",
      createdAt: deps.nowEpochMilliseconds(),
      safeSummary: defaultSummary(kind),
      kind,
      ...payload,
    };
    const result = deps.events.append(candidate);
    if (result.kind !== "appended") throw new TypeError(`agent run event append ${result.kind}`);
    return result.event;
  };
  const withDefaults = <Input extends Record<string, unknown>>(kind: AgentRunEventKind, extra: Input) =>
    append(kind, extra);
  type AcceptedInput = Parameters<AgentRunEventSupervisor["accepted"]>[0];
  type CapabilityInput = Parameters<AgentRunEventSupervisor["capability"]>[0];
  type ContextInput = Parameters<AgentRunEventSupervisor["context"]>[0];
  type StatusInput = Parameters<AgentRunEventSupervisor["status"]>[0];
  type ToolRequestInput = Parameters<AgentRunEventSupervisor["toolRequest"]>[0];
  type ToolResultInput = Parameters<AgentRunEventSupervisor["toolResult"]>[0];
  type ToolErrorInput = Parameters<AgentRunEventSupervisor["toolError"]>[0];
  type ApprovalRequestedInput = Parameters<AgentRunEventSupervisor["approvalRequested"]>[0];
  type ApprovalResolvedInput = Parameters<AgentRunEventSupervisor["approvalResolved"]>[0];
  type UsageInput = Parameters<AgentRunEventSupervisor["usage"]>[0];
  type RecoveryInput = Parameters<AgentRunEventSupervisor["recovery"]>[0];
  type TerminalInput = Parameters<AgentRunEventSupervisor["terminal"]>[0];
  return Object.freeze({
    accepted: (input: AcceptedInput) => withDefaults("run_accepted", input as unknown as Record<string, unknown>),
    capability: (input: CapabilityInput) => withDefaults("capability_receipt", input as unknown as Record<string, unknown>),
    context: (input: ContextInput) => withDefaults("context_receipt", input as unknown as Record<string, unknown>),
    status: (input: StatusInput) => withDefaults("status", input as unknown as Record<string, unknown>),
    toolRequest: (input: ToolRequestInput) => withDefaults("tool_request", input as unknown as Record<string, unknown>),
    toolResult: (input: ToolResultInput) => withDefaults("tool_result", input as unknown as Record<string, unknown>),
    toolError: (input: ToolErrorInput) => withDefaults("tool_error", input as unknown as Record<string, unknown>),
    approvalRequested: (input: ApprovalRequestedInput) => withDefaults("approval_requested", input as unknown as Record<string, unknown>),
    approvalResolved: (input: ApprovalResolvedInput) => withDefaults("approval_resolved", input as unknown as Record<string, unknown>),
    usage: (input: UsageInput) => withDefaults("usage", input as unknown as Record<string, unknown>),
    recovery: (input: RecoveryInput) => withDefaults("recovery", input as unknown as Record<string, unknown>),
    terminal: (input: TerminalInput) => withDefaults("terminal", input as unknown as Record<string, unknown>),
  });
};
