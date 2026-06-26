import React, { useEffect, useRef, useState } from 'react'
import { IconExternal, IconMic, IconSearch, IconStar, IconStop, IconTrash } from '../../components/Icons'
import { EmptyState, Spinner, Toggle } from '../../components/ui'
import { SpeakerModal, type SpeakerModalResult } from '../../components/SpeakerModal'
import { api } from '../../api/client'
import {
  conversationDurationSeconds,
  elapsedClock,
  formatDuration,
  segmentClock,
  speakerColor,
  timeAgo
} from '../../lib/format'
import { waveformBarColor, waveformBarHeight } from '../../lib/audio'
import { createPerson, personName as lookupPersonName, setSpeakerName, speakerName } from '../../lib/speakers'
import type { ServerConversation, ServerTranscriptSegment } from '../../api/types'
import { useConversations, useLive } from '../../stores/conversations'
import { useFolders } from '../../stores/folders'

export function ConversationsPage() {
  const store = useConversations()
  const live = useLive()
  const folders = useFolders()
  const [query, setQuery] = useState('')
  const [mergeMode, setMergeMode] = useState(false)
  const [mergeSel, setMergeSel] = useState<string[]>([])
  const searchTimer = useRef<number | null>(null)

  useEffect(() => {
    void store.load()
    void folders.load()
    void store.loadPeople()
  }, [])

  const visibleItems = folders.activeFolderId
    ? store.items.filter((c) => c.folder_id === folders.activeFolderId)
    : store.items

  const toggleMergeSel = (id: string) =>
    setMergeSel((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const doMerge = async () => {
    if (mergeSel.length < 2) return
    try {
      await api.mergeConversations(mergeSel)
    } catch {
      // ignore
    }
    setMergeMode(false)
    setMergeSel([])
    await store.load()
  }

  const onSearch = (q: string) => {
    setQuery(q)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => void store.search(q), 350)
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* List pane */}
      <div
        style={{
          width: 330,
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0
        }}
      >
        <div style={{ padding: '44px 14px 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: 18, fontWeight: 600 }}>Conversations</span>
            {store.loading && <Spinner size={14} />}
          </div>

          {/* Record control */}
          <div className="section" style={{ padding: 12, marginBottom: 10 }}>
            {live.status === 'idle' ? (
              <>
                <button
                  className="btn-primary"
                  style={{ width: '100%' }}
                  onClick={() => void live.start()}
                >
                  <IconMic size={15} /> Start Recording
                </button>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginTop: 10,
                    fontSize: 12,
                    color: 'var(--text-quaternary)'
                  }}
                >
                  <span>Capture system audio (meetings)</span>
                  <Toggle on={live.systemAudio} onChange={live.setSystemAudio} />
                </div>
                {live.statusDetail && (
                  <div style={{ fontSize: 11.5, color: 'var(--warning)', marginTop: 8 }}>{live.statusDetail}</div>
                )}
              </>
            ) : (
              <>
                <button
                  className="btn-secondary"
                  style={{ width: '100%', borderColor: 'rgba(239,68,68,0.5)', color: 'var(--error)' }}
                  onClick={() => void live.stop()}
                  disabled={live.status === 'stopping'}
                >
                  {live.status === 'stopping' ? (
                    <>
                      <Spinner size={13} /> Saving conversation…
                    </>
                  ) : (
                    <>
                      <IconStop size={14} />
                      {live.status === 'connecting' ? 'Connecting…' : 'Stop Recording'}
                    </>
                  )}
                </button>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 9 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      background: live.status === 'recording' ? 'var(--error)' : 'var(--warning)',
                      animation: 'pulse 1.4s ease-in-out infinite'
                    }}
                  />
                  <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)', flex: 1, minWidth: 0 }}>
                    {live.status === 'recording'
                      ? `Listening, ${live.segments.length} segment${live.segments.length === 1 ? '' : 's'}`
                      : 'Connecting to transcription…'}
                  </span>
                  <span className="tnum" style={{ fontSize: 11.5, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                    {elapsedClock(live.elapsedSeconds)}
                  </span>
                </div>
                {/* 12-bar live audio waveform (AudioLevelWaveformView) */}
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: 10 }}>
                  <LiveWaveform level={live.level} active={live.status === 'recording'} />
                </div>
              </>
            )}
          </div>

          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 12, top: 9, color: 'var(--text-quaternary)' }}>
              <IconSearch size={14} />
            </span>
            <input
              placeholder="Search conversations"
              value={query}
              onChange={(e) => onSearch(e.target.value)}
              style={{ width: '100%', paddingLeft: 34, borderRadius: 18, background: 'var(--bg-secondary)' }}
            />
          </div>

          {/* Folders + merge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
            <button
              className={`chip ${folders.activeFolderId === null ? 'active' : ''}`}
              style={{ fontSize: 11.5, padding: '3px 10px' }}
              onClick={() => folders.setActive(null)}
            >
              All
            </button>
            {folders.folders.map((f) => (
              <button
                key={f.id}
                className={`chip ${folders.activeFolderId === f.id ? 'active' : ''}`}
                style={{ fontSize: 11.5, padding: '3px 10px' }}
                onClick={() => folders.setActive(f.id)}
                onContextMenu={(e) => {
                  e.preventDefault()
                  if (window.confirm(`Delete folder "${f.name}"?`)) void folders.remove(f.id)
                }}
              >
                {f.name}
              </button>
            ))}
            <button
              className="chip"
              style={{ fontSize: 11.5, padding: '3px 9px' }}
              title="New folder"
              onClick={() => {
                const n = window.prompt('New folder name')
                if (n) void folders.create(n)
              }}
            >
              +
            </button>
            <span style={{ flex: 1 }} />
            <button
              className={`chip ${mergeMode ? 'active' : ''}`}
              style={{ fontSize: 11.5, padding: '3px 10px' }}
              onClick={() => {
                setMergeMode((v) => !v)
                setMergeSel([])
              }}
            >
              {mergeMode ? `Merge (${mergeSel.length})` : 'Merge'}
            </button>
          </div>
          {mergeMode && mergeSel.length >= 2 && (
            <button className="btn-primary" style={{ width: '100%', marginTop: 8, fontSize: 12.5 }} onClick={() => void doMerge()}>
              Merge {mergeSel.length} conversations
            </button>
          )}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 10px' }}>
          {live.status !== 'idle' && live.segments.length > 0 && (
            <button
              onClick={() => store.select(null)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 10px',
                borderRadius: 12,
                background: store.selectedId === null ? 'var(--bg-tertiary)' : 'transparent',
                border: '1px dashed rgba(139,92,246,0.4)',
                marginBottom: 6
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--purple-secondary)' }}>● Live conversation</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
                {live.segments[live.segments.length - 1]?.text.slice(0, 60)}
              </div>
            </button>
          )}
          {visibleItems.map((c) => (
            <ConversationRow
              key={c.id}
              conv={c}
              mergeMode={mergeMode}
              selected={mergeMode ? mergeSel.includes(c.id) : store.selectedId === c.id}
              onSelect={() => (mergeMode ? toggleMergeSel(c.id) : void store.select(c.id))}
            />
          ))}
          {!store.loading && store.items.length === 0 && (
            <EmptyState title="No conversations yet" subtitle="Hit Start Recording, Omi will transcribe, summarize and remember it." />
          )}
        </div>
      </div>

      {/* Detail pane */}
      <div style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>
        {store.selectedId === null && live.segments.length > 0 ? (
          <LiveDetail />
        ) : store.selected ? (
          <ConversationDetail />
        ) : (
          <EmptyState
            title="Select a conversation"
            subtitle="Transcripts, summaries and action items show up here."
          />
        )}
      </div>
    </div>
  )
}

