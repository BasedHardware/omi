/**
 * Shared durable-queue primitives for every kernel SQLite outbox.
 * Callers keep their existing tables; this is the single implementation of
 * per-item isolation, bounded attempts plus dead letter, identity adopt,
 * optional priority, oldest-ready age, and typed non-success outcomes.
 */

export type ProcessOutcome =
  | { kind: "ack" }
  | { kind: "retry"; errorText: string; reason?: string }
  | { kind: "reject"; errorText: string; reason: string };

export interface QueuePolicy {
  maxAttempts: number;
  baseBackoffMs: number;
  maxBackoffMs: number;
}

export interface AttemptDecision {
  terminal: boolean;
  attemptCount: number;
  retryAtMs: number | undefined;
  errorText: string;
  reason: string;
  status: "retrying" | "dead_letter";
}

export interface IsolatedResult<T> {
  item: T;
  outcome: ProcessOutcome;
  raised: boolean;
}

export const JOURNAL_OUTBOX_POLICY: QueuePolicy = {
  maxAttempts: 5,
  baseBackoffMs: 1_000,
  maxBackoffMs: 60_000,
};

export const DEFERRAL_OUTBOX_POLICY: QueuePolicy = {
  maxAttempts: 5,
  baseBackoffMs: 1_000,
  maxBackoffMs: 30_000,
};

export const RETRYABLE_BACKEND_OUTBOX_CODES = [
  "backend_sync_failed",
  "backend_delete_failed",
  "backend_sync_owner_changed",
  "backend_sync_http_retryable",
  "network_unavailable",
  "timeout",
  "connection_lost",
] as const;

const MAX_ERROR_TEXT = 2000;
const MAX_BACKOFF_EXPONENT = 30;

function boundError(text: string): string {
  return text.slice(0, MAX_ERROR_TEXT);
}

export function backoffMs(policy: QueuePolicy, attemptCount: number): number {
  const exponent = Math.min(Math.max(attemptCount - 1, 0), MAX_BACKOFF_EXPONENT);
  return Math.min(policy.maxBackoffMs, policy.baseBackoffMs * 2 ** exponent);
}

export function decideAttempt(input: {
  attemptCount: number;
  outcome: ProcessOutcome;
  policy: QueuePolicy;
  nowMs: number;
}): AttemptDecision {
  if (input.outcome.kind === "ack") {
    throw new Error("ack is not an attempt failure");
  }
  if (!Number.isSafeInteger(input.attemptCount) || input.attemptCount < 1) {
    throw new Error("attemptCount must be at least 1");
  }
  const errorText = boundError(input.outcome.errorText);
  const reason = input.outcome.kind === "reject"
    ? input.outcome.reason
    : (input.outcome.reason ?? "retryable");
  const terminal = input.outcome.kind === "reject"
    || input.attemptCount >= input.policy.maxAttempts;
  if (terminal) {
    return {
      terminal: true,
      attemptCount: input.attemptCount,
      retryAtMs: undefined,
      errorText,
      reason,
      status: "dead_letter",
    };
  }
  return {
    terminal: false,
    attemptCount: input.attemptCount,
    retryAtMs: input.nowMs + backoffMs(input.policy, input.attemptCount),
    errorText,
    reason,
    status: "retrying",
  };
}

export function adoptOnIdentity(existingId: string | null | undefined, itemId: string): { adopted: boolean } {
  if (!itemId) throw new Error("itemId is required");
  if (existingId == null) return { adopted: false };
  if (existingId !== itemId) throw new Error("enqueue identity mismatch");
  return { adopted: true };
}

export function oldestReadyCreatedAtMs(createdAtMs: Array<number | null | undefined>): number | null {
  let oldest: number | null = null;
  for (const value of createdAtMs) {
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    if (oldest == null || value < oldest) oldest = value;
  }
  return oldest;
}

export function oldestReadyAgeMs(
  createdAtMs: Array<number | null | undefined>,
  nowMs: number,
): number | null {
  const oldest = oldestReadyCreatedAtMs(createdAtMs);
  if (oldest == null) return null;
  return Math.max(0, nowMs - oldest);
}

export function drainIsolated<T>(
  items: readonly T[],
  processOne: (item: T) => ProcessOutcome,
): IsolatedResult<T>[] {
  const results: IsolatedResult<T>[] = [];
  for (const item of items) {
    let raised = false;
    let outcome: ProcessOutcome;
    try {
      outcome = processOne(item);
    } catch (error) {
      raised = true;
      outcome = {
        kind: "reject",
        errorText: boundError(error instanceof Error ? error.message : String(error)),
        reason: "processor_exception",
      };
    }
    if (outcome == null || (outcome.kind !== "ack" && outcome.kind !== "retry" && outcome.kind !== "reject")) {
      raised = true;
      outcome = { kind: "reject", errorText: "processor returned a non-outcome", reason: "invalid_outcome" };
    }
    results.push({ item, outcome, raised });
  }
  return results;
}

export function backendOutboxRetryAtMs(input: {
  attemptCount: number;
  errorCode: string;
  nowMs: number;
  policy?: QueuePolicy;
}): number | undefined {
  const retryable = (RETRYABLE_BACKEND_OUTBOX_CODES as readonly string[]).includes(input.errorCode);
  const outcome: ProcessOutcome = retryable
    ? { kind: "retry", errorText: input.errorCode, reason: input.errorCode }
    : { kind: "reject", errorText: input.errorCode, reason: input.errorCode };
  return decideAttempt({
    attemptCount: input.attemptCount,
    outcome,
    policy: input.policy ?? JOURNAL_OUTBOX_POLICY,
    nowMs: input.nowMs,
  }).retryAtMs;
}
