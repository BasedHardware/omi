// Pure display logic for the bar (orb state, retract-hold, list status). Kept
// out of the React components so it's unit-testable without a DOM or IPC — these
// are the load-bearing rules of the rework (orb is the sole status indicator;
// the pill stays open while a voice exchange is in flight).
import type { OrbState } from '../../orb/choreography'
import type {
  BarChatState,
  BarChatStatus,
  CodingAgentId,
  CodingAgentInfo
} from '../../../../shared/types'

export type BarActivity = {
  /** PTT is capturing the user's voice right now (local to the bar). */
  recording: boolean
  /** PTT is finalizing a captured transcript (local to the bar). */
  transcribing: boolean
  /** Projected chat status from the main window's engine. */
  status: BarChatStatus
  /** Continuous listening is on AND the user is signed in. */
  continuousListening: boolean
  /** A delegated coding-agent (ACP) task is running (projected from the shared
   *  chat engine). Shows the orb's distinctive 'agents' pose. */
  agentsActive: boolean
}

/**
 * The bar orb's state + whether to attach the live mic amplitude:
 *  - recording  → speaking, with the user's amplitude (the blob reacts)
 *  - TTS reply  → speaking, no amplitude (Omi is talking; playback-amp is v-next)
 *  - streaming/finalizing → thinking
 *  - continuous listen → listening
 *  - else idle
 * Recording wins over a still-playing TTS so the user's own turn is reactive.
 */
export function deriveOrbState(a: BarActivity): { state: OrbState; withAmplitude: boolean } {
  if (a.recording) return { state: 'speaking', withAmplitude: true }
  if (a.status === 'speaking') return { state: 'speaking', withAmplitude: false }
  // A running coding-agent shows the distinctive 'agents' pose over generic
  // 'thinking' (both carry status==='sending'), but live voice above still wins.
  if (a.agentsActive) return { state: 'agents', withAmplitude: false }
  if (a.transcribing || a.status === 'sending') return { state: 'thinking', withAmplitude: false }
  if (a.continuousListening) return { state: 'listening', withAmplitude: false }
  return { state: 'idle', withAmplitude: false }
}

/**
 * Main-window (sidebar) orb state from the shared chat engine's signals. The
 * sidebar has no local PTT, so it has no reactive mic amplitude — it projects the
 * one chat engine (streaming reply → thinking, spoken reply → speaking, coding
 * agent → agents) and the continuous-listen toggle through the SAME precedence as
 * the bar (deriveOrbState), so both orbs read identically for the same activity.
 */
export function deriveMainWindowOrbState(a: {
  speaking: boolean
  sending: boolean
  agentActive: boolean
  continuousListening: boolean
}): OrbState {
  const status: BarChatStatus = a.speaking ? 'speaking' : a.sending ? 'sending' : 'idle'
  return deriveOrbState({
    recording: false,
    transcribing: false,
    status,
    continuousListening: a.continuousListening,
    agentsActive: a.agentActive
  }).state
}

/** True while a summoned pill must NOT auto-retract — a PTT hold / streaming
 *  reply / spoken answer is in flight (the cursor is legitimately away). */
export function isBarBusy(a: Pick<BarActivity, 'recording' | 'transcribing' | 'status'>): boolean {
  return a.recording || a.transcribing || a.status === 'sending' || a.status === 'speaking'
}

/** One-line status for the list's "Omi Chat" row: what Omi is doing, a preview
 *  of the last turn, or an invitation when the thread is empty. */
export function omiChatListStatus(chat: BarChatState): string {
  if (chat.status === 'speaking') return 'Speaking…'
  if (chat.status === 'sending') return 'Thinking…'
  const last = chat.messages[chat.messages.length - 1]
  if (last?.content?.trim()) {
    const who = last.role === 'user' ? 'You: ' : ''
    return `${who}${last.content.replace(/\s+/g, ' ').trim()}`
  }
  return 'Ask me anything'
}

/** A coding-agent row in the bar's expanded list. */
export type BarAgentRow = { id: CodingAgentId; displayName: string; working: boolean }

/**
 * The connected coding agents to list in the bar (Mac-parity: same set
 * Settings→Agents manages, but only the ones actually reachable — a summon list
 * is for acting, not setup). `working` marks the one currently running a task:
 * the shared chat engine projects a single global `agentsActive`, and the last
 * `agent_selected` event names which adapter it is, so at most one row shows
 * "Working…". Anything not connected stays out of the quick list.
 */
export function deriveAgentRows(
  agents: CodingAgentInfo[],
  activeAgentId: CodingAgentId | null,
  agentsActive: boolean
): BarAgentRow[] {
  return agents
    .filter((a) => a.connected)
    .map((a) => ({
      id: a.id,
      displayName: a.displayName,
      working: agentsActive && activeAgentId === a.id
    }))
}

/** Status line for an agent row: what it's doing now, else that it's ready. */
export function agentRowStatus(row: BarAgentRow): string {
  return row.working ? 'Working…' : 'Ready'
}

/** The collapsed-pill wordmark: "Listening" whenever Omi is capturing the user's
 *  voice — an active PTT hold (recording, even though the orb pose derives as
 *  'speaking' for the reactive amplitude) OR always-on continuous listening. Omi's
 *  own spoken (TTS) reply is NOT the user being heard, so it keeps the resting
 *  "Omi" wordmark; every non-capture state does too (the orb stays the sole
 *  indicator for thinking/speaking/agents). Keyed off ACTIVITY, not the orb pose,
 *  so a silent hold visibly says "Listening" while the bar is pinned open. Both
 *  words fit the fixed pill width, so the label swaps in place without shifting
 *  the orb. */
export function pillLabel(a: { recording: boolean; continuousListening: boolean }): string {
  return a.recording || a.continuousListening ? 'Listening' : 'Omi'
}
