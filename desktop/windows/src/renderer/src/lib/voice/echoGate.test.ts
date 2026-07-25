import { describe, it, expect } from 'vitest'
import {
  EchoGate,
  classifyOutputDevice,
  isHeadsetOutput,
  GATE_RELEASE_MS,
  GATE_MAX_HOLD_MS
} from './echoGate'

describe('EchoGate', () => {
  it('is inactive until playback starts', () => {
    const g = new EchoGate()
    expect(g.isActive(0)).toBe(false)
  })

  it('activates on playback start and holds through the release tail', () => {
    const g = new EchoGate()
    g.playbackStarted(0)
    expect(g.isActive(1000)).toBe(true)
    g.playbackDrained(2000)
    // Still inside the acoustic-tail hangover…
    expect(g.isActive(2000)).toBe(true)
    expect(g.isActive(2000 + GATE_RELEASE_MS - 1)).toBe(true)
    // …and releases exactly at the boundary.
    expect(g.isActive(2000 + GATE_RELEASE_MS)).toBe(false)
  })

  it('barge-in interrupt schedules the same release tail', () => {
    const g = new EchoGate()
    g.playbackStarted(0)
    g.interrupted(5000)
    expect(g.isActive(5000 + GATE_RELEASE_MS - 1)).toBe(true)
    expect(g.isActive(5000 + GATE_RELEASE_MS)).toBe(false)
  })

  it('a new burst during the release tail re-activates and cancels the release', () => {
    const g = new EchoGate()
    g.playbackStarted(0)
    g.playbackDrained(1000)
    g.playbackStarted(1100) // next turn begins inside the tail
    expect(g.isActive(1000 + GATE_RELEASE_MS + 500)).toBe(true)
  })

  it('headset relaxes the gate entirely', () => {
    const g = new EchoGate()
    g.setHeadset(true)
    g.playbackStarted(0)
    expect(g.isActive(0)).toBe(false)
    // Unplugging the headset mid-burst re-hardens the gate.
    g.setHeadset(false)
    expect(g.isActive(0)).toBe(true)
  })

  it('spurious drain (nothing ever played) does not activate the gate', () => {
    const g = new EchoGate()
    g.playbackDrained(100)
    expect(g.isActive(100)).toBe(false)
  })

  it('nextTransitionAt exposes the release edge (and the watchdog while playing)', () => {
    const g = new EchoGate()
    expect(g.nextTransitionAt(0)).toBe(null)
    g.playbackStarted(0)
    // While playing the only self-transition is the watchdog ceiling.
    expect(g.nextTransitionAt(0)).toBe(GATE_MAX_HOLD_MS + GATE_RELEASE_MS)
    g.playbackDrained(1000)
    expect(g.nextTransitionAt(1000)).toBe(1000 + GATE_RELEASE_MS)
    expect(g.nextTransitionAt(1000 + GATE_RELEASE_MS)).toBe(null)
  })

  it('honors a custom release duration', () => {
    const g = new EchoGate(50)
    g.playbackStarted(0)
    g.playbackDrained(0)
    expect(g.isActive(49)).toBe(true)
    expect(g.isActive(50)).toBe(false)
  })

  it('REFCOUNT: the gate holds until the LAST concurrent source drains', () => {
    const g = new EchoGate()
    g.playbackStarted(0) // realtime turn
    g.playbackStarted(100) // overlapping TTS
    g.playbackDrained(1000) // first source ends — other still audible
    expect(g.isActive(1000 + GATE_RELEASE_MS + 500)).toBe(true)
    g.playbackDrained(3000) // last source ends → tail → release
    expect(g.isActive(3000 + GATE_RELEASE_MS - 1)).toBe(true)
    expect(g.isActive(3000 + GATE_RELEASE_MS)).toBe(false)
  })

  it('WATCHDOG: a missed end edge force-releases after the max hold', () => {
    const g = new EchoGate()
    g.playbackStarted(0)
    // No drain ever arrives (dropped provider event)…
    expect(g.isActive(GATE_MAX_HOLD_MS - 1)).toBe(true)
    expect(g.watchdogExpired(GATE_MAX_HOLD_MS - 1)).toBe(false)
    expect(g.watchdogExpired(GATE_MAX_HOLD_MS)).toBe(true)
    // …the gate still releases (with the tail) instead of deafening forever.
    expect(g.isActive(GATE_MAX_HOLD_MS + GATE_RELEASE_MS)).toBe(false)
    // A drain landing AFTER the ceiling must not re-activate the gate.
    g.playbackDrained(GATE_MAX_HOLD_MS + 60_000)
    expect(g.isActive(GATE_MAX_HOLD_MS + 60_000)).toBe(false)
  })

  it('watchdog anchors to the most recent burst start', () => {
    const g = new EchoGate(GATE_RELEASE_MS, 1000)
    g.playbackStarted(0)
    g.playbackDrained(500)
    g.playbackStarted(600) // new burst re-anchors the ceiling
    expect(g.isActive(1000 + GATE_RELEASE_MS)).toBe(true) // < 600 + 1000 + release
    expect(g.isActive(600 + 1000 + GATE_RELEASE_MS)).toBe(false)
  })

  it('reset() drops all sources and any pending tail immediately', () => {
    const g = new EchoGate()
    g.playbackStarted(0)
    g.playbackStarted(10)
    g.reset()
    expect(g.isActive(11)).toBe(false)
    expect(g.nextTransitionAt(11)).toBe(null)
    // And a stale drain after reset is a no-op…
    g.playbackDrained(20)
    expect(g.isActive(20)).toBe(false)
  })
})

describe('classifyOutputDevice', () => {
  it.each([
    ['Headphones (WH-1000XM5 Stereo)', 'headset'],
    ['Headset Earphone (Arctis 7)', 'headset'],
    ['AirPods Pro', 'headset'],
    ['Galaxy Buds2 Pro', 'headset'],
    ['Headset (JBL TUNE 510BT Hands-Free AG Audio)', 'headset'],
    ['Speakers (Realtek(R) Audio)', 'speaker'],
    ['LG ULTRAGEAR (NVIDIA High Definition Audio)', 'speaker'],
    ['CABLE Input (VB-Audio Virtual Cable)', 'speaker'],
    ['', 'speaker']
  ])('%s → %s', (label, kind) => {
    expect(classifyOutputDevice(label)).toBe(kind)
  })
})

describe('isHeadsetOutput', () => {
  const devices = [
    { kind: 'audiooutput', deviceId: 'default', label: 'Speakers (Realtek(R) Audio)' },
    { kind: 'audiooutput', deviceId: 'dev-headset', label: 'Headphones (WH-1000XM5)' },
    { kind: 'audioinput', deviceId: 'mic', label: 'Headset Microphone' }
  ]

  it('uses the default output for empty/default sinkId', () => {
    expect(isHeadsetOutput(devices, '')).toBe(false)
    expect(isHeadsetOutput(devices, 'default')).toBe(false)
  })

  it('uses the explicitly selected sink', () => {
    expect(isHeadsetOutput(devices, 'dev-headset')).toBe(true)
  })

  it('fails closed (speaker/gate) on missing or unlabeled devices', () => {
    expect(isHeadsetOutput([], 'default')).toBe(false)
    expect(
      isHeadsetOutput([{ kind: 'audiooutput', deviceId: 'default', label: '' }], 'default')
    ).toBe(false)
  })
})
