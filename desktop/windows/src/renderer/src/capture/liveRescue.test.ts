import { describe, it, expect } from 'vitest'
import {
  MAX_RECONNECT_ATTEMPTS,
  reconnectDelayMs,
  isRetryableDropError,
  toSyncSegments,
  segmentsToTranscript,
  createSegmentRetainer
} from './liveRescue'
import type { BackendSegment } from '../../../shared/types'

describe('reconnectDelayMs', () => {
  it('backs off exponentially and caps at 32s (matches the macOS reference)', () => {
    expect(reconnectDelayMs(1)).toBe(2000)
    expect(reconnectDelayMs(2)).toBe(4000)
    expect(reconnectDelayMs(3)).toBe(8000)
    expect(reconnectDelayMs(4)).toBe(16000)
    expect(reconnectDelayMs(5)).toBe(32000)
    expect(reconnectDelayMs(6)).toBe(32000)
    expect(reconnectDelayMs(MAX_RECONNECT_ATTEMPTS)).toBe(32000)
  })

  it('treats attempt 0/negative as the first delay (never zero)', () => {
    expect(reconnectDelayMs(0)).toBe(2000)
    expect(reconnectDelayMs(-3)).toBe(2000)
  })
})

describe('isRetryableDropError', () => {
  it('retries transient network/server drops', () => {
    expect(isRetryableDropError('socket dropped')).toBe(true)
    expect(isRetryableDropError('Omi /v4/listen closed (1006)')).toBe(true)
    expect(isRetryableDropError('Omi transcription stopped: connection reset')).toBe(true)
  })

  it('does NOT retry quota/entitlement/sign-in errors (reconnecting re-hits the same wall)', () => {
    expect(
      isRetryableDropError(
        'Omi transcription stopped: free Omi transcription quota is used up (1008)'
      )
    ).toBe(false)
    expect(isRetryableDropError('trial_expired')).toBe(false)
    expect(isRetryableDropError('Omi transcription unavailable (not signed in)')).toBe(false)
    expect(isRetryableDropError('Omi v4/listen requires sign-in.')).toBe(false)
  })
})

describe('toSyncSegments', () => {
  it('maps /v4/listen raw segments to the from-segments wire shape verbatim', () => {
    const segs: BackendSegment[] = [
      {
        id: 'a',
        text: 'hi',
        speaker: 'You',
        speaker_id: 0,
        is_user: true,
        person_id: 'p1',
        start: 0,
        end: 1.5
      }
    ]
    expect(toSyncSegments(segs)).toEqual([
      {
        text: 'hi',
        speaker: 'You',
        speaker_id: 0,
        is_user: true,
        person_id: 'p1',
        start: 0,
        end: 1.5
      }
    ])
  })

  it('nulls absent optional fields (never undefined — better-sqlite3 / the API reject it)', () => {
    const segs: BackendSegment[] = [{ text: 'x', is_user: false, start: 2, end: 3 }]
    expect(toSyncSegments(segs)).toEqual([
      {
        text: 'x',
        speaker: null,
        speaker_id: null,
        is_user: false,
        person_id: null,
        start: 2,
        end: 3
      }
    ])
  })
})

describe('segmentsToTranscript', () => {
  it('prefixes speakers and drops empties', () => {
    expect(
      segmentsToTranscript([
        { text: 'hello', speaker: 'You', is_user: true, start: 0, end: 1 },
        { text: 'there', is_user: false, start: 1, end: 2 }
      ])
    ).toBe('You: hello\nthere')
  })
})

describe('createSegmentRetainer', () => {
  it('appends new segments and upserts refinements by id (no duplication)', () => {
    const r = createSegmentRetainer()
    r.add([{ id: 'a', text: 'hel', is_user: true, start: 0, end: 1 }])
    r.add([{ id: 'b', text: 'world', is_user: false, start: 1, end: 2 }])
    // 'a' re-emitted refined — must replace in place, not append a second copy.
    r.add([{ id: 'a', text: 'hello', is_user: true, start: 0, end: 1.2 }])
    const out = r.list()
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ id: 'a', text: 'hello', end: 1.2 })
    expect(out[1]).toMatchObject({ id: 'b', text: 'world' })
  })

  it('keeps id-less segments as distinct appends', () => {
    const r = createSegmentRetainer()
    r.add([{ text: 'one', is_user: true, start: 0, end: 1 }])
    r.add([{ text: 'two', is_user: true, start: 1, end: 2 }])
    expect(r.list().map((s) => s.text)).toEqual(['one', 'two'])
  })
})