/** 12-bar audio waveform driven by the live RMS level (AudioLevelWaveformView). */
function LiveWaveform({ level, active, barCount = 12 }: { level: number; active: boolean; barCount?: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, height: 32 }}>
      {Array.from({ length: barCount }, (_, i) => (
        <div
          key={i}
          style={{
            width: 3,
            height: waveformBarHeight(level, i, barCount, active),
            borderRadius: 1.5,
            background: waveformBarColor(level, active),
            transition: 'height 0.08s linear, background 0.12s linear'
          }}
        />
      ))}
    </div>
  )
}

/** "NEW" pill for very short or very recently-created conversations (NewBadge). */
function NewPill() {
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: 0.4,
        padding: '1px 6px',
        borderRadius: 6,
        background: 'rgba(139,92,246,0.22)',
        color: 'var(--purple-secondary)',
        flexShrink: 0
      }}
    >
      NEW
    </span>
  )
}

function HoverIconButton({
  title,
  onClick,
  danger,
  children
}: {
  title: string
  onClick: () => void
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      title={title}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      style={{
        width: 22,
        height: 22,
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-raised)',
        color: danger ? 'rgba(239,68,68,0.85)' : 'var(--text-tertiary)',
        flexShrink: 0
      }}
    >
      {children}
    </button>
  )
}

