// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'
import { useRewind } from './useRewind'
import type { RewindFrame } from '../../../shared/types'
import { startOfLocalDay, endOfLocalDay } from '../lib/conversations/filtering'

function frame(ts: number, id: number): RewindFrame {
  return {
    id,
    ts,
    app: 'App',
    windowTitle: '',
    processName: '',
    ocrText: '',
    imagePath: '/x.jpg',
    width: 0,
    height: 0,
    indexed: 1
  }
}

const DAY = 86_400_000

let sampledCalls: Array<[number, number]>
let framesByDay: Map<number, RewindFrame[]>
// Optional per-day gate: when set, the sampled fetch for that day blocks until the
// promise resolves — lets a test force one day's load to land AFTER another's.
let gateByDay: Map<number, Promise<void>>

beforeEach(() => {
  sampledCalls = []
  framesByDay = new Map()
  gateByDay = new Map()
  const omi = {
    rewindFramesSampled: vi.fn(async (from: number, to: number) => {
      sampledCalls.push([from, to])
      const gate = gateByDay.get(startOfLocalDay(from))
      if (gate) await gate
      return framesByDay.get(startOfLocalDay(from)) ?? []
    }),
    rewindSearch: vi.fn(async () => []),
    onRewindSearchResults: vi.fn(() => () => {})
  }
  // @ts-expect-error partial bridge — only the methods useRewind touches are stubbed.
  window.omi = omi
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('useRewind day scoping', () => {
  it('loads today (down-sampled) on mount', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    const { result } = renderHook(() => useRewind())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.selectedDate).toBe(today)
    expect(result.current.isToday).toBe(true)
    // Loaded via the sampled range for today's local midnight → end of day.
    expect(sampledCalls[0]).toEqual([today, endOfLocalDay(today)])
  })

  // SHIPPED-BUG regression. Search "jump to result" used to call setCursorTs alone:
  // it never reloaded frames for the hit's day, so a hit outside the loaded window
  // landed on an EMPTY player. jumpTo must select the hit's DAY, load it, then seek.
  it('jumpTo an out-of-view day loads THAT day, then seeks to the exact moment', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    const threeDaysAgo = startOfLocalDay(Date.now() - 3 * DAY)
    const hitTs = threeDaysAgo + 5 * 3600_000 // 5am that day
    framesByDay.set(threeDaysAgo, [frame(threeDaysAgo + 1000, 10), frame(hitTs, 11)])

    const { result } = renderHook(() => useRewind())
    await waitFor(() => expect(result.current.loading).toBe(false))
    sampledCalls.length = 0

    act(() => result.current.jumpTo(hitTs))

    // The day containing the hit is loaded — the fix for the empty player.
    await waitFor(() =>
      expect(sampledCalls).toContainEqual([threeDaysAgo, endOfLocalDay(threeDaysAgo)])
    )
    await waitFor(() => expect(result.current.selectedDate).toBe(threeDaysAgo))
    // ...and the cursor lands on the exact hit moment, not the day's newest frame.
    await waitFor(() => expect(result.current.cursorTs).toBe(hitTs))
    expect(result.current.isToday).toBe(false)
  })

  // M1 regression — a tighter version of the same empty-player race bug #1 fixes.
  // A jumpTo(dayA) whose load is superseded by a move to dayB must NOT leave its stale
  // timestamp to be applied to dayB's timeline (which would seek dayB to a dayA moment
  // = an empty frame). Here dayA's load is gated to land AFTER dayB's, exercising the
  // ordering where the superseded-load early-return must not consume/clear the jump and
  // dayB's load must reject the day-mismatched jump.
  it('a superseded jump load never applies its stale timestamp to a newer day', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    const dayA = startOfLocalDay(Date.now() - 3 * DAY)
    const hitA = dayA + 5 * 3600_000
    const dayB = startOfLocalDay(Date.now() - 5 * DAY)
    const bNewest = dayB + 9 * 3600_000
    framesByDay.set(dayA, [frame(dayA + 1000, 10), frame(hitA, 11)])
    framesByDay.set(dayB, [frame(dayB + 1000, 20), frame(bNewest, 21)])

    const { result } = renderHook(() => useRewind())
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Hold dayA's fetch open so it resolves AFTER dayB's.
    let releaseA: () => void = () => {}
    gateByDay.set(dayA, new Promise<void>((r) => (releaseA = r)))

    act(() => result.current.jumpTo(hitA)) // pendingJump = hitA; dayA load starts (gated)
    await waitFor(() => expect(result.current.selectedDate).toBe(dayA))
    act(() => result.current.selectDate(dayB)) // supersede with dayB (ungated)
    await waitFor(() => expect(result.current.selectedDate).toBe(dayB))

    // dayB loaded and seeked to ITS newest frame — never to dayA's stale hit.
    await waitFor(() => expect(result.current.cursorTs).toBe(bNewest))

    // Now let dayA's superseded load finish: it must not touch the cursor.
    releaseA()
    await new Promise((r) => setTimeout(r, 0))
    expect(result.current.cursorTs).toBe(bNewest)
  })

  it('jumpTo within the loaded day just seeks — no reload', async () => {
    const today = startOfLocalDay(Date.now())
    const a = today + 1000
    const b = today + 9 * 3600_000
    framesByDay.set(today, [frame(a, 1), frame(b, 2)])
    const { result } = renderHook(() => useRewind())
    await waitFor(() => expect(result.current.loading).toBe(false))
    sampledCalls.length = 0

    act(() => result.current.jumpTo(b))

    await waitFor(() => expect(result.current.cursorTs).toBe(b))
    // Same day already in view → no additional day load.
    expect(sampledCalls).toHaveLength(0)
  })

  it('selectDate reloads only when the day actually changes', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    const { result } = renderHook(() => useRewind())
    await waitFor(() => expect(result.current.loading).toBe(false))
    sampledCalls.length = 0

    // Re-selecting the same day (a different ms within it) must NOT reload.
    act(() => result.current.selectDate(today + 12 * 3600_000))
    await Promise.resolve()
    expect(sampledCalls).toHaveLength(0)

    const yesterday = startOfLocalDay(Date.now() - DAY)
    framesByDay.set(yesterday, [frame(yesterday + 1000, 5)])
    act(() => result.current.selectDate(yesterday))
    await waitFor(() => expect(sampledCalls).toContainEqual([yesterday, endOfLocalDay(yesterday)]))
  })
})

