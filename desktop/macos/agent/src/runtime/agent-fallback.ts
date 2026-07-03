/**
 * Fallback executor: runs a routing plan's agents in order, advancing to the
 * next agent when one fails in a retryable way (crash, timeout, "can't handle
 * it"), and logging why each fallback happened.
 *
 * Pure control-flow only — the caller supplies `runOne` (which actually drives
 * the adapter for one attempt) and `isRetryable` (which classifies a failure,
 * typically via runtime/failures.ts). This keeps the fallback policy unit-
 * testable without spawning real agents.
 */

import type { RoutableAgentId } from "./agent-router.js";

export interface FallbackAttemptLog {
  agent: RoutableAgentId;
  ok: boolean;
  /** Why we moved on from this agent (only set when ok=false). */
  reason?: string;
  /** Whether the failure allowed trying the next agent. */
  retryable?: boolean;
}

export interface FallbackResult<T> {
  ok: boolean;
  /** The successful agent, if any. */
  agent?: RoutableAgentId;
  /** The value returned by `runOne` on success. */
  value?: T;
  /** Per-agent trail, in the order attempted. */
  attempts: FallbackAttemptLog[];
  /** The final error when every agent failed. */
  error?: unknown;
}

export interface FallbackOptions<T> {
  /** Execute one attempt against a single agent. Resolves on success, throws on failure. */
  runOne: (agent: RoutableAgentId) => Promise<T>;
  /** Classify a thrown failure: true => try the next agent, false => stop and surface it. */
  isRetryable: (error: unknown, agent: RoutableAgentId) => boolean;
  /** Structured log sink; called once per attempt outcome. */
  log?: (message: string) => void;
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

/**
 * Try each agent in `order` until one succeeds or a non-retryable failure
 * occurs. Returns the outcome plus a full attempt trail.
 */
export async function executeWithFallback<T>(
  order: readonly RoutableAgentId[],
  { runOne, isRetryable, log }: FallbackOptions<T>
): Promise<FallbackResult<T>> {
  const attempts: FallbackAttemptLog[] = [];

  if (order.length === 0) {
    return { ok: false, attempts, error: new Error("No agent available to run the task.") };
  }

  let lastError: unknown;
  for (let i = 0; i < order.length; i++) {
    const agent = order[i];
    try {
      const value = await runOne(agent);
      attempts.push({ agent, ok: true });
      log?.(`agent=${agent} succeeded`);
      return { ok: true, agent, value, attempts };
    } catch (error) {
      lastError = error;
      const retryable = isRetryable(error, agent);
      const reason = messageOf(error);
      attempts.push({ agent, ok: false, reason, retryable });
      const hasNext = i < order.length - 1;
      if (!retryable) {
        log?.(`agent=${agent} failed non-retryably: ${reason} — stopping`);
        break;
      }
      log?.(
        hasNext
          ? `agent=${agent} failed: ${reason} — falling back to ${order[i + 1]}`
          : `agent=${agent} failed: ${reason} — no more agents to try`
      );
    }
  }

  return { ok: false, attempts, error: lastError };
}
