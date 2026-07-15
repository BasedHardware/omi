import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Brain,
  Plus,
  Loader2,
  CheckSquare,
  Trash2,
  X,
  Pencil,
  Globe,
  Lock,
  Maximize2
} from 'lucide-react'
import { useMemories, type Memory } from '../hooks/useMemories'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { BrainGraph } from '../components/graph/LazyBrainGraph'
import { useMemoryGraph } from '../hooks/useMemoryGraph'
import { toast } from '../lib/toast'
import { fetchAllMemories, deleteMemoriesPaced } from '../lib/memoriesBulk'
import { isAppIndexMemory } from '../lib/memoryCleanup'

// Cap how many cards render at once so a multi-thousand list stays responsive;
// selection still operates on the full (filtered) set, not just what's rendered.
const RENDER_CAP = 400

export function Memories(): React.JSX.Element {
  const navigate = useNavigate()
  const { memories, loading, error, createMemory, editMemory, setMemoryVisibility, refresh } =
    useMemories()
  // Pass the live memories so the brain map scopes the server KG to entities
  // that reference a memory you actually have (no account-wide bloat / phantoms),
  // drops the layer when empty, and refetches on add/delete.
  const { graph: brainGraph, centerNodeId } = useMemoryGraph(memories)
  // The brain map lazy-loads a ~1MB three.js chunk and then spins up WebGL, so
  // the container can otherwise sit blank for seconds with no hint anything is
  // coming. Track readiness via BrainGraph's onCreated signal, with a bounded
  // fallback so a stalled/failed load (chunk error, WebGL crash) doesn't leave
  // the placeholder showing forever.
  const [graphReady, setGraphReady] = useState(false)
  const hasGraph = brainGraph.nodes.length > 0
  useEffect(() => {
    if (graphReady || !hasGraph) return
    const t = setTimeout(() => setGraphReady(true), 4000)
    return () => clearTimeout(t)
  }, [graphReady, hasGraph])
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // Manage mode: load ALL memories, multi-select, and delete the selection.
  const [manage, setManage] = useState(false)
  const [all, setAll] = useState<Memory[] | null>(null) // full set, owned locally so deletes can drop rows
  const [loadingAll, setLoadingAll] = useState(false)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [tally, setTally] = useState({ deleted: 0, failed: 0 })
  const stopRef = useRef({ stop: false }).current

  // Inline edit (pencil → textarea → save/cancel) and per-row visibility toggle.
  // Delete+recreate destroys the id/lineage the backend's temporal model
  // preserves, so this is the only in-place remediation path on the page.
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [savingEditId, setSavingEditId] = useState<string | null>(null)
  const [togglingVisId, setTogglingVisId] = useState<string | null>(null)

  const startEdit = (m: Memory): void => {
    setEditingId(m.id)
    setEditDraft(m.content)
  }

  const cancelEdit = (): void => {
    setEditingId(null)
    setEditDraft('')
  }

  const saveEdit = async (id: string): Promise<void> => {
    const text = editDraft.trim()
    if (!text || savingEditId) return
    setSavingEditId(id)
    try {
      await editMemory(id, text)
      cancelEdit()
    } catch (e) {
      toast('Could not update memory', { tone: 'error', body: (e as Error).message })
    } finally {
      setSavingEditId(null)
    }
  }

  const toggleVisibility = async (m: Memory): Promise<void> => {
    if (togglingVisId) return
    setTogglingVisId(m.id)
    try {
      await setMemoryVisibility(m.id, m.visibility === 'public' ? 'private' : 'public')
    } catch (e) {
      toast('Could not change visibility', { tone: 'error', body: (e as Error).message })
    } finally {
      setTogglingVisId(null)
    }
  }

  const closeCompose = (): void => {
    setComposing(false)
    setDraft('')
  }

  const save = async (): Promise<void> => {
    const text = draft.trim()
    if (!text || saving) return
    setSaving(true)
    try {
      await createMemory(text)
      toast('Memory created', { tone: 'info' })
      closeCompose()
    } catch (e) {
      toast('Could not create memory', { tone: 'error', body: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const enterManage = async (): Promise<void> => {
    setManage(true)
    if (all === null) {
      setLoadingAll(true)
      try {
        setAll(await fetchAllMemories())
      } catch (e) {
        toast('Could not load all memories', { tone: 'error', body: (e as Error).message })
      } finally {
        setLoadingAll(false)
      }
    }
  }

  const exitManage = (): void => {
    setManage(false)
    setSelected(new Set())
    setFilter('')
  }

  const source = manage ? (all ?? []) : memories
  const q = filter.trim().toLowerCase()
  const filtered = q ? source.filter((m) => m.content?.toLowerCase().includes(q)) : source
  const rendered = filtered.slice(0, RENDER_CAP)

  const toggle = (id: string): void =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const selectAllFiltered = (): void => setSelected(new Set(filtered.map((m) => m.id)))
  const selectJunk = (): void =>
    setSelected(new Set(source.filter(isAppIndexMemory).map((m) => m.id)))
  const clearSel = (): void => setSelected(new Set())

  const deleteSelected = async (): Promise<void> => {
    const ids = [...selected]
    if (ids.length === 0 || deleting) return
    if (
      !window.confirm(
        `Delete ${ids.length} selected memories? The server allows ~60 deletes/hour, so this pauses when the limit is hit (you can stop and resume anytime). This cannot be undone.`
      )
    )
      return
    setDeleting(true)
    stopRef.stop = false
    setTally({ deleted: 0, failed: 0 })
    const res = await deleteMemoriesPaced(
      ids,
      (id, ok, t) => {
        setTally(t)
        if (ok) {
          setAll((prev) => (prev ?? []).filter((m) => m.id !== id))
          setSelected((s) => {
            const n = new Set(s)
            n.delete(id)
            return n
          })
        }
      },
      () => stopRef.stop
    )
    setDeleting(false)
    toast(`Deleted ${res.deleted} of ${ids.length}`, {
      tone: res.failed ? 'warn' : 'success',
      body: res.failed
        ? `${res.failed} failed${res.firstError ? ` — ${res.firstError}` : ''}.`
        : undefined
    })
    await refresh()
  }

  const headerCount = manage
    ? loadingAll
      ? 'Loading all…'
      : `${filtered.length} shown${selected.size ? ` · ${selected.size} selected` : ''}`
    : loading
      ? 'Loading…'
      : `${memories.length} memor${memories.length === 1 ? 'y' : 'ies'}`

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Memories"
        subtitle={headerCount}
        actions={
          manage ? (
            <button onClick={exitManage} className="btn-ghost px-3 py-2" disabled={deleting}>
              <X className="h-4 w-4" />
              Done
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={enterManage}
                className="btn-ghost px-3 py-2"
                title="Select & delete memories"
              >
                <CheckSquare className="h-4 w-4" />
                Select
              </button>
              <button
                onClick={() => setComposing((c) => !c)}
                className="btn-primary px-3 py-2"
                title="Create a memory"
              >
                <Plus className="h-4 w-4" />
                New
              </button>
            </div>
          )
        }
      />

      {manage && (
        <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-6 py-3 lg:px-10">
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by text (e.g. local projects include)…"
            className="input-field max-w-xs flex-1 py-1.5 text-sm"
          />
          <button
            onClick={selectJunk}
            className="btn-ghost px-3 py-1.5 text-sm"
            disabled={deleting}
          >
            Select file-index junk
          </button>
          <button
            onClick={selectAllFiltered}
            className="btn-ghost px-3 py-1.5 text-sm"
            disabled={deleting}
          >
            Select all {q ? 'matching' : ''} ({filtered.length})
          </button>
          <button
            onClick={clearSel}
            className="btn-ghost px-3 py-1.5 text-sm"
            disabled={deleting || !selected.size}
          >
            Clear
          </button>
          <div className="ml-auto flex items-center gap-2">
            {deleting && (
              <>
                <span className="text-sm text-text-tertiary">
                  Deleting {tally.deleted}/{selected.size + tally.deleted}…
                </span>
                <button
                  onClick={() => (stopRef.stop = true)}
                  className="btn-ghost px-3 py-1.5 text-sm"
                >
                  Stop
                </button>
              </>
            )}
            <button
              onClick={deleteSelected}
              disabled={deleting || selected.size === 0}
              className="btn-primary px-4 py-1.5 text-sm disabled:opacity-40"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete selected ({selected.size})
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {error && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">
            Failed to load memories: {error}
          </div>
        )}

        {!manage && hasGraph && (
          <div className="mx-auto mb-6 max-w-4xl">
            {/* Flat background (no .glass backdrop-filter): layering a WebGL
                canvas over a blurred surface forces the compositor to re-blend
                the graph on every unrelated UI repaint, pinning GPU at 50-60%.
                Keeps the card look via a solid tint + hairline border. */}
            <div className="relative h-80 overflow-hidden rounded-2xl border border-white/[0.08] bg-black/40 p-0">
              <div
                className={`absolute inset-0 flex flex-col items-center justify-center gap-3 transition-opacity duration-500 ${
                  graphReady ? 'pointer-events-none opacity-0' : 'opacity-100'
                }`}
                aria-hidden={graphReady}
              >
                <div className="flex items-center gap-2">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span
                      key={i}
                      className="h-2.5 w-2.5 animate-pulse rounded-full bg-white/15"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
                <p className="text-xs text-white/30">Building your memory map…</p>
              </div>
              <div
                className={`h-full w-full transition-opacity duration-500 ${graphReady ? 'opacity-100' : 'opacity-0'}`}
              >
                <BrainGraph
                  graph={brainGraph}
                  centerNodeId={centerNodeId}
                  interactive={false}
                  pauseWhenHidden
                  frameLoop="demand"
                  onReady={() => setGraphReady(true)}
                  // pauseWhenHidden tears down and recreates the canvas when this
                  // tab goes hidden then shown again (e.g. it was pre-warmed in
                  // the background before you navigated here) — fall back to the
                  // loading state for that brief recreation gap instead of a
                  // blank pane; onReady above flips it back once the new canvas
                  // is ready (typically instant, since the layout is cached).
                  onVisibleChange={(v) => {
                    if (!v) setGraphReady(false)
                  }}
                />
              </div>
              {/* Expand to the full-screen, interactive (orbit/pan/zoom) brain
                  map. Sits above the non-interactive card canvas. */}
              <button
                onClick={() => navigate('/knowledge-graph')}
                className="btn-ghost absolute right-3 top-3 z-10 p-2"
                title="Open the full-screen brain map"
                aria-label="Open the full-screen brain map"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {composing && (
          <div className="mx-auto mb-5 max-w-4xl">
            <div className="surface-card animate-fade-in p-4">
              <textarea
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault()
                    void save()
                  } else if (e.key === 'Escape') {
                    closeCompose()
                  }
                }}
                rows={3}
                placeholder="Something Omi should remember about you…"
                className="input-field resize-none"
              />
              <div className="mt-3 flex items-center justify-end gap-2">
                <span className="mr-auto text-xs text-white/35">⌘/Ctrl + Enter to save</span>
                <button onClick={closeCompose} className="btn-ghost px-3 py-2" disabled={saving}>
                  Cancel
                </button>
                <button
                  onClick={save}
                  disabled={saving || !draft.trim()}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && memories.length === 0 && !composing && (
          <EmptyState
            icon={Brain}
            title="No memories yet"
            description="Memories are distilled insights from your conversations. They will show up here as Omi learns about you."
          />
        )}

        <ul className="mx-auto grid max-w-4xl grid-cols-1 gap-3 lg:grid-cols-2">
          {rendered.map((m) => {
            const isSel = selected.has(m.id)
            const isEditing = editingId === m.id
            return (
              <li
                key={m.id}
                onClick={manage ? () => toggle(m.id) : undefined}
                className={`surface-card-interactive group p-5 ${manage ? 'cursor-pointer' : ''} ${
                  isSel ? 'ring-2 ring-white/40' : ''
                }`}
              >
                <div className="flex items-start gap-3">
                  {manage && (
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={() => toggle(m.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1.5 h-4 w-4 shrink-0"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    {isEditing ? (
                      <div className="space-y-2">
                        <textarea
                          autoFocus
                          value={editDraft}
                          onChange={(e) => setEditDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                              e.preventDefault()
                              void saveEdit(m.id)
                            } else if (e.key === 'Escape') {
                              cancelEdit()
                            }
                          }}
                          rows={3}
                          className="input-field resize-none text-sm"
                        />
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={cancelEdit}
                            disabled={savingEditId === m.id}
                            className="btn-ghost px-3 py-1.5 text-sm"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => saveEdit(m.id)}
                            disabled={savingEditId === m.id || !editDraft.trim()}
                            className="btn-primary px-3 py-1.5 text-sm disabled:opacity-40"
                          >
                            {savingEditId === m.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              'Save'
                            )}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="font-display text-lg font-bold leading-snug text-text-primary">
                          {m.headline || m.content.slice(0, 80)}
                        </div>
                        {m.headline && (
                          <p className="mt-2.5 line-clamp-3 text-sm leading-relaxed text-text-tertiary">
                            {m.content}
                          </p>
                        )}
                        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-text-quaternary">
                          <time>{new Date(m.created_at).toLocaleString()}</time>
                          {m.category && (
                            <span className="badge text-text-tertiary">{m.category}</span>
                          )}
                          {m.tags && m.tags.length > 0 && (
                            <span className="truncate text-text-quaternary">
                              {m.tags.join(' · ')}
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                  {!manage && !isEditing && (
                    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-all group-hover:opacity-100">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          void toggleVisibility(m)
                        }}
                        disabled={togglingVisId === m.id}
                        className="rounded-md p-1.5 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70 disabled:opacity-50"
                        title={
                          m.visibility === 'public'
                            ? 'Public — visible to your apps/personas. Click to make private.'
                            : 'Private. Click to make public.'
                        }
                        aria-label={m.visibility === 'public' ? 'Make private' : 'Make public'}
                      >
                        {togglingVisId === m.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : m.visibility === 'public' ? (
                          <Globe className="h-3.5 w-3.5" />
                        ) : (
                          <Lock className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          startEdit(m)
                        }}
                        className="rounded-md p-1.5 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
                        title="Edit memory"
                        aria-label="Edit memory"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
        {manage && filtered.length > RENDER_CAP && (
          <p className="mx-auto mt-4 max-w-4xl text-center text-sm text-text-tertiary">
            Showing first {RENDER_CAP} of {filtered.length}. Selection and delete still apply to all{' '}
            {q ? 'matching' : ''} {filtered.length}.
          </p>
        )}
      </div>
    </div>
  )
}
