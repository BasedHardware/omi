import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, Play, Pause, X, ChevronLeft, List, Clock } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import type { RewindSearchGroup } from '../../../shared/types'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindDatePicker } from '../components/rewind/RewindDatePicker'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'
import { highlightTerms, lineTextMatches } from '../lib/rewindOverlay'

// macOS parity: typing is debounced before the search runs (RewindViewModel 300ms).
const SEARCH_DEBOUNCE_MS = 300

const CTRL =
  'inline-flex items-center gap-1.5 rounded-control border border-line bg-white/[0.06] px-3 py-1.5 text-sm text-white/80 transition-colors hover:border-line-strong hover:bg-white/[0.10] hover:text-white'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  // Stable useCallbacks — destructured so effects can depend on them without
  // re-running on every render (the `r` object identity changes each render).
  const { search, jumpTo } = r
  // The search field is always present in the top bar (macOS keeps one page — the
  // content switches between the day timeline and the search results, it is not a
  // separate mode/route). A non-empty query IS "searching".
  const [query, setQuery] = useState('')
  const searching = query.trim().length > 0
  // The query whose results are on screen — set only when a search resolves, so
  // "still loading" is a pure derivation (no setState-in-effect).
  const [resolvedQuery, setResolvedQuery] = useState('')
  const searchLoading = searching && resolvedQuery !== query.trim()
  // Search sub-mode (macOS searchViewMode): the results list, or a drill-down
  // mini-timeline of one selected group. `group` is null until a result is opened.
  const [group, setGroup] = useState<RewindSearchGroup | null>(null)
  const drilldown = searching && group != null
  const inputRef = useRef<HTMLInputElement>(null)

  // Debounced search — re-runs whenever the query changes.
  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const id = setTimeout(() => {
      void search(q).finally(() => setResolvedQuery(q))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [query, search])

  // Changing or clearing the query drops any open drill-down (done in the handlers,
  // not an effect, so there's no cascading setState).
  const changeQuery = (v: string): void => {
    setQuery(v)
    setGroup(null)
  }
  const clearSearch = (): void => changeQuery('')

  // Ctrl/Cmd+F focuses the search field; Escape backs out (drill-down → list → clear).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        inputRef.current?.focus()
      } else if (e.key === 'Escape' && searching) {
        e.preventDefault()
        if (group) setGroup(null)
        else setQuery('') // clearing the query also drops the drill-down via `drilldown`
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [searching, group])

  const openGroup = (g: RewindSearchGroup): void => {
    jumpTo(g.representative.ts) // load the hit's DAY (fixes the empty-player bug) + seek
    setGroup(g)
  }

  // The group's frames that literally match the query — marked yellow on the
  // drill-down mini-timeline (macOS search-result markers).
  const markerTimes = useMemo(() => {
    if (!group) return []
    const terms = highlightTerms(query)
    return group.frames.filter((f) => lineTextMatches(f.ocrText, terms)).map((f) => f.ts)
  }, [group, query])

  return (
    <div data-testid="rewind-page" className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="shrink-0 text-lg font-semibold text-white">Rewind</h1>
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
          <div className="relative min-w-0 max-w-xs flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => changeQuery(e.target.value)}
              placeholder="Search what was on screen…"
              className="w-full rounded-control border border-line bg-white/[0.07] py-1.5 pl-8 pr-8 text-sm text-white outline-none transition-colors placeholder:text-white/35 focus:border-line-strong"
            />
            {searching && (
              <button
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 transition-colors hover:text-white"
                title="Clear search (Esc)"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          {searching && <ViewModeToggle drilldown={drilldown} onList={() => setGroup(null)} />}
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

      {!searching ? (
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
      ) : drilldown ? (
        <>
          <button
            onClick={() => setGroup(null)}
            className="inline-flex w-fit items-center gap-1 text-sm text-white/55 transition-colors hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to results
          </button>
          <RewindPlayer frames={group.frames} cursorTs={r.cursorTs} highlightQuery={query} />
          <RewindTimelineBar
            frames={group.frames}
            bounds={null}
            cursorTs={r.cursorTs}
            onSeek={r.setCursorTs}
            markerTimes={markerTimes}
          />
        </>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <SearchResultsFilmstrip
            groups={r.results}
            query={query}
            loading={searchLoading}
            onSelect={openGroup}
          />
        </div>
      )}
    </div>
  )
}

/** macOS view-mode toggle (list ⇆ timeline), visible only while searching. Timeline
 *  is reachable only once a result group is open (drill-down); the List side backs
 *  out of the drill-down. */
function ViewModeToggle({
  drilldown,
  onList
}: {
  drilldown: boolean
  onList: () => void
}): React.JSX.Element {
  const seg = 'flex items-center gap-1 rounded-control px-2.5 py-1.5 text-sm transition-colors'
  return (
    <div className="flex items-center gap-0.5 rounded-control border border-line bg-white/[0.04] p-0.5">
      <button
        onClick={onList}
        className={`${seg} ${!drilldown ? 'bg-white/[0.12] text-white' : 'text-white/55 hover:text-white'}`}
        title="Results list"
      >
        <List className="h-4 w-4" />
      </button>
      <span
        className={`${seg} ${drilldown ? 'bg-white/[0.12] text-white' : 'text-white/30'}`}
        title="Timeline (open a result to drill in)"
      >
        <Clock className="h-4 w-4" />
      </span>
    </div>
  )
}
