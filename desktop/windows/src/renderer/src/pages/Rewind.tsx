import { useEffect, useState } from 'react'
import { Search, Play, Pause, ArrowLeft } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindSearchBar } from '../components/rewind/RewindSearchBar'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

// Compact header control matching the Phase-8 token set (neutral/white, hairline
// border, rounded-control) — shared by the search, play/pause, and back buttons.
const CTRL =
  'inline-flex items-center gap-1.5 rounded-control border border-line bg-white/[0.06] px-3 py-1.5 text-sm text-white/80 transition-colors hover:border-line-strong hover:bg-white/[0.10] hover:text-white'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  const [showSearch, setShowSearch] = useState(false)
  // Gate the results filmstrip until a query actually runs, so the "No matches."
  // empty state doesn't flash the moment search opens.
  const [hasSearched, setHasSearched] = useState(false)

  const openSearch = (): void => {
    setHasSearched(false)
    setShowSearch(true)
  }
  const closeSearch = (): void => setShowSearch(false)

  // Ctrl/Cmd+F opens search while on this page; Escape returns to the timeline.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        openSearch()
      } else if (e.key === 'Escape' && showSearch) {
        e.preventDefault()
        closeSearch()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [showSearch])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-white">Rewind</h1>
        <div className="flex items-center gap-2">
          {showSearch ? (
            <button onClick={closeSearch} className={CTRL} title="Back to timeline (Esc)">
              <ArrowLeft className="h-4 w-4" />
              Timeline
            </button>
          ) : (
            <>
              <button onClick={openSearch} className={CTRL} title="Search screen history (Ctrl+F)">
                <Search className="h-4 w-4" />
                Search
              </button>
              <button
                onClick={() => r.setPlaying(!r.playing)}
                className={CTRL}
                title={r.playing ? 'Pause' : 'Play'}
              >
                {r.playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {r.playing ? 'Pause' : 'Play'}
              </button>
            </>
          )}
        </div>
      </div>

      {showSearch ? (
        <div className="flex min-h-0 flex-col gap-3">
          <RewindSearchBar
            onSearch={(q) => {
              setHasSearched(true)
              void r.search(q)
            }}
          />
          {hasSearched ? (
            <div className="min-h-0 overflow-y-auto">
              <SearchResultsFilmstrip
                groups={r.results}
                onJump={(ts) => {
                  r.setCursorTs(ts)
                  setShowSearch(false)
                }}
              />
            </div>
          ) : (
            <p className="px-1 py-2 text-sm text-white/35">
              Type a word that appeared on your screen to jump back to that moment.
            </p>
          )}
        </div>
      ) : (
        <>
          <RewindPlayer frames={r.frames} cursorTs={r.cursorTs} />
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
