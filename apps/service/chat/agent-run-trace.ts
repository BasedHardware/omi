// domain-pending(DIV-CHAT-SOURCE-001)

/**
 * A developer-facing, provider-free trace artifact for one agent run.
 *
 * The durable event ledger intentionally contains internal identifiers and
 * source references.  They must not cross this boundary.  We therefore emit a
 * second, deliberately smaller wire shape with stable labels (run:1,
 * event:1, call:1, …), and rebuild a synthetic event ledger from those labels
 * during replay.  Replay proves the redacted trace still produces the exact
 * same UI projection without consulting a model, filesystem corpus, or
 * network service.
 */

import { createHash } from "node:crypto";
import {
  CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
  parseAgentRunEvent,
  projectAgentRunTimeline,
  scanAgentRunRedactions,
  type AgentRunEvent,
  type AgentRunEventStore,
  type AgentRunVisibleTimeline,
} from "./agent-run-events";

export const AGENT_RUN_TRACE_SCHEMA = "omi.agent-run-trace" as const;
export const CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION = 1 as const;
export const AGENT_RUN_TRACE_BUILD_ID_MAX = 128;

const SAFE_LABEL = /^[A-Za-z][A-Za-z0-9._:/+-]{0,127}$/u;
const SAFE_DIGEST = /^sha256:[0-9a-f]{64}$/u;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/u;
// Attachment references are intentionally opaque.  Even when a caller puts
// one in a prose field (rather than an `attachmentId` key), it must not leave
// this export boundary.
const BARE_ATTACHMENT_REFERENCE = /\battachment[_-][A-Za-z0-9][A-Za-z0-9._:@+-]*/iu;
const EVENT_KINDS = new Set<AgentRunEvent["kind"]>([
  "run_accepted", "capability_receipt", "context_receipt", "status", "tool_request",
  "tool_result", "tool_error", "approval_requested", "approval_resolved", "usage",
  "recovery", "terminal",
]);

type JsonPrimitive = null | boolean | number | string;
type JsonValue = JsonPrimitive | readonly JsonValue[] | { readonly [key: string]: JsonValue };

export interface AgentRunTraceEvent {
  readonly schemaVersion: typeof CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION;
  readonly runLabel: string;
  readonly attemptLabel: string;
  readonly eventLabel: string;
  readonly sequence: number;
  readonly visibility: "ui" | "internal";
  readonly createdAt: number;
  readonly safeSummary: string;
  readonly kind: AgentRunEvent["kind"];
  readonly payload: Readonly<Record<string, JsonValue>>;
}

export interface AgentRunTraceBundle {
  readonly schema: typeof AGENT_RUN_TRACE_SCHEMA;
  readonly schemaVersion: typeof CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION;
  readonly buildId: string;
  /** A safe label, never the durable run id. */
  readonly runId: string;
  readonly eventTrace: readonly AgentRunTraceEvent[];
  readonly contextReceipts: readonly Readonly<Record<string, JsonValue>>[];
  readonly toolEnvelopes: readonly Readonly<Record<string, JsonValue>>[];
  readonly timings: readonly Readonly<Record<string, JsonValue>>[];
  readonly durableState: readonly Readonly<Record<string, JsonValue>>[];
  readonly projection: AgentRunVisibleTimeline;
  readonly projectionDigest: string;
  readonly traceDigest: string;
  /** Binds every field above, including identity and diagnostic detail arrays. */
  readonly bundleDigest: string;
}

export interface AgentRunTraceExport {
  readonly bundle: AgentRunTraceBundle;
  readonly bytes: string;
}

export interface AgentRunTraceReplay {
  readonly bundle: AgentRunTraceBundle;
  readonly projection: AgentRunVisibleTimeline;
  readonly projectionDigest: string;
}

const fail = (message: string): never => {
  throw new TypeError(`invalid agent run trace: ${message}`);
};

