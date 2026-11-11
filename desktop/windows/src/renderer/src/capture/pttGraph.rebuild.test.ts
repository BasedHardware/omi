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

describe('rebuild ↔ warm race — no orphaned graph under PTT stress', () => {
  // A key-down calls touchMic() → warmPttMic() on every press. If one lands while a
  // rebuild ladder (device-change A7a / silent-mic A7b) is mid-createGraph — warmGraph
  // momentarily null, reconfiguring true — warmPttMic must NOT start a second,
  // competing createGraph. If it does, whichever resolves last wins warmGraph and the
  // other graph is orphaned: a live mic stream + AudioContext + ScriptProcessorNode
  // that is never torn down. Under PTT stress those leaked capture graphs accumulate
  // and crash the audio service.
  it('a key-down warm during the rebuild createGraph does not leak a second graph', async () => {
    const mod = await freshModule()

    // Deferred acquire: each createGraph parks on its own resolver, so we can hold the
    // rebuild's createGraph in flight and slip a warmPttMic() (a key-down) in beside it.
    const resolvers: Array<() => void> = []
    h.acquire.mockReset().mockImplementation(
      () =>
        new Promise<MediaStream>((resolve) => {
          resolvers.push(() => resolve({ getTracks: () => [] } as unknown as MediaStream))
        })
    )
    const settleOne = async (): Promise<void> => {
      const r = resolvers.shift()
      if (!r) return
      r()
      // Flush createGraph's continuation + the awaiting caller's continuation.
      for (let i = 0; i < 8; i++) await Promise.resolve()
    }

    // 1) Warm the mic → first graph G1.
    const warm1 = mod.warmPttMic()
    await settleOne()
    await warm1

    // 2) Rebuild: after the 0.3s settle it tears down G1 and parks on createGraph.
    mod.rebuildWarmGraph('silent_mic', false)
    await vi.advanceTimersByTimeAsync(300)
    expect(h.teardown).toHaveBeenCalledTimes(1) // G1 gone; rebuild awaiting acquire

    // 3) A key-down warms the mic WHILE the rebuild's createGraph is still in flight.
    const warm2 = mod.warmPttMic()

    // 4) Resolve every in-flight acquire and let all chains settle.
    while (resolvers.length) await settleOne()
    await warm2

    // Exactly one live warm graph must remain: every graph created is either the
    // current warm graph or was torn down. A leak shows up as acquires outrunning
    // teardowns by more than one.
    const live = h.acquire.mock.calls.length - h.teardown.mock.calls.length
    expect(live).toBe(1)
  })
})

describe('orb AGC-free tap — never gates capture readiness', () => {
  // The tap (attachOrbTap) is a fire-and-forget visual upgrade. The regression
  // this guards: an awaited tap acquire put a second getUserMedia on the
  // capture-readiness critical path — a driver wedged on the concurrent
  // same-device open would have hung warm/capture forever.
  const tapCapableStream = (): MediaStream =>
    ({
      getTracks: () => [],
      getAudioTracks: () => [{ getSettings: () => ({ deviceId: 'default', groupId: 'g1' }) }]
    }) as unknown as MediaStream

  it('warm + capture complete while the tap getUserMedia is still PENDING; a late resolve after timeout is stopped, not leaked', async () => {
    let resolveTap: ((s: MediaStream) => void) | undefined
    const getUserMedia = vi.fn(
      () =>
        new Promise<MediaStream>((resolve) => {
          resolveTap = resolve
        })
    )
    vi.stubGlobal('navigator', {
      mediaDevices: {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        enumerateDevices: vi.fn(async () => []),
        getUserMedia
      }
    })
    h.acquire.mockReset().mockResolvedValue(tapCapableStream())

    const mod = await freshModule()
    await mod.warmPttMic() // must resolve with the tap acquire parked forever
    const cap = await mod.startPttCapture({}) // capture attaches on the fallback wiring
    expect(cap).toBeTruthy()
    // The tap attempt WAS made (async, off the critical path) and is still pending.
    await vi.advanceTimersByTimeAsync(0)
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    // The timeout converts the hang into the loud fallback…
    await vi.advanceTimersByTimeAsync(3000)
    // …and a LATE resolution of the wedged open is stopped, never leaked.
    const stop = vi.fn()
    resolveTap!({
      getTracks: () => [{ stop }],
      getAudioTracks: () => [{ getSettings: () => ({}) }]
    } as unknown as MediaStream)
    await vi.advanceTimersByTimeAsync(0)
    expect(stop).toHaveBeenCalled()

    cap.dispose()
  })

  it('a tap resolving after the graph was destroyed discards itself (no live mic left behind)', async () => {
    let resolveTap: ((s: MediaStream) => void) | undefined
    vi.stubGlobal('navigator', {
      mediaDevices: {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        enumerateDevices: vi.fn(async () => []),
        getUserMedia: vi.fn(
          () =>
            new Promise<MediaStream>((resolve) => {
              resolveTap = resolve
            })
        )
      }
    })
    h.acquire.mockReset().mockResolvedValue(tapCapableStream())

    const mod = await freshModule()
    await mod.warmPttMic()
    await vi.advanceTimersByTimeAsync(0) // let attachOrbTap reach the acquire await
    mod.releasePttMic() // destroys the warm graph while the tap is in flight

    const stop = vi.fn()
    resolveTap!({
      getTracks: () => [{ stop }],
      getAudioTracks: () => [{ getSettings: () => ({ autoGainControl: false }) }]
    } as unknown as MediaStream)
    await vi.advanceTimersByTimeAsync(0)
    expect(stop).toHaveBeenCalled()
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