/**
 * A conversation row in the list, ported from ConversationRowView.swift:
 * 36px emoji tile, title + NEW pill + hover action cluster, timestamp · duration,
 * star, rounded 18px card with a purple@0.22 selected tint.
 */
function ConversationRow({
  conv,
  selected,
  mergeMode,
  onSelect
}: {
  conv: ServerConversation
  selected: boolean
  mergeMode: boolean
  onSelect: () => void
}) {
  const store = useConversations()
  const [hover, setHover] = useState(false)

  const durationSecs = conversationDurationSeconds(conv)
  const duration = formatDuration(durationSecs)
  // "NEW": created under a minute ago, or a very short snippet (<30s) just captured.
  const ageSecs = conv.created_at ? (Date.now() - new Date(conv.created_at).getTime()) / 1000 : Infinity
  const isNew = ageSecs < 60 || (durationSecs !== undefined && durationSecs < 30 && ageSecs < 6 * 3600)

  const bg = selected
    ? 'rgba(139,92,246,0.22)'
    : hover
      ? 'var(--bg-raised)'
      : isNew
        ? 'rgba(67,56,159,0.18)'
        : 'transparent'
  const borderColor = selected ? 'rgba(139,92,246,0.4)' : hover ? 'var(--border)' : 'transparent'

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '11px 12px',
        borderRadius: 18,
        background: bg,
        border: `1px solid ${borderColor}`,
        marginBottom: 4,
        cursor: 'pointer'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {mergeMode && (
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: 4,
              flexShrink: 0,
              border: selected ? 'none' : '1.5px solid var(--text-quaternary)',
              background: selected ? 'var(--purple-primary)' : 'transparent',
              color: '#fff',
              fontSize: 10,
              lineHeight: '16px',
              textAlign: 'center'
            }}
          >
            {selected ? '✓' : ''}
          </span>
        )}
        {/* 36px emoji tile */}
        <span
          style={{
            width: 36,
            height: 36,
            flexShrink: 0,
            borderRadius: 12,
            background: 'var(--bg-raised)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16
          }}
        >
          {conv.structured?.emoji || '💬'}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                minWidth: 0
              }}
            >
              {conv.structured?.title || 'Untitled'}
            </span>
            {isNew && <NewPill />}
            {/* Hover action cluster */}
            {hover && !mergeMode && (
              <span style={{ display: 'flex', gap: 4, marginLeft: 'auto', flexShrink: 0 }}>
                <HoverIconButton
                  title="Share (make public)"
                  onClick={async () => {
                    try {
                      await api.setConversationVisibility(conv.id, 'public')
                    } catch {
                      // ignore
                    }
                  }}
                >
                  <IconExternal size={11} />
                </HoverIconButton>
                <HoverIconButton title="Delete" danger onClick={() => void store.remove(conv.id)}>
                  <IconTrash size={11} />
                </HoverIconButton>
              </span>
            )}
          </div>
          <div
            style={{
              fontSize: 11.5,
              color: 'var(--text-tertiary)',
              marginTop: 3,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <span>{timeAgo(conv.created_at)}</span>
            {duration && (
              <>
                <span style={{ color: 'var(--text-quaternary)' }}>·</span>
                <span className="tnum">{duration}</span>
              </>
            )}
            {conv.structured?.category && (
              <>
                <span style={{ color: 'var(--text-quaternary)' }}>·</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {conv.structured.category}
                </span>
              </>
            )}
          </div>
        </div>

        {conv.starred && !hover && (
          <span style={{ color: 'var(--warning)', flexShrink: 0 }}>
            <IconStar size={12} filled />
          </span>
        )}
      </div>
    </div>
  )
}