const isRecord = (value: unknown): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const exactKeys = (value: Record<string, unknown>, expected: readonly string[]): boolean => {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const isSafeLabel = (value: unknown): value is string => typeof value === "string" && SAFE_LABEL.test(value);
const isSafeString = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= 240 && !CONTROL_CHARACTERS.test(value);
const isSafeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const assertPlainJson = (value: unknown, seen = new Set<object>()): asserts value is JsonValue => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) fail("non-finite number");
    return;
  }
  if (typeof value !== "object") fail("non-plain JSON");
  const objectValue = value as object;
  if (seen.has(objectValue)) fail("non-plain JSON");
  seen.add(objectValue);
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      if (!Object.prototype.hasOwnProperty.call(value, index)) fail("sparse array");
      assertPlainJson(value[index], seen);
    }
  } else {
    if (!isRecord(value)) fail("non-plain JSON");
    const descriptors = Object.getOwnPropertyDescriptors(value);
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string") fail("symbol key");
      const descriptor = descriptors[key];
      if (descriptor === undefined || !("value" in descriptor)) fail("accessor value");
      if (CONTROL_CHARACTERS.test(key)) fail("control character in key");
      assertPlainJson(descriptor.value, seen);
    }
  }
  seen.delete(objectValue);
};

const sortJson = (value: JsonValue): JsonValue => {
  if (Array.isArray(value)) return value.map(sortJson);
  if (value !== null && typeof value === "object") {
    const record = value as { readonly [key: string]: JsonValue };
    return Object.fromEntries(Object.keys(record).sort().map((key) => [key, sortJson(record[key]!)]));
  }
  return value;
};

/** Stable bytes are the artifact contract; key order is not caller-defined. */
export const canonicalTraceJson = (value: JsonValue): string => {
  assertPlainJson(value);
  const sorted = sortJson(value);
  const output = JSON.stringify(sorted);
  if (output === undefined) fail("unable to serialize");
  return output;
};

const jsonStringValues = (value: unknown, visit: (text: string) => void): void => {
  if (typeof value === "string") {
    visit(value);
    return;
  }
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item) => jsonStringValues(item, visit));
    return;
  }
  if (!isRecord(value)) return;
  for (const item of Object.values(value)) jsonStringValues(item, visit);
};

const assertTracePrivacy = (value: unknown): void => {
  if (scanAgentRunRedactions(value).length > 0) fail("privacy denylist match");
  let bareAttachment = false;
  jsonStringValues(value, (text) => {
    if (BARE_ATTACHMENT_REFERENCE.test(text)) bareAttachment = true;
  });
  if (bareAttachment) fail("bare attachment reference");
};

const digest = (bytes: string): string => `sha256:${createHash("sha256").update(bytes, "utf8").digest("hex")}`;

const labeler = () => {
  const labels = new Map<string, string>();
  const counters = new Map<string, number>();
  return (kind: string, value: string): string => {
    const key = `${kind}\0${value}`;
    const existing = labels.get(key);
    if (existing !== undefined) return existing;
    const next = (counters.get(kind) ?? 0) + 1;
    counters.set(kind, next);
    const label = `${kind}:${next}`;
    labels.set(key, label);
    return label;
  };
};

const safeDigest = (kind: string, value: string): string =>
  digest(`${kind}\0${value}`);

