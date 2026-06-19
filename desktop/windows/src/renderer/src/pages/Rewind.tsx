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

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-white">Rewind</h1>
        <div className="flex items-center gap-2">
          {showSearch ? (
            <button
              onClick={() => setShowSearch(false)}
              className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.75} />
              Close search
            </button>
          ) : (
            <>
              <button
                onClick={() => setShowSearch(true)}
                title="Search screen history"
                className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
              >
                <Search className="h-3.5 w-3.5" strokeWidth={1.75} />
                Search
              </button>
              <button
                onClick={() => r.setPlaying(!r.playing)}
                className="rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
              >
                {r.playing ? 'Pause' : 'Play'}
              </button>
            </>
          )}
        </div>
      </div>

      {showSearch ? (
        <div className="flex flex-col gap-3">
          <RewindSearchBar onSearch={(q) => void r.search(q)} />
          <SearchResultsFilmstrip
            groups={r.results}
            onJump={(ts) => {
              r.setCursorTs(ts)
              setShowSearch(false)
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