function LiveDetail() {
  const live = useLive()
  const endRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [live.segments.length])

  return (
    <div style={{ padding: '46px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
        <span style={{ fontSize: 20, fontWeight: 700 }}>Live conversation</span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 9px',
            borderRadius: 999,
            background: 'rgba(239,68,68,0.14)'
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: 4,
              background: live.status === 'recording' ? 'var(--error)' : 'var(--warning)',
              animation: 'pulse 1.4s ease-in-out infinite'
            }}
          />
          <span
            className="tnum"
            style={{ fontSize: 12.5, fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}
          >
            {elapsedClock(live.elapsedSeconds)}
          </span>
        </span>
        <span style={{ marginLeft: 'auto' }}>
          <LiveWaveform level={live.level} active={live.status === 'recording'} barCount={8} />
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginBottom: 18 }}>
        Transcribing in real time, speakers are identified automatically
      </div>
      {live.notes.length > 0 && (
        <div className="section" style={{ padding: 14, marginBottom: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--purple-secondary)', marginBottom: 8 }}>
            Live notes
          </div>
          {live.notes.map((n, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, padding: '3px 0', fontSize: 13, color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--purple-secondary)' }}>•</span>
              {n}
            </div>
          ))}
        </div>
      )}
      <TranscriptList segments={live.segments} />
      <div ref={endRef} />
    </div>
  )
}