// Idle-burn fix: the Rewind panel stays mounted-hidden behind the Home hub, so the
// silent 3s today-refresh must pause while the panel is off-screen (`active` false)
// and resume — resampling immediately so it isn't stale — the moment it is shown.
describe('useRewind today-refresh pauses while inactive', () => {
  const TODAY_REFRESH_MS = 3000 // mirrors the hook's silent-refresh cadence

  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('does NOT resample on the 3s cadence while the panel is hidden', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    renderHook(({ active }) => useRewind({ active }), { initialProps: { active: false } })
    // Flush the mount-time loadDay (runs regardless of visibility so the panel is
    // pre-populated for an instant first open).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    const afterMount = sampledCalls.length
    expect(afterMount).toBe(1)

    // Several refresh intervals elapse — none should fire while hidden.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TODAY_REFRESH_MS * 3)
    })
    expect(sampledCalls.length).toBe(afterMount)
  })

  it('resamples immediately on show, then resumes the 3s cadence', async () => {
    const today = startOfLocalDay(Date.now())
    framesByDay.set(today, [frame(today + 1000, 1)])
    const { rerender } = renderHook(({ active }) => useRewind({ active }), {
      initialProps: { active: false }
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    const afterMount = sampledCalls.length // 1 (mount load only; refresh paused)

    // Panel shown → one immediate resample so it reflects frames added while hidden.
    await act(async () => {
      rerender({ active: true })
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(sampledCalls.length).toBe(afterMount + 1)

    // Cadence resumed.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TODAY_REFRESH_MS)
    })
    expect(sampledCalls.length).toBe(afterMount + 2)

    // Hidden again → the interval is torn down (flush the re-render first so its
    // cleanup runs before time advances), so no further resamples fire.
    await act(async () => {
      rerender({ active: false })
    })
    const afterHide = sampledCalls.length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TODAY_REFRESH_MS * 2)
    })
    expect(sampledCalls.length).toBe(afterHide)
  })
})