const payloadFor = (event: AgentRunEvent, label: ReturnType<typeof labeler>): Readonly<Record<string, JsonValue>> => {
  switch (event.kind) {
    case "run_accepted": return { admissionLabel: label("admission", event.admissionId) };
    case "capability_receipt": return {
      capabilityLabel: label("capability", event.capabilityId), tier: event.tier,
      adapter: event.adapter, deterministic: event.deterministic,
    };
    case "context_receipt": return {
      contextLabel: label("context", event.contextReceiptId), sourceKind: event.sourceKind,
      sourceLabel: label("source", event.sourceRef), sourceDigest: safeDigest("source", event.sourceHash),
      ownerLabel: label("owner", event.ownerRef), expiresAt: event.expiresAt,
      redactedPreview: event.redactedPreview, itemCount: event.tokenEstimate,
      inclusionReason: event.inclusionReason, policyDecision: event.policyDecision,
    };
    case "status": return { status: event.status, progressPct: event.progressPct };
    case "tool_request": return {
      callLabel: label("call", event.callId), toolName: event.toolName, timeoutMs: event.timeoutMs,
      idemLabel: label("idem", event.idempotencyKey),
    };
    case "tool_result": return {
      callLabel: label("call", event.callId), toolName: event.toolName,
      resultSummary: event.resultSummary, durationMs: event.durationMs, retryable: event.retryable,
    };
    case "tool_error": return {
      callLabel: label("call", event.callId), toolName: event.toolName,
      errorCode: event.errorCode, errorSummary: event.errorSummary, retryable: event.retryable,
    };
    case "approval_requested": return {
      approvalLabel: label("approval", event.approvalId), callLabel: label("call", event.callId),
      reason: event.reason, expiresAt: event.expiresAt,
    };
    case "approval_resolved": return {
      approvalLabel: label("approval", event.approvalId), callLabel: label("call", event.callId),
      resolution: event.resolution,
    };
    case "usage": return {
      usageLabel: label("usage", event.usageId), inputCount: event.inputTokens,
      outputCount: event.outputTokens, totalCount: event.totalTokens, durationMs: event.durationMs,
    };
    case "recovery": return {
      recoveryLabel: label("recovery", event.recoveryId), action: event.action, reason: event.reason,
      fromAttemptLabel: label("attempt", event.fromAttemptId), toAttemptLabel: label("attempt", event.toAttemptId),
    };
    case "terminal": return {
      terminalOutcome: event.terminalOutcome, terminalCode: event.terminalCode,
      retryable: event.retryable, recoveryAction: event.recoveryAction,
    };
  }
};

const redactEvent = (
  event: AgentRunEvent,
  labels: ReturnType<typeof labeler>,
  runLabel: string,
): AgentRunTraceEvent => ({
  schemaVersion: CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION,
  runLabel,
  attemptLabel: labels("attempt", event.attemptId),
  eventLabel: labels("event", event.eventId),
  sequence: event.sequence,
  visibility: event.visibility,
  createdAt: event.createdAt,
  safeSummary: event.safeSummary,
  kind: event.kind,
  payload: payloadFor(event, labels),
});

const traceEventKeys = [
  "attemptLabel", "createdAt", "eventLabel", "kind", "payload", "runLabel",
  "safeSummary", "schemaVersion", "sequence", "visibility",
] as const;

const validateTraceEvent = (value: unknown): AgentRunTraceEvent => {
  if (!isRecord(value) || !exactKeys(value, traceEventKeys)) fail("trace event shape");
  if (value.schemaVersion !== CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION || !isSafeLabel(value.runLabel)
    || !isSafeLabel(value.attemptLabel) || !isSafeLabel(value.eventLabel) || !isSafeInteger(value.sequence)
    || value.sequence === 0 || (value.visibility !== "ui" && value.visibility !== "internal")
    || !isSafeInteger(value.createdAt) || !isSafeString(value.safeSummary) || typeof value.kind !== "string"
    || !EVENT_KINDS.has(value.kind as AgentRunEvent["kind"])
    || !isRecord(value.payload)) fail("trace event fields");
  assertPlainJson(value.payload);
  return value as unknown as AgentRunTraceEvent;
};