function ConversationDetail() {
  const store = useConversations()
  const c = store.selected!
  const people = store.people
  const [editingTitle, setEditingTitle] = useState(false)
  const [title, setTitle] = useState('')
  const [namingSegment, setNamingSegment] = useState<ServerTranscriptSegment | null>(null)

  const actionItems = c.structured?.action_items ?? []
  const segments = c.transcript_segments ?? []
  const durationSecs = conversationDurationSeconds(c)
  const duration = formatDuration(durationSecs)
  const category = c.structured?.category && c.structured.category !== 'other' ? c.structured.category : ''

  return (
    <div style={{ padding: '46px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 28 }}>{c.structured?.emoji || '💬'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          {editingTitle ? (
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => {
                setEditingTitle(false)
                if (title.trim()) void store.rename(c.id, title.trim())
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur()
                if (e.key === 'Escape') setEditingTitle(false)
              }}
              style={{ fontSize: 19, fontWeight: 700, width: '100%' }}
            />
          ) : (
            <div
              style={{ fontSize: 21, fontWeight: 700, cursor: 'text' }}
              title="Click to rename"
              onClick={() => {
                setTitle(c.structured?.title || '')
                setEditingTitle(true)
              }}
            >
              {c.structured?.title || 'Untitled conversation'}
            </div>
          )}
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 3 }}>
            {new Date(c.created_at).toLocaleString()}
          </div>
        </div>
        <button
          onClick={async () => {
            try {
              await api.setConversationVisibility(c.id, 'public')
              window.alert('Conversation is now shareable (public link enabled on omi.me).')
            } catch {
              window.alert('Could not update sharing.')
            }
          }}
          title="Share (make public)"
          style={{ color: 'var(--text-quaternary)', padding: 6 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--purple-secondary)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
        >
          <IconExternal size={15} />
        </button>
        <button
          onClick={() => void store.toggleStar(c.id)}
          title={c.starred ? 'Unstar' : 'Star'}
          style={{ color: c.starred ? 'var(--warning)' : 'var(--text-quaternary)', padding: 6 }}
        >
          <IconStar size={16} filled={c.starred} />
        </button>
        <button
          onClick={() => void store.remove(c.id)}
          title="Delete"
          style={{ color: 'var(--text-quaternary)', padding: 6 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
        >
          <IconTrash size={16} />
        </button>
      </div>

      {/* Summary card (ConversationDetailView's card container) */}
      <div className="card" style={{ margin: '18px 0', overflow: 'hidden', background: 'var(--bg-secondary)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 16px',
            background: 'rgba(37,37,37,0.4)',
            borderBottom: '1px solid var(--border)',
            fontSize: 13,
            fontWeight: 500,
            color: 'var(--text-secondary)'
          }}
        >
          <DocIcon size={12} />
          Conversation Details
        </div>
        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* Summary heading + overview */}
          {c.structured?.overview && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: '#f2bf26', display: 'flex' }}>
                  <IconStar size={13} filled />
                </span>
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Summary</span>
              </div>
              <span
                className="text-selectable"
                style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}
              >
                {c.structured.overview}
              </span>
            </div>
          )}

          {/* Metadata capsule chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <MetaChip icon="source" text={sourceLabel(c.source)} />
            {duration && <MetaChip icon="duration" text={duration} />}
            {category && <MetaChip icon="tag" text={category} />}
          </div>

          {/* Action items as bordered cards */}
          {actionItems.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-secondary)' }}>Action Items</span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: 'var(--purple-secondary)',
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: 'rgba(139,92,246,0.15)'
                  }}
                >
                  {actionItems.length}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {actionItems.map((a, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      gap: 10,
                      alignItems: 'flex-start',
                      padding: 12,
                      borderRadius: 12,
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border)'
                    }}
                  >
                    <span style={{ marginTop: 1, flexShrink: 0, display: 'flex' }}>
                      {a.completed ? <CheckCircle size={16} /> : <EmptyCircle size={16} />}
                    </span>
                    <span
                      className="text-selectable"
                      style={{
                        fontSize: 13.5,
                        color: a.completed ? 'var(--text-tertiary)' : 'var(--text-primary)',
                        textDecoration: a.completed ? 'line-through' : 'none'
                      }}
                    >
                      {a.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-quaternary)', margin: '16px 0 10px' }}>
        TRANSCRIPT
      </div>
      <TranscriptList
        segments={segments}
        personOf={(id) => people.find((p) => p.id === id)?.name ?? lookupPersonName(id)}
        onNameSpeaker={(seg) => setNamingSegment(seg)}
      />
      {segments.length === 0 && (
        <div style={{ fontSize: 13, color: 'var(--text-quaternary)' }}>No transcript stored.</div>
      )}

      {namingSegment && (
        <SpeakerModal
          segment={namingSegment}
          allSegments={segments}
          people={people}
          onCreatePerson={async (name) => {
            const person = await createPerson(name)
            if (person) await store.loadPeople()
            return person
          }}
          onSave={async (result: SpeakerModalResult) => {
            await store.assignSpeaker(c.id, result.segments, {
              isUser: result.isUser,
              personId: result.personId
            })
            setNamingSegment(null)
          }}
          onDismiss={() => setNamingSegment(null)}
        />
      )}
    </div>
  )
}

function sourceLabel(source?: string): string {
  switch (source) {
    case 'desktop':
      return 'Desktop'
    case 'omi':
      return 'omi'
    case 'phone':
      return 'Phone'
    case 'apple_watch':
      return 'Apple Watch'
    case 'workflow':
      return 'Workflow'
    case 'screenpipe':
      return 'Screenpipe'
    default:
      return source ? source.charAt(0).toUpperCase() + source.slice(1) : 'Desktop'
  }
}

function MetaChip({ icon, text }: { icon: 'source' | 'duration' | 'tag'; text: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 10px',
        borderRadius: 999,
        background: 'var(--bg-tertiary)',
        fontSize: 12,
        color: 'var(--text-secondary)',
        whiteSpace: 'nowrap'
      }}
    >
      <span style={{ color: 'var(--text-tertiary)', display: 'flex' }}>
        {icon === 'source' ? <SignalIcon size={11} /> : icon === 'duration' ? <HourglassIcon size={11} /> : <TagIcon size={11} />}
      </span>
      {text}
    </span>
  )
}

