import React, { useEffect, useRef, useState } from 'react'
import { IconPlus, IconTrash } from '../../components/Icons'
import { CategoryChip, EmptyState, Spinner } from '../../components/ui'
import { timeAgo } from '../../lib/format'
import {
  MEMORY_CATEGORIES,
  MEMORY_CATEGORY_LABELS,
  useMemories,
  type MemoryCategory
} from '../../stores/memories'
import { BrainMapGraph, useKnowledgeGraph } from './GraphPage'
import { useAuth } from '../../stores/auth'

// Inline SVGs (this file owns its icons; theme.css/Icons.tsx are off-limits here).
const Svg = (p: React.SVGProps<SVGSVGElement> & { size?: number }) => (
  <svg
    width={p.size ?? 14}
    height={p.size ?? 14}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...p}
  />
)
const SearchIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" />
  </Svg>
)
const ChevronDown = ({ size = 12 }: { size?: number }) => (
  <Svg size={size}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
)
const FilterIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M3 6h18M6 12h12M10 18h4" />
  </Svg>
)
const CheckIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="m20 6-11 11-5-5" />
  </Svg>
)
const LockIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <rect x="4" y="11" width="16" height="9" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </Svg>
)
const GlobeIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18" />
  </Svg>
)
const CloseIcon = ({ size = 12 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
)

const CATEGORY_LABEL = (c: MemoryCategory) => MEMORY_CATEGORY_LABELS[c]

export function MemoriesPage() {
  const store = useMemories()
  const auth = useAuth((s) => s.state)
  const [draft, setDraft] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  // Category dropdown popover state (Apply-on-commit, like the Mac popover).
  const [showFilter, setShowFilter] = useState(false)
  const [catSearch, setCatSearch] = useState('')
  const [pendingTags, setPendingTags] = useState<Set<MemoryCategory>>(new Set())
  const filterRef = useRef<HTMLDivElement | null>(null)

  // Management ("...") menu state.
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    void store.load()
  }, [])

  // Dismiss popovers on outside click.
  useEffect(() => {
    if (!showFilter && !showMenu) return
    const onDown = (e: MouseEvent) => {
      if (showFilter && filterRef.current && !filterRef.current.contains(e.target as Node)) setShowFilter(false)
      if (showMenu && menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMenu(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [showFilter, showMenu])

  const items = store.filtered()
  const hasMemories = store.items.length > 0

  const filterLabel =
    store.selectedTags.size === 0
      ? 'All'
      : store.selectedTags.size === 1
        ? CATEGORY_LABEL([...store.selectedTags][0])
        : `${store.selectedTags.size} selected`

  const visibleCategories = MEMORY_CATEGORIES.filter((c) =>
    catSearch.trim() ? CATEGORY_LABEL(c).toLowerCase().includes(catSearch.trim().toLowerCase()) : true
  ).sort((a, b) => store.tagCount(b) - store.tagCount(a))

  const openFilter = () => {
    setPendingTags(new Set(store.selectedTags))
    setCatSearch('')
    setShowFilter(true)
  }

  const countBadge = (n: number) => (
    <span
      className="tnum"
      style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        background: 'var(--bg-tertiary)',
        borderRadius: 4,
        padding: '1px 6px'
      }}
    >
      {n}
    </span>
  )

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px', position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700 }}>Memories</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            Everything Omi knows about you, editable, deletable, yours
          </div>
        </div>
        {store.loading && <Spinner size={15} />}
      </div>

      {/* Add memory row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <input
          value={draft}
          placeholder="Add something Omi should remember…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && draft.trim()) {
              void store.add(draft)
              setDraft('')
            }
          }}
          style={{ flex: 1 }}
        />
        <button
          className="btn-primary"
          onClick={() => {
            if (draft.trim()) {
              void store.add(draft)
              setDraft('')
            }
          }}
          disabled={!draft.trim()}
        >
          <IconPlus size={14} /> Add
        </button>
      </div>

      {/* Search + category dropdown + management menu */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <span style={{ position: 'absolute', left: 12, top: 9, color: 'var(--text-quaternary)' }}>
            <SearchIcon size={14} />
          </span>
          <input
            placeholder="Search memories…"
            value={store.search}
            onChange={(e) => store.setSearch(e.target.value)}
            style={{ width: '100%', paddingLeft: 34, paddingRight: store.search ? 30 : 12, borderRadius: 14 }}
          />
          {store.search && (
            <button
              onClick={() => store.setSearch('')}
              title="Clear search"
              style={{ position: 'absolute', right: 8, top: 8, color: 'var(--text-quaternary)' }}
            >
              <CloseIcon size={13} />
            </button>
          )}
        </div>

        {/* Category multi-select dropdown */}
        <div style={{ position: 'relative' }} ref={filterRef}>
          <button
            className="btn-secondary"
            style={{
              fontSize: 12.5,
              padding: '8px 12px',
              ...(store.selectedTags.size > 0
                ? { borderColor: 'rgba(139,92,246,0.45)', color: 'var(--text-primary)' }
                : {})
            }}
            onClick={() => (showFilter ? setShowFilter(false) : openFilter())}
          >
            <FilterIcon size={13} />
            {filterLabel}
            <ChevronDown size={11} />
          </button>

          {showFilter && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                right: 0,
                width: 280,
                zIndex: 30,
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-strong)',
                borderRadius: 14,
                boxShadow: 'var(--shadow-content)',
                overflow: 'hidden'
              }}
            >
              {/* search field */}
              <div style={{ padding: '12px 12px 8px' }}>
                <div style={{ position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 10, top: 8, color: 'var(--text-quaternary)' }}>
                    <SearchIcon size={12} />
                  </span>
                  <input
                    autoFocus
                    placeholder="Search categories…"
                    value={catSearch}
                    onChange={(e) => setCatSearch(e.target.value)}
                    style={{ width: '100%', paddingLeft: 30, fontSize: 12.5, borderRadius: 8 }}
                  />
                </div>
              </div>
              <div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />

              <div style={{ maxHeight: 300, overflowY: 'auto', padding: '8px' }}>
                {/* "All" option */}
                <button
                  onClick={() => setPendingTags(new Set())}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    textAlign: 'left',
                    padding: '8px 10px',
                    borderRadius: 8,
                    color: 'var(--text-primary)',
                    fontSize: 13,
                    background: pendingTags.size === 0 ? 'var(--bg-tertiary)' : 'transparent'
                  }}
                >
                  <span style={{ flex: 1 }}>All</span>
                  {countBadge(store.totalCount())}
                  <span style={{ width: 16, color: 'var(--text-primary)' }}>
                    {pendingTags.size === 0 && <CheckIcon size={13} />}
                  </span>
                </button>

                <div style={{ height: 1, background: 'var(--border)', margin: '4px 6px' }} />

                {visibleCategories.map((c) => {
                  const selected = pendingTags.has(c)
                  return (
                    <button
                      key={c}
                      onClick={() =>
                        setPendingTags((prev) => {
                          const next = new Set(prev)
                          if (next.has(c)) next.delete(c)
                          else next.add(c)
                          return next
                        })
                      }
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px',
                        borderRadius: 8,
                        color: 'var(--text-primary)',
                        fontSize: 13,
                        background: selected ? 'var(--bg-tertiary)' : 'transparent'
                      }}
                    >
                      <span style={{ flex: 1 }}>{CATEGORY_LABEL(c)}</span>
                      {countBadge(store.tagCount(c))}
                      <span style={{ width: 16, color: 'var(--text-primary)' }}>
                        {selected && <CheckIcon size={13} />}
                      </span>
                    </button>
                  )
                })}
              </div>

              <div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />
              <div style={{ display: 'flex', gap: 8, padding: 12 }}>
                <button
                  className="btn-secondary"
                  style={{ flex: 1, fontSize: 12.5, padding: '7px 0' }}
                  onClick={() => setPendingTags(new Set())}
                >
                  Clear
                </button>
                <button
                  className="btn-primary"
                  style={{ flex: 1, fontSize: 12.5, padding: '7px 0' }}
                  onClick={() => {
                    store.setSelectedTags(pendingTags)
                    setShowFilter(false)
                  }}
                >
                  Apply
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Management "..." menu */}
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button
            className="btn-secondary"
            style={{ fontSize: 15, padding: '6px 12px', lineHeight: 1 }}
            title="More"
            onClick={() => setShowMenu((v) => !v)}
          >
            …
          </button>
          {showMenu && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                right: 0,
                width: 210,
                zIndex: 30,
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-strong)',
                borderRadius: 12,
                boxShadow: 'var(--shadow-content)',
                overflow: 'hidden',
                padding: '6px'
              }}
            >
              <MenuItem
                disabled={!hasMemories || store.bulkBusy}
                onClick={() => {
                  setShowMenu(false)
                  void store.makeAllPublic()
                }}
              >
                <GlobeIcon size={13} /> Make All Public
              </MenuItem>
              <MenuItem
                disabled={!hasMemories || store.bulkBusy}
                onClick={() => {
                  setShowMenu(false)
                  void store.makeAllPrivate()
                }}
              >
                <LockIcon size={13} /> Make All Private
              </MenuItem>
              <div style={{ height: 1, background: 'var(--border)', margin: '5px 4px' }} />
              <MenuItem
                danger
                disabled={!hasMemories || store.bulkBusy}
                onClick={() => {
                  setShowMenu(false)
                  if (window.confirm(`Permanently delete all ${store.items.length} memories? This cannot be undone.`)) {
                    void store.deleteAll()
                  }
                }}
              >
                <IconTrash size={13} /> Delete All
              </MenuItem>
            </div>
          )}
        </div>
      </div>

      {/* List: Brain Map card is always the first item */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 720 }}>
        <BrainMapCard userName={auth?.name || 'You'} />

        {items.length === 0 && !store.loading ? (
          <EmptyState
            title={store.search || store.selectedTags.size > 0 ? 'No matching memories' : 'No memories here yet'}
            subtitle={
              store.search || store.selectedTags.size > 0
                ? 'Try a different search or category.'
                : 'Memories are extracted from conversations and your screen, or added manually.'
            }
          />
        ) : (
          items.map((m) => (
            <div key={m.id} className="card" style={{ padding: 14, position: 'relative' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                <CategoryChip label={m.category || 'memory'} />
                <span style={{ fontSize: 11, color: 'var(--text-quaternary)', flex: 1 }}>{timeAgo(m.created_at)}</span>
                <button
                  onClick={() => void store.remove(m.id)}
                  title="Delete memory"
                  style={{ color: 'var(--text-quaternary)', padding: 2 }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
                >
                  <IconTrash size={13} />
                </button>
              </div>
              {editingId === m.id ? (
                <textarea
                  autoFocus
                  value={editText}
                  rows={3}
                  onChange={(e) => setEditText(e.target.value)}
                  onBlur={() => {
                    setEditingId(null)
                    if (editText.trim() && editText !== m.content) void store.edit(m.id, editText.trim())
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) e.currentTarget.blur()
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  style={{ width: '100%', fontSize: 13 }}
                />
              ) : (
                <div
                  className="text-selectable"
                  style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--text-secondary)', cursor: 'text' }}
                  title="Click to edit"
                  onClick={() => {
                    setEditingId(m.id)
                    setEditText(m.content)
                  }}
                >
                  {m.content}
                </div>
              )}
            </div>
          ))
        )}

        {/* Load more */}
        {store.hasMore && !store.search && store.selectedTags.size === 0 && (
          <button
            className="btn-secondary"
            style={{ alignSelf: 'center', fontSize: 12.5, marginTop: 2 }}
            onClick={() => void store.loadMore()}
            disabled={store.loadingMore}
          >
            {store.loadingMore ? 'Loading…' : 'Load more memories'}
          </button>
        )}
      </div>

      {/* Undo-delete countdown toast */}
      {store.pendingDelete && (
        <div
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 24,
            transform: 'translateX(-50%)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 18px',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-strong)',
            borderRadius: 20,
            boxShadow: 'var(--shadow-content)'
          }}
        >
          <span style={{ color: 'var(--text-secondary)' }}>
            <IconTrash size={14} />
          </span>
          <span style={{ fontSize: 13.5, color: 'var(--text-primary)' }}>Memory deleted</span>
          <span className="tnum" style={{ fontSize: 12, color: 'var(--text-tertiary)', minWidth: 22, textAlign: 'right' }}>
            {Math.ceil(store.undoRemaining)}s
          </span>
          <button
            onClick={() => store.undoDelete()}
            style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--purple-secondary)' }}
          >
            Undo
          </button>
          <button onClick={() => store.confirmDelete()} title="Dismiss" style={{ color: 'var(--text-tertiary)' }}>
            <CloseIcon size={12} />
          </button>
        </div>
      )}
    </div>
  )
}