const payloadKeys = (kind: AgentRunEvent["kind"]): readonly string[] => {
  switch (kind) {
    case "run_accepted": return ["admissionLabel"];
    case "capability_receipt": return ["adapter", "capabilityLabel", "deterministic", "tier"];
    case "context_receipt": return ["contextLabel", "expiresAt", "inclusionReason", "itemCount", "ownerLabel", "policyDecision", "redactedPreview", "sourceDigest", "sourceKind", "sourceLabel"];
    case "status": return ["progressPct", "status"];
    case "tool_request": return ["callLabel", "idemLabel", "timeoutMs", "toolName"];
    case "tool_result": return ["callLabel", "durationMs", "resultSummary", "retryable", "toolName"];
    case "tool_error": return ["callLabel", "errorCode", "errorSummary", "retryable", "toolName"];
    case "approval_requested": return ["approvalLabel", "callLabel", "expiresAt", "reason"];
    case "approval_resolved": return ["approvalLabel", "callLabel", "resolution"];
    case "usage": return ["durationMs", "inputCount", "outputCount", "totalCount", "usageLabel"];
    case "recovery": return ["action", "fromAttemptLabel", "reason", "recoveryLabel", "toAttemptLabel"];
    case "terminal": return ["recoveryAction", "retryable", "terminalCode", "terminalOutcome"];
  }
};

const validateTraceBundle = (value: unknown): AgentRunTraceBundle => {
  if (!isRecord(value) || !exactKeys(value, ["buildId", "bundleDigest", "contextReceipts", "durableState", "eventTrace", "projection", "projectionDigest", "runId", "schema", "schemaVersion", "timings", "toolEnvelopes", "traceDigest"])) fail("bundle shape");
  if (value.schema !== AGENT_RUN_TRACE_SCHEMA || value.schemaVersion !== CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION
    || !isSafeLabel(value.buildId) || !isSafeLabel(value.runId) || !Array.isArray(value.eventTrace)
    || !Array.isArray(value.contextReceipts) || !Array.isArray(value.toolEnvelopes)
    || !Array.isArray(value.timings) || !Array.isArray(value.durableState)
    || !SAFE_DIGEST.test(String(value.projectionDigest)) || !SAFE_DIGEST.test(String(value.traceDigest))
    || !SAFE_DIGEST.test(String(value.bundleDigest))) fail("bundle fields");
  const eventTrace = value.eventTrace.map(validateTraceEvent);
  if (eventTrace.length === 0 || eventTrace[0]!.kind !== "run_accepted") fail("empty or unaccepted trace");
  for (const [index, event] of eventTrace.entries()) {
    if (event.runLabel !== value.runId || event.sequence !== index + 1 || !exactKeys(event.payload, payloadKeys(event.kind))) fail("trace ordering");
  }
  const detailShapes: readonly (readonly string[])[] = [
    ["contextLabel", "policyDecision", "sequence", "sourceKind"],
    ["callLabel", "kind", "outcome", "sequence", "toolName"],
    ["createdAt", "durationMs", "sequence"],
    ["sequence", "stateKind", "stateLabel"],
  ];
  for (const [entries, expected] of [
    [value.contextReceipts, detailShapes[0]!], [value.toolEnvelopes, detailShapes[1]!],
    [value.timings, detailShapes[2]!], [value.durableState, detailShapes[3]!],
  ] as const) {
    for (const entry of entries) {
      if (!isRecord(entry) || !exactKeys(entry, expected)) fail("bundle detail");
      assertPlainJson(entry);
    }
  }
  assertPlainJson(value.projection);
  assertTracePrivacy(value);
  return value as unknown as AgentRunTraceBundle;
};

