import { useEffect, useMemo, useRef, useState } from 'react'
import type { RewindFrame } from '../../../shared/types'
import { useRewind } from '../hooks/useRewind'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindSearchBar } from '../components/rewind/RewindSearchBar'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

function uniqueFrames(frames: RewindFrame[]): RewindFrame[] {
  const seen = new Set<string>()
  return frames
    .filter((frame) => {
      const key = frame.id != null ? `id:${frame.id}` : `${frame.ts}:${frame.imagePath}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => a.ts - b.ts)
}

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  const { frames, bounds, cursorTs, setCursorTs, playing, setPlaying, results, search } = r
  const [activeQuery, setActiveQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const searchSeq = useRef(0)

  const resultFrames = useMemo(
    () => uniqueFrames(results.flatMap((group) => group.frames)),
    [results]
  )
  const inSearchMode = activeQuery.length > 0
  const showingResults = inSearchMode && !searching && results.length > 0
  const playerFrames = showingResults ? resultFrames : frames

  useEffect(() => {
    if (!showingResults || results.length === 0) return
    const hasCursorFrame = resultFrames.some((frame) => frame.ts === cursorTs)
    if (!hasCursorFrame) setCursorTs(results[0].representative.ts)
  }, [cursorTs, resultFrames, results, setCursorTs, showingResults])

  const handleSearch = (query: string): void => {
    const trimmed = query.trim()
    if (!trimmed) {
      setActiveQuery('')
      setSearchError(null)
      return
    }

    const seq = searchSeq.current + 1
    searchSeq.current = seq
    setActiveQuery(trimmed)
    setSearchError(null)
    setSearching(true)
    void search(trimmed)
      .catch(() => {
        if (searchSeq.current === seq) setSearchError('Search failed. Try again.')
      })
      .finally(() => {
        if (searchSeq.current === seq) setSearching(false)
      })
  }

  const clearSearch = (): void => {
    searchSeq.current += 1
    setActiveQuery('')
    setSearchError(null)
    setSearching(false)
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex shrink-0 items-start justify-between gap-4">
        <h1 className="text-lg font-semibold text-white">Rewind</h1>
        <button
          onClick={() => setPlaying(!playing)}
          className="w-20 rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>

      <div className="shrink-0">
        <RewindSearchBar
          onSearch={handleSearch}
          onClear={clearSearch}
          searching={searching}
          activeQuery={activeQuery}
        />
        {searchError && <div className="mt-2 text-xs text-red-300">{searchError}</div>}
      </div>

      <RewindPlayer frames={playerFrames} cursorTs={cursorTs} />

      <div className="flex h-44 shrink-0 flex-col gap-2 overflow-hidden">
        {inSearchMode ? (
          <SearchResultsFilmstrip
            groups={results}
            query={activeQuery}
            searching={searching}
            onJump={(ts) => {
              setCursorTs(ts)
            }}
          />
        ) : (
          <>
            <RewindThumbnailStrip frames={frames} cursorTs={cursorTs} onSeek={setCursorTs} />
            <RewindTimelineBar
              frames={frames}
              bounds={bounds}
              cursorTs={cursorTs}
              onSeek={setCursorTs}
            />
          </>
        )}
      </div>
    </div>
  )
}
