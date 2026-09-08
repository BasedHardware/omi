import { describe, it, expect } from 'vitest'
import {
  step,
  initialDetectorState,
  type DetectorConfig,
  type DetectorSignals,
  type DetectorState
} from './detector'
import type { AgreedMatch } from './patterns'

const zoom: AgreedMatch = {
  id: 'zoom',
  name: 'Zoom',
  exe: 'zoom.exe',
  via: 'process',
  tier2Key: 'zoom.exe'
}
const meetWeb: AgreedMatch = {
  id: 'meet-web',
  name: 'Google Meet',
  exe: 'chrome.exe',
  via: 'title',
  tier2Key: 'chrome.exe'
}

const cfg: DetectorConfig = { debounceMs: 3000, endGraceMs: 120_000, mode: 'ask', perApp: {} }

const quiet: DetectorSignals = { candidate: false, agreed: null, tier2Ids: [] }
const zoomPresent: DetectorSignals = { candidate: true, agreed: null, tier2Ids: [] }
const zoomAgreed: DetectorSignals = { candidate: true, agreed: zoom, tier2Ids: ['zoom.exe'] }
// Meeting continues but the user switched away from the tab: Tier 1 gone,
// Tier 2 still holds the mic.
const zoomMicOnly: DetectorSignals = { candidate: false, agreed: null, tier2Ids: ['zoom.exe'] }

/** Drive the machine to 'active' (agreement at t0, debounce elapses at t1). */
function activate(t0 = 0, config = cfg): DetectorState {
  const a = step(initialDetectorState, zoomAgreed, t0, config)
  expect(a.state.phase).toBe('candidate')
  const b = step(a.state, zoomAgreed, t0 + config.debounceMs, config)
  expect(b.state.phase).toBe('active')
  return b.state
}