const syntheticEvent = (event: AgentRunTraceEvent): AgentRunEvent => {
  const payload = event.payload;
  const base = {
    schemaVersion: CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
    runId: event.runLabel, attemptId: event.attemptLabel, eventId: event.eventLabel,
    sequence: event.sequence, visibility: event.visibility, createdAt: event.createdAt,
    safeSummary: event.safeSummary,
  };
  const p = (key: string): unknown => payload[key];
  const value = (() => {
    switch (event.kind) {
      case "run_accepted": return { ...base, kind: event.kind, admissionId: p("admissionLabel") };
      case "capability_receipt": return { ...base, kind: event.kind, capabilityId: p("capabilityLabel"), tier: p("tier"), adapter: p("adapter"), deterministic: p("deterministic") };
      case "context_receipt": return { ...base, kind: event.kind, contextReceiptId: p("contextLabel"), sourceKind: p("sourceKind"), sourceRef: p("sourceLabel"), sourceHash: p("sourceDigest"), ownerRef: p("ownerLabel"), expiresAt: p("expiresAt"), redactedPreview: p("redactedPreview"), tokenEstimate: p("itemCount"), inclusionReason: p("inclusionReason"), policyDecision: p("policyDecision") };
      case "status": return { ...base, kind: event.kind, status: p("status"), progressPct: p("progressPct") };
      case "tool_request": return { ...base, kind: event.kind, callId: p("callLabel"), toolName: p("toolName"), timeoutMs: p("timeoutMs"), idempotencyKey: p("idemLabel") };
      case "tool_result": return { ...base, kind: event.kind, callId: p("callLabel"), toolName: p("toolName"), resultSummary: p("resultSummary"), durationMs: p("durationMs"), retryable: p("retryable") };
      case "tool_error": return { ...base, kind: event.kind, callId: p("callLabel"), toolName: p("toolName"), errorCode: p("errorCode"), errorSummary: p("errorSummary"), retryable: p("retryable") };
      case "approval_requested": return { ...base, kind: event.kind, approvalId: p("approvalLabel"), callId: p("callLabel"), reason: p("reason"), expiresAt: p("expiresAt") };
      case "approval_resolved": return { ...base, kind: event.kind, approvalId: p("approvalLabel"), callId: p("callLabel"), resolution: p("resolution") };
      case "usage": return { ...base, kind: event.kind, usageId: p("usageLabel"), inputTokens: p("inputCount"), outputTokens: p("outputCount"), totalTokens: p("totalCount"), durationMs: p("durationMs") };
      case "recovery": return { ...base, kind: event.kind, recoveryId: p("recoveryLabel"), action: p("action"), reason: p("reason"), fromAttemptId: p("fromAttemptLabel"), toAttemptId: p("toAttemptLabel") };
      case "terminal": return { ...base, kind: event.kind, terminalOutcome: p("terminalOutcome"), terminalCode: p("terminalCode"), retryable: p("retryable"), recoveryAction: p("recoveryAction") };
    }
  })();
  const parsed = parseAgentRunEvent(value);
  if (!parsed.ok) fail(`trace event ${event.sequence} cannot replay (${parsed.reason})`);
  return parsed.event;
};

const validateNoRawSecrets = (bundle: AgentRunTraceBundle, sourceEvents: readonly AgentRunEvent[], bytes: string): void => {
  assertTracePrivacy(bundle);
  let parsed: unknown;
  try {
    parsed = JSON.parse(bytes);
  } catch {
    fail("export bytes are not JSON");
  }
  const strings: string[] = [];
  jsonStringValues(parsed, (text) => strings.push(text));
  for (const event of sourceEvents) {
    const candidate = event as unknown as Record<string, unknown>;
    for (const key of ["runId", "attemptId", "eventId", "admissionId", "capabilityId", "contextReceiptId", "sourceRef", "sourceHash", "ownerRef", "callId", "idempotencyKey", "approvalId", "usageId", "recoveryId", "fromAttemptId", "toAttemptId"]) {
      const raw = candidate[key];
      if (typeof raw !== "string" || raw.length < 3) continue;
      const escaped = raw.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
      const token = new RegExp(`(?:^|[^A-Za-z0-9])${escaped}(?:$|[^A-Za-z0-9])`, "u");
      if (strings.some((text) => text === raw || token.test(text))) fail(`raw ${key} escaped`);
    }
  }
};

