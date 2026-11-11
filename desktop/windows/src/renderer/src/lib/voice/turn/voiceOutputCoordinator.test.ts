// 1:1 port of macOS `Tests/PTTVoiceOutputCoordinatorTests.swift` (12 cases).
// The Swift test NAMES are preserved verbatim — each name documents the
// invariant the lease coordinator exists to hold.
//
// Two Swift cases inspect a source file instead of exercising behavior:
//   * `testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease` — a pure policy
//     check; ported behaviorally against `VoicePlaybackStartPolicy`.
//   * `testFillerCarriesTextIntoSystemVoiceFallback` — a Mac source-inspection
//     tripwire on `FloatingBarVoicePlaybackService.swift`, a file with NO Windows
//     counterpart (A5 does not port the playback service — A1 already shipped
//     Windows playback in `voiceController.ts`). It is ported as a source
//     tripwire retargeted to `voiceController.ts`; the *behavioral* coverage of
//     the same fallback lives (and is stronger) in `voiceController.pipeline.test.ts`.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import {
  leasesEqual,
  type VoiceLeaseID,
  type VoiceOutputLane,
  type VoiceOutputLease,
  type VoiceTurnID
} from './voiceTurnMachine'
import {
  VoiceOutputCoordinator,
  VoiceOutputHandoffPolicy,
  VoicePlaybackStartPolicy,
  type VoiceOutputDecision
} from './voiceOutputCoordinator'

// Swift's private `tryLease` (`guard case .acquired(let lease) = decision`).
const tryLease = (decision: VoiceOutputDecision): VoiceOutputLease | null =>
  decision.kind === 'acquired' ? decision.lease : null

const freshTurnID = (): VoiceTurnID => crypto.randomUUID() as VoiceTurnID
const freshLeaseID = (): VoiceLeaseID => crypto.randomUUID() as VoiceLeaseID

// Swift `VoiceOutputLane.allCases`.
const ALL_LANES: VoiceOutputLane[] = [
  'nativeRealtime',
  'selectedVoiceFallback',
  'deterministicAgentAck',
  'filler',
  'systemVoiceFallback'
]

