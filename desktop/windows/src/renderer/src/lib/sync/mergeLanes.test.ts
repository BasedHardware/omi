import { describe, expect, it } from 'vitest'
import { mergeLanes } from './mergeLanes'
import type { RetainedSegment } from './segmentRetention'

function r(p: Partial<RetainedSegment> & { text: string; start: number; end: number }): RetainedSegment {
  return { is_user: false, ...p }
}

describe('mergeLanes', () => {
  it('interleaves the two lanes by wall-clock start', () => {
    const mic = [r({ text: 'mic-1', start: 0, end: 2, is_user: true }), r({ text: 'mic-2', start: 10, end: 12, is_user: true })]
    const system = [r({ text: 'sys-1', start: 4, end: 6 })]
    expect(mergeLanes(mic, system).map((s) => s.text)).toEqual(['mic-1', 'sys-1', 'mic-2'])
  })

  it('system segments are never the user and their speaker ids are offset past the mic lane', () => {
    const mic = [
      r({ text: 'me', start: 0, end: 1, is_user: true, speaker_id: 0 }),
      r({ text: 'guest on my mic', start: 1, end: 2, is_user: false, speaker_id: 2 })
    ]
    const system = [
      r({ text: 'remote a', start: 3, end: 4, speaker_id: 0, is_user: true /* stream lies */ }),
      r({ text: 'remote b', start: 4, end: 5, speaker_id: 1 })
    ]
    const merged = mergeLanes(mic, system)
    const remoteA = merged.find((s) => s.text === 'remote a')!
    const remoteB = merged.find((s) => s.text === 'remote b')!
    expect(remoteA.is_user).toBe(false)
    expect(remoteA.speaker_id).toBe(3) // 0 + (max mic id 2) + 1
    expect(remoteB.speaker_id).toBe(4)
    expect(remoteA.speaker).toBe('SPEAKER_3') // regenerated — no collision with mic labels
    // Mic lane passes through untouched.
    const me = merged.find((s) => s.text === 'me')!
    expect(me.is_user).toBe(true)
    expect(me.speaker_id).toBe(0)
  })

  it('drops empty/whitespace segments and clamps end >= start', () => {
    const mic = [r({ text: '   ', start: 0, end: 1, is_user: true }), r({ text: 'ok', start: 5, end: 4, is_user: true })]
    const merged = mergeLanes(mic, [])
    expect(merged).toHaveLength(1)
    expect(merged[0].end).toBeGreaterThanOrEqual(merged[0].start)
  })

  it('mic wins ties so the user leads at identical instants', () => {
    const merged = mergeLanes(
      [r({ text: 'mic', start: 1, end: 2, is_user: true })],
      [r({ text: 'sys', start: 1, end: 2 })]
    )
    expect(merged.map((s) => s.text)).toEqual(['mic', 'sys'])
  })

  it('produces the from-segments wire shape (speaker label, null person_id default)', () => {
    const merged = mergeLanes([r({ text: 'hello', start: 0, end: 1, is_user: true })], [])
    expect(merged[0]).toEqual({
      text: 'hello',
      speaker: 'SPEAKER_0',
      speaker_id: 0,
      is_user: true,
      person_id: null,
      start: 0,
      end: 1
    })
  })
})
