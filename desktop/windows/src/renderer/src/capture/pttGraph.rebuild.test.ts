import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Capture-graph rebuild ladder + device-change handling (A7a). The warm mic graph
// is torn down + reopened after a 0.3s settle, retrying at linear 1s/2s/3s backoff
// (4 attempts) before giving up. acquireMicStream / AudioContext / navigator are
// faked so the ladder timing, telemetry, overlap-guard, and device-change wiring
// are exercised without a real mic. pttGraph is a module singleton, so each test
// re-imports it fresh (vi.resetModules) for isolated state.

const h = vi.hoisted(() => ({
  acquire: vi.fn(),
  teardown: vi.fn(),
  trackEvent: vi.fn()
}))

vi.mock('../lib/audio', () => ({
  acquireMicStream: h.acquire,
  teardownAudioGraph: h.teardown,
  floatTo16BitPCM: (f: Float32Array) => new Int16Array(f.length)
}))
vi.mock('../lib/analytics', () => ({ trackEvent: h.trackEvent }))

// Minimal Web-Audio graph the createGraph() path touches.
class FakeAudioContext {
  destination = {}
  createMediaStreamSource(): { connect: () => void } {
    return { connect: () => {} }
  }
  createAnalyser(): Record<string, unknown> {
    return {
      connect: () => {},
      fftSize: 0,
      smoothingTimeConstant: 0,
      frequencyBinCount: 16,
      getByteFrequencyData: () => {}
    }
  }
  createScriptProcessor(): { connect: () => void; onaudioprocess: unknown } {
    return { connect: () => {}, onaudioprocess: null }
  }
}

let deviceListeners: Array<() => void>
const fireDeviceChange = (): void => deviceListeners.slice().forEach((cb) => cb())

const fakeStream = { getTracks: () => [] } as unknown as MediaStream

type PttGraph = typeof import('./pttGraph')
async function freshModule(): Promise<PttGraph> {
  vi.resetModules()
  return await import('./pttGraph')
}

beforeEach(() => {
  vi.useFakeTimers()
  h.acquire.mockReset().mockResolvedValue(fakeStream)
  h.teardown.mockReset()
  h.trackEvent.mockReset()
  deviceListeners = []
  // navigator is a getter-only global in Node — stub both via vitest.
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('navigator', {
    mediaDevices: {
      addEventListener: vi.fn((type: string, cb: () => void) => {
        if (type === 'devicechange') deviceListeners.push(cb)
      }),
      removeEventListener: vi.fn((type: string, cb: () => void) => {
        if (type === 'devicechange') deviceListeners = deviceListeners.filter((x) => x !== cb)
      })
    }
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('rebuildWarmGraph — retry ladder', () => {
  it('settles 0.3s, rebuilds once, and reports recovered on first success', async () => {
    const mod = await freshModule()
    await mod.warmPttMic() // establishes the warm graph (1 acquire)
    h.acquire.mockClear()
    h.trackEvent.mockClear()

    mod.rebuildWarmGraph('device_changed', true)
    expect(h.acquire).not.toHaveBeenCalled() // still inside the settle window

    await vi.advanceTimersByTimeAsync(300)
    expect(h.acquire).toHaveBeenCalledTimes(1) // one attempt, succeeds
    expect(h.trackEvent).toHaveBeenCalledTimes(1)
    expect(h.trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'ptt_capture',
      from: 'default_device',
      to: 'rebuilt',
      reason: 'device_changed',
      outcome: 'recovered'
    })
  })

  it('retries at 1s/2s/3s backoff and reports exhausted after 4 failures', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    h.acquire.mockClear().mockRejectedValue(new Error('device gone'))
    h.trackEvent.mockClear()

    mod.rebuildWarmGraph('device_changed', true)

    await vi.advanceTimersByTimeAsync(300) // settle → attempt 1 fails
    expect(h.acquire).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000) // attempt 2 fails
    expect(h.acquire).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2000) // attempt 3 fails
    expect(h.acquire).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(3000) // attempt 4 fails → give up
    expect(h.acquire).toHaveBeenCalledTimes(4)

    expect(h.trackEvent).toHaveBeenCalledTimes(1)
    expect(h.trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'ptt_capture',
      from: 'default_device',
      to: 'none',
      reason: 'device_changed',
      outcome: 'exhausted'
    })
  })

  it('stops early — a mid-ladder success emits recovered and no further retries', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    h.acquire
      .mockClear()
      .mockRejectedValueOnce(new Error('gone')) // attempt 1 fails
      .mockResolvedValue(fakeStream) // attempt 2 succeeds
    h.trackEvent.mockClear()

    mod.rebuildWarmGraph('device_changed', true)
    await vi.advanceTimersByTimeAsync(300) // attempt 1
    await vi.advanceTimersByTimeAsync(1000) // attempt 2 → success
    expect(h.acquire).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(5000) // no further attempts scheduled
    expect(h.acquire).toHaveBeenCalledTimes(2)
    expect(h.trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ outcome: 'recovered' })
    )
  })

  it('guards against overlapping rebuilds', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    h.acquire.mockClear()

    mod.rebuildWarmGraph('device_changed', true)
    mod.rebuildWarmGraph('device_changed', true) // ignored — a ladder is running
    await vi.advanceTimersByTimeAsync(300)
    expect(h.acquire).toHaveBeenCalledTimes(1)
  })

  it('is a no-op when there is no warm graph to rebuild', async () => {
    const mod = await freshModule()
    // never warmed
    mod.rebuildWarmGraph('device_changed', true)
    await vi.advanceTimersByTimeAsync(300)
    expect(h.acquire).not.toHaveBeenCalled()
    expect(h.trackEvent).not.toHaveBeenCalled()
  })

  it('does not emit telemetry on the silent-mic path (hook owns it)', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    h.acquire.mockClear()
    h.trackEvent.mockClear()

    mod.rebuildWarmGraph('silent_mic', false)
    await vi.advanceTimersByTimeAsync(300)
    expect(h.acquire).toHaveBeenCalledTimes(1) // rebuild still ran
    expect(h.trackEvent).not.toHaveBeenCalled() // but no ptt_capture event
  })
})