describe('meeting detector state machine', () => {
  it('stays idle with no signals', () => {
    const r = step(initialDetectorState, quiet, 0, cfg)
    expect(r).toEqual({ state: { phase: 'idle' }, effects: [], deadline: null })
  })

  it('idle → candidate on Tier 1 only (no activation without Tier 2)', () => {
    const r = step(initialDetectorState, zoomPresent, 0, cfg)
    expect(r.state.phase).toBe('candidate')
    expect(r.effects).toEqual([])
    // Tier 1 alone never activates, no matter how long it persists.
    const later = step(r.state, zoomPresent, 60_000, cfg)
    expect(later.state.phase).toBe('candidate')
    expect(later.effects).toEqual([])
  })

  it('false-positive guard: YouTube playing (no Tier 1 match) never activates', () => {
    // Audio playing + even a stray mic user (e.g. a voice recorder) is NOT a
    // meeting: with no Tier 1 conferencing match the machine stays idle.
    const sig: DetectorSignals = { candidate: false, agreed: null, tier2Ids: ['audacity.exe'] }
    const r = step(initialDetectorState, sig, 0, cfg)
    expect(r.state.phase).toBe('idle')
    expect(r.effects).toEqual([])
  })

  it('agreement must hold through the debounce before activating', () => {
    const a = step(initialDetectorState, zoomAgreed, 0, cfg)
    expect(a.state.phase).toBe('candidate')
    expect(a.deadline).toBe(3000)
    // Still under the debounce → no activation.
    const b = step(a.state, zoomAgreed, 2000, cfg)
    expect(b.state.phase).toBe('candidate')
    expect(b.effects).toEqual([])
    // Debounce elapsed with agreement still present → active + started(ask).
    const c = step(b.state, zoomAgreed, 3000, cfg)
    expect(c.state.phase).toBe('active')
    expect(c.effects).toEqual([{ type: 'meeting-started', match: zoom, mode: 'ask' }])
  })

  it('a blip that drops agreement resets the debounce', () => {
    const a = step(initialDetectorState, zoomAgreed, 0, cfg)
    const blip = step(a.state, zoomPresent, 1500, cfg) // mic released briefly
    expect(blip.state.phase).toBe('candidate')
    // Agreement resumes at t=2000; debounce restarts from there.
    const b = step(blip.state, zoomAgreed, 2000, cfg)
    const c = step(b.state, zoomAgreed, 4000, cfg) // only 2s of continuous agreement
    expect(c.state.phase).toBe('candidate')
    const d = step(c.state, zoomAgreed, 5000, cfg)
    expect(d.state.phase).toBe('active')
  })

  it('switching the agreeing app restarts the debounce for the new app', () => {
    const a = step(initialDetectorState, zoomAgreed, 0, cfg)
    const meetSig: DetectorSignals = { candidate: true, agreed: meetWeb, tier2Ids: ['chrome.exe'] }
    const b = step(a.state, meetSig, 2900, cfg)
    expect(b.state.phase).toBe('candidate')
    expect(b.effects).toEqual([]) // zoom's 2.9s does not carry over to meet
    const c = step(b.state, meetSig, 2900 + 3000, cfg)
    expect(c.state.phase).toBe('active')
    expect(c.effects[0]).toMatchObject({ type: 'meeting-started', mode: 'ask' })
  })

  it('candidate → idle when Tier 1 disappears', () => {
    const a = step(initialDetectorState, zoomPresent, 0, cfg)
    const r = step(a.state, quiet, 1000, cfg)
    expect(r.state.phase).toBe('idle')
  })

  it('active survives losing Tier 1 (switched away from the tab)', () => {
    const active = activate()
    const r = step(active, zoomMicOnly, 60_000, cfg)
    expect(r.state.phase).toBe('active')
    expect(r.effects).toEqual([])
  })

  it('active → ending when Tier 2 goes quiet, back to active if the mic returns', () => {
    const active = activate()
    const a = step(active, quiet, 10_000, cfg)
    expect(a.state.phase).toBe('ending')
    expect(a.deadline).toBe(10_000 + 120_000)
    const b = step(a.state, zoomMicOnly, 30_000, cfg)
    expect(b.state.phase).toBe('active')
    expect(b.effects).toEqual([])
  })

  it('ending → ended after the grace period', () => {
    const active = activate()
    const a = step(active, quiet, 10_000, cfg)
    const still = step(a.state, quiet, 60_000, cfg)
    expect(still.state.phase).toBe('ending')
    const done = step(still.state, quiet, 130_000, cfg)
    expect(done.state.phase).toBe('idle')
    expect(done.effects).toEqual([{ type: 'meeting-ended', match: zoom }])
  })

  it('a new meeting starting right at end re-arms in the same step', () => {
    const active = activate()
    const ending = step(active, quiet, 10_000, cfg)
    const meetSig: DetectorSignals = { candidate: true, agreed: meetWeb, tier2Ids: ['chrome.exe'] }
    const r = step(ending.state, meetSig, 200_000, cfg)
    expect(r.effects[0]).toEqual({ type: 'meeting-ended', match: zoom })
    expect(r.state.phase).toBe('candidate')
    expect(r.deadline).toBe(200_000 + 3000)
  })

  it("mode 'auto' emits started(auto)", () => {
    const auto = { ...cfg, mode: 'auto' as const }
    const a = step(initialDetectorState, zoomAgreed, 0, auto)
    const b = step(a.state, zoomAgreed, 3000, auto)
    expect(b.effects).toEqual([{ type: 'meeting-started', match: zoom, mode: 'auto' }])
  })

  it("mode 'off' latches active silently (no effect, no re-trigger)", () => {
    const off = { ...cfg, mode: 'off' as const }
    const a = step(initialDetectorState, zoomAgreed, 0, off)
    const b = step(a.state, zoomAgreed, 3000, off)
    expect(b.state.phase).toBe('active')
    expect(b.effects).toEqual([])
    // Re-stepping while the meeting continues emits nothing again.
    const c = step(b.state, zoomAgreed, 60_000, off)
    expect(c.effects).toEqual([])
  })

  it('per-app override beats the global mode', () => {
    const perApp = { ...cfg, mode: 'auto' as const, perApp: { zoom: 'ask' as const } }
    const a = step(initialDetectorState, zoomAgreed, 0, perApp)
    const b = step(a.state, zoomAgreed, 3000, perApp)
    expect(b.effects).toEqual([{ type: 'meeting-started', match: zoom, mode: 'ask' }])

    const offZoom = { ...cfg, mode: 'auto' as const, perApp: { zoom: 'off' as const } }
    const c = step(initialDetectorState, zoomAgreed, 0, offZoom)
    const d = step(c.state, zoomAgreed, 3000, offZoom)
    expect(d.effects).toEqual([]) // zoom disabled even though the global is auto
  })

  it('packaged app: agreement without a candidate flag still activates', () => {
    const teams: AgreedMatch = {
      id: 'teams',
      name: 'Microsoft Teams',
      exe: null,
      via: 'process',
      tier2Key: 'msteams_8wekyb3d8bbwe'
    }
    const sig: DetectorSignals = {
      candidate: false,
      agreed: teams,
      tier2Ids: ['msteams_8wekyb3d8bbwe']
    }
    const a = step(initialDetectorState, sig, 0, cfg)
    expect(a.state.phase).toBe('candidate')
    const b = step(a.state, sig, 3000, cfg)
    expect(b.state.phase).toBe('active')
    expect(b.effects[0]).toMatchObject({ type: 'meeting-started', mode: 'ask' })
  })
})
