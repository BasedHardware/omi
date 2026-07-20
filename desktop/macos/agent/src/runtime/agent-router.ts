/**
 * Agent router: decides which agent (adapter) should execute a task, and in
 * what fallback order.
 *
 * Priority (MVP, per Track-1 spec):
 *   1. Explicit mention  — the user named an agent ("use openclaw to ...").
 *   2. Capability match  — task type maps to a ranked list of agents.
 *   3. Default           — Claude Code (the `acp` adapter).
 *
 * The router is intentionally pure: it takes the task text plus a snapshot of
 * which agents are currently available, and returns an ordered execution plan.
 * It never spawns processes, reads credentials, or performs I/O — the caller
 * (index.ts) owns activation and execution. This keeps routing unit-testable
 * and keeps the "is this agent connected?" check in the existing detectors
 * (LocalAgentProviderDetector on Swift, adapterIsActivated on Node), which
 * only probe env vars / PATH and never open auth files.
 */

/** Agents the router can route to. Mirrors adapter ids, plus `codex`. */
export type RoutableAgentId = "acp" | "pi-mono" | "hermes" | "openclaw" | "codex";

/** Human-facing names, used for explicit-mention parsing and setup prompts. */
export const AGENT_DISPLAY_NAMES: Record<RoutableAgentId, string> = {
  acp: "Claude Code",
  "pi-mono": "Omi",
  hermes: "Hermes",
  openclaw: "OpenClaw",
  codex: "Codex",
};

/** The default agent when nothing else selects one. Claude Code == `acp`. */
export const DEFAULT_AGENT: RoutableAgentId = "acp";

/**
 * Coarse task types the router understands. Deliberately small for the MVP;
 * extend `CAPABILITY_TABLE` and this union together to add more.
 */
export type TaskType = "code_edit" | "research" | "quick_command" | "general";

/**
 * Task type -> agents ranked best-first. Only a preference order; the router
 * filters to what's actually available before picking. Easy to extend later
 * with more signals (past success rate, cost, latency) without touching call sites.
 */
export const CAPABILITY_TABLE: Record<TaskType, RoutableAgentId[]> = {
  code_edit: ["acp", "openclaw", "codex", "pi-mono", "hermes"],
  research: ["hermes", "acp", "pi-mono", "openclaw", "codex"],
  quick_command: ["codex", "openclaw", "acp", "pi-mono", "hermes"],
  general: ["acp", "pi-mono", "openclaw", "hermes", "codex"],
};

/** Global tie-break order used to append fallbacks after the primary pick. */
const GLOBAL_PRIORITY: RoutableAgentId[] = ["acp", "pi-mono", "openclaw", "hermes", "codex"];

/** Availability snapshot: which agents are currently connected/installed. */
export type AvailabilityMap = Partial<Record<RoutableAgentId, boolean>>;

export type RoutingReason =
  | "explicit_mention"
  | "capability_match"
  | "default"
  | "explicit_unavailable";

export interface RoutingPlan {
  /** Ordered adapters to try: primary first, then fallbacks. Empty if none available. */
  order: RoutableAgentId[];
  /** Why the primary was chosen. */
  reason: RoutingReason;
  /** Set when the user named an agent that isn't connected — caller should trigger setup. */
  needsSetup?: RoutableAgentId;
  /** The agent explicitly named in the task, if any (whether or not available). */
  mentioned?: RoutableAgentId;
  /** One-line explanation, safe to log/surface. */
  explanation: string;
}

// Longest-first so "claude code" matches before a bare "claude", etc.
const MENTION_PATTERNS: Array<{ id: RoutableAgentId; re: RegExp }> = [
  { id: "acp", re: /\bclaude[\s-]?code\b/i },
  { id: "openclaw", re: /\bopen[\s-]?claw\b/i },
  { id: "hermes", re: /\bhermes\b/i },
  { id: "codex", re: /\bcodex\b/i },
  { id: "pi-mono", re: /\b(pi[\s-]?mono|omi)\b/i },
  { id: "acp", re: /\bclaude\b/i },
];

/** Parse an explicitly named agent from free task text, or undefined. */
export function parseExplicitMention(task: string): RoutableAgentId | undefined {
  for (const { id, re } of MENTION_PATTERNS) {
    if (re.test(task)) return id;
  }
  return undefined;
}

function isAvailable(map: AvailabilityMap, id: RoutableAgentId): boolean {
  // `acp` (Claude Code) is always available — it's the built-in default and
  // ships with the runtime. Others must be explicitly marked available.
  if (id === "acp") return map.acp !== false;
  return map[id] === true;
}

/** Append every still-available agent not already in `order`, in priority order. */
function withFallbacks(order: RoutableAgentId[], map: AvailabilityMap): RoutableAgentId[] {
  const seen = new Set(order);
  for (const id of GLOBAL_PRIORITY) {
    if (!seen.has(id) && isAvailable(map, id)) {
      order.push(id);
      seen.add(id);
    }
  }
  return order;
}

export interface ResolveInput {
  task: string;
  taskType?: TaskType;
  availability?: AvailabilityMap;
  /**
   * An agent chosen structurally (e.g. a Swift UI provider pick that arrives as
   * query.adapterId). Takes precedence over a name parsed from the task text.
   */
  explicitAgent?: RoutableAgentId;
}

/**
 * Decide the execution plan for a task. Pure and synchronous.
 */
export function resolveAgent(input: ResolveInput): RoutingPlan {
  const { task } = input;
  const availability = input.availability ?? {};
  const taskType = input.taskType ?? "general";
  // A structured pick (query.adapterId) outranks a name mentioned in the text.
  const mentioned = input.explicitAgent ?? parseExplicitMention(task);

  // 1. Explicit mention wins — but never silently fall back if it's not
  //    connected. The caller uses `needsSetup` to trigger the guided install.
  if (mentioned) {
    if (isAvailable(availability, mentioned)) {
      const order = withFallbacks([mentioned], availability);
      return {
        order,
        reason: "explicit_mention",
        mentioned,
        explanation: `Routed to ${AGENT_DISPLAY_NAMES[mentioned]} (named in the task).`,
      };
    }
    return {
      order: [],
      reason: "explicit_unavailable",
      mentioned,
      needsSetup: mentioned,
      explanation: `${AGENT_DISPLAY_NAMES[mentioned]} was requested but isn't connected.`,
    };
  }

  // 2. Capability match — first available agent for this task type.
  const ranked = CAPABILITY_TABLE[taskType];
  const primary = ranked.find((id) => isAvailable(availability, id));
  if (primary && primary !== DEFAULT_AGENT) {
    const order = withFallbacks([primary], availability);
    return {
      order,
      reason: "capability_match",
      explanation: `Routed to ${AGENT_DISPLAY_NAMES[primary]} (best match for ${taskType}).`,
    };
  }

  // 3. Default — Claude Code, with any other available agents as fallbacks.
  const order = withFallbacks([DEFAULT_AGENT], availability);
  return {
    order,
    reason: "default",
    explanation: `Routed to ${AGENT_DISPLAY_NAMES[DEFAULT_AGENT]} (default).`,
  };
}
