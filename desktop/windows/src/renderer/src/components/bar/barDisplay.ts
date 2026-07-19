// Pure display logic for the bar (orb state, retract-hold, list status). Kept
// out of the React components so it's unit-testable without a DOM or IPC — these
// are the load-bearing rules of the rework (orb is the sole status indicator;
// the pill stays open while a voice exchange is in flight).
import type { OrbState } from '../../orb/choreography'
import type { BarChatStatus, WaveformSource } from '../../../../shared/types'

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

/** The bar's turn phase — the ONE precedence ladder every bar status surface
 *  (orb pose+amplitude, pill word) derives from, so they can never desync:
 *  - capturing: the user's voice is being recorded (a PTT hold; wins over
 *    everything — including a still-playing reply — so the user's own turn is
 *    the reactive one)
 *  - replying:  Omi's spoken reply is playing (hub or cascade TTS — both raise
 *    chat status 'speaking')
 *  - agents:    a delegated coding-agent task is running (over generic
 *    thinking; both carry status 'sending')
 *  - thinking:  finalizing the transcript / awaiting or streaming the reply
 *  - ambient:   always-on continuous listening, no active turn
 *  - idle:      nothing in flight */
export type BarTurnPhase = 'capturing' | 'replying' | 'agents' | 'thinking' | 'ambient' | 'idle'

export function deriveTurnPhase(a: Omit<BarActivity, 'locked'>): BarTurnPhase {
  if (a.recording) return 'capturing'
  if (a.status === 'speaking') return 'replying'
  if (a.agentsActive) return 'agents'
  if (a.transcribing || a.status === 'sending') return 'thinking'
  if (a.continuousListening) return 'ambient'
  return 'idle'
}

/**
 * The bar orb's state + which live amplitude lane (if any) to attach, mapped
 * from the shared turn phase:
 *  - capturing → speaking (or the distinct locked-listening pose), with the
 *    user's MIC amplitude (the blob reacts)
 *  - replying  → speaking, with the PLAYBACK amplitude (the reply's own speech
 *    dynamics animate the dots — the same visual language as the mic, driven by
 *    the audio actually playing)
 *  - thinking/agents/ambient/idle → their poses, no live amplitude
 */
export function deriveOrbState(a: BarActivity): { state: OrbState; amplitude: OrbAmplitudeLane } {
  switch (deriveTurnPhase(a)) {
    case 'capturing':
      return { state: a.locked ? 'listening' : 'speaking', amplitude: 'mic' }
    case 'replying':
      return { state: 'speaking', amplitude: 'playback' }
    case 'agents':
      return { state: 'agents', amplitude: null }
    case 'thinking':
      return { state: 'thinking', amplitude: null }
    case 'ambient':
      return { state: 'listening', amplitude: null }
    case 'idle':
      return { state: 'idle', amplitude: null }
  }
}

/** How long a received playback level stays trustworthy. The player tap posts
 *  ~31Hz while audio actually plays (plus one trailing 0 at burst end), so a
 *  gap this long means the lane is NOT being fed — e.g. the reply is playing
 *  through a path without the PCM-player tap (the `<audio>`-element cascade
 *  TTS or the speechSynthesis fallback). Stale ⇒ the orb falls back to its
 *  pose-only speaking choreography (exactly the pre-tap behavior) instead of
 *  freezing on dead-zero dots.
 *
 *  Staleness-as-presence-detection is an accepted BRIDGE, not the end state:
 *  it infers "this playback route has no tap" from silence on the channel. The
 *  structural version is an explicit has-tap signal from the playback route
 *  itself (v-next, alongside tapping the `<audio>` cascade via a
 *  MediaElementSource graph). */
export const PLAYBACK_LEVEL_FRESH_MS = 600

/** True while a playback level received at `lastLevelAt` may still drive the
 *  orb (both timestamps from the same clock). Pure for unit-testing the
 *  fallback rule. */
export function isPlaybackLevelFresh(lastLevelAt: number, now: number): boolean {
  return now - lastLevelAt < PLAYBACK_LEVEL_FRESH_MS
}

/** A WaveformSource that reads a single live level (the orb's canonical linear
 *  0..1 unit) through `getLevel`: `getOrbLevel` hands it to the orb's fast
 *  lane untouched (the adaptive mapper bounds hot input downstream), and the
 *  bar-graph fallback paints every bin at the clamped level. Shared by the
 *  bar's hub-projected mic lane and the playback lane — one shape, two feeds. */
export function constantLevelWaveformSource(getLevel: () => number): WaveformSource {
  return {
    getByteFrequencyData: (dest) => {
      dest.fill(Math.round(Math.min(1, Math.max(0, getLevel())) * 255))
    },
    getOrbLevel: getLevel
  }
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
export function pillLabel(
  a: Omit<BarActivity, 'locked'>
): 'Listening' | 'Thinking' | 'Speaking' | 'Omi' {
  switch (deriveTurnPhase(a)) {
    case 'capturing':
    case 'ambient':
      return 'Listening'
    case 'replying':
      return 'Speaking'
    case 'thinking':
      return 'Thinking'
    case 'agents':
    case 'idle':
      return 'Omi'
  }
}