function MenuItem({
  children,
  onClick,
  disabled,
  danger
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        width: '100%',
        textAlign: 'left',
        padding: '8px 10px',
        borderRadius: 8,
        fontSize: 13,
        color: danger ? 'var(--error)' : 'var(--text-primary)',
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? 'default' : 'pointer'
      }}
      onMouseEnter={(e) => {
        if (!disabled) e.currentTarget.style.background = 'var(--bg-tertiary)'
      }}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      {children}
    </button>
  )
}

/** Compact Brain Map card embedded at the top of the Memories list. */
function BrainMapCard({ userName }: { userName: string }) {
  const { nodes, edges, loading, rebuilding, rebuild } = useKnowledgeGraph()
  const populated = nodes.length > 0

  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>Brain Map</div>
        <button
          className="btn-secondary"
          style={{ fontSize: 12, padding: '6px 12px' }}
          onClick={() => void rebuild()}
          disabled={rebuilding}
        >
          {rebuilding ? 'Rebuilding…' : 'Rebuild'}
        </button>
      </div>
      <div
        style={{
          height: 280,
          borderRadius: 16,
          overflow: 'hidden',
          background: '#1A1A1A',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        {populated ? (
          <BrainMapGraph nodes={nodes} edges={edges} userName={userName} width={680} height={280} />
        ) : loading || rebuilding ? (
          <Spinner size={20} />
        ) : (
          <div style={{ padding: 18, textAlign: 'center', fontSize: 12.5, color: 'var(--text-tertiary)', maxWidth: 320 }}>
            Brain map will appear once enough linked memories are available.
          </div>
        )}
      </div>
    </div>
  )
}
