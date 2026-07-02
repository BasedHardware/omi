import React, { useEffect, useState } from 'react'
import { IconTrash } from '../../components/Icons'
import { EmptyState } from '../../components/ui'
import { timeAgo } from '../../lib/format'
import { insightCounts, useProactive } from '../../stores/proactive'
import { useSettings } from '../../stores/settings'

// Inline SF-Symbols-style search/clear icons (magnifyingglass + xmark.circle.fill).
const IconSearch = ({ size = 13 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </svg>
)
const IconClear = ({ size = 13 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm3.5 12.1-1.4 1.4L12 13.4l-2.1 2.1-1.4-1.4L10.6 12 8.5 9.9l1.4-1.4L12 10.6l2.1-2.1 1.4 1.4L13.4 12l2.1 2.1z" />
  </svg>
)

const CATEGORY_COLOR: Record<string, string> = {
  focus: '#3B82F6',
  insight: '#8B5CF6',
  reminder: '#F59E0B'
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'insight', label: 'Insights' },
  { key: 'focus', label: 'Focus' },
  { key: 'reminder', label: 'Reminders' }
]

export function InsightsPage() {
  const store = useProactive()
  const { settings, update } = useSettings()
  const [filter, setFilter] = useState('all')
  const unread = store.insights.filter((i) => i.read === 0).length

  useEffect(() => {
    void store.load()
    // Mark everything read shortly after opening (so the unread badge is visible first).
    const t = setTimeout(() => void store.markAllRead(), 1500)
    return () => clearTimeout(t)
  }, [])

  if (!settings) return null
  const counts = insightCounts(store.insights)
  const q = store.search.trim().toLowerCase()
  const filtered = store.insights.filter((i) => {
    if (filter !== 'all' && i.category !== filter) return false
    if (!q) return true
    return (
      i.title.toLowerCase().includes(q) ||
      i.body.toLowerCase().includes(q) ||
      (i.sourceApp?.toLowerCase().includes(q) ?? false)
    )
  })

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ fontSize: 19, fontWeight: 700 }}>Insights</span>
            {unread > 0 && (
              <span
                style={{
                  minWidth: 20,
                  height: 20,
                  padding: '0 6px',
                  borderRadius: 10,
                  background: 'var(--purple-primary)',
                  color: '#fff',
                  fontSize: 11,
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                {unread}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            Omi watches your screen and surfaces what matters, memories and tasks are filed automatically
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {settings.proactiveEnabled && (
            <button className="btn-secondary" style={{ fontSize: 12 }} onClick={() => void store.runNow()}>
              {store.status?.running ? 'Analyzing…' : 'Analyze now'}
            </button>
          )}
          <button
            className={`btn-primary`}
            style={{ fontSize: 12, padding: '8px 14px' }}
            onClick={() => void update({ proactiveEnabled: !settings.proactiveEnabled })}
          >
            {settings.proactiveEnabled ? 'On' : 'Turn on'}
          </button>
        </div>
      </div>

      {!settings.proactiveEnabled ? (
        <div className="section" style={{ padding: 20, lineHeight: 1.6 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Proactive assistant is off</div>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
            When on, Omi periodically reads your recent screen activity (using the same on-device capture as Rewind)
            and extracts durable memories, action items, and the occasional useful nudge. Memories and tasks sync to
            your account; nudges show up here and in the floating bar. Nothing is uploaded except the short text sent
            to the model for analysis.
          </div>
          <button
            className="btn-primary"
            style={{ marginTop: 14 }}
            onClick={() => void update({ proactiveEnabled: true, rewindEnabled: true })}
          >
            Enable proactive assistant
          </button>
        </div>
      ) : store.insights.length === 0 ? (
        <EmptyState
          title="No insights yet"
          subtitle="Omi analyzes your screen every few minutes. As soon as something useful surfaces, it'll appear here."
        />
      ) : (
        <>
          <div style={{ display: 'flex', gap: 7, marginBottom: 14, alignItems: 'center' }}>
            {FILTERS.map((f) => {
              const c = f.key === 'all' ? store.insights.length : counts[f.key] ?? 0
              return (
                <button key={f.key} className={`chip ${filter === f.key ? 'active' : ''}`} onClick={() => setFilter(f.key)}>
                  {f.label}
                  <span
                    className="tnum"
                    style={{
                      fontSize: 10.5,
                      fontWeight: 600,
                      padding: '1px 6px',
                      borderRadius: 8,
                      background: filter === f.key ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)',
                      color: filter === f.key ? 'var(--text-primary)' : 'var(--text-quaternary)'
                    }}
                  >
                    {c}
                  </span>
                </button>
              )
            })}
            <span style={{ flex: 1 }} />
            {/* Search field, ported from FocusPage.swift history search */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                width: 200,
                padding: '6px 10px',
                borderRadius: 10,
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border)'
              }}
            >
              <span style={{ color: 'var(--text-quaternary)', display: 'inline-flex' }}>
                <IconSearch />
              </span>
              <input
                value={store.search}
                onChange={(e) => store.setSearch(e.target.value)}
                placeholder="Search…"
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  fontSize: 13
                }}
              />
              {store.search && (
                <button
                  onClick={() => store.setSearch('')}
                  title="Clear"
                  style={{ color: 'var(--text-quaternary)', display: 'inline-flex', flexShrink: 0 }}
                >
                  <IconClear />
                </button>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map((i) => (
            <div key={i.id} className="card" style={{ padding: 14, display: 'flex', gap: 12 }}>
              <div
                style={{
                  width: 4,
                  borderRadius: 2,
                  background: CATEGORY_COLOR[i.category] || 'var(--purple-primary)',
                  flexShrink: 0
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{i.title}</span>
                  {i.read === 0 && (
                    <span style={{ width: 7, height: 7, borderRadius: 4, background: 'var(--purple-primary)' }} />
                  )}
                  <span style={{ flex: 1 }} />
                  <span style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
                    {i.sourceApp ? `${i.sourceApp} · ` : ''}
                    {timeAgo(new Date(i.ts).toISOString())}
                  </span>
                  <button
                    onClick={() => void store.remove(i.id)}
                    title="Dismiss"
                    style={{ color: 'var(--text-quaternary)', padding: 2 }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                    onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
                  >
                    <IconTrash size={13} />
                  </button>
                </div>
                <div className="text-selectable" style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.55 }}>
                  {i.body}
                </div>
              </div>
            </div>
          ))}
          </div>
        </>
      )}
    </div>
  )
}
