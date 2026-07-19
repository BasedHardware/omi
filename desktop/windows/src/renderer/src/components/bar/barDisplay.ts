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
  /** The capture is a tap-to-lock hands-free turn (mic open, no key held) — shown
   *  in the distinct 'listening' pose (still reacting to the user's amplitude),
   *  not the held-press 'speaking' pose. Absent ⇒ a normal held press. */
  locked?: boolean
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

/** Which live level feeds the orb: the user's mic, Omi's own audible reply
 *  (the played-out PCM's peak), or nothing (pose-only choreography). */
export type OrbAmplitudeLane = 'mic' | 'playback' | null

/**
 * The bar orb's state + which live amplitude lane (if any) to attach:
 *  - recording  → speaking, with the user's MIC amplitude (the blob reacts)
 *  - TTS reply  → speaking, with the PLAYBACK amplitude (the reply's own speech
 *    dynamics animate the dots — the same visual language as the mic, driven by
 *    the audio actually playing)
 *  - streaming/finalizing → thinking
 *  - continuous listen → listening
 *  - else idle
 * Recording wins over a still-playing TTS so the user's own turn is reactive.
 */
export function deriveOrbState(a: BarActivity): { state: OrbState; amplitude: OrbAmplitudeLane } {
  if (a.recording) return { state: a.locked ? 'listening' : 'speaking', amplitude: 'mic' }
  if (a.status === 'speaking') return { state: 'speaking', amplitude: 'playback' }
  // A running coding-agent shows the distinctive 'agents' pose over generic
  // 'thinking' (both carry status==='sending'), but live voice above still wins.
  if (a.agentsActive) return { state: 'agents', amplitude: null }
  if (a.transcribing || a.status === 'sending') return { state: 'thinking', amplitude: null }
  if (a.continuousListening) return { state: 'listening', amplitude: null }
  return { state: 'idle', amplitude: null }
}

/** How long a received playback level stays trustworthy. The player tap posts
 *  ~31Hz while audio actually plays (plus one trailing 0 at burst end), so a
 *  gap this long means the lane is NOT being fed — e.g. the reply is playing
 *  through a path without the PCM-player tap (the `<audio>`-element cascade
 *  TTS). Stale ⇒ the orb falls back to its pose-only speaking choreography
 *  (exactly the pre-tap behavior) instead of freezing on dead-zero dots. */
export const PLAYBACK_LEVEL_FRESH_MS = 600

/** True while a playback level received at `lastLevelAt` may still drive the
 *  orb (both timestamps from the same clock). Pure for unit-testing the
 *  fallback rule. */
export function isPlaybackLevelFresh(lastLevelAt: number, now: number): boolean {
  return now - lastLevelAt < PLAYBACK_LEVEL_FRESH_MS
}

/** True while a summoned pill must NOT auto-retract — a PTT hold / streaming
 *  reply / spoken answer is in flight (the cursor is legitimately away). */
export function isBarBusy(a: Pick<BarActivity, 'recording' | 'transcribing' | 'status'>): boolean {
  return a.recording || a.transcribing || a.status === 'sending' || a.status === 'speaking'
}

/** The bar's effective voice signals for the current turn. A main-owned warm-hub
 *  turn (A5 PR-6b) owns the orb while `hub.active`; otherwise the local PTT signals
 *  pass through unchanged (flag off, this is exactly today's behavior).
 *
 *  The load-bearing rule: a hub SPOKEN reply (`isResponseActive`) is a 'speaking'
 *  phase, NOT thinking. It maps to chat status 'speaking' — the same signal the
 *  cascade STT→chat→TTS path raises via `chat.status` — so `deriveOrbState` lands it
 *  in the identical 'speaking' branch (orb speaking pose, list row "Speaking…"), and
 *  it is deliberately kept OUT of `transcribing` so the orb never sticks in the
 *  thinking pose for the whole reply (the bug this guards). `hubSpeaking` is returned
 *  so callers can still treat an in-flight reply as an active turn (Esc-abort,
 *  keep-alive) without reviving the thinking conflation. Pure so the hub→orb mapping
 *  is unit-tested without a DOM or IPC. */
