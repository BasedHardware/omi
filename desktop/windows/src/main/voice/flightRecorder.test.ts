import { describe, it, expect } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { VoiceFlightRecorder, VOICE_FLIGHT_DATA_CAP, type VoiceFlightEntry } from './flightRecorder'

function tmpDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'voice-flight-test-'))
}

describe('VoiceFlightRecorder — ring', () => {
  it('captures a scripted sequence in order with timestamps', () => {
    let t = 1000
    const r = new VoiceFlightRecorder({ now: () => t++ })
    r.record('bar', 'gesture', { phase: 'down' })
    r.record('main', 'route', { lane: 'hub' })
    r.record('home', 'turn', { event: 'start' })
    const snap = r.snapshot()
    expect(snap.map((e) => `${e.src}:${e.type}`)).toEqual([
      'bar:gesture',
      'main:route',
      'home:turn'
    ])
    expect(snap.map((e) => e.t)).toEqual([1000, 1001, 1002])
    expect(snap[0].data).toEqual({ phase: 'down' })
  })

  it('is bounded: keeps only the newest `limit` entries', () => {
    const r = new VoiceFlightRecorder({ limit: 5 })
    for (let i = 0; i < 20; i++) r.record('bar', 'gesture', { i })
    const snap = r.snapshot()
    expect(snap).toHaveLength(5)
    expect(snap.map((e) => e.data?.i)).toEqual([15, 16, 17, 18, 19])
  })

  it('truncates an oversized payload instead of storing it (privacy cap)', () => {
    const r = new VoiceFlightRecorder()
    r.record('home', 'turn', { smuggled: 'x'.repeat(VOICE_FLIGHT_DATA_CAP + 100) })
    const [entry] = r.snapshot()
    expect(entry.data).toEqual({ truncated: true, bytes: expect.any(Number) })
  })

  it('never throws on an unserializable payload', () => {
    const r = new VoiceFlightRecorder()
    const cyclic: Record<string, unknown> = {}
    cyclic.self = cyclic
    expect(() => r.record('home', 'turn', cyclic)).not.toThrow()
  })
})

describe('VoiceFlightRecorder — dump', () => {
  it('dumps the ring to a file on fire and returns the path', () => {
    const dir = tmpDir()
    const r = new VoiceFlightRecorder({ logsDir: () => dir, now: () => 1752900000000 })
    r.record('bar', 'gesture', { phase: 'down' })
    r.record('bar', 'supervisor_fired', { lane: 'hub' })
    const file = r.dump('supervisor_timeout')
    expect(file).not.toBeNull()
    const parsed = JSON.parse(fs.readFileSync(file!, 'utf8')) as {
      reason: string
      entries: VoiceFlightEntry[]
    }
    expect(parsed.reason).toBe('supervisor_timeout')
    expect(parsed.entries.map((e) => e.type)).toEqual(['gesture', 'supervisor_fired'])
    // The ring survives the dump (a second trigger still has history).
    expect(r.snapshot()).toHaveLength(2)
  })

  it('rotates old dumps beyond maxDumps', () => {
    const dir = tmpDir()
    let t = 1752900000000
    const r = new VoiceFlightRecorder({ logsDir: () => dir, now: () => (t += 1000), maxDumps: 3 })
    r.record('bar', 'gesture')
    for (let i = 0; i < 6; i++) r.dump(`r${i}`)
    const files = fs.readdirSync(dir).filter((f) => f.startsWith('voice-flight-'))
    expect(files).toHaveLength(3)
  })

  it('returns null (never throws) with no logsDir wired', () => {
    const r = new VoiceFlightRecorder()
    r.record('bar', 'gesture')
    expect(r.dump('early')).toBeNull()
  })

  it('seed entries carry over with original timestamps', () => {
    const a = new VoiceFlightRecorder({ now: () => 42 })
    a.record('bar', 'gesture')
    const b = new VoiceFlightRecorder({ seed: a.snapshot(), now: () => 9999 })
    expect(b.snapshot()[0].t).toBe(42)
  })
})
