import { getPreferences } from '../preferences'
import type { PttEffect } from './machine'

// Renderer half of PTT system-audio muting (Track 2 A4) — the macOS
// SystemAudioMuteController's job: while a hold is capturing, other apps' audio
// is muted so a playing video doesn't bleed into the mic. The actual WASAPI work
// lives in the main process (src/main/audio/systemAudioMute.ts → the native
// helper); this module is the pure policy seam the PTT hook drives, so both the
// pref gate and the mute/restore mapping are unit-testable without a mic.
//
// Two rules, both load-bearing:
//   * MUTE is gated on the pttMuteSystemAudio pref (default ON).
//   * RESTORE is UNCONDITIONAL — never pref-gated, never conditional on us
//     believing we muted. A mute must ALWAYS be undone, including on the error,
//     cancel, watchdog, and unmount paths. (The main-process bridge and the
//     native helper are both idempotent: restoring when we hold no mute is a
//     no-op, and we never unmute a device the user muted themselves.)
//
// DEVIATION FROM macOS (deliberate): macOS restores at capture teardown AND
// again defensively right before TTS playback, because its teardown isn't a
// single deterministic point. Windows restores at the deterministic PTT-END
// effects below (release → startDrain, cancel/watchdog/unmount → stopCapture),
// which precede the STT → LLM → TTS roundtrip by seconds — so there is no
// self-mute window and no restore-before-TTS hook is needed. Do NOT add one.

/** True unless the user explicitly turned muting off (undefined ⇒ ON). */
function muteEnabled(): boolean {
  return getPreferences().pttMuteSystemAudio !== false
}

/** What a given PTT machine effect means for system audio, if anything.
 *  `startCapture` is the one capture-START effect; `startDrain` (release) and
 *  `stopCapture` (cancel / watchdog / unmount teardown) are the ONLY ways a hold
 *  can end — see machine.ts: from `holding`, RELEASE emits startDrain and
 *  CANCEL/WATCHDOG emit the TEARDOWN block containing stopCapture. */
export function systemAudioActionFor(effect: PttEffect['kind']): 'mute' | 'restore' | null {
  if (effect === 'startCapture') return 'mute'
  if (effect === 'startDrain' || effect === 'stopCapture') return 'restore'
  return null
}

/** Apply a PTT effect's system-audio consequence. Fire-and-forget over IPC —
 *  never awaited, so a slow or absent helper can never delay a hold. Safe with
 *  no bridge (jsdom tests, capture window). */
export function applyPttSystemAudio(effect: PttEffect['kind']): void {
  const action = systemAudioActionFor(effect)
  if (!action) return
  if (action === 'mute') {
    if (!muteEnabled()) return
    window.omi?.muteSystemAudio?.()
    return
  }
  window.omi?.restoreSystemAudio?.()
}

/** Unconditional restore, for teardown paths that bypass the effect stream
 *  (hook unmount). Idempotent — a no-op when nothing is muted. */
export function restoreSystemAudio(): void {
  window.omi?.restoreSystemAudio?.()
}

/** Pref-gated MUTE for a warm-hub (A5) PTT turn's capture start. Identical gate +
 *  IPC as the cascade's `startCapture` mute (`applyPttSystemAudio('startCapture')`),
 *  separated so the hub turn has a named, turn-boundary entry point — the cascade
 *  path is untouched (still `applyPttSystemAudio`), so the flag-off behavior is
 *  byte-for-byte unchanged. RESTORE is the SAME unconditional `restoreSystemAudio`;
 *  the host guarantees exactly one restore per turn (`voiceTurnHost.ts`). */
export function muteSystemAudioForHubCapture(): void {
  if (!muteEnabled()) return
  window.omi?.muteSystemAudio?.()
}