export function deriveBarVoiceState(args: {
  hub: { active: boolean; isListening: boolean; isThinking: boolean; isResponseActive: boolean }
  localRecording: boolean
  localTranscribing: boolean
  chatStatus: BarChatStatus
}): { recording: boolean; transcribing: boolean; hubSpeaking: boolean; status: BarChatStatus } {
  const { hub, localRecording, localTranscribing, chatStatus } = args
  const hubSpeaking = hub.active && hub.isResponseActive
  return {
    recording: hub.active ? hub.isListening : localRecording,
    transcribing: hub.active ? hub.isThinking : localTranscribing,
    hubSpeaking,
    status: hubSpeaking ? 'speaking' : chatStatus
  }
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

/** The draft an agent row seeds when it opens the conversation: the agent's name
 *  in the leading-mention form `detectAgentTask` recognizes ("Claude Code, "),
 *  so whatever the user types next is delegated to that agent. The trailing
 *  comma + space is the delimiter NAME_LEADS matches; every agent displayName
 *  ("Claude Code" / "OpenClaw" / "Hermes" / "Codex") is a recognized alias. */
export function agentDraftPrefill(displayName: string): string {
  return `${displayName}, `
}

/**
 * The draft to show when the conversation opens for `target` (null = Omi Chat),
 * given the current draft and the previously-open `target`. Seeds the agent
 * delegation phrasing when an agent row opens, drops a now-stale agent seed when
 * returning to Omi, and never clobbers text the user actually typed. Pure so the
 * bar's re-entry rule (agent header + prefill on an agent, clean Omi Chat after)
 * is unit-tested without a DOM.
 */
export function nextConversationDraft(args: {
  target: BarAgentRow | null
  previous: BarAgentRow | null
  current: string
}): string {
  const { target, previous, current } = args
  const staleSeed = previous ? current === agentDraftPrefill(previous.displayName) : false
  if (target) {
    if (current.trim() === '' || staleSeed) return agentDraftPrefill(target.displayName)
    return current
  }
  return staleSeed ? '' : current
}

/** The collapsed-pill wordmark, tracking the whole voice turn (not just the
 *  capture): Listening → Thinking → Speaking → Omi.
 *   - "Listening" — Omi is capturing the user's voice: an active PTT hold
 *     (recording, even though the orb pose derives as 'speaking' for the
 *     reactive amplitude) OR always-on continuous listening. Matches the Mac
 *     bar's capture word (FloatingControlBarView "Listening...").
 *   - "Speaking" — Omi's spoken reply is playing (hub or cascade TTS; the same
 *     'speaking' chat status deriveBarVoiceState maps a hub reply onto). Same
 *     word as the list row's "Speaking…".
 *   - "Thinking" — the turn is between capture and reply: finalizing the
 *     transcript or awaiting/streaming the response. Matches Mac's typing
 *     indicator ("Thinking") and the list row's "Thinking…".
 *   - "Omi" — resting wordmark otherwise. A delegated coding-agent run also
 *     rests: the orb's distinctive 'agents' pose is the indicator there, and a
 *     minutes-long task must not pin "Thinking" on the pill.
 *  Keyed off ACTIVITY, not the orb pose, so a silent hold visibly says
 *  "Listening" while the bar is pinned open. "Listening" is the longest word
 *  and fits the fixed pill width, so the label swaps in place without shifting
 *  the orb. */
export function pillLabel(a: {
  recording: boolean
  transcribing: boolean
  status: BarChatStatus
  continuousListening: boolean
  agentsActive: boolean
}): 'Listening' | 'Thinking' | 'Speaking' | 'Omi' {
  if (a.recording) return 'Listening'
  if (a.status === 'speaking') return 'Speaking'
  if (a.agentsActive) return 'Omi'
  if (a.transcribing || a.status === 'sending') return 'Thinking'
  if (a.continuousListening) return 'Listening'
  return 'Omi'
}
