// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useIsVisible } from './useIsVisible'

// Controllable IntersectionObserver stub: captures the callback so a test can
// drive intersecting true/false, and records observe/disconnect.
let ioCallback: ((entries: Array<{ isIntersecting: boolean }>) => void) | null
let disconnected: number

class StubIO {
  constructor(cb: (entries: Array<{ isIntersecting: boolean }>) => void) {
    ioCallback = cb
  }
  observe(): void {
    /* no-op stub */
  }
  unobserve(): void {
    /* no-op stub */
  }
  disconnect(): void {
    disconnected += 1
  }
}

beforeEach(() => {
  ioCallback = null
  disconnected = 0
  vi.stubGlobal('IntersectionObserver', StubIO)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useIsVisible', () => {
  it('starts hidden and follows the observer: false → true → false', () => {
    const ref = { current: document.createElement('div') }
    const { result } = renderHook(() => useIsVisible(ref))

    // A mounted-hidden panel is off-screen until the observer says otherwise.
    expect(result.current).toBe(false)

    act(() => ioCallback?.([{ isIntersecting: true }]))
    expect(result.current).toBe(true)

    act(() => ioCallback?.([{ isIntersecting: false }]))
    expect(result.current).toBe(false)
  })

  it('disconnects the observer on unmount', () => {
    const ref = { current: document.createElement('div') }
    const { unmount } = renderHook(() => useIsVisible(ref))
    expect(disconnected).toBe(0)
    unmount()
    expect(disconnected).toBe(1)
  })

  it('fails open (returns true) where IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const ref = { current: document.createElement('div') }
    const { result } = renderHook(() => useIsVisible(ref))
    // No observer to report visibility → gated work must run, not be suppressed.
    expect(result.current).toBe(true)
  })
})
