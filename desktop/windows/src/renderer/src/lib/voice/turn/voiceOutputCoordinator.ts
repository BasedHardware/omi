// Authoritative audible-output owner for a PTT turn — a 1:1 port of macOS
// `PTTVoiceOutputCoordinator.swift` (`VoiceOutputCoordinator`).
//
// Every PTT audio path (native realtime, the selected-voice fallback, the
// deterministic agent ack, the filler, the system-voice fallback) must acquire a
// turn-scoped lease before it can play. Releases and turn endings are identity
// checked so an old playback callback cannot clear a newer turn's output or UI.
//
// The reducer (`voiceTurnMachine.ts`) already owns `VoiceLeaseID`,
// `VoiceOutputLease`, `VoiceOutputLane` and `VoiceTurnID` — reuse those exact
// types here; do NOT redefine them. This module is the *runtime owner* of the
// lease the reducer models as a value.
//
// Port notes (traps a "natural" TS translation gets wrong):
//   * Swift structs are VALUE-equal. `release` fences on `activeLease == lease`
//     (full field equality via `leasesEqual`), not object identity — a
//     reconstructed impostor lease with the same fields would (correctly) match,
//     which is why `release` ALSO requires the current turn to still own it.
//   * `acquire` on the SAME lane is IDEMPOTENT — it returns the existing lease,
//     never `.denied`. Any DIFFERENT lane is denied while a lease is held.
//   * `deterministicAgentAck` acquiring flips `providerOutputSuppressed` true for
//     the whole turn (the ack has spoken; suppress the provider's own output).
//   * Every mutation is turn-ID fenced: a stale turnID yields `.staleTurn`
//     (acquire) or `false` (endTurn/interrupt/release) with NO state change.

import {
  leasesEqual,
  type VoiceLeaseID,
  type VoiceOutputLane,
  type VoiceOutputLease,
  type VoiceTurnID
} from './voiceTurnMachine'

// MARK: - Decision (Swift `VoiceOutputDecision`, :3)

export type VoiceOutputDecision =
  | { kind: 'acquired'; lease: VoiceOutputLease }
  | { kind: 'denied'; active: VoiceOutputLease }
  | { kind: 'staleTurn' }

// MARK: - Snapshot (Swift `VoiceOutputSnapshot`, :9)

export type VoiceOutputSnapshot = {
  readonly turnID: VoiceTurnID | null
  readonly activeLease: VoiceOutputLease | null
  readonly providerOutputSuppressed: boolean
}

// MARK: - Handoff policy (Swift `VoiceOutputHandoffPolicy`, :15)

export const VoiceOutputHandoffPolicy = {
  /** The FILLER lane yields to any non-filler lane on the SAME turn, and nothing
   *  else yields. Ported verbatim from Swift (:21):
   *  `active.turnID == turnID && active.lane == .filler && incomingLane != .filler`. */
  fillerCanYield(
    active: VoiceOutputLease,
    incomingLane: VoiceOutputLane,
    turnID: VoiceTurnID
  ): boolean {
    return active.turnID === turnID && active.lane === 'filler' && incomingLane !== 'filler'
  }
} as const

// MARK: - Playback-start policy (Swift `VoicePlaybackStartPolicy`,
// FloatingBarVoicePlaybackService.swift:975 — referenced by
// `testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease`)

export const VoicePlaybackStartPolicy = {
  /** A player only owns the lease once it has ACTUALLY started
   *  (`accepts(started: Bool) -> Bool { started }`). */
  accepts(started: boolean): boolean {
    return started
  }
} as const

// MARK: - Coordinator

/** Swift mints `VoiceTurnID()` / `VoiceLeaseID()` (UUIDs) inside the coordinator;
 *  minting is injectable here purely so tests can pin identities. */
export type VoiceOutputCoordinatorOptions = {
  mintTurnID?: () => VoiceTurnID
  mintLeaseID?: () => VoiceLeaseID
}

export class VoiceOutputCoordinator {
  private readonly mintTurnID: () => VoiceTurnID
  private readonly mintLeaseID: () => VoiceLeaseID

  private currentTurnID: VoiceTurnID | null = null
  private currentActiveLease: VoiceOutputLease | null = null
  private providerOutputSuppressed = false

  constructor(options: VoiceOutputCoordinatorOptions = {}) {
    this.mintTurnID = options.mintTurnID ?? (() => crypto.randomUUID() as VoiceTurnID)
    this.mintLeaseID = options.mintLeaseID ?? (() => crypto.randomUUID() as VoiceLeaseID)
  }

  /** Swift `beginTurn(id: VoiceTurnID = VoiceTurnID())` (:41). */
  beginTurn(id: VoiceTurnID = this.mintTurnID()): VoiceTurnID {
    this.currentTurnID = id
    this.currentActiveLease = null
    this.providerOutputSuppressed = false
    return id
  }

  /** Swift `endTurn` (:49) — no-op unless the requested turn is current. */
  endTurn(requestedTurnID: VoiceTurnID): boolean {
    if (requestedTurnID !== this.currentTurnID) return false
    this.currentTurnID = null
    this.currentActiveLease = null
    this.providerOutputSuppressed = false
    return true
  }

  /** Swift `interrupt` (:58) — revokes the lease but KEEPS the turn open. */
  interrupt(requestedTurnID: VoiceTurnID): boolean {
    if (requestedTurnID !== this.currentTurnID) return false
    this.currentActiveLease = null
    this.providerOutputSuppressed = false
    return true
  }

  /** Swift `acquire(_ lane:, turnID:)` (:65). Same-lane acquire is idempotent;
   *  any other lane is denied while a lease is held; a stale turn is rejected. */
  acquire(lane: VoiceOutputLane, requestedTurnID: VoiceTurnID): VoiceOutputDecision {
    if (requestedTurnID !== this.currentTurnID) return { kind: 'staleTurn' }
    const active = this.currentActiveLease
    if (active !== null) {
      if (active.turnID === requestedTurnID && active.lane === lane) {
        return { kind: 'acquired', lease: active }
      }
      return { kind: 'denied', active }
    }
    const lease: VoiceOutputLease = {
      id: this.mintLeaseID(),
      turnID: requestedTurnID,
      lane
    }
    this.currentActiveLease = lease
    if (lane === 'deterministicAgentAck') {
      this.providerOutputSuppressed = true
    }
    return { kind: 'acquired', lease }
  }

  /** Swift `release` (:83) — exact lease identity AND the turn must still own it. */
  release(lease: VoiceOutputLease): boolean {
    if (
      this.currentActiveLease === null ||
      !leasesEqual(this.currentActiveLease, lease) ||
      this.currentTurnID !== lease.turnID
    ) {
      return false
    }
    this.currentActiveLease = null
    this.providerOutputSuppressed = false
    return true
  }

  snapshot(): VoiceOutputSnapshot {
    return {
      turnID: this.currentTurnID,
      activeLease: this.currentActiveLease,
      providerOutputSuppressed: this.providerOutputSuppressed
    }
  }
}
