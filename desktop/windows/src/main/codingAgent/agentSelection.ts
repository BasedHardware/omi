// Task-aware ranking for the "no agent named, pick the best one" case
// (taskRunner.candidateAgents). Previously the fallback order was purely
// static — PRODUCTION_ADAPTER_IDS declaration order (acp, openclaw, hermes,
// codex) — so Claude Code was always chosen first regardless of what the task
// actually needed, and OpenClaw (which cannot use Omi tools at all — see
// ADAPTER_CAPABILITY_MATRIX.openclaw.toolSupport) could be handed a task it
// structurally can't complete.
//
// This module scores each connected agent against the task text using the
// real capability differences already recorded in ADAPTER_CAPABILITY_MATRIX
// (interface.ts) — it does not invent new agent facts, it just uses the ones
// the codebase already asserts. Two task shapes matter in practice:
//
//   1. Tool-heavy work (reading/editing files, running commands, tests,
//      builds) — an agent with toolSupport !== 'required' cannot do this at
//      all through Omi's per-session MCP tools, so it must be demoted hard
//      rather than tried and silently fail.
//   2. Long-running / resumable work ("keep working on", "continue X") —
//      agents with supportsNativeResume survive being reopened later; ones
//      without it are fine for one-shot tasks but a worse fit here.
//
// Ties (including the common case of an empty/ambiguous prompt) fall back to
// each agent's original position in the candidate list — a stable sort — so
// this never reshuffles things without a concrete signal to act on.

import { ADAPTER_CAPABILITY_MATRIX, type CodingAgentAdapterId } from './interface'

const TOOL_USE_HINTS =
  /\b(file|files|read|write|edit|create|delete|run|execute|tests?|build|compile|install|refactor|fix|debug|repo|repository|codebase|script|command|terminal|search|grep|folder|directory)\b/i

const LONG_RUNNING_HINTS =
  /\b(continue|keep working|long[- ]running|background|resume|multi[- ]step|over the next|ongoing|overnight)\b/i

/**
 * Score one agent against the task prompt. Higher is better. Only meant to
 * rank agents that are already known to be connected — this has no opinion on
 * activation/availability, that's adapterIsActivated's job.
 */
export function scoreAgentForTask(agentId: CodingAgentAdapterId, prompt: string): number {
  const expectations = ADAPTER_CAPABILITY_MATRIX[agentId].expectations
  const needsTools = TOOL_USE_HINTS.test(prompt)
  const needsResume = LONG_RUNNING_HINTS.test(prompt)

  // No primary signal at all → a true tie. Every agent returns exactly 0, so
  // rankAgentsForTask's stable sort falls through to input order untouched.
  if (!needsTools && !needsResume) return 0

  let score = 0

  if (needsTools) {
    // OpenClaw rejects per-session MCP servers outright (see interface.ts) —
    // a tool-heavy task handed to it will not fail loudly, it'll just run
    // without the tools it needed. Demote hard rather than let taskRunner's
    // fallback-on-failure logic discover this only after a bad attempt.
    score += expectations.toolSupport.status === 'required' ? 2 : -3
  }

  if (needsResume) {
    score += expectations.nativeResume.status === 'required' ? 2 : 0
  }

  // Small, sub-integer nudges that only ever break ties between agents that
  // already scored equally above (e.g. two tool-capable agents on a
  // tool-heavy task) — they never fire on their own and never outweigh a
  // primary signal.
  if (expectations.modelSwitching.status === 'required') score += 0.5
  if (expectations.artifactEmission.status === 'required') score += 0.5

  return score
}

/**
 * Rank connected agents for a task, highest score first. Stable: agents that
 * score equally (notably every agent, when the prompt has no tool/duration
 * signal) keep their original relative order.
 */
export function rankAgentsForTask(
  candidates: readonly CodingAgentAdapterId[],
  prompt: string
): CodingAgentAdapterId[] {
  return candidates
    .map((id, index) => ({ id, index, score: scoreAgentForTask(id, prompt) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((entry) => entry.id)
}
