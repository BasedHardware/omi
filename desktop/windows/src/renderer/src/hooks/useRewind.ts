import { useCallback, useEffect, useRef, useState } from 'react'
import type { RewindFrame, RewindSearchGroup } from '../../../shared/types'
import { startOfLocalDay, endOfLocalDay } from '../lib/conversations/filtering'

// macOS parity: only "today" auto-refreshes, and silently — every 3.0s, never
// touching the loading state and republishing only when the frame set actually
// changed, so a live capture never destroys scrub position or a typed note.
const TODAY_REFRESH_MS = 3000

export type RewindState = {
  frames: RewindFrame[]
  bounds: { min: number; max: number } | null
  /** Local-midnight ms of the day currently in view. */
  selectedDate: number
  /** True when `selectedDate` is today (drives the silent auto-refresh + live edge). */
  isToday: boolean
  /** Jump the timeline to a whole day (local-midnight ms of any moment in it).
   *  Reloads only when the day actually changes. */
  selectDate: (dayMs: number) => void
  /** Jump to a specific moment — loads that moment's DAY first if it isn't the one
   *  in view, THEN seeks. This is the shipped search "jump to result" fix: seeking
   *  alone left the player empty whenever the hit fell outside the loaded window. */
  jumpTo: (ts: number) => void
  loading: boolean
  cursorTs: number
  setCursorTs: (ts: number) => void
  playing: boolean
  setPlaying: (p: boolean) => void
  results: RewindSearchGroup[]
  search: (q: string) => Promise<void>
}

/** Same frames, by id, in the same order — the "did the day actually change" test
 *  the silent today-refresh gates on (macOS compares the fetched id list). */
function sameFrameIds(a: RewindFrame[], b: RewindFrame[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i].id !== b[i].id) return false
  return true
}

