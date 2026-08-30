// Decides which connected agent gets tried first when the user hasn't named
// one (and which order the rest fall back through). Before this,
// taskRunner.candidateAgents just returned PRODUCTION_ADAPTER_IDS' declared
// order — "best connected one" per CodingAgentRunArgs.agentId's own doc
// comment, but in practice always "whichever one happens to be listed first
// in interface.ts". That's fine when only one agent is even connected, which
// is the common case today, but it stops being true the moment someone has
// two or three wired up, and there was no path to it becoming true later.
//
// Two inputs feed the ranking, both real, neither invented for this file:
//  1. Capability facts that already exist in ADAPTER_CAPABILITY_MATRIX
//     (interface.ts) — e.g. OpenClaw's ACP adapter documents that it rejects
//     per-session MCP servers, so it can't actually call Omi's tools. A coding
//     task that can't touch files or run commands isn't really "done".
//  2. What has actually happened before, from agentOutcomeLedger.ts — recent
//     wins/losses for this agent on this rough kind of task, on this machine.
// There is no per-vendor "Codex is better at X" table in here. Nobody
// maintaining this file has benchmarked these products against each other,
// and pretending otherwise would be worse than not ranking at all. The
// capability prior only ever leans on facts the runtime already asserts about
// itself; everything else is left to the ledger to earn.

import { adapterCapabilitiesFor, type CodingAgentAdapterId } from './interface'
import { readOutcomeLedger, type AgentOutcomeEntry, type TaskTag } from './agentOutcomeLedger'

export type { TaskTag } from './agentOutcomeLedger'

// Checked in this order because a prompt can match more than one — "refactor
// this in the background overnight" is both long_running and bulk_refactor,
// and resumability (long_running) is the more consequential property to route
// on: an agent that can't survive a restart loses the whole run, where one
// that's merely mediocre at big-scope edits just does a mediocre job of them.
const TASK_TAG_PATTERNS: ReadonlyArray<{ tag: TaskTag; pattern: RegExp }> = [
  {
    tag: 'long_running',
    pattern:
      /\b(overnight|while i'?m away|in the background|keep (?:working|going)|long[- ]running)\b/i
  },
  {
    tag: 'bulk_refactor',
    pattern:
      /\b(refactor|migrate|rename (?:it |them )?(?:across|throughout)|every file|across the codebase|large[- ]scale)\b/i
  },
  {
    tag: 'research',
    pattern:
      /\b(research|look up|find out|compare|what'?s the best (?:way|approach)|investigate)\b/i
  },
  {
    tag: 'quick_script',
    pattern: /\b(quick|one[- ]off|small script|one[- ]liner|tiny (?:script|fix))\b/i
  }
]

/** Guess the task's rough shape from the prompt text. Deliberately a plain
 *  keyword match, not a model call: this only has to pick a fallback order
 *  among agents that are already about to run, so a wrong guess costs a
 *  slightly worse ordering, never a wrong answer — that doesn't justify a
 *  network round trip (or a place for a prompt-injected task description to
 *  influence anything beyond try-this-agent-before-that-one). */
export function classifyTask(prompt: string): TaskTag {
  for (const { tag, pattern } of TASK_TAG_PATTERNS) {
    if (pattern.test(prompt)) return tag
  }
  return 'general'
}

// Claude Code is Omi's built-in agent — no install, no launch command to
// configure, always the one every user already has. All else being equal it's
// the reasonable first thing to try, matching the standing expectation
// (taskRunner.test.ts) that an unnamed task reaches for it before an external
// CLI the user had to go set up.
const BUILT_IN_ADAPTER_BONUS = 2

// interface.ts's own capability matrix documents OpenClaw's ACP adapter as
// rejecting per-session MCP servers, so it can't call Omi's tools at all
// (toolSupport: unsupported). A delegated coding task is, almost by
// definition, "edit files or run something" — an agent that structurally
// can't do either is a real handicap, not a style preference, so this outweighs
// the bounded history swing below rather than just nudging against it.
const NO_TOOL_SUPPORT_PENALTY = -3

// A task tag's capability-specific nudge, applied only when it's actually
// relevant to that shape of work.
const LONG_RUNNING_RESUME_BONUS = 1
const BULK_REFACTOR_MODEL_SWITCH_BONUS = 1

function capabilityScore(adapterId: CodingAgentAdapterId, tag: TaskTag): number {
  const capabilities = adapterCapabilitiesFor(adapterId)
  let score = adapterId === 'acp' ? BUILT_IN_ADAPTER_BONUS : 0
  if (!capabilities.supportsTools) score += NO_TOOL_SUPPORT_PENALTY
  if (tag === 'long_running' && capabilities.supportsNativeResume)
    score += LONG_RUNNING_RESUME_BONUS
  if (tag === 'bulk_refactor' && capabilities.supportsModelSwitching) {
    score += BULK_REFACTOR_MODEL_SWITCH_BONUS
  }
  return score
}

// Only the most recent matching attempts count, so a bad stretch a month ago
// can't permanently outrank an agent that's since been fixed (or the ledger
// hasn't caught up with an upgrade the user just installed). Small on
// purpose: this is meant to converge in an afternoon of real use, not a week.
const RECENCY_WINDOW = 20

// Capped so the ledger can nudge the capability prior but never fully invert
// it on a short streak — three lucky/unlucky runs in a row shouldn't be able
// to promote a tool-less adapter over one that can actually edit files.
const MAX_HISTORY_SCORE = 2

function historyScore(
  entries: readonly AgentOutcomeEntry[],
  adapterId: CodingAgentAdapterId,
  tag: TaskTag
): number {
  const recent = entries
    .filter((entry) => entry.adapterId === adapterId && entry.tag === tag)
    .slice(-RECENCY_WINDOW)
  if (recent.length === 0) return 0
  const wins = recent.filter((entry) => entry.outcome === 'success').length
  const net = wins - (recent.length - wins)
  return Math.max(-MAX_HISTORY_SCORE, Math.min(MAX_HISTORY_SCORE, net))
}

/**
 * Order a set of already-connected agents by fit for this task. `connected`
 * is expected in taskRunner's declared preference order (PRODUCTION_ADAPTER_IDS,
 * filtered to what's activated) — that order is reused as the tie-break, so
 * two agents scoring identically keep today's behavior instead of shuffling
 * on every call.
 *
 * Pure given `ledgerEntries`; taskRunner passes the real persisted ledger and
 * tests pass a fixed one, so ranking never depends on wall-clock disk state
 * mid-test.
 */
export function rankAgentsForTask(
  connected: readonly CodingAgentAdapterId[],
  prompt: string,
  ledgerEntries: readonly AgentOutcomeEntry[] = readOutcomeLedger()
): CodingAgentAdapterId[] {
  const tag = classifyTask(prompt)
  return connected
    .map((adapterId, declaredIndex) => ({
      adapterId,
      declaredIndex,
      score: capabilityScore(adapterId, tag) + historyScore(ledgerEntries, adapterId, tag)
    }))
    .sort((a, b) => b.score - a.score || a.declaredIndex - b.declaredIndex)
    .map((ranked) => ranked.adapterId)
}
