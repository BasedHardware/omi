// Pure echo-gate decision logic (Phase 6, layer 2 of the echo architecture).
//
// Layer 1 is Chromium AEC on every mic stream. Layer 2 — this module — is the
// hard app-wide `assistantSpeaking` gate: while Omi's voice is audibly playing
// (realtime audio or TTS), the always-on transcription feed must be PAUSED so
// Omi never transcribes itself; the assistant's words are instead injected into
// the record from source text (see injectedTranscript.ts). The gate releases a
// short RELEASE_MS after the playback buffer drains, covering the acoustic tail
// (room reverb + output latency) that outlives the last queued sample.
//
// When the default output is a HEADSET, the speaker→mic acoustic path is gone,
// so the gate relaxes (feed keeps running) — Omi's voice physically can't leak
// into the mic. Classification is by device label, conservative toward
// 'speaker' (gating too much is safer than transcribing Omi).
//
// This module is pure and clock-explicit (every method takes `now` in ms) so
// the decision logic is exhaustively unit-testable; the impure driver
// (voiceController) owns timers and IPC.

export const GATE_RELEASE_MS = 300

/** Watchdog ceiling: if a terminal "speaking ended" edge is ever missed (a
 *  dropped provider event / worklet message), the gate must not stay active
 *  forever — that would silently deafen continuous transcription for the rest
 *  of the session. A playing burst older than this is treated as drained.
 *  Sized above any plausible single spoken turn. */
export const GATE_MAX_HOLD_MS = 120_000

export type OutputDeviceKind = 'headset' | 'speaker'

// Head-worn output devices: no air path back to the microphone. Matches common
// wired/BT/USB naming. 'hands-free' is the Bluetooth HFP endpoint of a headset.
const HEADSET_RE = /headphone|headset|earbud|earphone|airpod|hands-free|\bbuds|in-ear/i

/** Classify one audio-OUTPUT device label. Unknown labels → 'speaker' (gate). */
export function classifyOutputDevice(label: string): OutputDeviceKind {
  return HEADSET_RE.test(label) ? 'headset' : 'speaker'
}

/** True when the device list says Omi's voice is playing into a headset.
 *  `sinkId` '' / 'default' means the system default output; otherwise the
 *  explicitly selected sink is what matters. Missing/unlabeled devices →
 *  false (assume speakers; keep the gate hard). */
export function isHeadsetOutput(
  devices: Array<{ kind: string; deviceId: string; label: string }>,
  sinkId: string
): boolean {
  const outputs = devices.filter((d) => d.kind === 'audiooutput')
  const wanted = sinkId === '' || sinkId === 'default' ? 'default' : sinkId
  const dev = outputs.find((d) => d.deviceId === wanted) ?? outputs[0]
  if (!dev || !dev.label) return false
  return classifyOutputDevice(dev.label) === 'headset'
}

/**
 * The gate state machine. `isActive(now)` is the single question the capture
 * feed cares about: should the transcription feed be paused right now?
 */
export class EchoGate {
  // REFCOUNTED: realtime playback and a TTS element are independent audio
  // sources that can overlap — the gate must stay active until the LAST one
  // drains, not release when the first does.
  private sources = 0
  private startedAt = 0 // most recent burst start (watchdog anchor)
  private releaseAt: number | null = null
  private headset = false

  constructor(
    private readonly releaseMs: number = GATE_RELEASE_MS,
    private readonly maxHoldMs: number = GATE_MAX_HOLD_MS
  ) {}

  private get playing(): boolean {
    return this.sources > 0
  }

  /** An assistant audio source started (first sample queued/playing). Every
   *  playbackStarted must be paired with exactly one playbackDrained. */
  playbackStarted(now: number): void {
    this.sources++
    this.startedAt = now
    this.releaseAt = null
  }

  /** One source's playback fully drained (buffer empty / media element ended).
   *  The release tail starts only when the LAST source drains, and never
   *  extends past the watchdog window — a drain landing after the ceiling must
   *  not re-activate an already force-released gate. */
  playbackDrained(now: number): void {
    if (!this.playing && this.releaseAt === null) return // spurious
    this.sources = Math.max(0, this.sources - 1)
    if (this.playing) return // another source is still audible
    this.releaseAt = Math.min(now, this.startedAt + this.maxHoldMs) + this.releaseMs
  }

  /** True when the watchdog force-released a still-"playing" burst (a missed
   *  end edge). The driver reports this as a fallback — silent ops is not ok. */
  watchdogExpired(now: number): boolean {
    return this.playing && now >= this.startedAt + this.maxHoldMs
  }

  /** Barge-in: the buffer was cleared instantly. Same release tail — the sound
   *  already in the air still needs the hangover. */
  interrupted(now: number): void {
    this.playbackDrained(now)
  }

  /** Session teardown: drop every source and any pending tail immediately.
   *  The caller is responsible for silencing the sources themselves. */
  reset(): void {
    this.sources = 0
    this.releaseAt = null
    this.headset = false
  }

  setHeadset(headset: boolean): void {
    this.headset = headset
  }

  /** Should the always-on transcription feed be paused at `now`? */
  isActive(now: number): boolean {
    if (this.headset) return false
    // Watchdog: a "playing" burst older than maxHold means an end edge was
    // missed — release (with the tail) instead of deafening transcription.
    if (this.playing) return now < this.startedAt + this.maxHoldMs + this.releaseMs
    return this.releaseAt !== null && now < this.releaseAt
  }

  /** When the answer of isActive() will change on its own (release elapsing or
   *  the watchdog ceiling), or null if it only changes via events. The driver
   *  arms one timer off this. */
  nextTransitionAt(now: number): number | null {
    if (this.headset) return null
    if (this.playing) {
      const edge = this.startedAt + this.maxHoldMs + this.releaseMs
      return now < edge ? edge : null
    }
    if (this.releaseAt === null) return null
    return now < this.releaseAt ? this.releaseAt : null
  }
}
