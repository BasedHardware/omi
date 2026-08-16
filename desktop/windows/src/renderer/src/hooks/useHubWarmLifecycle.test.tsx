// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useHubWarmLifecycle } from './useHubWarmLifecycle'

const makeHub = (): { warm: ReturnType<typeof vi.fn>; teardown: ReturnType<typeof vi.fn> } => ({
  warm: vi.fn(),
  teardown: vi.fn()
})
type Gate = { ready: boolean; signedIn: boolean; hubEnabled: boolean }

describe('useHubWarmLifecycle — the pttHubEnabled opt-out contract', () => {
  it('warms exactly once when ready + signed-in + hubEnabled', () => {
    const hub = makeHub()
    renderHook(() => useHubWarmLifecycle(hub, { ready: true, signedIn: true, hubEnabled: true }))
    expect(hub.warm).toHaveBeenCalledTimes(1)
    expect(hub.teardown).not.toHaveBeenCalled()
  })

  it('OPT-OUT: flag off ⇒ never warms (no mint, no socket) and tears down', () => {
    const hub = makeHub()
    renderHook(() => useHubWarmLifecycle(hub, { ready: true, signedIn: true, hubEnabled: false }))
    expect(hub.warm).not.toHaveBeenCalled()
    expect(hub.teardown).toHaveBeenCalledTimes(1)
  })

  it('tears the live socket down when the flag toggles off at runtime', () => {
    const hub = makeHub()
    const { rerender } = renderHook((g: Gate) => useHubWarmLifecycle(hub, g), {
      initialProps: { ready: true, signedIn: true, hubEnabled: true }
    })
    expect(hub.warm).toHaveBeenCalledTimes(1)
    rerender({ ready: true, signedIn: true, hubEnabled: false })
    expect(hub.teardown).toHaveBeenCalledTimes(1)
  })

  it('tears down on sign-out', () => {
    const hub = makeHub()
    const { rerender } = renderHook((g: Gate) => useHubWarmLifecycle(hub, g), {
      initialProps: { ready: true, signedIn: true, hubEnabled: true }
    })
    rerender({ ready: true, signedIn: false, hubEnabled: true })
    expect(hub.teardown).toHaveBeenCalledTimes(1)
  })

  it('does not warm before ready (no mint before Firebase restores the session)', () => {
    const hub = makeHub()
    renderHook(() => useHubWarmLifecycle(hub, { ready: false, signedIn: true, hubEnabled: true }))
    expect(hub.warm).not.toHaveBeenCalled()
  })
})