describe('device-change handling (A7a)', () => {
  it('registers via addEventListener so it coexists with the headset listener', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    expect(navigator.mediaDevices.addEventListener).toHaveBeenCalledWith(
      'devicechange',
      expect.any(Function)
    )
    // Never clobbers the shared ondevicechange property voiceController may use.
    expect(
      (navigator.mediaDevices as unknown as { ondevicechange?: unknown }).ondevicechange
    ).toBeUndefined()
  })

  it('a burst of device-change events triggers exactly one rebuild', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    h.acquire.mockClear()
    h.trackEvent.mockClear()

    fireDeviceChange()
    fireDeviceChange()
    fireDeviceChange()
    await vi.advanceTimersByTimeAsync(300)

    expect(h.acquire).toHaveBeenCalledTimes(1) // debounced by the settle + guard
    expect(h.trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ component: 'ptt_capture', outcome: 'recovered' })
    )
  })

  it('removes the listener when the warm graph is released', async () => {
    const mod = await freshModule()
    await mod.warmPttMic()
    mod.releasePttMic()
    expect(navigator.mediaDevices.removeEventListener).toHaveBeenCalledWith(
      'devicechange',
      expect.any(Function)
    )
    expect(deviceListeners).toHaveLength(0)
  })
})

describe('rebuild safety — never yanks an active hold', () => {
  it('defers when a hold is already attached, then runs on detach', async () => {
    const mod = await freshModule()
    await mod.warmPttMic() // warm graph (acquire 1)
    const cap = await mod.startPttCapture({}) // hold attaches (attachedCaptures = 1)
    h.acquire.mockClear()
    h.teardown.mockClear()

    mod.rebuildWarmGraph('device_changed', true) // up-front guard defers (hold active)
    await vi.advanceTimersByTimeAsync(300)
    // The live graph must NOT be torn down while the hold holds it.
    expect(h.teardown).not.toHaveBeenCalled()
    expect(h.acquire).not.toHaveBeenCalled()

    cap.dispose() // detach → runs the deferred rebuild
    await vi.advanceTimersByTimeAsync(300)
    expect(h.teardown).toHaveBeenCalled() // old graph destroyed now (hold gone)
    expect(h.acquire).toHaveBeenCalledTimes(1) // new graph acquired
    expect(h.trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ outcome: 'recovered' })
    )
  })

  it('does not tear down a hold that attaches DURING the settle window (race)', async () => {
    const mod = await freshModule()
    await mod.warmPttMic() // warm graph (acquire 1)
    h.acquire.mockClear()
    h.teardown.mockClear()

    // Rebuild scheduled while nothing is attached (guard passes), THEN a hold
    // attaches before the settle timer fires — the regression the fix closes.
    mod.rebuildWarmGraph('device_changed', true)
    const cap = await mod.startPttCapture({}) // attaches mid-settle (attachedCaptures = 1)

    await vi.advanceTimersByTimeAsync(300) // settle fires attemptRebuild
    // attemptRebuild must re-check attachedCaptures and defer — NOT destroy the
    // graph the active capture is reading from.
    expect(h.teardown).not.toHaveBeenCalled()
    expect(h.acquire).not.toHaveBeenCalled()

    cap.dispose() // detach → deferred rebuild now runs safely
    await vi.advanceTimersByTimeAsync(300)
    expect(h.teardown).toHaveBeenCalled()
    expect(h.acquire).toHaveBeenCalledTimes(1)
  })
})
