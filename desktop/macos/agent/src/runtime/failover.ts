// Execution-time failover for the "auto" agent chain.
//
// The selector (agent-selector.ts) produces an ordered fallback chain for a task.
// This module drives that chain at runtime: if the primary agent fails to start
// or fails mid-run BEFORE it has streamed any answer to the user, it transparently
// hands off to the next agent in the chain. Once answer content has reached the
// user, we never retry on another agent (that would double-post or re-run tools).
//
// All side effects are injected so the orchestration is pure and unit-testable.

import type { ErrorMessage } from "../protocol.js";
import type { HandleQueryOutcome } from "./compatibility-facade.js";
import { isRetryableAgentFailure, planFailover, type AgentId } from "./agent-selector.js";

export interface RunAgentChainDeps {
  /** Ordered adapter ids to try; chain[0] is the primary. */
  chain: string[];
  /** Activate/start the adapter; throws on startup/activation failure. */
  ensure: (adapterId: string) => Promise<void>;
  /**
   * Run the query on the adapter. When `suppressError` is true the facade must
   * NOT emit its terminal error, so we can fail over without the user first
   * seeing an error from the agent we are abandoning.
   */
  run: (adapterId: string, suppressError: boolean) => Promise<HandleQueryOutcome>;
  /** Whether user-visible answer content has already streamed for this request. */
  hasEmitted: () => boolean;
  /**
   * True for adapters that may have performed side effects (e.g. a one-shot exec
   * agent that edits files with buffered, non-streaming output) and so must NOT be
   * failed over from once it has started running. Startup failover is still allowed.
   */
  blockRunFailover?: (adapterId: string) => boolean;
  /** Emit a transparent "trying X instead" notice to the user. */
  onFailover: (message: string) => void;
  /** Emit the terminal error when we give up (chain exhausted / not retryable). */
  onError: (message: string, errorMessage?: ErrorMessage) => void;
  log?: (message: string) => void;
}

export interface RunAgentChainResult {
  /** Adapter ids attempted, in order. */
  attempted: string[];
  /** Whether the final attempt still failed. */
  failed: boolean;
  /** Number of transparent hand-offs performed. */
  handoffs: number;
}

/**
 * Run a query across a fallback chain, handing off to the next agent when one
 * fails before streaming any answer. Returns a summary of what was attempted.
 */
export async function runAgentChain(deps: RunAgentChainDeps): Promise<RunAgentChainResult> {
  const chain = deps.chain;
  const attempted: string[] = [];
  let handoffs = 0;

  for (let i = 0; i < chain.length; i++) {
    const adapterId = chain[i];
    const isLast = i === chain.length - 1;
    attempted.push(adapterId);

    // 1) Activation / startup. This precedes any streaming, so a failure here is
    //    always safe to fail over from.
    let startupError: string | undefined;
    try {
      await deps.ensure(adapterId);
    } catch (err) {
      startupError = err instanceof Error ? err.message : String(err);
    }
    if (startupError !== undefined) {
      const plan = isLast ? null : planFailover(chain as AgentId[], adapterId as AgentId, startupError);
      if (plan) {
        deps.log?.(`Agent failover (startup): ${adapterId} -> ${plan.next}: ${startupError}`);
        deps.onFailover(plan.message);
        handoffs++;
        continue;
      }
      deps.onError(startupError);
      return { attempted, failed: true, handoffs };
    }

    // 2) Run. Suppress the terminal error unless this is the last resort, so a
    //    retryable failure can hand off silently.
    const suppress = !isLast;
    const outcome = await deps.run(adapterId, suppress);
    if (!outcome.failed) {
      return { attempted, failed: false, handoffs };
    }

    const errText = outcome.errorMessage?.message ?? "Agent run failed";
    if (!suppress) {
      // Last resort: the facade already emitted the error itself.
      return { attempted, failed: true, handoffs };
    }
    // Suppressed: we own the emit-or-fail-over decision. Never retry once the user
    // has seen answer content, and never retry a side-effecting adapter that already
    // started running (it may have edited files even though it emitted nothing).
    const runFailoverBlocked = deps.blockRunFailover?.(adapterId) ?? false;
    const canRetry = !runFailoverBlocked && !deps.hasEmitted() && isRetryableAgentFailure(errText);
    const plan = canRetry ? planFailover(chain as AgentId[], adapterId as AgentId, errText) : null;
    if (plan) {
      deps.log?.(`Agent failover (run): ${adapterId} -> ${plan.next}: ${errText}`);
      deps.onFailover(plan.message);
      handoffs++;
      continue;
    }
    deps.onError(errText, outcome.errorMessage);
    return { attempted, failed: true, handoffs };
  }

  return { attempted, failed: true, handoffs };
}
