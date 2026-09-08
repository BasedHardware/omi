// Runtime voice-plane invariants (2026-07-18) — executable cross-port checks
// for conditions no single owner's state machine can see. The failure class
// they exist for: tonight's muted-reply bug spanned three owners (the WASAPI
// helper's endpoint mute, the turn host's restore timing, the hub session's
// player) and every owner was individually "correct" — only the CROSS-port
// condition was broken. Invariants are checked event-driven off the flight
// recorder stream (zero polling, zero cost when events don't match), and a
// violation is never silent: anomaly entry + auto-heal + throttled dump.
//
// INV-VOICE-1 — "the default output endpoint must never be muted while a reply
// playback window is active." The A4 duck exists only to protect the open mic;
// a reply plays after capture ends, so any turn entering its playing phase
// while main still holds an endpoint mute means a restore was missed — the
// user is about to hear silence while every internal signal reads healthy.

export type VoicePlaneInvariantDeps = {
  /** Does main currently hold the A4 endpoint mute? (`systemAudioMuteBridge`). */
  isHoldingMute: () => boolean
  /** Auto-heal: the bridge's unconditional, idempotent restore. */
  restoreSystemAudio: () => void
  /** Append an anomaly entry to the flight recorder. */
  record: (type: string, data?: Record<string, unknown>) => void
  /** Dump the flight recorder (throttled here — one violation per turn already
   *  bounds it, this guards a pathological loop). */
  dump: (reason: string) => void
  now?: () => number
}

export const INVARIANT_DUMP_THROTTLE_MS = 60_000

export class VoicePlaneInvariants {
  private readonly deps: VoicePlaneInvariantDeps
  private readonly now: () => number
  private lastDumpAt = 0

  constructor(deps: VoicePlaneInvariantDeps) {
    this.deps = deps
    this.now = deps.now ?? (() => Date.now())
  }

  /** Feed every flight-recorder event through the invariant set. Cheap: a
   *  couple of string compares on the non-matching path. Throw-proof — a
   *  checker must never break the plane it guards. */
  checkEvent(type: string, data?: Record<string, unknown>): void {
    try {
      this.checkMutedPlayback(type, data)
    } catch (err) {
      console.error('[voice-invariant] checker threw (contained):', err)
    }
  }

  /** INV-VOICE-1: a turn entering `playing` while the endpoint mute is held. */
  private checkMutedPlayback(type: string, data?: Record<string, unknown>): void {
    if (type !== 'turn') return
    if (data?.after !== 'playing') return
    if (!this.deps.isHoldingMute()) return

    console.error(
      '[voice-invariant] INV-VOICE-1 VIOLATED: reply playback started while the default ' +
        'output endpoint is muted — the reply would be silent. Auto-restoring.'
    )
    this.deps.record('invariant_violation', { invariant: 'muted_during_playback' })
    // Auto-heal FIRST — the reply is playing right now; every ms muted is lost
    // audio. The restore is unconditional and idempotent.
    this.deps.restoreSystemAudio()
    const now = this.now()
    if (now - this.lastDumpAt >= INVARIANT_DUMP_THROTTLE_MS) {
      this.lastDumpAt = now
      this.deps.dump('invariant:muted_during_playback')
    }
  }
}
