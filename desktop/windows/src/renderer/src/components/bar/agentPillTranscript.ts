// Pure client-side transcript synthesis for a floating agent pill (B3).
//
// A pill's transcript is CLIENT-SYNTHESIZED and SEPARATE from the shared Omi
// chat thread (INV-CHAT-1 — this never reads or writes the shared message
// array). It is a faithful port of macOS' AgentMainChatView.displayedMessages
// (upstream FloatingControlBar/FloatingControlBarView.swift:1863-1870), built
// from the pill's own query + the get_agent_run poll's evolving assistant text:
//   message 1 = the pill's `query`     (user role)
//   message 2 = the run's `finalText`  (assistant role, evolves until terminal)
//              — or, on a failed pill, the error bubble.
//
// Kept out of React so the mapping (row-from-run-detail, transcript shape, the
// chip tint→className mapping) is unit-testable without a DOM or IPC.
import type { ChatMsg } from '../../hooks/useChat'
import {
  isFinished,
  type AgentPill,
  type AgentPillTintToken,
  type PillProjectionRow
} from './agentPills'

/** The minimal shape read out of a parsed `get_agent_run` door result
 *  (`{ ok, run, session, ... }`). Everything is `unknown` because it crosses a
 *  JSON.parse boundary — the helpers below narrow each field defensively. */
export type AgentRunDetail = {
  run?: Record<string, unknown> | null
  session?: Record<string, unknown> | null
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function num(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

/** The assistant text a `get_agent_run` poll currently exposes for a pill:
 *  `run.finalText` (may be empty until the run finishes). */
export function runDetailFinalText(detail: AgentRunDetail): string {
  const finalText = detail.run?.finalText
  return typeof finalText === 'string' ? finalText : ''
}

/**
 * Fold a `get_agent_run` detail into a `PillProjectionRow` for the SAME pill, so
 * the per-run poll refreshes status/text through the exact B2 merge path the
 * list poll uses (no-resurrection, becameFinished, error resolution all apply).
 * Identity comes from the pill (the run detail may omit sessionId); the run
 * supplies the live status, text, completion time, and error. Returns null when
 * the detail carries no run object.
 */
export function runDetailToProjectionRow(
  pill: AgentPill,
  detail: AgentRunDetail
): PillProjectionRow | null {
  const run = detail.run
  if (!run || typeof run !== 'object') return null
  const session = detail.session ?? undefined
  const input = (run.input as Record<string, unknown> | undefined) ?? {}
  const finalText = str(run.finalText)
  const errorMessage = str(run.errorMessage)
  return {
    id: pill.id,
    runId: str(run.runId) ?? pill.runId,
    sessionId: str(run.sessionId) ?? pill.sessionId,
    title: str(session?.title) ?? pill.title,
    status: str(run.status) ?? 'unknown',
    latestActivity: finalText ?? errorMessage ?? pill.latestActivity ?? '',
    query: str(input.prompt) ?? pill.query,
    createdAtMs: num(run.createdAtMs) ?? pill.createdAtMs,
    completedAtMs: num(run.completedAtMs),
    provider: pill.provider,
    errorCode: str(run.errorCode),
    errorMessage
  }
}

/** The assistant bubble's text for a pill, given the latest polled finalText.
 *  A failed pill shows its error (never a silent stall); a finished-but-empty
 *  run gets a terminal placeholder so the bubble is never blank; an active run
 *  with no text yet returns '' so ChatMessages shows the thinking spinner. */
function assistantContent(pill: AgentPill, finalText: string): string {
  if (pill.displayStatus === 'failed') return pill.errorMessage ?? 'Agent failed'
  if (finalText.trim() !== '') return finalText
  if (pill.displayStatus === 'stopped') return 'Agent stopped.'
  if (pill.displayStatus === 'done') return 'Agent finished with no output.'
  return ''
}

/**
 * Build the per-pill transcript: the user's original query, then one evolving
 * assistant message from the run's finalText (or the error bubble on failure).
 * `sending` is true while the run is not finished, so ChatMessages renders the
 * thinking spinner for an empty in-flight reply and the progressive reveal as
 * text streams in. Message ids are STABLE (keyed by pill id) so the assistant
 * bubble is not remounted on each poll — the reveal continues instead of
 * restarting. Pure: no DOM, no IPC.
 */
export function synthesizePillTranscript(
  pill: AgentPill,
  finalText: string | null
): { messages: ChatMsg[]; sending: boolean } {
  const messages: ChatMsg[] = []
  if (pill.query.trim() !== '') {
    messages.push({ id: `${pill.id}:query`, role: 'user', content: pill.query })
  }
  messages.push({
    id: `${pill.id}:assistant`,
    role: 'assistant',
    content: assistantContent(pill, finalText ?? '')
  })
  return { messages, sending: !isFinished(pill.displayStatus) }
}

/** Tailwind chip classes for a pill status tint token. NO PURPLE (INV-UI-1):
 *  running→amber, done→emerald, stopped→neutral, failed→red, queued→neutral. */
export function pillChipClasses(token: AgentPillTintToken): string {
  switch (token) {
    case 'running':
      return 'bg-amber-500/15 text-amber-300'
    case 'done':
      return 'bg-emerald-500/15 text-emerald-300'
    case 'failed':
      return 'bg-red-500/15 text-red-300'
    case 'stopped':
      return 'bg-neutral-600/40 text-neutral-300'
    case 'queued':
      return 'bg-neutral-700/50 text-neutral-400'
  }
}

/** Drop cached per-pill assistant text for pills that no longer exist (evicted by
 *  soft-cap / viewed-TTL, or dismissed) so the useAgentPills text map can't grow
 *  without bound. Returns the SAME reference when nothing was pruned, so it never
 *  churns a new object into state. */
export function retainTextForPills(
  textByPillId: Record<string, string>,
  pills: readonly Pick<AgentPill, 'id'>[]
): Record<string, string> {
  const live = new Set(pills.map((p) => p.id))
  const keys = Object.keys(textByPillId)
  if (keys.every((id) => live.has(id))) return textByPillId
  const next: Record<string, string> = {}
  for (const id of keys) if (live.has(id)) next[id] = textByPillId[id]
  return next
}