export const exportAgentRunTrace = (
  store: AgentRunEventStore,
  runId: string,
  input: { readonly buildId: string },
): AgentRunTraceExport => {
  if (!isSafeLabel(runId) || !isSafeLabel(input.buildId) || input.buildId.length > AGENT_RUN_TRACE_BUILD_ID_MAX) fail("unsafe run/build id");
  const sourceEvents = store.list(runId);
  if (sourceEvents.length === 0) fail("run not found");
  const labels = labeler();
  const safeRunId = labels("run", runId);
  const eventTrace = sourceEvents.map((event) => redactEvent(event, labels, safeRunId));
  // Project the redacted synthetic events, not the source events.  This is the
  // important privacy boundary: even an otherwise-safe UI projection contains
  // event/run/attempt IDs, so projecting first would copy durable identifiers
  // into the bundle before the remapper had a chance to run.
  const projection = projectAgentRunTimeline(eventTrace.map(syntheticEvent));
  if (projection === null) fail("run has no valid projection");
  const contextReceipts = eventTrace.filter((event) => event.kind === "context_receipt").map((event) => ({ sequence: event.sequence, contextLabel: event.payload.contextLabel!, sourceKind: event.payload.sourceKind!, policyDecision: event.payload.policyDecision! }));
  const toolEnvelopes = eventTrace.filter((event) => event.kind === "tool_request" || event.kind === "tool_result" || event.kind === "tool_error").map((event) => ({ sequence: event.sequence, kind: event.kind, callLabel: event.payload.callLabel!, toolName: event.payload.toolName!, outcome: event.kind === "tool_result" ? "succeeded" : event.kind === "tool_error" ? "failed" : "requested" }));
  const timings = eventTrace.map((event) => ({ sequence: event.sequence, createdAt: event.createdAt, durationMs: event.payload.durationMs ?? null }));
  const durableState = eventTrace.map((event) => ({ sequence: event.sequence, stateLabel: event.eventLabel, stateKind: event.kind }));
  const redactedProjection = JSON.parse(canonicalTraceJson(projection as unknown as JsonValue)) as AgentRunVisibleTimeline;
  const traceWithoutDigests = { schema: AGENT_RUN_TRACE_SCHEMA, schemaVersion: CURRENT_AGENT_RUN_TRACE_SCHEMA_VERSION, buildId: input.buildId, runId: safeRunId, eventTrace, contextReceipts, toolEnvelopes, timings, durableState, projection: redactedProjection } as const;
  const traceDigest = digest(canonicalTraceJson(eventTrace as unknown as JsonValue));
  const projectionDigest = digest(canonicalTraceJson(redactedProjection as unknown as JsonValue));
  const unsignedBundle = { ...traceWithoutDigests, projectionDigest, traceDigest } as const;
  const bundleDigest = digest(canonicalTraceJson(unsignedBundle as unknown as JsonValue));
  const bundle = { ...unsignedBundle, bundleDigest } as AgentRunTraceBundle;
  const bytes = `${canonicalTraceJson(bundle as unknown as JsonValue)}\n`;
  validateNoRawSecrets(bundle, sourceEvents, bytes);
  return { bundle, bytes };
};

export const replayAgentRunTrace = (input: unknown): AgentRunTraceReplay => {
  const bundle = validateTraceBundle(input);
  const { bundleDigest, ...unsignedBundle } = bundle;
  if (digest(canonicalTraceJson(unsignedBundle as unknown as JsonValue)) !== bundleDigest) {
    fail("bundle digest mismatch");
  }
  const traceDigest = digest(canonicalTraceJson(bundle.eventTrace as unknown as JsonValue));
  if (traceDigest !== bundle.traceDigest) fail("trace digest mismatch");
  const projection = projectAgentRunTimeline(bundle.eventTrace.map(syntheticEvent));
  if (projection === null) fail("replayed trace has no valid projection");
  const projectionDigest = digest(canonicalTraceJson(projection as unknown as JsonValue));
  if (projectionDigest !== bundle.projectionDigest
    || canonicalTraceJson(projection as unknown as JsonValue) !== canonicalTraceJson(bundle.projection as unknown as JsonValue)) fail("projection mismatch");
  return { bundle, projection, projectionDigest };
};
