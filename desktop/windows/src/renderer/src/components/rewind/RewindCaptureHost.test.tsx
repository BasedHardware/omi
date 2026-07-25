// @vitest-environment jsdom
//
// #10504: after hours of capture the Windows timeline filled with blank frames.
// The host opens ONE persistent desktop stream; when that track dies (display
// sleep, GPU/driver reset, session change) nothing noticed — the sampler kept
// drawing a dead <video> and saving frames from it, and capture never recovered.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import { RewindCaptureHost } from './RewindCaptureHost'

const INTERVAL_MS = 1000
const RESTART_DELAY_MS = 2000

class FakeTrack extends EventTarget {
  readyState: 'live' | 'ended' = 'live'
  stop(): void {
    this.readyState = 'ended'
  }
  /** What the OS does when the capture source goes away (NOT our own stop()). */
  die(): void {
    this.readyState = 'ended'
    this.dispatchEvent(new Event('ended'))
  }
}

function fakeStream(track: FakeTrack): MediaStream {
  return {
    getTracks: () => [track],
    getVideoTracks: () => [track]
  } as unknown as MediaStream
}

let tracks: FakeTrack[] = []
let getUserMedia: ReturnType<typeof vi.fn>
let saveFrame: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  tracks = []
  saveFrame = vi.fn(async () => undefined)
  getUserMedia = vi.fn(async () => {
    const t = new FakeTrack()
    tracks.push(t)
    return fakeStream(t)
  })
  ;(navigator as unknown as { mediaDevices: unknown }).mediaDevices = { getUserMedia }
  ;(window as unknown as { omi: unknown }).omi = {
    rewindGetSettings: async () => ({ captureEnabled: true, intervalMs: INTERVAL_MS }),
    onRewindSettings: () => () => undefined,
    rewindGetCaptureDirective: async () => ({ paused: false, intervalMs: INTERVAL_MS }),
    onRewindCaptureDirective: () => () => undefined,
    rewindPrimarySourceId: async () => 'screen:0:0',
    rewindSaveFrame: saveFrame
  }
  // jsdom has no media pipeline or 2D canvas: give the host a video that reports
  // a frame size and a canvas that encodes, so the sampling path can run.
  HTMLMediaElement.prototype.play = vi.fn(async () => undefined)
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', {
    configurable: true,
    get: () => 1280
  })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', {
    configurable: true,
    get: () => 720
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn()
  } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb) =>
    cb({ arrayBuffer: async () => new ArrayBuffer(8) } as Blob)
  )
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  delete (window as unknown as { omi?: unknown }).omi
})

/** Let the mount's awaited settings/directive/getUserMedia promises settle. */
async function settle(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('RewindCaptureHost — dead capture track', () => {
  it('stops saving frames and reopens the stream when the capture track dies', async () => {
    render(<RewindCaptureHost />)
    await settle()
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    // Baseline: a live track produces frames.
    await tick(INTERVAL_MS)
    expect(saveFrame).toHaveBeenCalledTimes(1)

    // The OS kills the capture source.
    saveFrame.mockClear()
    await act(async () => {
      tracks[0].die()
    })

    // No blank frames from the dead <video> while the stream is down...
    await tick(INTERVAL_MS)
    expect(saveFrame).not.toHaveBeenCalled()

    // ...and capture comes back on its own.
    await tick(RESTART_DELAY_MS)
    expect(getUserMedia).toHaveBeenCalledTimes(2)
    expect(tracks[1].readyState).toBe('live')
    saveFrame.mockClear()
    await tick(INTERVAL_MS)
    expect(saveFrame).toHaveBeenCalled()
  })

  it('keeps a single sampling loop when the track dies mid-save', async () => {
    // A save is an IPC round-trip, so over hours the track often dies while one is
    // in flight. That grab must not reschedule itself after the recovery tore the
    // stream down, or every recovery leaves an extra loop sampling in parallel.
    let releaseSave: () => void = () => undefined
    saveFrame.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          releaseSave = () => resolve()
        })
    )
    render(<RewindCaptureHost />)
    await settle()

    await tick(INTERVAL_MS)
    expect(saveFrame).toHaveBeenCalledTimes(1)

    // Track dies with that save still pending, then the save completes.
    await act(async () => {
      tracks[0].die()
    })
    await act(async () => {
      releaseSave()
    })

    await tick(RESTART_DELAY_MS)
    expect(getUserMedia).toHaveBeenCalledTimes(2)

    saveFrame.mockClear()
    await tick(INTERVAL_MS)
    expect(saveFrame).toHaveBeenCalledTimes(1)
  })

  it('does not reopen the stream after unmount', async () => {
    const view = render(<RewindCaptureHost />)
    await settle()
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    view.unmount()
    await tick(RESTART_DELAY_MS + INTERVAL_MS)
    expect(getUserMedia).toHaveBeenCalledTimes(1)
    expect(saveFrame).not.toHaveBeenCalled()
  })
})
