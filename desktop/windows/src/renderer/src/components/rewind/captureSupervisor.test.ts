import { describe, it, expect, vi } from 'vitest'
import { onCaptureStreamDeath } from './captureSupervisor'

// #10504: a capture track ending mid-session left the host sampling a dead
// <video> forever (blank/dark frames). These pin that a track `ended` is
// observed exactly once, and that unsubscribing before a deliberate stop
// silences it (so our own teardown never looks like a death).

class FakeTrack extends EventTarget {
  end(): void {
    this.dispatchEvent(new Event('ended'))
  }
}

function fakeStream(trackCount: number): { stream: MediaStream; tracks: FakeTrack[] } {
  const tracks = Array.from({ length: trackCount }, () => new FakeTrack())
  const stream = { getVideoTracks: () => tracks } as unknown as MediaStream
  return { stream, tracks }
}

describe('onCaptureStreamDeath', () => {
  it('fires onDeath when a video track ends', () => {
    const { stream, tracks } = fakeStream(1)
    const onDeath = vi.fn()
    onCaptureStreamDeath(stream, onDeath)

    tracks[0].end()

    expect(onDeath).toHaveBeenCalledTimes(1)
  })

  it('fires at most once even if multiple tracks end', () => {
    const { stream, tracks } = fakeStream(2)
    const onDeath = vi.fn()
    onCaptureStreamDeath(stream, onDeath)

    tracks[0].end()
    tracks[1].end()

    expect(onDeath).toHaveBeenCalledTimes(1)
  })

  it('does not fire after unsubscribe (a deliberate stop is not a death)', () => {
    const { stream, tracks } = fakeStream(1)
    const onDeath = vi.fn()
    const unsubscribe = onCaptureStreamDeath(stream, onDeath)

    unsubscribe()
    tracks[0].end()

    expect(onDeath).not.toHaveBeenCalled()
  })
})
