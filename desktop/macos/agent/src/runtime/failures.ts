import type { ProductionAdapterId } from "../adapters/interface.js";

export type RuntimeFailureSource = "adapter_process" | "adapter_execution" | "runtime";

export interface RuntimeFailure {
  code: string;
  userMessage: string;
  technicalMessage?: string;
  source?: RuntimeFailureSource;
  adapterId?: string;
  provider?: string;
  retryable?: boolean;
}

type ClassifiedRuntimeFailure = Pick<RuntimeFailure, "code" | "userMessage"> &
  Partial<Omit<RuntimeFailure, "code" | "userMessage">>;

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
    userMessage,
    technicalMessage: technicalMessage || undefined,
  };
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
): ClassifiedRuntimeFailure | undefined {
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
    case "codex":
      return "Codex";
    case "pi-mono":
      return "pi-mono";
    case "acp":
      if (provider === "openai") {
        return "OpenAI";
      }
      return "ACP";
  }
}

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}
