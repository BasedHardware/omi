import { useCallback, useEffect, useRef, useState } from 'react'
import type { RewindFrame, RewindSearchGroup } from '../../../shared/types'
import { mergeFrames, isFollowingLive } from '../lib/rewindLive'

const DAY_MS = 24 * 60 * 60 * 1000
// How often the open timeline polls for newly-captured frames.
const LIVE_POLL_MS = 1000

export type RewindState = {
  frames: RewindFrame[]
  bounds: { min: number; max: number } | null
  cursorTs: number
  setCursorTs: (ts: number) => void
  playing: boolean
  setPlaying: (p: boolean) => void
  results: RewindSearchGroup[]
  search: (q: string) => Promise<void>
  reload: () => Promise<void>
}

export function useRewind(): RewindState {
  const [frames, setFrames] = useState<RewindFrame[]>([])
  const [bounds, setBounds] = useState<{ min: number; max: number } | null>(null)
  const [cursorTs, setCursorTs] = useState<number>(Date.now())
  const [playing, setPlaying] = useState(false)
  const [results, setResults] = useState<RewindSearchGroup[]>([])
  const playTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const framesRef = useRef(frames)
  useEffect(() => { framesRef.current = frames }, [frames])
  const cursorRef = useRef(cursorTs)
  useEffect(() => { cursorRef.current = cursorTs }, [cursorTs])

  const reload = useCallback(async () => {
    const b = await window.omi.rewindDayBounds()
    setBounds(b)
    const to = b?.max ?? Date.now()
    const from = to - DAY_MS
    const f = await window.omi.rewindFrames(from, to)
    setFrames(f)
    if (f.length > 0) setCursorTs(f[f.length - 1].ts)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  // Live refresh: poll for newly-captured frames and extend the timeline in
  // place. We append (never reload) so the user's scrub position is preserved;
  // the cursor only jumps to the newest frame when they're already following
  // the live edge.
  useEffect(() => {
    let alive = true
    const id = setInterval(async () => {
      const b = await window.omi.rewindDayBounds()
      if (!alive || !b) return
      // Keep the same object when unchanged so we don't re-render every tick.
      setBounds((prev) => (prev && prev.min === b.min && prev.max === b.max ? prev : b))
      const current = framesRef.current
      const haveMax = current.length > 0 ? current[current.length - 1].ts : 0
      if (b.max <= haveMax) return
      const incoming = await window.omi.rewindFrames(haveMax + 1, b.max)
      if (!alive || incoming.length === 0) return
      const following = isFollowingLive(cursorRef.current, current)
      const merged = mergeFrames(current, incoming)
      setFrames(merged)
      if (following) setCursorTs(merged[merged.length - 1].ts)
    }, LIVE_POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  // Playback advances the cursor frame-by-frame.
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

  const search = useCallback(async (q: string) => {
    setResults(await window.omi.rewindSearch(q))
  }, [])

  return {
    frames,
    bounds,
    cursorTs,
    setCursorTs,
    playing,
    setPlaying,
    results,
    search,
    reload
  }
}
