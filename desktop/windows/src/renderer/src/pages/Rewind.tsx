import { useState } from 'react'
import { AlignLeft, Download, Search, X } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindSearchBar } from '../components/rewind/RewindSearchBar'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  const [showSearch, setShowSearch] = useState(false)
  const [showOcr, setShowOcr] = useState(false)

  const exportJson = (): void => {
    const data = {
      exportedAt: new Date().toISOString(),
      frameCount: r.frames.length,
      frames: r.frames.map((f) => ({
        timestamp: new Date(f.ts).toISOString(),
        timestampMs: f.ts,
        app: f.app,
        windowTitle: f.windowTitle,
        ocrText: f.ocrText
      }))
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `omi-rewind-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

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
                onClick={() => setShowOcr((v) => !v)}
                title={showOcr ? 'Hide OCR text' : 'Show OCR text'}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-sm transition-colors hover:bg-white/15 ${showOcr ? 'bg-white/15 text-white' : 'bg-white/10 text-white/70'}`}
              >
                <AlignLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
                Text
              </button>
              {r.frames.length > 0 && (
                <button
                  onClick={exportJson}
                  title="Export frames as JSON"
                  className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white/70 transition-colors hover:bg-white/15 hover:text-white"
                >
                  <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                  Export
                </button>
              )}
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
          <RewindPlayer frames={r.frames} cursorTs={r.cursorTs} showOcr={showOcr} />
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
