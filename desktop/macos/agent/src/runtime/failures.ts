import type { ProductionAdapterId } from "../adapters/interface.js";

export type RuntimeFailureSource = "adapter_process" | "adapter_execution" | "runtime";

/** Closed cross-surface taxonomy; detailed legacy codes remain diagnostic-only. */
export const RUNTIME_FAILURE_CODES = [
  "authentication",
  "quota_exceeded",
  "invalid_request",
  "timeout",
  "transport_interruption",
  "adapter_unavailable",
  "adapter_incompatible",
  "bridge_start_failed",
  "provider_setup_needed",
  "malformed_or_oversized_tool_result",
  "cancelled",
  "stale_owner",
  "policy_denied",
  "unknown",
] as const;

export type RuntimeFailureCode = (typeof RUNTIME_FAILURE_CODES)[number];

export function isRuntimeFailureCode(value: unknown): value is RuntimeFailureCode {
  return typeof value === "string" && (RUNTIME_FAILURE_CODES as readonly string[]).includes(value);
}

export interface RuntimeFailure {
  /** Detailed local code retained for logs and backward-compatible UI copy. */
  code: string;
  /** Bounded code carried across adapters and checked by the shared fixture. */
  failureCode?: RuntimeFailureCode;
  userMessage: string;
  technicalMessage?: string;
  source?: RuntimeFailureSource;
  adapterId?: string;
  provider?: string;
  retryable?: boolean;
}

export class AdapterRuntimeError extends Error {
  readonly failure: RuntimeFailure;

  constructor(failure: RuntimeFailure) {
    super(failure.userMessage);
    this.name = "AdapterRuntimeError";
    this.failure = normalizeRuntimeFailure(failure);
  }
}

export function messageFrom(error: unknown): string {
  if (error instanceof AdapterRuntimeError) {
    return error.failure.userMessage;
  }
  return error instanceof Error ? error.message : String(error);
}

const CONTEXT_SNAPSHOT_PROJECTION_MISMATCH = "context_snapshot_projection_mismatch";

export function unexpectedQueryErrorDiagnostic(error: unknown): string | null {
  const message = messageFrom(error);
  if (message === CONTEXT_SNAPSHOT_PROJECTION_MISMATCH) return null;
  return `Unhandled query error: ${String(error)}`;
}

export function failureFromError(
  error: unknown,
  fallback: Omit<RuntimeFailure, "userMessage"> & { userMessage?: string }
): RuntimeFailure {
  if (error instanceof AdapterRuntimeError) {
    return error.failure;
  }
  return normalizeRuntimeFailure({
    ...fallback,
    userMessage: fallback.userMessage ?? messageFrom(error),
    technicalMessage: fallback.technicalMessage ?? messageFrom(error),
  });
}

export function normalizeRuntimeFailure(failure: RuntimeFailure): RuntimeFailure {
  const userMessage = compactWhitespace(failure.userMessage) || "Agent run failed";
  const technicalMessage = compactWhitespace(failure.technicalMessage ?? "");
  return {
    ...failure,
    failureCode: failure.failureCode ?? normalizeRuntimeFailureCode(failure.code),
    userMessage,
    technicalMessage: technicalMessage || undefined,
  };
}

/** Maps every adapter/runtime detail code onto the shared bounded vocabulary. */
export function normalizeRuntimeFailureCode(value: string): RuntimeFailureCode {
  const code = value.toLowerCase();
  if (code.includes("auth")) return "authentication";
  if (code.includes("quota") || code.includes("rate_limit") || code.includes("429")) return "quota_exceeded";
  if (code.includes("invalid") || code.includes("malformed") || code.includes("400")) return "invalid_request";
  if (code.includes("timeout") || code.includes("timed_out")) return "timeout";
  if (code.includes("transport") || code.includes("process") || code.includes("connection")) return "transport_interruption";
  if (code.includes("not_registered") || code.includes("unavailable")) return "adapter_unavailable";
  if (code.includes("config") || code.includes("incompatible") || code.includes("stale_binding")) return "adapter_incompatible";
  if (code.includes("bridge_start")) return "bridge_start_failed";
  if (code.includes("provider_setup")) return "provider_setup_needed";
  if (code.includes("oversized") || code.includes("tool_result")) return "malformed_or_oversized_tool_result";
  if (code.includes("cancel")) return "cancelled";
  if (code.includes("stale_owner") || code.includes("owner_changed")) return "stale_owner";
  if (code.includes("policy") || code.includes("permission") || code.includes("authority")) return "policy_denied";
  return "unknown";
}

