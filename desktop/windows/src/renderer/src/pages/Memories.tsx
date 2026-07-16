import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Brain, Plus, Loader2, CheckSquare, Trash2, X, Search, Maximize2 } from 'lucide-react'
import { useMemories, type Memory } from '../hooks/useMemories'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { BrainGraph } from '../components/graph/LazyBrainGraph'
import { useMemoryGraph } from '../hooks/useMemoryGraph'
import { toast } from '../lib/toast'
import { fetchAllMemories, deleteMemoriesPaced } from '../lib/memoriesBulk'
import { isAppIndexMemory } from '../lib/memoryCleanup'
import {
  categoryOf,
  filterMemories,
  MEMORY_CATEGORIES,
  type MemoryCategory,
  type MemoryLayerFilter
} from '../lib/memoryFilters'
import { MemoryCard } from '../components/memories/MemoryCard'
import { MemoryFilterBar } from '../components/memories/MemoryFilterBar'
import { MemoryDetailSheet } from '../components/memories/MemoryDetailSheet'
import { UndoDeleteToast } from '../components/memories/UndoDeleteToast'

// Cap how many cards render at once so a multi-thousand list stays responsive;
// filtering/selection still operate on the full (filtered) set, not just what's
// rendered.
const RENDER_CAP = 400

const emptyCategorySet = (): Set<MemoryCategory> => new Set<MemoryCategory>()

