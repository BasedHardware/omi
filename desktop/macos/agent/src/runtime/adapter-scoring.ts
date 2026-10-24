// Choosing between connected agents, and the order to fall back through.
//
// `adapterIdForHarnessMode()` answers "which agent did the settings pick?" —
// a static lookup that defaults to `acp`. Nothing answered "which of the agents
// this user actually connected suits this task?", so a machine with Hermes and
// OpenClaw connected still sent every task to Claude Code, and a task that died
// on one agent died outright.
//
// Selection here is deterministic and capability-driven, not model-judged. The
// capability matrix in adapters/interface.ts already records what each adapter
// can do (OpenClaw, for instance, reports `supportsTools: false`), so a task
// that needs tools can rule it out as a fact rather than a guess. Every score
// carries its reasons so the choice can be logged and explained.
//
// Ties resolve to the existing default order, so a runtime with nothing to
// distinguish its adapters keeps behaving exactly as it does today.

import type {
  AdapterCapabilities,
  ProductionAdapterId,
} from "../adapters/interface.js";

/**
 * What a task needs from an agent. Supplied by the caller from the run request
 * — deliberately not inferred from the utterance, which would put language
 * heuristics back into the selection path.
 */
export interface AgentTaskRequirements {
  /** The task will call tools (most coding work). Hard requirement. */
  readonly needsTools?: boolean;
  /** The task must emit artifacts (files, diffs). Hard requirement. */
  readonly needsArtifacts?: boolean;
  /** The user pinned a model, so the agent must be able to switch. Hard. */
  readonly needsModelSwitching?: boolean;
  /** The task should be interruptible. Preferred, not required. */
  readonly prefersCancellation?: boolean;
  /** The task may be resumed later. Preferred, not required. */
  readonly prefersResume?: boolean;
}

export interface AdapterCandidate {
  readonly adapterId: ProductionAdapterId;
  readonly capabilities: AdapterCapabilities;
}

export interface AdapterScore {
  readonly adapterId: ProductionAdapterId;
  /** Higher wins. Only comparable between adapters scored together. */
  readonly score: number;
  /** False when a hard requirement is unmet — never selected, never fallen back to. */
  readonly eligible: boolean;
  /** Hard requirements this adapter fails, for the "why not" explanation. */
  readonly missing: readonly string[];
  /** Human-readable reasons, in the order they were applied. */
  readonly reasons: readonly string[];
}

/**
 * Tie-break order. `acp` leads because it is today's default: when no
 * requirement separates the candidates, selection must land where it already
 * lands. Later entries are progressively more specialised.
 */
const DEFAULT_PREFERENCE: readonly ProductionAdapterId[] = [
  "acp",
  "pi-mono",
  "hermes",
  "codex",
  "openclaw",
];

/** Weight for a satisfied preference, kept well above any tie-break bonus. */
const PREFERENCE_WEIGHT = 10;

/**
 * Score every candidate against the task. Ineligible adapters are scored too —
 * the caller needs their `missing` list to explain why an agent was skipped.
 * Returned best-first; ineligible adapters sort last.
 */
export function scoreAdapters(
  candidates: readonly AdapterCandidate[],
  requirements: AgentTaskRequirements = {},
): readonly AdapterScore[] {
  return candidates
    .map((candidate) => scoreOne(candidate, requirements))
    .sort(byScoreThenPreference);
}

/**
 * The order to try adapters in: best first, then every other eligible adapter
 * as fallback. Ineligible adapters are dropped — falling back to an agent that
 * cannot do the job just fails twice and wastes the user's time.
 */
export function selectAdapterChain(
  candidates: readonly AdapterCandidate[],
  requirements: AgentTaskRequirements = {},
): readonly ProductionAdapterId[] {
  return scoreAdapters(candidates, requirements)
    .filter((scored) => scored.eligible)
    .map((scored) => scored.adapterId);
}

/**
 * The chain to use when the user named an agent explicitly: that agent first,
 * then the ranked remainder. An explicit request outranks scoring — the user
 * asked — but it should still survive that agent failing.
 *
 * Returns the ranked chain unchanged when the requested agent is ineligible or
 * absent, so the caller can tell "not connected" apart from "not chosen".
 */
export function selectRequestedAdapterChain(
  candidates: readonly AdapterCandidate[],
  requestedAdapterId: string,
  requirements: AgentTaskRequirements = {},
): readonly ProductionAdapterId[] {
  const chain = selectAdapterChain(candidates, requirements);
  if (!chain.includes(requestedAdapterId as ProductionAdapterId)) return chain;
  const requested = requestedAdapterId as ProductionAdapterId;
  return [requested, ...chain.filter((adapterId) => adapterId !== requested)];
}

function scoreOne(
  candidate: AdapterCandidate,
  requirements: AgentTaskRequirements,
): AdapterScore {
  const { adapterId, capabilities } = candidate;
  const missing: string[] = [];
  const reasons: string[] = [];
  let score = 0;

  if (requirements.needsTools) {
    if (capabilities.supportsTools) reasons.push("supports tools");
    else missing.push("tool support");
  }
  if (requirements.needsArtifacts) {
    if (capabilities.supportsArtifactEmission) reasons.push("emits artifacts");
    else missing.push("artifact emission");
  }
  if (requirements.needsModelSwitching) {
    if (capabilities.supportsModelSwitching) reasons.push("can switch models");
    else missing.push("model switching");
  }

  if (requirements.prefersCancellation && capabilities.supportsCancellation) {
    score += PREFERENCE_WEIGHT;
    reasons.push("cancellable");
  }
  if (requirements.prefersResume && capabilities.supportsNativeResume) {
    score += PREFERENCE_WEIGHT;
    reasons.push("resumes natively");
  }

  const preferenceIndex = DEFAULT_PREFERENCE.indexOf(adapterId);
  // Unlisted adapters sort after listed ones rather than throwing: a new
  // adapter should degrade to "last resort", not break selection.
  const tieBreak =
    preferenceIndex === -1 ? 0 : DEFAULT_PREFERENCE.length - preferenceIndex;
  score += tieBreak;

  const eligible = missing.length === 0;
  if (!eligible) reasons.push(`ineligible: missing ${missing.join(", ")}`);

  return { adapterId, score, eligible, missing, reasons };
}

function byScoreThenPreference(left: AdapterScore, right: AdapterScore): number {
  if (left.eligible !== right.eligible) return left.eligible ? -1 : 1;
  if (left.score !== right.score) return right.score - left.score;
  return (
    DEFAULT_PREFERENCE.indexOf(left.adapterId) -
    DEFAULT_PREFERENCE.indexOf(right.adapterId)
  );
}
