import { useEffect, useRef, useState } from 'react'
import { Search, Play, Pause, X } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindDatePicker } from '../components/rewind/RewindDatePicker'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

// macOS parity: typing is debounced before the search runs (RewindViewModel 300ms).
const SEARCH_DEBOUNCE_MS = 300

const CTRL =
  'inline-flex items-center gap-1.5 rounded-control border border-line bg-white/[0.06] px-3 py-1.5 text-sm text-white/80 transition-colors hover:border-line-strong hover:bg-white/[0.10] hover:text-white'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  // Stable useCallbacks — destructured so effects can depend on them without
  // re-running on every render (the `r` object identity changes each render).
  const { search } = r
  // The search field is always present in the top bar (macOS keeps one page — the
  // content switches between the day timeline and the search results, it is not a
  // separate mode/route). A non-empty query IS "searching".
  const [query, setQuery] = useState('')
  const searching = query.trim().length > 0
  const inputRef = useRef<HTMLInputElement>(null)

  // Debounced search — re-runs whenever the query changes, clears when emptied.
  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const id = setTimeout(() => void search(q), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [query, search])

  // Ctrl/Cmd+F focuses the search field; Escape clears it (back to the timeline).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        inputRef.current?.focus()
      } else if (e.key === 'Escape' && searching) {
        e.preventDefault()
        setQuery('')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [searching])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="shrink-0 text-lg font-semibold text-white">Rewind</h1>
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
          <div className="relative min-w-0 max-w-xs flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search what was on screen…"
              className="w-full rounded-control border border-line bg-white/[0.07] py-1.5 pl-8 pr-8 text-sm text-white outline-none transition-colors placeholder:text-white/35 focus:border-line-strong"
            />
            {searching && (
              <button
                onClick={() => setQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 transition-colors hover:text-white"
                title="Clear search (Esc)"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <RewindDatePicker selectedDate={r.selectedDate} onSelect={r.selectDate} />
          {!searching && (
            <button
              onClick={() => r.setPlaying(!r.playing)}
              className={CTRL}
              title={r.playing ? 'Pause' : 'Play'}
            >
              {r.playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {r.playing ? 'Pause' : 'Play'}
            </button>
          )}
        </div>
      </div>

      {searching ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <SearchResultsFilmstrip
            groups={r.results}
            onJump={(ts) => {
              r.jumpTo(ts)
              setQuery('')
            }}
          />
        </div>
      ) : (
        <>
          <RewindPlayer frames={r.frames} cursorTs={r.cursorTs} highlightQuery={query} />
          <RewindThumbnailStrip frames={r.frames} cursorTs={r.cursorTs} onSeek={r.setCursorTs} />
          <RewindTimelineBar
            frames={r.frames}
            bounds={r.bounds}
            cursorTs={r.cursorTs}
            onSeek={r.setCursorTs}
          />
        </>
      )}
    </div>
  )
}