export function sanitizeProcessDiagnostic(text: string): string {
  return text
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/sk-[A-Za-z0-9_-]{12,}/g, "sk-[redacted]")
    .replace(/(api[_-]?key["'\s:=]+)[A-Za-z0-9._~+/=-]+/gi, "$1[redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1_000);
}

export function failureFromProcessExit(input: {
  adapterId: ProductionAdapterId;
  exitCode: number | null;
  recentStderr: string;
}): RuntimeFailure {
  const diagnostic = sanitizeProcessDiagnostic(input.recentStderr);
  const technicalMessage = diagnostic || `${input.adapterId} ACP process exited with code ${input.exitCode}`;
  const classified = classifyAdapterProcessFailure(input.adapterId, diagnostic);
  if (classified) {
    return normalizeRuntimeFailure({
      source: "adapter_process",
      adapterId: input.adapterId,
      technicalMessage,
      ...classified,
    });
  }
  const provider = providerFromDiagnostic(diagnostic);
  const label = adapterFailureLabel(input.adapterId, provider);
  return normalizeRuntimeFailure({
    code: "adapter_process_exited",
    source: "adapter_process",
    adapterId: input.adapterId,
    provider,
    retryable: true,
    userMessage: `${label} failed: ${technicalMessage}`,
    technicalMessage,
  });
}

function classifyAdapterProcessFailure(
  adapterId: ProductionAdapterId,
  diagnostic: string
): (Pick<RuntimeFailure, "code" | "userMessage"> & Partial<RuntimeFailure>) | undefined {
  if (adapterId === "openclaw" && isOpenClawInvalidConfig(diagnostic)) {
    return {
      code: "adapter_config_invalid",
      retryable: false,
      userMessage:
        "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`.",
    };
  }
  return undefined;
}

// Adapter stderr is unstructured; this is the sanctioned adapter-boundary sniffing site
// (Phase 6 item 7 exception). Prefer typed RuntimeFailure codes when the adapter can classify.
function isOpenClawInvalidConfig(diagnostic: string): boolean {
  const lower = diagnostic.toLowerCase();
  return (
    lower.includes("openclaw config is invalid") ||
    lower.includes("invalid config at") ||
    lower.includes("legacy config keys detected") ||
    lower.includes("openclaw doctor --fix") ||
    lower.includes("openclaw config validate") ||
    lower.includes("channels.telegram.streaming: invalid config")
  );
}

export function failureFromProcessError(input: {
  adapterId: ProductionAdapterId;
  message: string;
}): RuntimeFailure {
  const diagnostic = sanitizeProcessDiagnostic(input.message);
  const provider = providerFromDiagnostic(diagnostic);
  const label = adapterFailureLabel(input.adapterId, provider);
  return normalizeRuntimeFailure({
    code: "adapter_process_error",
    source: "adapter_process",
    adapterId: input.adapterId,
    provider,
    retryable: true,
    userMessage: `${label} failed: ${diagnostic || `${input.adapterId} ACP process error`}`,
    technicalMessage: diagnostic,
  });
}

function providerFromDiagnostic(diagnostic: string): string | undefined {
  const lower = diagnostic.toLowerCase();
  if (lower.includes("openai")) return "openai";
  if (lower.includes("anthropic") || lower.includes("claude")) return "anthropic";
  if (lower.includes("gemini") || lower.includes("google")) return "google";
  return undefined;
}

function adapterFailureLabel(adapterId: ProductionAdapterId, provider?: string): string {
  switch (adapterId) {
    case "openclaw":
      return "OpenClaw";
    case "hermes":
      return "Hermes";
    case "pi-mono":
      return "pi-mono";
    case "acp":
      if (provider === "openai") {
        return "OpenAI";
      }
      return "ACP";
    case "codex":
      return "Codex";
  }
}

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}
