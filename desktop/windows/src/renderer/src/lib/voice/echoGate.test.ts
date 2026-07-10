import { describe, it, expect } from 'vitest'
import { EchoGate, classifyOutputDevice, isHeadsetOutput, GATE_RELEASE_MS } from './echoGate'

describe('EchoGate', () => {
  it('is inactive until playback starts', () => {
    const g = new EchoGate()
    expect(g.isActive(0)).toBe(false)
  })

  it('activates on playback start and holds through the release tail', () => {
    const g = new EchoGate()
    g.playbackStarted()
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
    g.playbackStarted()
    g.interrupted(5000)
    expect(g.isActive(5000 + GATE_RELEASE_MS - 1)).toBe(true)
    expect(g.isActive(5000 + GATE_RELEASE_MS)).toBe(false)
  })

  it('a new burst during the release tail re-activates and cancels the release', () => {
    const g = new EchoGate()
    g.playbackStarted()
    g.playbackDrained(1000)
    g.playbackStarted() // next turn begins inside the tail
    expect(g.isActive(1000 + GATE_RELEASE_MS + 500)).toBe(true)
  })

  it('headset relaxes the gate entirely', () => {
    const g = new EchoGate()
    g.setHeadset(true)
    g.playbackStarted()
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

  it('nextTransitionAt exposes the release edge and nothing else', () => {
    const g = new EchoGate()
    expect(g.nextTransitionAt(0)).toBe(null)
    g.playbackStarted()
    expect(g.nextTransitionAt(0)).toBe(null) // only events end 'playing'
    g.playbackDrained(1000)
    expect(g.nextTransitionAt(1000)).toBe(1000 + GATE_RELEASE_MS)
    expect(g.nextTransitionAt(1000 + GATE_RELEASE_MS)).toBe(null)
  })

  it('honors a custom release duration', () => {
    const g = new EchoGate(50)
    g.playbackStarted()
    g.playbackDrained(0)
    expect(g.isActive(49)).toBe(true)
    expect(g.isActive(50)).toBe(false)
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
