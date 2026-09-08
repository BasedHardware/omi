// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useWebglRecovery } from './useWebglRecovery'

// A cancelable WebGL context-loss event, like Chromium fires on a GPU-process
// crash. dispatchEvent returns false iff a handler called preventDefault.
function fireLost(canvas: HTMLCanvasElement): boolean {
  return !canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
}

describe('useWebglRecovery', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    cleanup()
  })

  it('remounts (bumps the key) after a debounce when the canvas loses its context', () => {
    const host = document.createElement('div')
    const canvas = document.createElement('canvas')
    host.appendChild(canvas)
    const ref = { current: host }

    const { result } = renderHook(() => useWebglRecovery(ref))
    expect(result.current).toBe(0)

    // Handler must preventDefault so the canvas element survives for the remount.
    let prevented = false
    act(() => {
      prevented = fireLost(canvas)
    })
    expect(prevented).toBe(true)

    // Debounced: no bump before the delay, one bump after.
    act(() => vi.advanceTimersByTime(500))
    expect(result.current).toBe(0)
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe(1)
  })

  it('caps remounts so recovery cannot become a remount storm', () => {
    const host = document.createElement('div')
    const canvas = document.createElement('canvas')
    host.appendChild(canvas)
    const ref = { current: host }

    const { result } = renderHook(() => useWebglRecovery(ref))

    // Fire far more losses than the cap; each remount is debounced separately.
    for (let i = 0; i < 8; i++) {
      act(() => {
        fireLost(canvas)
        vi.advanceTimersByTime(700)
      })
    }
    // Bounded to the max-in-window (4), not 8.
    expect(result.current).toBe(4)
  })

  it('also recovers from the main-process GPU-crash broadcast', () => {
    let broadcast: (() => void) | undefined
    const off = vi.fn()
    // @ts-expect-error jsdom has no window.omi; inject just the channel used here.
    window.omi = {
      onGpuContextLost: (cb: () => void) => {
        broadcast = cb
        return off
      }
    }

    const host = document.createElement('div')
    host.appendChild(document.createElement('canvas'))
    const ref = { current: host }
    const { result, unmount } = renderHook(() => useWebglRecovery(ref))

    expect(broadcast).toBeTypeOf('function')
    act(() => {
      broadcast?.()
      vi.advanceTimersByTime(700)
    })
    expect(result.current).toBe(1)

    unmount()
    expect(off).toHaveBeenCalled()
    // @ts-expect-error clean up the injected global
    delete window.omi
  })
})
