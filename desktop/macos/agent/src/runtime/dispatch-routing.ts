/**
 * Glue between an inbound query and the agent router, used by index.ts live
 * dispatch. Kept as pure functions so the wiring can be unit-tested with a Node
 * harness (no process, no sockets) the same way the router/fallback are.
 */

import {
  resolveAgent,
  type AvailabilityMap,
  type RoutableAgentId,
  type RoutingPlan,
  type TaskType,
} from "./agent-router.js";
import type { RuntimeFailure } from "./failures.js";

/**
 * A single agent attempt failed. Carries whether the fallback executor should
 * advance to the next agent, plus the structured failure for the final emit.
 */
export class DispatchAttemptError extends Error {
  constructor(
    message: string,
    readonly retryable: boolean,
    readonly failure?: RuntimeFailure
  ) {
    super(message);
    this.name = "DispatchAttemptError";
  }
}

/** Which local agents activated at startup. `acp` (Claude Code) is always present. */
export interface AdapterAvailabilityFlags {
  piMono: boolean;
  hermes: boolean;
  openclaw: boolean;
  codex: boolean;
}

export function buildAvailabilitySnapshot(flags: AdapterAvailabilityFlags): AvailabilityMap {
  return {
    acp: true,
    "pi-mono": flags.piMono,
    hermes: flags.hermes,
    openclaw: flags.openclaw,
    codex: flags.codex,
  };
}

const ROUTABLE_IDS: readonly RoutableAgentId[] = ["acp", "pi-mono", "hermes", "openclaw", "codex"];

/** Narrow an arbitrary adapterId string to a RoutableAgentId, or undefined. */
export function asRoutableAgentId(id: string | undefined): RoutableAgentId | undefined {
  return id && (ROUTABLE_IDS as readonly string[]).includes(id) ? (id as RoutableAgentId) : undefined;
}

// Coarse keyword heuristic so the capability tier is actually reachable in live
// dispatch (the query carries no task type). Deliberately simple — swap for a
// real classifier later without touching callers.
const TASK_TYPE_PATTERNS: Array<{ type: TaskType; re: RegExp }> = [
  { type: "code_edit", re: /\b(edit|refactor|fix|implement|debug|rename|write (a |the )?(test|function|code|class))\b/i },
  { type: "research", re: /\b(research|investigate|compare|look up|find out|explain|summari[sz]e|what is|how does|why)\b/i },
  { type: "quick_command", re: /\b(run|deploy|build|install|start|stop|restart|launch|open)\b/i },
];

export function inferTaskType(prompt: string): TaskType {
  for (const { type, re } of TASK_TYPE_PATTERNS) {
    if (re.test(prompt)) return type;
  }
  return "general";
}

/**
 * Decide the ordered execution plan for a query.
 *
 * - A structured `adapterId` on the query (a Swift UI pick) is honored as the
 *   primary, with fallbacks — unless it isn't available, in which case the plan
 *   carries `needsSetup` and no order (caller guides the user to connect it).
 * - Otherwise the router chooses from the task text: explicit mention >
 *   capability match > default (Claude Code).
 */
export function planQueryDispatch(
  query: { adapterId?: string; prompt: string },
  availability: AvailabilityMap
): RoutingPlan {
  return resolveAgent({
    task: query.prompt ?? "",
    taskType: inferTaskType(query.prompt ?? ""),
    availability,
    explicitAgent: asRoutableAgentId(query.adapterId),
  });
}

/** Activation/spawn failures are retryable (try the next agent); guard errors are not. */
export function isDispatchRetryable(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return !/already active/i.test(message);
}
