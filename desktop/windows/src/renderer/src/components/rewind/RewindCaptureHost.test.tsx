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
})

// #10489: every frame was captured at 720p and encoded at 0.6 no matter the
// display, so OCR could not read normal on-screen text — and nothing in the app
// could raise it. Quality is now a setting, and each tier has to reach the
// stream, the sampled canvas AND the encode to be worth anything.
describe('RewindCaptureHost — capture quality', () => {
  /** Sample a 1440p display, so a tier that downscales is visible in the canvas. */
  function displayIs1440p(): void {
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', {
      configurable: true,
      get: () => 2560
    })
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', {
      configurable: true,
      get: () => 1440
    })
  }

  function setQuality(captureQuality: string): void {
    ;(
      window as unknown as { omi: { rewindGetSettings: () => Promise<unknown> } }
    ).omi.rewindGetSettings = async () => ({
      captureEnabled: true,
      intervalMs: INTERVAL_MS,
      captureQuality
    })
  }

  /** The stream constraints of the nth getUserMedia call. */
  function constraints(call: number): { maxWidth: number; maxHeight: number } {
    return (
      getUserMedia.mock.calls[call][0] as {
        video: { mandatory: { maxWidth: number; maxHeight: number } }
      }
    ).video.mandatory
  }

  /** Canvas size + JPEG quality of each encode. */
  let encodes: { width: number; height: number; quality: number }[]
  beforeEach(() => {
    encodes = []
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (
      this: HTMLCanvasElement,
      cb,
      _type,
      quality
    ) {
      encodes.push({ width: this.width, height: this.height, quality: quality as number })
      cb({ arrayBuffer: async () => new ArrayBuffer(8) } as Blob)
    })
  })

  it('defaults to the proven 720p tier when no quality is persisted', async () => {
    displayIs1440p()
    render(<RewindCaptureHost />)
    await settle()
    await tick(INTERVAL_MS)

    expect(constraints(0)).toMatchObject({ maxWidth: 1280, maxHeight: 720 })
    expect(encodes[0]).toEqual({ width: 1600, height: 900, quality: 0.6 })
  })

  it('captures a 1440p display at full size and a higher JPEG quality on "max"', async () => {
    displayIs1440p()
    setQuality('max')
    render(<RewindCaptureHost />)
    await settle()
    await tick(INTERVAL_MS)

    expect(constraints(0)).toMatchObject({ maxWidth: 2560, maxHeight: 1440 })
    // Not downscaled by the sampler either — the whole point is readable text.
    expect(encodes[0]).toEqual({ width: 2560, height: 1440, quality: 0.82 })
  })

  it('raises the stream to 1080p on "high"', async () => {
    setQuality('high')
    render(<RewindCaptureHost />)
    await settle()

    expect(constraints(0)).toMatchObject({ maxWidth: 1920, maxHeight: 1080 })
  })

  it('re-opens the stream when the quality setting changes', async () => {
    // Resolution is a stream constraint, so a live change has to tear the stream
    // down — otherwise the new tier would only apply at the next launch.
    let push: (s: unknown) => void = () => undefined
    ;(
      window as unknown as { omi: { onRewindSettings: (cb: (s: unknown) => void) => () => void } }
    ).omi.onRewindSettings = (cb) => {
      push = cb
      return () => undefined
    }
    render(<RewindCaptureHost />)
    await settle()
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    await act(async () => {
      push({ captureEnabled: true, intervalMs: INTERVAL_MS, captureQuality: 'high' })
    })
    await settle()

    expect(getUserMedia).toHaveBeenCalledTimes(2)
    expect(constraints(1)).toMatchObject({ maxWidth: 1920, maxHeight: 1080 })
  })

  it('falls back to the default tier for an unknown persisted value', async () => {
    setQuality('ultra')
    render(<RewindCaptureHost />)
    await settle()

    expect(constraints(0)).toMatchObject({ maxWidth: 1280, maxHeight: 720 })
  })
})

describe('RewindCaptureHost — unmount', () => {
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
