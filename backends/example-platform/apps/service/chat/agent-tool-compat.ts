// domain-pending(DIV-CHAT-TOOL-001)

import {
  AGENT_TOOL_SCHEMA_VERSION,
  type AgentToolDefinition,
  type AgentToolRisk,
} from "./agent-tools";

export const PREVIOUS_AGENT_TOOL_SCHEMA_VERSION = 0 as const;

export const SUPPORTED_AGENT_TOOL_SCHEMA_VERSIONS = Object.freeze([
  PREVIOUS_AGENT_TOOL_SCHEMA_VERSION,
  AGENT_TOOL_SCHEMA_VERSION,
] as const);

const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const SUMMARY_MAX = 240;
const CONTROL = /[\u0000-\u001f\u007f]/u;

export type ParsedAgentToolDefinition =
  | { readonly ok: true; readonly definition: AgentToolDefinition }
  | { readonly ok: false; readonly reason: "unsupported_schema_version" | "invalid_definition" };

const safeSummary = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= SUMMARY_MAX
  && value.trim().length > 0 && !CONTROL.test(value);

/** Parse tool defs with a current-minus-one compatibility window. */
export const parseAgentToolDefinition = (input: unknown): ParsedAgentToolDefinition => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return { ok: false, reason: "invalid_definition" };
  }
  const record = input as Record<string, unknown>;
  const schemaVersion = record.schemaVersion;
  if (!SUPPORTED_AGENT_TOOL_SCHEMA_VERSIONS.includes(schemaVersion as typeof AGENT_TOOL_SCHEMA_VERSION)) {
    return { ok: false, reason: "unsupported_schema_version" };
  }
  const name = record.name;
  const risk = record.risk;
  const timeoutMs = record.timeoutMs;
  const retryable = record.retryable;
  const displaySummary = record.displaySummary;
  if (!SAFE_TOKEN.test(name as string) || (risk !== "safe" && risk !== "approval-required")
    || typeof timeoutMs !== "number" || !Number.isSafeInteger(timeoutMs)
    || timeoutMs <= 0 || timeoutMs > 300_000 || typeof retryable !== "boolean"
    || !safeSummary(displaySummary)) {
    return { ok: false, reason: "invalid_definition" };
  }
  return {
    ok: true,
    definition: Object.freeze({
      schemaVersion: AGENT_TOOL_SCHEMA_VERSION,
      name: name as string,
      risk: risk as AgentToolRisk,
      timeoutMs,
      retryable,
      displaySummary,
      validateInput: () => false,
      execute: async () => ({ summary: "replay stub", durationMs: 0, retryable: false }),
    }),
  };
};

/** Golden v0 fixture shape for replay tests. */
export const goldenAgentToolDefinitionV0 = Object.freeze({
  schemaVersion: PREVIOUS_AGENT_TOOL_SCHEMA_VERSION,
  name: "safe.lookup",
  risk: "safe",
  timeoutMs: 1_000,
  retryable: false,
  displaySummary: "Lookup fixture value",
});

/** Golden v0 run-event fixture lives beside agent-run-events tests. */
export const goldenAgentRunEventV0 = Object.freeze({
  schemaVersion: 0,
  runId: "run-golden-v0",
  attemptId: "attempt-golden-v0",
  eventId: "run-golden-v0:1:run_accepted",
  sequence: 1,
  visibility: "ui",
  createdAt: 1,
  safeSummary: "Run accepted",
  kind: "run_accepted",
  admissionId: "admission-golden-v0",
});
