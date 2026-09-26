// Falling back to the next agent when a run dies.
//
// adapter-scoring.ts ranks the connected agents and produces a chain; that
// chain has to survive somewhere, because a spawn cannot observe the failure it
// is supposed to recover from. `spawnBackgroundAgent` creates the durable run
// and returns a receipt, then executes the adapter asynchronously (`void
// execution` in kernel-runs.ts) — so "the agent could not start" lands after
// the caller already has its answer.
//
// The untried remainder of the chain therefore rides on the run's own metadata,
// and this supervisor watches terminal run failures. When a failed run still
// has agents left, it re-dispatches the same prompt to the next one. Each retry
// carries a shorter chain, so the sequence always terminates.
//
// Kernel-side facts come from `agentFallbackPlanForRun`; the decision to retry
// is made here, so the kernel keeps no retry policy of its own.

import type { AgentEvent } from "./types.js";

/** Run-metadata key holding the untried remainder of the routing chain. */
export const AGENT_FALLBACK_CHAIN_KEY = "agentFallbackChain";

/**
 * Run-metadata key listing the agents that already failed this task, oldest
 * first. This is how a fallback becomes visible: the retry run itself records
 * what it replaced, so any surface reading the run can say "Claude Code failed,
 * Hermes took over" instead of the task quietly changing agents.
 */
export const AGENT_FALLBACK_FROM_KEY = "agentFallbackFrom";

/** The one event that means an agent finished without doing the job. */
const RUN_FAILED_EVENT = "run.failed";

/**
 * A hard ceiling on retries per originating request, independent of the chain
 * length. The chain already shrinks on every hop; this only bounds pathological
 * cases such as hand-written metadata.
 */
const MAX_FALLBACKS_PER_REQUEST = 4;

export interface AgentFallbackPlan {
  readonly ownerId: string;
  readonly sessionId: string;
  /** The run that just failed. */
  readonly failedRunId: string;
  readonly clientId: string;
  /** Request id of the failed run, used to derive the retry's own id. */
  readonly requestId: string;
  readonly prompt: string;
  readonly cwd?: string;
  /** The agent that just failed. */
  readonly failedAdapterId: string;
  /** The agent to try now. */
  readonly nextAdapterId: string;
  /** Agents still untried after this one. */
  readonly remainingChain: readonly string[];
  /** Metadata for the retry, already carrying `remainingChain`. */
  readonly metadata: Record<string, unknown>;
}

export interface AgentFallbackSpawnInput {
  ownerId: string;
  clientId: string;
  requestId: string;
  prompt: string;
  adapterId: string;
  defaultAdapterId: string;
  cwd?: string;
  metadata: Record<string, unknown>;
  trustedUserSpawn: true;
}

export interface AgentFallbackSupervisorOptions {
  /** Kernel-side facts about a failed run. Null when nothing is left to try. */
  planForRun: (runId: string) => AgentFallbackPlan | null;
  /** Starts the retry. Rejections are logged, never thrown at the emitter. */
  spawn: (input: AgentFallbackSpawnInput) => Promise<unknown>;
  log?: (message: string) => void;
}

/**
 * A kernel event subscriber that retries failed runs on their next agent.
 *
 * Returns synchronously: subscribers run inside the kernel's emit path, so the
 * retry is started and awaited out of band. A failure to re-dispatch is logged
 * and dropped — a broken fallback must never take down the run that reported it.
 */
export function createAgentFallbackSupervisor(
  options: AgentFallbackSupervisorOptions,
): (event: AgentEvent) => void {
  const { planForRun, spawn, log } = options;
  // A run reports terminal failure once, but a duplicate emit must not spawn
  // twice; ids are retained only while the process lives.
  const handledRunIds = new Set<string>();

  return (event: AgentEvent): void => {
    if (event.type !== RUN_FAILED_EVENT || !event.runId) return;
    if (handledRunIds.has(event.runId)) return;

    const plan = planForRun(event.runId);
    if (!plan) return;

    const attempt = fallbackAttemptNumber(plan);
    if (attempt > MAX_FALLBACKS_PER_REQUEST) {
      log?.(`agent_fallback_exhausted run=${plan.failedRunId} attempts=${attempt}`);
      return;
    }

    handledRunIds.add(event.runId);
    if (handledRunIds.size > 512) {
      // Bounded so a long-lived daemon cannot grow this without limit.
      const oldest = handledRunIds.values().next().value as string | undefined;
      if (oldest) handledRunIds.delete(oldest);
    }

    log?.(
      `agent_fallback run=${plan.failedRunId} from=${plan.failedAdapterId} next=${plan.nextAdapterId} remaining=${plan.remainingChain.length}`,
    );
    void spawn({
      ownerId: plan.ownerId,
      clientId: plan.clientId,
      requestId: fallbackRequestId(plan, attempt),
      prompt: plan.prompt,
      adapterId: plan.nextAdapterId,
      defaultAdapterId: plan.nextAdapterId,
      cwd: plan.cwd,
      metadata: plan.metadata,
      // The user already authorized this task; the retry is the daemon
      // re-dispatching it, and has no caller session of its own.
      trustedUserSpawn: true,
    }).catch((error: unknown) => {
      log?.(
        `agent_fallback_failed run=${plan.failedRunId} next=${plan.nextAdapterId} error=${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    });
  };
}

/** How many hops this request has already taken, derived from its request id. */
function fallbackAttemptNumber(plan: AgentFallbackPlan): number {
  const match = /-fallback-(\d+)$/.exec(plan.requestId);
  return match ? Number(match[1]) + 1 : 1;
}

/** A distinct request id per hop, so no retry replays an earlier one by key. */
function fallbackRequestId(plan: AgentFallbackPlan, attempt: number): string {
  const base = plan.requestId.replace(/-fallback-\d+$/, "");
  return `${base}-fallback-${attempt}`;
}