describe('VoiceOutputCoordinator — PTT output leases (ported from PTTVoiceOutputCoordinatorTests)', () => {
  it('testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease', () => {
    expect(VoicePlaybackStartPolicy.accepts(true)).toBe(true)
    expect(VoicePlaybackStartPolicy.accepts(false)).toBe(false)
  })

  it('testFillerCarriesTextIntoSystemVoiceFallback', () => {
    // Windows deviation: the Swift original greps `FloatingBarVoicePlaybackService.swift`;
    // Windows owns this in `voiceController.ts`. Windows has a single fallback path
    // (no exhausted-vs-degraded split), so the Swift `? .exhausted : .degraded` /
    // "no fallback speech available" assertions have no Windows analog. Behavioral
    // coverage: voiceController.pipeline.test.ts "falls back to the system voice …".
    const source = readFileSync(
      fileURLToPath(new URL('../voiceController.ts', import.meta.url)),
      'utf8'
    )
    // The chunk text is carried INTO the system-voice fallback (not dropped).
    expect(source).toContain('await playSystemVoice(res.text)')
    // …and the fail-open is recorded with the shared fallback telemetry.
    expect(source).toContain("to: 'system_voice'")
    expect(source).toContain("outcome: 'degraded'")
  })

  it('testFallbackCannotStartAfterNativeRealtimeLease', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()
    const native = tryLease(coordinator.acquire('nativeRealtime', turnID))

    expect(native?.lane).toBe('nativeRealtime')
    const decision = coordinator.acquire('selectedVoiceFallback', turnID)
    expect(decision.kind).toBe('denied')
    expect(
      decision.kind === 'denied' && native !== null && leasesEqual(decision.active, native)
    ).toBe(true)
  })

  it('testLateNativeAudioIsDeniedAfterFallbackLease', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()
    const fallback = tryLease(coordinator.acquire('selectedVoiceFallback', turnID))

    const decision = coordinator.acquire('nativeRealtime', turnID)
    expect(decision.kind).toBe('denied')
    expect(
      decision.kind === 'denied' && fallback !== null && leasesEqual(decision.active, fallback)
    ).toBe(true)
  })

  it('testEveryPTTAudibleLaneCompetesForTheSameLease', () => {
    for (const firstLane of ALL_LANES) {
      for (const competingLane of ALL_LANES) {
        if (competingLane === firstLane) continue
        const coordinator = new VoiceOutputCoordinator()
        const turnID = coordinator.beginTurn()
        const first = tryLease(coordinator.acquire(firstLane, turnID))

        const decision = coordinator.acquire(competingLane, turnID)
        expect(
          decision.kind === 'denied' && first !== null && leasesEqual(decision.active, first),
          `${competingLane} should not overlap ${firstLane}`
        ).toBe(true)
      }
    }
  })

  it('testFillerIsTheOnlyLaneThatYieldsToRealOutputOnTheSameTurn', () => {
    const turnID = freshTurnID()
    const filler: VoiceOutputLease = { id: freshLeaseID(), turnID, lane: 'filler' }

    for (const lane of ALL_LANES) {
      if (lane === 'filler') continue
      expect(VoiceOutputHandoffPolicy.fillerCanYield(filler, lane, turnID)).toBe(true)
    }
    expect(VoiceOutputHandoffPolicy.fillerCanYield(filler, 'filler', turnID)).toBe(false)

    const native: VoiceOutputLease = { id: freshLeaseID(), turnID, lane: 'nativeRealtime' }
    expect(VoiceOutputHandoffPolicy.fillerCanYield(native, 'selectedVoiceFallback', turnID)).toBe(
      false
    )
    expect(VoiceOutputHandoffPolicy.fillerCanYield(filler, 'nativeRealtime', freshTurnID())).toBe(
      false
    )
  })

  it('testSameLaneAcquireIsIdempotent', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()
    const first = tryLease(coordinator.acquire('nativeRealtime', turnID))
    const second = tryLease(coordinator.acquire('nativeRealtime', turnID))

    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    expect(leasesEqual(first as VoiceOutputLease, second as VoiceOutputLease)).toBe(true)
  })

  it('testDeterministicAckSuppressesProviderOutputForTurn', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()

    expect(tryLease(coordinator.acquire('deterministicAgentAck', turnID))).not.toBeNull()
    expect(coordinator.snapshot().providerOutputSuppressed).toBe(true)
  })

  it('testStaleReleaseCannotClearCurrentLease', () => {
    const coordinator = new VoiceOutputCoordinator()
    const firstTurnID = coordinator.beginTurn()
    const staleLease = tryLease(coordinator.acquire('nativeRealtime', firstTurnID))
    const secondTurnID = coordinator.beginTurn()
    const currentLease = tryLease(coordinator.acquire('selectedVoiceFallback', secondTurnID))

    expect(staleLease).not.toBeNull()
    expect(currentLease).not.toBeNull()
    expect(coordinator.release(staleLease as VoiceOutputLease)).toBe(false)
    expect(
      leasesEqual(
        coordinator.snapshot().activeLease as VoiceOutputLease,
        currentLease as VoiceOutputLease
      )
    ).toBe(true)
  })

  it('testStaleTurnCannotAcquireOrEndCurrentTurn', () => {
    const coordinator = new VoiceOutputCoordinator()
    const staleTurnID = coordinator.beginTurn()
    const currentTurnID = coordinator.beginTurn()

    expect(coordinator.acquire('nativeRealtime', staleTurnID)).toEqual({ kind: 'staleTurn' })
    expect(coordinator.endTurn(staleTurnID)).toBe(false)
    expect(coordinator.snapshot().turnID).toBe(currentTurnID)
  })

  it('testReleaseRequiresExactLeaseIdentity', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()
    const lease = tryLease(coordinator.acquire('nativeRealtime', turnID))
    const impostor: VoiceOutputLease = { id: freshLeaseID(), turnID, lane: 'nativeRealtime' }

    expect(lease).not.toBeNull()
    expect(coordinator.release(impostor)).toBe(false)
    expect(
      leasesEqual(coordinator.snapshot().activeLease as VoiceOutputLease, lease as VoiceOutputLease)
    ).toBe(true)
    expect(coordinator.release(lease as VoiceOutputLease)).toBe(true)
    expect(coordinator.snapshot().activeLease).toBeNull()
  })

  it('testInterruptRequiresCurrentTurnAndRevokesLease', () => {
    const coordinator = new VoiceOutputCoordinator()
    const turnID = coordinator.beginTurn()
    expect(tryLease(coordinator.acquire('systemVoiceFallback', turnID))).not.toBeNull()

    expect(coordinator.interrupt(freshTurnID())).toBe(false)
    expect(coordinator.snapshot().activeLease).not.toBeNull()
    expect(coordinator.interrupt(turnID)).toBe(true)
    expect(coordinator.snapshot().activeLease).toBeNull()
  })
})

describe('voiceController leaseID seam (PR-3 additive, inert until PR-6)', () => {
  it('speakText and interruptCurrentResponse take an optional leaseID defaulting to null and ignore it', () => {
    // The seam PR-6 threads real leases through. In PR-3 it MUST be byte-for-byte
    // today's behavior when omitted — proven statically here (the default is null
    // and the value is `void`-discarded) and behaviorally by A1's unchanged
    // voiceController.pipeline.test.ts / voiceController.test.ts suites.
    const source = readFileSync(
      fileURLToPath(new URL('../voiceController.ts', import.meta.url)),
      'utf8'
    )
    expect(source).toContain('leaseID: VoiceLeaseID | null = null')
    expect(source).toContain('void leaseID')
  })
})
