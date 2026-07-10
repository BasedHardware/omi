import { describe, expect, it } from 'vitest'
import { createSegmentStore } from './segmentRetention'
import type { BackendSegment } from '../../../../shared/types'

const T0 = 1_000_000 // session start, epoch ms

function seg(p: Partial<BackendSegment> & { text: string }): BackendSegment {
  return { is_user: true, start: 0, end: 1, ...p }
}

describe('createSegmentStore (wall-clock stamping)', () => {
  it('anchors a batch so its latest stream end maps to the arrival offset', () => {
    const store = createSegmentStore(T0)
    // Two segments, stream 0→1s and 1→2.5s, arriving 5s into the session.
    store.add(
      [seg({ id: 'a', text: 'one', start: 0, end: 1 }), seg({ id: 'b', text: 'two', start: 1, end: 2.5 })],
      T0 + 5_000
    )
    const [a, b] = store.list()
    expect(a.start).toBeCloseTo(2.5) // 5 - (2.5 - 0)
    expect(a.end).toBeCloseTo(3.5) // 5 - (2.5 - 1)
    expect(b.start).toBeCloseTo(3.5)
    expect(b.end).toBeCloseTo(5)
  })

  it('silence compression: a burst after 30s of silence lands at ~30s wall-clock, not stream time', () => {
    const store = createSegmentStore(T0)
    store.add([seg({ id: 'a', text: 'first', start: 0, end: 2 })], T0 + 3_000)
    // The stream clock only advanced to 2→4s (VAD dropped the silence), but the
    // batch arrives 40s into the session.
    store.add([seg({ id: 'b', text: 'after the gap', start: 2, end: 4 })], T0 + 40_000)
    const [, b] = store.list()
    expect(b.start).toBeCloseTo(38) // 40 - (4 - 2), NOT 2
    expect(b.end).toBeCloseTo(40)
  })

  it('upserts a re-emitted segment id: text refreshes, wall-clock start is preserved', () => {
    const store = createSegmentStore(T0)
    store.add([seg({ id: 'a', text: 'hel', start: 0, end: 1 })], T0 + 2_000)
    const before = store.list()[0]
    store.add([seg({ id: 'a', text: 'hello world', start: 0, end: 3 })], T0 + 6_000)
    const list = store.list()
    expect(list).toHaveLength(1)
    expect(list[0].text).toBe('hello world')
    expect(list[0].start).toBeCloseTo(before.start) // NOT re-stamped to the refinement's arrival
    expect(list[0].end).toBeCloseTo(before.start + 3) // duration extended to the stream's
  })

  it('clamps to non-negative and keeps starts monotonic across batches', () => {
    const store = createSegmentStore(T0)
    // 5s of stream audio arriving only 1s in: anchor math would go negative.
    store.add([seg({ id: 'a', text: 'early', start: 0, end: 5 })], T0 + 1_000)
    expect(store.list()[0].start).toBe(0)
    // A later batch whose anchor math lands BEFORE the previous start is floored.
    store.add([seg({ id: 'b', text: 'later', start: 0, end: 60 })], T0 + 2_000)
    const [a, b] = store.list()
    expect(b.start).toBeGreaterThanOrEqual(a.start)
    expect(b.end).toBeGreaterThanOrEqual(b.start)
  })

  it('keeps intra-batch ordering by stream timestamps and retains speaker fields', () => {
    const store = createSegmentStore(T0)
    store.add(
      [
        seg({ id: 'b', text: 'second', start: 3, end: 4, is_user: false, speaker_id: 1, speaker: 'SPEAKER_1' }),
        seg({ id: 'a', text: 'first', start: 0, end: 2, person_id: 'p-9' })
      ],
      T0 + 10_000
    )
    const list = store.list()
    expect(list.map((s) => s.text)).toEqual(['first', 'second'])
    expect(list[0].person_id).toBe('p-9')
    expect(list[1].speaker_id).toBe(1)
    expect(list[1].is_user).toBe(false)
    expect(list[1].speaker).toBe('SPEAKER_1')
  })

  it('list() returns copies — callers cannot corrupt the store', () => {
    const store = createSegmentStore(T0)
    store.add([seg({ id: 'a', text: 'x' })], T0 + 1_000)
    store.list()[0].text = 'mutated'
    expect(store.list()[0].text).toBe('x')
  })
})
