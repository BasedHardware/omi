// Pure display logic for the bar (orb state, retract-hold, list status). Kept
// out of the React components so it's unit-testable without a DOM or IPC — these
// are the load-bearing rules of the rework (orb is the sole status indicator;
// the pill stays open while a voice exchange is in flight).
import type { OrbState } from '../../orb/choreography'
import type { BarChatState, BarChatStatus } from '../../../../shared/types'

export type BarActivity = {
  /** PTT is capturing the user's voice right now (local to the bar). */
  recording: boolean
  /** PTT is finalizing a captured transcript (local to the bar). */
  transcribing: boolean
  /** Projected chat status from the main window's engine. */
  status: BarChatStatus
  /** Continuous listening is on AND the user is signed in. */
  continuousListening: boolean
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
  if (a.transcribing || a.status === 'sending') return { state: 'thinking', withAmplitude: false }
  if (a.continuousListening) return { state: 'listening', withAmplitude: false }
  return { state: 'idle', withAmplitude: false }
}

/** True while a summoned pill must NOT auto-retract — a PTT hold / streaming
 *  reply / spoken answer is in flight (the cursor is legitimately away). */
export function isBarBusy(a: Pick<BarActivity, 'recording' | 'transcribing' | 'status'>): boolean {
  return (
    a.recording || a.transcribing || a.status === 'sending' || a.status === 'speaking'
  )
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
