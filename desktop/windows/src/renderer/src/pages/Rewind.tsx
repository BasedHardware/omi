import { useEffect, useRef, useState } from 'react'
import { AlignLeft, Download, FileText, Search, X } from 'lucide-react'
import { useRewind } from '../hooks/useRewind'
import type { RewindFrame } from '../../../shared/types'
import { RewindPlayer } from '../components/rewind/RewindPlayer'
import { RewindTimelineBar } from '../components/rewind/RewindTimelineBar'
import { RewindThumbnailStrip } from '../components/rewind/RewindThumbnailStrip'
import { RewindSearchBar } from '../components/rewind/RewindSearchBar'
import { SearchResultsFilmstrip } from '../components/rewind/SearchResultsFilmstrip'

export function Rewind(): React.JSX.Element {
  const r = useRewind()
  const [showSearch, setShowSearch] = useState(false)
  const [showOcr, setShowOcr] = useState(false)

  // Date filter — defaults to today; switching to a past date loads that day's frames.
  const todayStr = new Date().toISOString().slice(0, 10)
  const [dateStr, setDateStr] = useState(todayStr)
  const [dateFrames, setDateFrames] = useState<RewindFrame[] | null>(null)
  const [dateLoading, setDateLoading] = useState(false)

  const isToday = dateStr === todayStr
  const frames = isToday ? r.frames : (dateFrames ?? [])

  // Keep a mutable ref updated every render so the keydown handler always has
  // the latest values without needing to re-register on every state change.
  const latest = useRef({ frames, cursorTs: r.cursorTs, playing: r.playing, isToday, showSearch })
  useEffect(() => {
    latest.current = { frames, cursorTs: r.cursorTs, playing: r.playing, isToday, showSearch }
  })

  // Keyboard shortcuts — macOS RewindPage parity:
  //   ← / →  step one frame back / forward
  //   Space   play / pause (today's live timeline only)
  //   Ctrl+F  toggle search bar
  //   Escape  close search bar
  useEffect(() => {
    const handler = (e: KeyboardEvent): void => {
      const tag = (document.activeElement as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      const { frames: fs, cursorTs, playing, isToday: isTd, showSearch: ss } = latest.current

      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault()
        if (fs.length === 0) return
        // findIndex of the first frame whose ts > cursor, then subtract 1 to get
        // the current frame (the last one that is at-or-before the cursor).
        const ahead = fs.findIndex((f) => f.ts > cursorTs)
        const curIdx = ahead === -1 ? fs.length - 1 : Math.max(0, ahead - 1)
        if (e.key === 'ArrowLeft' && curIdx > 0) r.setCursorTs(fs[curIdx - 1].ts)
        else if (e.key === 'ArrowRight' && curIdx < fs.length - 1) r.setCursorTs(fs[curIdx + 1].ts)
      } else if (e.key === ' ' && isTd) {
        e.preventDefault()
        r.setPlaying(!playing)
      } else if (e.ctrlKey && e.key === 'f') {
        e.preventDefault()
        setShowSearch((v) => !v)
      } else if (e.key === 'Escape' && ss) {
        e.preventDefault()
        setShowSearch(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Registered once; latest values read via the `latest` ref

  useEffect(() => {
    if (isToday) { setDateFrames(null); return }
    setDateLoading(true)
    const dayStart = new Date(dateStr + 'T00:00:00').getTime()
    const dayEnd = new Date(dateStr + 'T23:59:59.999').getTime()
    void window.omi.rewindFrames(dayStart, dayEnd).then((f) => {
      setDateFrames(f)
      if (f.length > 0) r.setCursorTs(f[f.length - 1].ts)
    }).finally(() => setDateLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateStr, isToday])

  const exportJson = (): void => {
    const data = {
      exportedAt: new Date().toISOString(),
      frameCount: frames.length,
      frames: frames.map((f) => ({
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
    a.download = `omi-rewind-${dateStr}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const exportMarkdown = (): void => {
    const lines: string[] = ['# Omi Rewind Export', '', `**Date:** ${dateStr}`, '']
    for (const f of frames) {
      const ts = new Date(f.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      lines.push(`## ${ts}`)
      lines.push(`**App:** ${f.app || 'Unknown'} · **Window:** ${f.windowTitle || '—'}`)
      lines.push('')
      if (f.ocrText) { lines.push(f.ocrText); lines.push('') }
      lines.push('---')
      lines.push('')
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `omi-rewind-${dateStr}.md`
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
              {/* Date picker — filters to a specific day's frames */}
              <input
                type="date"
                value={dateStr}
                max={todayStr}
                onChange={(e) => { if (e.target.value) setDateStr(e.target.value) }}
                disabled={dateLoading}
                className="rounded bg-white/10 px-2 py-1 text-sm text-white/70 [color-scheme:dark] hover:bg-white/15 disabled:opacity-40"
                title="Filter to a specific date"
              />
              <button
                onClick={() => setShowOcr((v) => !v)}
                title={showOcr ? 'Hide OCR text' : 'Show OCR text'}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-sm transition-colors hover:bg-white/15 ${showOcr ? 'bg-white/15 text-white' : 'bg-white/10 text-white/70'}`}
              >
                <AlignLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
                Text
              </button>
              {frames.length > 0 && (
                <>
                  <button
                    onClick={exportJson}
                    title="Export frames as JSON"
                    className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white/70 transition-colors hover:bg-white/15 hover:text-white"
                  >
                    <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                    JSON
                  </button>
                  <button
                    onClick={exportMarkdown}
                    title="Export frames as Markdown"
                    className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white/70 transition-colors hover:bg-white/15 hover:text-white"
                  >
                    <FileText className="h-3.5 w-3.5" strokeWidth={1.75} />
                    MD
                  </button>
                </>
              )}
              <button
                onClick={() => setShowSearch(true)}
                title="Search screen history"
                className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
              >
                <Search className="h-3.5 w-3.5" strokeWidth={1.75} />
                Search
              </button>
              {isToday && (
                <button
                  onClick={() => r.setPlaying(!r.playing)}
                  className="rounded bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/15"
                >
                  {r.playing ? 'Pause' : 'Play'}
                </button>
              )}
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
          {dateLoading && (
            <div className="flex items-center justify-center py-4 text-sm text-white/40">
              Loading frames for {dateStr}…
            </div>
          )}
          {!dateLoading && (
            <>
              <RewindPlayer frames={frames} cursorTs={r.cursorTs} showOcr={showOcr} />
              <RewindThumbnailStrip frames={frames} cursorTs={r.cursorTs} onSeek={r.setCursorTs} />
              <RewindTimelineBar
                frames={frames}
                bounds={isToday ? r.bounds : (frames.length > 0 ? { min: frames[0].ts, max: frames[frames.length - 1].ts } : null)}
                cursorTs={r.cursorTs}
                onSeek={r.setCursorTs}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}
