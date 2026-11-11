// The single audible-output owner for the renderer voice plane.
//
// macOS guarantees "exactly one voice lane is ever audible" through ONE shared
// `VoiceTurnCoordinator.shared` output lease that BOTH audible lanes acquire —
// the realtime provider lane (`RealtimeHubController+VoiceOutput.acquireVoiceOutput`
// → `preemptFillerIfNeeded`) and the TTS/cascade lane
// (`FloatingBarVoicePlaybackService.acquirePTTLeaseIfNeeded`). A realtime lane
// coming up PREEMPTS the filler/TTS; a TTS reply is DENIED while a realtime turn
// owns the lease. Windows split those lanes across two modules and never shared
// the lease: the hub player (`hub/hubSession` via `voiceHubTurnDriver`) owns its
// own turn-scoped `VoiceOutputCoordinator`, while the TTS cascade
// (`voiceController.speakText`, fired by `useChat` for every `fromVoice` reply)
// plays through `<audio>`/system-voice consulting nothing. So a realtime hub
// reply and a late/duplicate cascade reply could both be audible at once (the
// "two/three voices at the same time" bug when a hub tool call degraded).
//
// This module is the Windows distillation of Mac's cross-lane arbitration: one
// process-wide audible owner (every audible lane runs in the MAIN renderer per
// decision D1 — `pcmPlayer` + `voiceController` + the hub driver are all
// main-resident), with the same two rules Mac enforces:
//   * A REALTIME lane (hub or the continuous Home session) becoming audible is
//     the single owner and PREEMPTS any in-flight TTS cascade (Mac
//     `preemptFillerIfNeeded`).
//   * The TTS cascade is DENIED while a realtime lane is audible (Mac's lease
//     denial) — the reply text is still recorded/shown, just never double-spoken.
//
// It holds no audio itself: the TTS-stop is an injected hook (`registerTtsStop`,
// wired by `voiceController` to its `resetTtsPipeline`) so this module stays a
// pure, hermetically-testable arbiter with no import cycle.

type StopFn = () => void

/** Realtime lanes (hub / continuous session) currently producing audible output.
 *  A Set of opaque tokens rather than a counter so a missed end() can only ever
 *  leak ONE lane's token (cleaned up on every terminal/teardown/dispose path),
 *  and double-end is a safe no-op. */
const realtimeSpeakers = new Set<symbol>()

/** The TTS cascade's stop hook (`voiceController.resetTtsPipeline`). Injected so
 *  a realtime lane can physically preempt an in-flight cascade without this
 *  module importing `voiceController` (no cycle). */
let stopTts: StopFn | null = null

/** Wire the cascade-stop hook once (voiceController module load). Passing `null`
 *  clears it (test isolation). */
export function registerTtsStop(stop: StopFn | null): void {
  stopTts = stop
}

/** A realtime lane began audible output. It is now the single audible owner:
 *  any in-flight TTS cascade is preempted immediately (Mac `preemptFillerIfNeeded`),
 *  and later cascade replies are denied until every realtime speaker ends. Returns
 *  a token the caller MUST pass to `endRealtimeAudible` on drain/teardown. */
export function beginRealtimeAudible(): symbol {
  const token = Symbol('realtime-audible')
  realtimeSpeakers.add(token)
  // Preempt any cascade already speaking — the realtime lane wins (it is the live
  // provider reply; a concurrent cascade is a stale/duplicate answer).
  try {
    stopTts?.()
  } catch (err) {
    console.error('[voice-arbiter] TTS preempt hook threw (contained):', err)
  }
  return token
}

/** A realtime lane's audible output ended (drain / barge-in / terminal / teardown).
 *  Idempotent — safe to call for an already-ended or unknown token. */
export function endRealtimeAudible(token: symbol | null): void {
  if (token !== null) realtimeSpeakers.delete(token)
}

/** True while any realtime lane is audible. `voiceController.speakText` consults
 *  this before going audible and drops (does not play) when it is true. */
export function isRealtimeAudible(): boolean {
  return realtimeSpeakers.size > 0
}

/** Test-only: drop all state so one test can't leak a realtime speaker into the
 *  next. Never called in production. */
export function __resetAudibleArbiterForTests(): void {
  realtimeSpeakers.clear()
  stopTts = null
}
