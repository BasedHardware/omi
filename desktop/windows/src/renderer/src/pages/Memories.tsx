import { useCallback, useEffect, useRef, useState } from 'react'
import { Brain, Plus, Loader2, CheckSquare, Trash2, X, Search } from 'lucide-react'
import { useMemories, type Memory } from '../hooks/useMemories'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { BrainGraph } from '../components/graph/LazyBrainGraph'
import { useMemoryGraph } from '../hooks/useMemoryGraph'
import { toast } from '../lib/toast'
import { fetchAllMemories, deleteMemoriesPaced } from '../lib/memoriesBulk'
import { isAppIndexMemory } from '../lib/memoryCleanup'
import { filterMemories } from '../lib/memorySearch'

// Cap how many cards render at once so a multi-thousand list stays responsive;
// selection still operates on the full (filtered) set, not just what's rendered.
const RENDER_CAP = 400

function sortMemoriesNewestFirst(list: Memory[]): Memory[] {
  return [...list].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
}

export function Memories(): React.JSX.Element {
  const { memories, loading, error, createMemory, refresh } = useMemories()
  // Pass the live memories so the brain map scopes the server KG to entities
  // that reference a memory you actually have (no account-wide bloat / phantoms),
  // drops the layer when empty, and refetches on add/delete.
  const { graph: brainGraph, centerNodeId } = useMemoryGraph(memories)
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')

  // Manage mode: load ALL memories, multi-select, and delete the selection.
  const [manage, setManage] = useState(false)
  const [all, setAll] = useState<Memory[] | null>(null) // full set, owned locally so deletes can drop rows
  const [loadingAll, setLoadingAll] = useState(false)
  const loadingAllPromise = useRef<Promise<Memory[] | null> | null>(null)
  const [manageFilter, setManageFilter] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [tally, setTally] = useState({ deleted: 0, failed: 0 })
  const stopRequested = useRef(false)

  const loadAllMemories = useCallback(async (): Promise<Memory[] | null> => {
    if (all) return all
    if (loadingAllPromise.current) return loadingAllPromise.current

    setLoadingAll(true)
    loadingAllPromise.current = fetchAllMemories()
      .then((list) => {
        const sorted = sortMemoriesNewestFirst(list)
        setAll(sorted)
        return sorted
      })
      .catch((e) => {
        toast('Could not load all memories', { tone: 'error', body: (e as Error).message })
        return null
      })
      .finally(() => {
        loadingAllPromise.current = null
        setLoadingAll(false)
      })

    return loadingAllPromise.current
  }, [all])

  useEffect(() => {
    if (!manage && search.trim() && all === null) {
      void loadAllMemories()
    }
  }, [all, loadAllMemories, manage, search])

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
      setAll(null)
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
    await loadAllMemories()
  }

  const exitManage = (): void => {
    setManage(false)
    setSelected(new Set())
    setManageFilter('')
  }

  const searchQuery = search.trim()
  const activeQuery = manage ? manageFilter : search
  const source = manage ? (all ?? []) : searchQuery ? (all ?? memories) : memories
  const filtered = filterMemories(source, activeQuery)
  const rendered = filtered.slice(0, RENDER_CAP)
  const isLoadingSearchCorpus = !manage && Boolean(searchQuery) && loadingAll && all === null

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
    stopRequested.current = false
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
      () => stopRequested.current
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
    : searchQuery
      ? isLoadingSearchCorpus
        ? 'Searching all memories…'
        : `${filtered.length} matching memor${filtered.length === 1 ? 'y' : 'ies'}`
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

      {!manage && (
        <div className="border-b border-white/5 px-6 py-3 lg:px-10">
          <div className="relative mx-auto max-w-4xl">
            {loadingAll && searchQuery ? (
              <Loader2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-text-tertiary" />
            ) : (
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
            )}
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onFocus={() => {
                if (search.trim()) void loadAllMemories()
              }}
              placeholder="Search memories..."
              className="input-field w-full py-2 pl-10 pr-10 text-sm"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 rounded-md p-1 text-text-tertiary transition-colors hover:bg-white/10 hover:text-text-primary"
                title="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      )}

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
            Select all {manageFilter.trim() ? 'matching' : ''} ({filtered.length})
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
                  onClick={() => {
                    stopRequested.current = true
                  }}
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

        {!manage && !searchQuery && brainGraph.nodes.length > 0 && (
          <div className="mx-auto mb-6 max-w-4xl">
            <div className="surface-card relative h-80 overflow-hidden p-0">
              <BrainGraph
                graph={brainGraph}
                centerNodeId={centerNodeId}
                interactive={false}
                pauseWhenHidden
              />
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

        {!loading &&
          !error &&
          !isLoadingSearchCorpus &&
          memories.length > 0 &&
          filtered.length === 0 &&
          !composing && (
            <EmptyState
              icon={Search}
              title="No matching memories"
              description="Try a different search term."
            />
          )}

        <ul className="mx-auto grid max-w-4xl grid-cols-1 gap-3 lg:grid-cols-2">
          {rendered.map((m) => {
            const isSel = selected.has(m.id)
            return (
              <li
                key={m.id}
                onClick={manage ? () => toggle(m.id) : undefined}
                className={`surface-card-interactive p-5 ${manage ? 'cursor-pointer' : ''} ${
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
                      {m.category && <span className="badge text-text-tertiary">{m.category}</span>}
                      {m.tags && m.tags.length > 0 && (
                        <span className="truncate text-text-quaternary">{m.tags.join(' · ')}</span>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
        {filtered.length > RENDER_CAP && (
          <p className="mx-auto mt-4 max-w-4xl text-center text-sm text-text-tertiary">
            Showing first {RENDER_CAP} of {filtered.length}
            {manage
              ? `. Selection and delete still apply to all ${manageFilter.trim() ? 'matching ' : ''}${filtered.length}.`
              : '. Refine your search to narrow the results.'}
          </p>
        )}
      </div>
    </div>
  )
}