// ---- Inline metadata / action-item icons (Icons.tsx owned elsewhere) ----
const DocIcon = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 17h6" />
  </svg>
)
const SignalIcon = ({ size = 11 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 13a9 9 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0" />
    <circle cx="12" cy="19" r="1" fill="currentColor" stroke="none" />
  </svg>
)
const HourglassIcon = ({ size = 11 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M7 3h10M7 21h10M7 3c0 4 5 5 5 9M17 3c0 4-5 5-5 9M7 21c0-4 5-5 5-9M17 21c0-4-5-5-5-9" />
  </svg>
)
const TagIcon = ({ size = 11 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 11l8.5 8.5a2 2 0 0 0 2.8 0l5.2-5.2a2 2 0 0 0 0-2.8L11 3H3z" />
    <circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" stroke="none" />
  </svg>
)
const CheckCircle = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" fill="var(--success)" stroke="none" />
    <path d="M8.5 12.2l2.4 2.4 4.6-5" stroke="#0f0f0f" strokeWidth={2} />
  </svg>
)
const EmptyCircle = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth={1.8}>
    <circle cx="12" cy="12" r="9" />
  </svg>
)

function TranscriptList({
  segments,
  personOf,
  onNameSpeaker
}: {
  segments: ServerTranscriptSegment[]
  /** Resolve a person_id to a display name (saved conversations). */
  personOf?: (personId: string) => string | null | undefined
  /** Open the speaker-naming modal for this segment (saved conversations). */
  onNameSpeaker?: (segment: ServerTranscriptSegment) => void
}) {
  // Local fallback for the live transcript (segments have no backend id yet): name
  // by diarization speaker_id via window.prompt, the original behavior.
  const [, force] = useState(0)
  const renameLocally = (speakerId: number | undefined) => {
    if (speakerId === undefined) return
    const current = speakerName(speakerId) ?? ''
    const name = window.prompt('Name this speaker', current)
    if (name !== null) {
      setSpeakerName(speakerId, name)
      force((n) => n + 1)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {segments.map((s, i) => {
        const personLabel = s.person_id ? personOf?.(s.person_id) ?? null : null
        const localName = speakerName(s.speaker_id)
        const named = personLabel || localName
        const label = s.is_user ? 'You' : named || s.speaker || `Speaker ${(s.speaker_id ?? 0) + 1}`
        const initial = s.is_user ? 'Y' : named ? named.charAt(0).toUpperCase() : String((s.speaker_id ?? 0) + 1)
        const clickable = !s.is_user
        const handleName = () => {
          if (s.is_user) return
          if (onNameSpeaker) onNameSpeaker(s)
          else renameLocally(s.speaker_id)
        }

        const avatar = (
          <span
            style={{
              width: 32,
              height: 32,
              flexShrink: 0,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 13,
              fontWeight: 600,
              color: '#fff',
              background: s.is_user
                ? 'var(--purple-primary)'
                : named
                  ? 'rgba(139,92,246,0.3)'
                  : 'var(--bg-quaternary)'
            }}
          >
            {initial}
          </span>
        )

        return (
          <div
            key={s.id ?? i}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              flexDirection: s.is_user ? 'row-reverse' : 'row',
              justifyContent: 'flex-start'
            }}
          >
            {avatar}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: s.is_user ? 'flex-end' : 'flex-start',
                maxWidth: '78%'
              }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                <span
                  onClick={clickable ? handleName : undefined}
                  title={s.is_user ? undefined : 'Click to name this speaker'}
                  style={{
                    fontSize: 12,
                    fontWeight: named ? 600 : 500,
                    color: named ? 'var(--purple-secondary)' : 'var(--text-tertiary)',
                    cursor: s.is_user ? 'default' : 'pointer'
                  }}
                >
                  {label}
                  {!s.is_user && !named && <span style={{ opacity: 0.5 }}> ✎</span>}
                </span>
              </div>
              <div
                style={{
                  background: speakerColor(s.speaker_id, s.is_user),
                  borderRadius: 'var(--radius-bubble)',
                  padding: '10px 14px'
                }}
              >
                <div className="text-selectable" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                  {s.text}
                </div>
              </div>
              {s.start !== undefined && (
                <span style={{ fontSize: 10.5, color: 'var(--text-quaternary)', marginTop: 3 }}>
                  {segmentClock(s.start)}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