export function Memories(): React.JSX.Element {
  const navigate = useNavigate()
  const {
    memories,
    loading,
    error,
    canonicalLifecycleExposed,
    createMemory,
    editMemory,
    setMemoryVisibility,
    deleteMemory,
    refresh
  } = useMemories()
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

  // Compose (add memory).
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // Default-mode filters.
  const [search, setSearch] = useState('')
  const [categories, setCategories] = useState<Set<MemoryCategory>>(emptyCategorySet)
  const [layer, setLayer] = useState<MemoryLayerFilter>('default')

  // Detail sheet + per-memory mutation busy flags.
  const [detailMemory, setDetailMemory] = useState<Memory | null>(null)
  const [togglingVis, setTogglingVis] = useState(false)

  // Undo-delete: a deleted memory is hidden locally and the server DELETE is
  // held for a countdown window. Committing (timeout or explicit dismiss) fires
  // the real delete; undo just clears the pending state. Only one delete is
  // pending at a time — starting a second commits the first immediately.
  const [pendingDelete, setPendingDelete] = useState<Memory | null>(null)
  // Ids whose server delete has already been committed, so a given memory fires
  // DELETE /v3/memories/<id> at most once. Guards two double-fire paths: the
  // undo toast's countdown elapsing within ~100ms of the user clicking its X
  // (both call onCommit), and StrictMode double-invoking dev code. Cleared on
  // failure so a failed delete can still be retried.
  const committedDeleteIds = useRef<Set<string>>(new Set())

  // Manage mode: load ALL memories, multi-select, and delete the selection.
  const [manage, setManage] = useState(false)
  const [all, setAll] = useState<Memory[] | null>(null)
  const [loadingAll, setLoadingAll] = useState(false)
  const [manageFilter, setManageFilter] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [tally, setTally] = useState({ deleted: 0, failed: 0 })
  const stopRef = useRef({ stop: false }).current

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

  const onEdit = async (id: string, content: string): Promise<void> => {
    try {
      await editMemory(id, content)
      // Reflect the new content in the open sheet without a refetch — otherwise
      // the sheet keeps rendering the stale detailMemory prop and the edit looks
      // like it reverted. Mirrors onToggleVisibility below.
      setDetailMemory((cur) => (cur && cur.id === id ? { ...cur, content } : cur))
    } catch (e) {
      toast('Could not update memory', { tone: 'error', body: (e as Error).message })
      throw e
    }
  }

  const onToggleVisibility = async (m: Memory): Promise<void> => {
    if (togglingVis) return
    setTogglingVis(true)
    try {
      await setMemoryVisibility(m.id, m.visibility === 'public' ? 'private' : 'public')
      // Reflect the flip in the open sheet without a refetch.
      setDetailMemory((cur) =>
        cur && cur.id === m.id
          ? { ...cur, visibility: m.visibility === 'public' ? 'private' : 'public' }
          : cur
      )
    } catch (e) {
      toast('Could not change visibility', { tone: 'error', body: (e as Error).message })
    } finally {
      setTogglingVis(false)
    }
  }

  // Commit a held delete to the server. Idempotent per id (see
  // committedDeleteIds). Clears the pending slot if it still points at this
  // memory. Failures revert inside deleteMemory + surface a toast, and release
  // the id so the delete can be retried.
  const commitDelete = async (m: Memory): Promise<void> => {
    if (committedDeleteIds.current.has(m.id)) return
    committedDeleteIds.current.add(m.id)
    setPendingDelete((cur) => (cur?.id === m.id ? null : cur))
    try {
      await deleteMemory(m.id)
    } catch (e) {
      committedDeleteIds.current.delete(m.id)
      toast('Could not delete memory', { tone: 'error', body: (e as Error).message })
    }
  }

  const requestDelete = (m: Memory): void => {
    setDetailMemory(null)
    // Starting a new delete commits any already-pending one right away. Commit
    // OUTSIDE the state updater — an updater must be pure, and StrictMode
    // double-invokes it in dev, which would fire the delete twice.
    if (pendingDelete && pendingDelete.id !== m.id) void commitDelete(pendingDelete)
    setPendingDelete(m)
  }

  const undoDelete = (): void => setPendingDelete(null)

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
    setManageFilter('')
  }

  // Default-mode derived lists. Hide the memory whose delete is counting down so
  // the undo window feels immediate.
  const visibleBase = useMemo(
    () => (pendingDelete ? memories.filter((m) => m.id !== pendingDelete.id) : memories),
    [memories, pendingDelete]
  )
  // Category counts reflect the current search + layer (but not the category
  // selection itself), so the popover shows how many memories each category
  // would add.
  const categoryCounts = useMemo(() => {
    const afterSearchLayer = filterMemories(visibleBase, {
      search,
      categories: emptyCategorySet(),
      layer,
      thisDeviceOnly: false
    })
    const counts = Object.fromEntries(MEMORY_CATEGORIES.map((c) => [c, 0])) as Record<
      MemoryCategory,
      number
    >
    for (const m of afterSearchLayer) counts[categoryOf(m)]++
    return counts
  }, [visibleBase, search, layer])

  const filtered = useMemo(
    () => filterMemories(visibleBase, { search, categories, layer, thisDeviceOnly: false }),
    [visibleBase, search, categories, layer]
  )
  const rendered = filtered.slice(0, RENDER_CAP)
  const hasActiveFilters = search.trim().length > 0 || categories.size > 0 || layer !== 'default'

  const clearFilters = (): void => {
    setSearch('')
    setCategories(emptyCategorySet())
    setLayer('default')
  }

  const toggleCategory = (c: MemoryCategory): void =>
    setCategories((s) => {
      const n = new Set(s)
      if (n.has(c)) n.delete(c)
      else n.add(c)
      return n
    })

  // Manage-mode derived list + selection.
  const manageSource = all ?? []
  const mq = manageFilter.trim().toLowerCase()
  const manageFiltered = mq
    ? manageSource.filter((m) => m.content?.toLowerCase().includes(mq))
    : manageSource
  const manageRendered = manageFiltered.slice(0, RENDER_CAP)

  const toggleSel = (id: string): void =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const selectAllFiltered = (): void => setSelected(new Set(manageFiltered.map((m) => m.id)))
  const selectJunk = (): void =>
    setSelected(new Set(manageSource.filter(isAppIndexMemory).map((m) => m.id)))
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
      : `${manageFiltered.length} shown${selected.size ? ` · ${selected.size} selected` : ''}`
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
                title="Add a memory"
              >
                <Plus className="h-4 w-4" />
                New
              </button>
            </div>
          )
        }
      />

      {/* Default-mode filter bar */}
      {!manage && (
        <div className="border-b border-white/5 px-6 py-3 lg:px-10">
          <MemoryFilterBar
            search={search}
            onSearchChange={setSearch}
            categories={categories}
            onToggleCategory={toggleCategory}
            onClearCategories={() => setCategories(emptyCategorySet())}
            categoryCounts={categoryCounts}
            layerExposed={canonicalLifecycleExposed}
            layer={layer}
            onLayerChange={setLayer}
          />
        </div>
      )}

      {/* Manage-mode toolbar */}
      {manage && (
        <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-6 py-3 lg:px-10">
          <input
            value={manageFilter}
            onChange={(e) => setManageFilter(e.target.value)}
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
            Select all {mq ? 'matching' : ''} ({manageFiltered.length})
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

        {/* Empty (no memories at all) */}
        {!loading && !error && memories.length === 0 && !composing && (
          <EmptyState
            icon={Brain}
            title="No memories yet"
            description="Memories are distilled insights from your conversations. They will show up here as Omi learns about you."
          />
        )}

        {/* No results (filtered empty, default mode) */}
        {!manage && !loading && memories.length > 0 && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-12 text-center text-white/55">
            <Search className="mb-3 h-9 w-9 opacity-40" />
            <p className="text-sm">No results</p>
            <p className="mt-1 text-xs text-white/40">Try a different search or filter.</p>
            {hasActiveFilters && (
              <button onClick={clearFilters} className="btn-ghost mt-4 px-3 py-1.5 text-sm">
                Clear filters
              </button>
            )}
          </div>
        )}

        {/* Default-mode card grid */}
        {!manage && (
          <ul className="mx-auto grid max-w-4xl grid-cols-1 gap-3 lg:grid-cols-2">
            {rendered.map((m) => (
              <MemoryCard key={m.id} memory={m} onOpen={setDetailMemory} />
            ))}
          </ul>
        )}
        {!manage && filtered.length > RENDER_CAP && (
          <p className="mx-auto mt-4 max-w-4xl text-center text-sm text-text-tertiary">
            Showing first {RENDER_CAP} of {filtered.length}.
          </p>
        )}

        {/* Manage-mode selectable list */}
        {manage && (
          <ul className="mx-auto grid max-w-4xl grid-cols-1 gap-3 lg:grid-cols-2">
            {manageRendered.map((m) => {
              const isSel = selected.has(m.id)
              return (
                <li
                  key={m.id}
                  onClick={() => toggleSel(m.id)}
                  className={`surface-card-interactive group cursor-pointer p-5 ${
                    isSel ? 'ring-2 ring-white/40' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={() => toggleSel(m.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1.5 h-4 w-4 shrink-0"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-3 text-sm leading-relaxed text-text-primary">
                        {m.content}
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-quaternary">
                        <time>{new Date(m.created_at).toLocaleString()}</time>
                        {m.category && (
                          <span className="badge text-text-tertiary">{m.category}</span>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        {manage && manageFiltered.length > RENDER_CAP && (
          <p className="mx-auto mt-4 max-w-4xl text-center text-sm text-text-tertiary">
            Showing first {RENDER_CAP} of {manageFiltered.length}. Selection and delete still apply
            to all {mq ? 'matching' : ''} {manageFiltered.length}.
          </p>
        )}
      </div>

      {/* Detail sheet */}
      {detailMemory && (
        <MemoryDetailSheet
          key={detailMemory.id}
          memory={detailMemory}
          onClose={() => setDetailMemory(null)}
          onEdit={onEdit}
          onToggleVisibility={onToggleVisibility}
          onDelete={requestDelete}
          onOpenConversation={(id) => {
            setDetailMemory(null)
            navigate(`/conversations/${id}`)
          }}
          togglingVisibility={togglingVis}
        />
      )}

      {/* Undo-delete countdown */}
      {pendingDelete && (
        <UndoDeleteToast
          key={pendingDelete.id}
          onUndo={undoDelete}
          onCommit={() => void commitDelete(pendingDelete)}
        />
      )}
    </div>
  )
}
