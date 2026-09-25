// @vitest-environment jsdom
// The window-focus refetch throttle. Three always-mounted surfaces (Memories, Apps,
// Home goal chips) revalidate on focus, and the app blurs its own main window every
// time the bar/orb/capture window takes focus — so before the throttle, ordinary voice
// use re-issued six-plus backend requests per interaction, including a full
// `/v3/memories` page-through for a page that was not even on screen.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { FOCUS_REFETCH_MIN_INTERVAL_MS, useThrottledWindowFocus } from './focusRefetch'

const focus = (): void => {
  window.dispatchEvent(new Event('focus'))
}

beforeEach(() => {
  vi.useFakeTimers()
  // A realistic wall clock. The hook uses 0 as its "never run" sentinel, so a 1970
  // clock would make a genuine run indistinguishable from never having run.
  vi.setSystemTime(1_700_000_000_000)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useThrottledWindowFocus', () => {
  it('collapses a burst of focus events into a single run', () => {
    const handler = vi.fn()
    renderHook(() => useThrottledWindowFocus(handler))

    // Alt-tabbing between the main window and the floating bar, five times, fast.
    for (let i = 0; i < 5; i++) {
      focus()
      vi.advanceTimersByTime(200)
    }
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('runs again once the interval has genuinely elapsed', () => {
    const handler = vi.fn()
    renderHook(() => useThrottledWindowFocus(handler))

    focus()
    expect(handler).toHaveBeenCalledTimes(1)

    // One millisecond short: still throttled. This is the assertion that fails if the
    // comparison is flipped or the interval is dropped to zero.
    vi.advanceTimersByTime(FOCUS_REFETCH_MIN_INTERVAL_MS - 1)
    focus()
    expect(handler).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(1)
    focus()
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it('always runs the first focus of a session', () => {
    // Revalidating on focus is the behavior these surfaces promise (a goal completed
    // in another window shows up when you come back). The throttle only drops the
    // repeats — deferring the first one would be a behavior change, not a cost fix.
    // Memories.focusRefresh and Apps.focusRefresh assert this from the page side.
    const handler = vi.fn()
    renderHook(() => useThrottledWindowFocus(handler))
    focus()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('honors a caller-supplied interval', () => {
    const handler = vi.fn()
    renderHook(() => useThrottledWindowFocus(handler, 5_000))

    focus()
    focus()
    expect(handler).toHaveBeenCalledTimes(1) // second one throttled

    vi.advanceTimersByTime(5_000)
    focus()
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it('re-renders resubscribe the listener without disturbing the throttle window', () => {
    // Call sites pass a NEW closure every render (they close over loading/refresh), so
    // the effect really does tear down and re-add the listener constantly. Wrapping
    // the spy in a fresh arrow here reproduces that; passing the spy directly would
    // keep the dep stable and never exercise a resubscribe at all.
    const handler = vi.fn()
    const { rerender } = renderHook(({ fn }) => useThrottledWindowFocus(() => fn()), {
      initialProps: { fn: handler }
    })

    focus()
    expect(handler).toHaveBeenCalledTimes(1)

    // A re-render mid-window must not REOPEN the window.
    vi.advanceTimersByTime(1_000)
    rerender({ fn: handler })
    focus()
    expect(handler).toHaveBeenCalledTimes(1)

    // ...and must not EXTEND it either. A surface that re-renders faster than the
    // interval would otherwise stop revalidating on focus entirely.
    for (let i = 0; i < 6; i++) {
      vi.advanceTimersByTime(10_000)
      rerender({ fn: handler })
    }
    focus()
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it('stops listening once unmounted', () => {
    const handler = vi.fn()
    const { unmount } = renderHook(() => useThrottledWindowFocus(handler))
    unmount()
    focus()
    expect(handler).not.toHaveBeenCalled()
  })
})