// The Rewind panel stays mounted-hidden behind the Home hub (layout/MainViews.tsx),
// so `active` lets the page pause the silent today-refresh while it is off-screen —
// otherwise the 3s resample keeps hitting the frames DB (and, because live capture
// is always adding frames, re-rendering the whole hidden Rewind subtree) for a view
// nobody is looking at. Defaults to true so every other caller (and the tests) keep
// the always-refreshing behavior; the page flips it from useIsVisible.
export function useRewind({ active = true }: { active?: boolean } = {}): RewindState {
  const [selectedDate, setSelectedDate] = useState(() => startOfLocalDay(Date.now()))
  const [frames, setFrames] = useState<RewindFrame[]>([])
  const [loading, setLoading] = useState(true)
  const [cursorTs, setCursorTs] = useState<number>(() => Date.now())
  const [playing, setPlaying] = useState(false)
  const [results, setResults] = useState<RewindSearchGroup[]>([])

  const framesRef = useRef(frames)
  useEffect(() => {
    framesRef.current = frames
  }, [frames])
  const selectedDateRef = useRef(selectedDate)
  useEffect(() => {
    selectedDateRef.current = selectedDate
  }, [selectedDate])

  const playTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  // Guards the async day load against races: pick day A then B fast, and A must not
  // land after B and clobber the view.
  const loadSeq = useRef(0)
  // A pending `jumpTo` target: set the cursor to this exact moment once the day it
  // lives in has loaded, instead of the day's newest frame.
  const pendingJump = useRef<number | null>(null)
  // The query whose results are on screen, so a late semantic result for a
  // superseded query can be dropped.
  const queryRef = useRef('')

  const bounds = { min: selectedDate, max: endOfLocalDay(selectedDate) }

  // Load one day's frames, evenly down-sampled to ~500 (see rewindFramesSampled).
  const loadDay = useCallback(async (dayStart: number) => {
    const seq = ++loadSeq.current
    setLoading(true)
    const f = await window.omi.rewindFramesSampled(dayStart, endOfLocalDay(dayStart))
    // Superseded by a newer day selection: do NOT consume pendingJump here — the
    // newest load owns it. Consuming it (or clearing it) on a stale load could seek
    // the *newer* day's timeline to *this* day's timestamp — an empty frame, the very
    // race this feature fixes (M1) — or wipe a jump the newer load still needs.
    if (seq !== loadSeq.current) return
    setFrames(f)
    setLoading(false)
    // This is the newest load, so it consumes the pending jump. Apply it only when it
    // belongs to the day we just loaded (a jumpTo(dayA) quickly followed by a move to
    // dayB must not seek dayB to dayA's moment); clear it regardless so it can't linger.
    const jump = pendingJump.current
    pendingJump.current = null
    if (jump != null && startOfLocalDay(jump) === dayStart) setCursorTs(jump)
    else if (f.length > 0) setCursorTs(f[f.length - 1].ts)
    else setCursorTs(dayStart)
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load-on-mount / reload-on-day-change; not a self-retriggering loop
    void loadDay(selectedDate)
  }, [selectedDate, loadDay])

  // Silent today-only refresh (macOS): resample the day and republish ONLY when the
  // frame set changed. Never sets loading, never moves the cursor — preserves the
  // user's scrub position and any transient view state. Past days are static.
  //
  // Paused while the panel is hidden (`active` false): the interval stops, so no
  // frames-DB hit and no hidden-subtree re-render happen off-screen. On show
  // (`active` false→true) this effect re-runs and resamples IMMEDIATELY, so the
  // panel reflects any frames captured while it was hidden with no visible lag —
  // then resumes the 3s cadence. Only today ticks; past days are static.
  const wasActiveRef = useRef(active)
  useEffect(() => {
    const dayStart = selectedDate
    const becameVisible = active && !wasActiveRef.current
    wasActiveRef.current = active
    if (!active) return
    if (startOfLocalDay(Date.now()) !== dayStart) return // only today ticks
    let alive = true
    const resample = async (): Promise<void> => {
      if (startOfLocalDay(Date.now()) !== dayStart) return // rolled past midnight
      const f = await window.omi.rewindFramesSampled(dayStart, endOfLocalDay(dayStart))
      if (!alive) return
      setFrames((prev) => (sameFrameIds(prev, f) ? prev : f))
    }
    // Immediate resample ONLY when the panel just became visible (catch up on
    // frames captured while hidden). Not on the first mount — loadDay already
    // fetched — and not on a day change, which loadDay owns.
    //
    // Trade-off when Rewind is the LANDING view: it mounts with active=false (the
    // observer reports visibility a frame late), loadDay fetches once, then the
    // observer flips active→true and this fires one more resample — two fetches on
    // first open. Accepted deliberately: it keeps the common case (Home is the
    // landing view, Rewind hidden) doing zero refresh work, and the extra fetch is
    // a cheap, deduped (sameFrameIds) same-day sample.
    if (becameVisible) void resample()
    const id = setInterval(() => void resample(), TODAY_REFRESH_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [selectedDate, active])

  const selectDate = useCallback((dayMs: number) => {
    const day = startOfLocalDay(dayMs)
    setSelectedDate((prev) => (prev === day ? prev : day)) // reload only if it changed
  }, [])

  const jumpTo = useCallback((ts: number) => {
    const day = startOfLocalDay(ts)
    if (day === selectedDateRef.current) {
      setCursorTs(ts) // same day already loaded — just seek
      return
    }
    pendingJump.current = ts
    setSelectedDate(day) // loads the day, then the cursor lands on `ts`
  }, [])

  // Playback advances the cursor frame-by-frame through the loaded day.
  useEffect(() => {
    if (playTimer.current) clearInterval(playTimer.current)
    if (!playing || frames.length === 0) return
    playTimer.current = setInterval(() => {
      setCursorTs((cur) => {
        const idx = framesRef.current.findIndex((f) => f.ts >= cur)
        const next = framesRef.current[idx + 1] ?? framesRef.current[0]
        return next.ts
      })
    }, 700)
    return () => {
      if (playTimer.current) clearInterval(playTimer.current)
    }
  }, [playing, frames])

  // Keyword results, immediately — never waits on the network. Semantic hits are
  // merged in later by the subscription below, if they arrive at all.
  const search = useCallback(async (q: string) => {
    queryRef.current = q.trim()
    setResults(await window.omi.rewindSearch(q))
  }, [])

  // Phase 2 of a search (see the rewind:search handler): the same list with
  // semantic recall merged in. Applied only if it belongs to the query currently on
  // screen — a slow round-trip for "invoice" must not overwrite "receipt".
  useEffect(() => {
    return window.omi.onRewindSearchResults(({ query, groups }) => {
      if (query === queryRef.current) setResults(groups)
    })
  }, [])

  // eslint-disable-next-line react-hooks/purity -- "is the day in view today?" is inherently clock-relative; recomputed each render so it flips at midnight
  const isToday = startOfLocalDay(Date.now()) === selectedDate

  return {
    frames,
    bounds,
    selectedDate,
    isToday,
    selectDate,
    jumpTo,
    loading,
    cursorTs,
    setCursorTs,
    playing,
    setPlaying,
    results,
    search
  }
}
