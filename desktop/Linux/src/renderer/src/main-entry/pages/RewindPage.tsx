import React, { useEffect, useRef, useState } from 'react'
import { IconSearch } from '../../components/Icons'
import { EmptyState, Toggle } from '../../components/ui'
import { formatBytes } from '../../lib/format'
import { useSettings } from '../../stores/settings'
import type { RewindFrame } from '../../../../shared/types'

// Rewind-lite: 3s captures + Windows OCR + FTS5 search over your screen history,
// mirroring the Mac RewindTimelineView (scrubber + search + preview).

export function RewindPage() {
  const { settings, update } = useSettings()
  const [days, setDays] = useState<{ day: string; count: number }[]>([])
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const [frames, setFrames] = useState<RewindFrame[]>([])
  const [index, setIndex] = useState(0)
  const [image, setImage] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RewindFrame[] | null>(null)
  const [status, setStatus] = useState<{ frames: number; bytes: number; ocrPending: number; capturing: boolean } | null>(null)
  const searchTimer = useRef<number | null>(null)

  const loadDays = async () => {
    const d = await window.omi.rewind.days()
    setDays(d)
    if (!selectedDay && d.length > 0) setSelectedDay(d[0].day)
  }

  useEffect(() => {
    void loadDays()
    void window.omi.rewind.status().then(setStatus)
    const unsub = window.omi.rewind.onStatus((s) => setStatus(s as typeof status))
    return unsub
  }, [])

  useEffect(() => {
    if (!selectedDay) return
    void window.omi.rewind.list(selectedDay, 2000, 0).then((f) => {
      setFrames(f)
      setIndex(Math.max(0, f.length - 1))
    })
  }, [selectedDay, status?.frames])

  const current = results ? null : frames[index]

  useEffect(() => {
    if (!current) return
    let cancelled = false
    void window.omi.rewind.image(current.id).then((img) => {
      if (!cancelled) setImage(img)
    })
    return () => {
      cancelled = true
    }
  }, [current?.id])

  const onSearch = (q: string) => {
    setQuery(q)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(async () => {
      if (!q.trim()) {
        setResults(null)
        return
      }
      setResults(await window.omi.rewind.search(q, 60))
    }, 300)
  }

  if (!settings) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top bar */}
      <div style={{ padding: '44px 22px 12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
          <div style={{ fontSize: 19, fontWeight: 700, flex: 1 }}>Rewind</div>
          <span style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>
            {status ? `${status.frames} frames · ${formatBytes(status.bytes)}${status.ocrPending ? ` · OCR ${status.ocrPending} pending` : ''}` : ''}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>
              {settings.rewindEnabled ? 'Recording' : 'Paused'}
            </span>
            <Toggle on={settings.rewindEnabled} onChange={(v) => void update({ rewindEnabled: v })} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <span style={{ position: 'absolute', left: 10, top: 8, color: 'var(--text-quaternary)' }}>
              <IconSearch size={14} />
            </span>
            <input
              placeholder="Search your screen history..."
              value={query}
              onChange={(e) => onSearch(e.target.value)}
              style={{ width: '100%', paddingLeft: 32 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 6, overflowX: 'auto', maxWidth: 360 }}>
            {days.slice(0, 7).map((d) => (
              <button
                key={d.day}
                className={`chip ${selectedDay === d.day && !results ? 'active' : ''}`}
                onClick={() => {
                  setResults(null)
                  setQuery('')
                  setSelectedDay(d.day)
                }}
              >
                {formatDayChip(d.day)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Body */}
      {results ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
          {results.length === 0 ? (
            <EmptyState title="No matches" subtitle="OCR indexing may still be running for recent frames." />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
              {results.map((r) => (
                <SearchResult key={r.id} frame={r} onOpen={() => openResult(r)} />
              ))}
            </div>
          )}
        </div>
      ) : frames.length === 0 ? (
        <EmptyState
          title={settings.rewindEnabled ? 'Recording your screen…' : 'Rewind is paused'}
          subtitle={
            settings.rewindEnabled
              ? 'Frames appear here a few seconds after capture. Everything stays on this machine.'
              : 'Turn on Screen Capture to build a searchable history of everything you see.'
          }
        />
      ) : (
        <>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000', minHeight: 0 }}>
            {image && <img src={image} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} alt="frame" />}
          </div>
          <div style={{ padding: '10px 22px 16px', borderTop: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-quaternary)', marginBottom: 6 }}>
              <span>{current ? new Date(current.ts).toLocaleTimeString() : ''}</span>
              <span>
                {frames.length ? index + 1 : 0} / {frames.length}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(0, frames.length - 1)}
              value={index}
              onChange={(e) => setIndex(parseInt(e.target.value, 10))}
              style={{ width: '100%', accentColor: 'var(--purple-primary)', padding: 0, background: 'transparent', border: 'none' }}
            />
          </div>
        </>
      )}
    </div>
  )

  function openResult(r: RewindFrame) {
    setResults(null)
    setQuery('')
    setSelectedDay(r.day)
    void window.omi.rewind.list(r.day, 2000, 0).then((f) => {
      setFrames(f)
      const i = f.findIndex((x) => x.id === r.id)
      setIndex(i >= 0 ? i : 0)
    })
  }
}

function formatDayChip(day: string): string {
  const today = new Date()
  const d = new Date(day + 'T00:00:00')
  const diff = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - d.getTime()) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function SearchResult({ frame, onOpen }: { frame: RewindFrame; onOpen: () => void }) {
  const [thumb, setThumb] = useState<string | null>(null)
  useEffect(() => {
    void window.omi.rewind.thumbnail(frame.id, 480).then(setThumb)
  }, [frame.id])
  return (
    <button className="card" style={{ padding: 0, overflow: 'hidden', textAlign: 'left' }} onClick={onOpen}>
      {thumb ? (
        <img src={thumb} style={{ width: '100%', display: 'block' }} alt="" />
      ) : (
        <div style={{ height: 130, background: 'var(--bg-tertiary)' }} />
      )}
      <div style={{ padding: '8px 11px 11px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-quaternary)', marginBottom: 4 }}>
          {new Date(frame.ts).toLocaleString()}
        </div>
        {frame.snippet && (
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.4 }}>
            {frame.snippet.replace(/<</g, '').replace(/>>/g, '')}
          </div>
        )}
      </div>
    </button>
  )
}
