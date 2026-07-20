import { useState } from 'react'
import { Search, X } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindSearchBar } from '../components/rewind/RewindSearchBar'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  const [showSearch, setShowSearch] = useState(false)
  const [searched, setSearched] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const openSearch = (): void => {
    r.setPlaying(false)
    setShowSearch(true)
  }

  const closeSearch = (): void => {
    setShowSearch(false)
    setSearched(false)
    setSearchError(null)
  }

  const search = async (query: string): Promise<void> => {
    setSearching(true)
    setSearchError(null)
    try {
      await r.search(query)
      setSearched(true)
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : String(error))
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex items-start justify-between">
        <h1 className="text-lg font-semibold text-white">Rewind</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={showSearch ? closeSearch : openSearch}
            className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white"
          >
            {showSearch ? <X className="h-4 w-4" /> : <Search className="h-4 w-4" />}
            {showSearch ? 'Close search' : 'Search'}
          </button>
          {!showSearch && (
            <button
              onClick={() => r.setPlaying(!r.playing)}
              className="rounded bg-white/10 px-3 py-1 text-sm text-white"
            >
              {r.playing ? 'Pause' : 'Play'}
            </button>
          )}
        </div>
      </div>

      {showSearch ? (
        <div className="flex flex-col gap-3">
          <RewindSearchBar onSearch={(q) => void search(q)} searching={searching} />
          <SearchResultsFilmstrip
            groups={r.results}
            searched={searched}
            error={searchError}
            onJump={(ts) => {
              r.setCursorTs(ts)
              closeSearch()
            }}
          />
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
