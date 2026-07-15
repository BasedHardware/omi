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

beforeEach(() => {
  sampledCalls = []
  framesByDay = new Map()
  const omi = {
    rewindFramesSampled: vi.fn(async (from: number, to: number) => {
      sampledCalls.push([from, to])
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
