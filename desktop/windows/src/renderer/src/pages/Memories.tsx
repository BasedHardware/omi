import { useRef, useState } from 'react'
import { Brain, Plus, Loader2, CheckSquare, Trash2, X } from 'lucide-react'
import { useMemories, type Memory } from '../hooks/useMemories'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { BrainGraph } from '../components/graph/LazyBrainGraph'
import { useMemoryGraph } from '../hooks/useMemoryGraph'
import { toast } from '../lib/toast'
import { fetchAllMemories, deleteMemoriesPaced } from '../lib/memoriesBulk'
import { isAppIndexMemory } from '../lib/memoryCleanup'
import {
  DATE_RANGE_LABELS,
  SOURCE_LABELS,
  filterMemories,
  hasActiveFilter,
  sourceCounts,
  type DateRange,
  type MemorySourceKind
} from '../lib/memoryProvenance'
import { FilterChip, ProvenanceLine } from '../components/memories/provenanceUi'
import { SOURCE_ICONS } from '../components/memories/sourceIcons'
import { KnowsBand } from '../components/memories/KnowsBand'
import { ForgetPreviewPanel, ForgetProgressPanel } from '../components/memories/ForgetPanels'
import { MemoryAuditDetail } from '../components/memories/MemoryAuditDetail'

// Cap how many cards render at once so a multi-thousand list stays responsive;
// selection still operates on the full (filtered) set, not just what's rendered.
const RENDER_CAP = 400

const DATE_RANGES: DateRange[] = ['any', 'today', '7d', '30d']

export function Memories(): React.JSX.Element {
  const { memories, loading, error, createMemory, refresh } = useMemories()
  // Pass the live memories so the brain map scopes the server KG to entities
  // that reference a memory you actually have (no account-wide bloat / phantoms),
  // drops the layer when empty, and refetches on add/delete.
  const { graph: brainGraph, centerNodeId } = useMemoryGraph(memories)
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // Audit filters: text, source, and date compose (lib/memoryProvenance) and
  // apply in both the audit view and manage mode.
  const [filter, setFilter] = useState('')
  const [srcFilter, setSrcFilter] = useState<MemorySourceKind | 'all'>('all')
  const [dateFilter, setDateFilter] = useState<DateRange>('any')

  // Audit detail: a memory opened from a card (in-page, like a detail route).
  const [detail, setDetail] = useState<Memory | null>(null)

  // Manage mode: load ALL memories, multi-select, and delete the selection.
  const [manage, setManage] = useState(false)
  const [all, setAll] = useState<Memory[] | null>(null) // full set, owned locally so deletes can drop rows
  const [loadingAll, setLoadingAll] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false) // consequence preview open
  const [deleting, setDeleting] = useState(false)
  const [deleteTotal, setDeleteTotal] = useState(0)
  const [waitSeconds, setWaitSeconds] = useState(0) // active rate-limit pause
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
      // category 'manual' is the provenance stamp: the backend derives
      // manually_added from it (createMemoryBody defaults it too — explicit
      // here because this compose box is exactly the user-typed path).
      await createMemory(text, { category: 'manual' })
      toast('Memory created', { tone: 'info' })
      closeCompose()
    } catch (e) {
      toast('Could not create memory', { tone: 'error', body: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const enterManage = async (): Promise<Memory[]> => {
    setManage(true)
    if (all !== null) return all
    setLoadingAll(true)
    try {
      const list = await fetchAllMemories()
      setAll(list)
      return list
    } catch (e) {
      toast('Could not load all memories', { tone: 'error', body: (e as Error).message })
      return []
    } finally {
      setLoadingAll(false)
    }
  }

  const exitManage = (): void => {
    setManage(false)
    setSelected(new Set())
    setConfirming(false)
    setFilter('')
    setSrcFilter('all')
    setDateFilter('any')
  }

  const source = manage ? (all ?? []) : memories
  const filters = { text: filter, source: srcFilter, range: dateFilter }
  const filtered = filterMemories(source, filters)
  const rendered = filtered.slice(0, RENDER_CAP)
  const filterActive = hasActiveFilter(filters)
  // Source chip counts reflect what clicking each chip would show (text + date
  // filters applied, source not).
  const chipCounts = sourceCounts(filterMemories(source, { text: filter, range: dateFilter }))
  const selectedMemories = source.filter((m) => selected.has(m.id))

  const toggle = (id: string): void =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const selectAllFiltered = (): void => setSelected(new Set(filtered.map((m) => m.id)))
  const selectJunk = (): void => setSelected(new Set(source.filter(isAppIndexMemory).map((m) => m.id)))
  const clearSel = (): void => setSelected(new Set())

  // Runs after the consequence preview is confirmed — the preview replaced the
  // old window.confirm, the paced delete machinery is unchanged.
  const deleteSelected = async (): Promise<void> => {
    const ids = [...selected]
    if (ids.length === 0 || deleting) return
    setConfirming(false)
    setDeleting(true)
    stopRef.stop = false
    setDeleteTotal(ids.length)
    setWaitSeconds(0)
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
      () => stopRef.stop,
      (seconds) => setWaitSeconds(seconds)
    )
    setDeleting(false)
    setWaitSeconds(0)
    toast(`Forgot ${res.deleted} of ${ids.length}`, {
      tone: res.failed ? 'warn' : 'success',
      body: res.failed ? `${res.failed} failed${res.firstError ? ` — ${res.firstError}` : ''}.` : undefined
    })
    await refresh()
  }

  // Scope escalators from the audit detail: enter manage mode with the scope
  // pre-applied (filter-as-selection), then let the consequence preview gate
  // the actual delete.
  const forgetConversation = async (ids: string[]): Promise<void> => {
    setDetail(null)
    const list = await enterManage()
    const known = new Set(list.map((m) => m.id))
    setSelected(new Set(ids.filter((id) => known.has(id))))
    setConfirming(true)
  }

  const forgetSource = async (kind: MemorySourceKind): Promise<void> => {
    setDetail(null)
    setSrcFilter(kind)
    const list = await enterManage()
    setSelected(new Set(filterMemories(list, { source: kind }).map((m) => m.id)))
  }

  const forgottenFromDetail = (id: string): void => {
    setDetail(null)
    setAll((prev) => (prev ? prev.filter((m) => m.id !== id) : prev))
    void refresh()
  }

  if (detail) {
    return (
      <MemoryAuditDetail
        key={detail.id}
        memory={detail}
        all={source}
        onBack={() => setDetail(null)}
        onOpenMemory={setDetail}
        onForgotten={forgottenFromDetail}
        onForgetConversation={(ids) => void forgetConversation(ids)}
        onForgetSource={(kind) => void forgetSource(kind)}
      />
    )
  }

  const headerCount = manage
    ? loadingAll
      ? 'Loading all…'
      : `Forget mode · ${filtered.length} of ${source.length} match${
          selected.size ? ` · ${selected.size} selected` : ''
        }`
    : loading
      ? 'Loading…'
      : `${memories.length} memor${memories.length === 1 ? 'y' : 'ies'}${
          filterActive ? ` · ${filtered.length} match your filter` : ''
        }`

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
              <button onClick={() => void enterManage()} className="btn-ghost px-3 py-2" title="Select & forget memories">
                <CheckSquare className="h-4 w-4" />
                Select
              </button>
              <button onClick={() => setComposing((c) => !c)} className="btn-primary px-3 py-2" title="Create a memory">
                <Plus className="h-4 w-4" />
                New
              </button>
            </div>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-6 py-3 lg:px-10">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by text…"
          className="input-field max-w-xs flex-1 py-1.5 text-sm"
        />
        <span className="ml-1 text-[11px] font-medium tracking-wide text-white/35">SOURCE</span>
        <FilterChip
          label="All"
          count={filterMemories(source, { text: filter, range: dateFilter }).length}
          active={srcFilter === 'all'}
          onClick={() => setSrcFilter('all')}
          disabled={deleting}
        />
        {chipCounts.map(({ kind, count }) => (
          <FilterChip
            key={kind}
            label={SOURCE_LABELS[kind]}
            icon={SOURCE_ICONS[kind]}
            count={count}
            active={srcFilter === kind}
            onClick={() => setSrcFilter(srcFilter === kind ? 'all' : kind)}
            disabled={deleting}
          />
        ))}
        <span className="ml-1 text-[11px] font-medium tracking-wide text-white/35">WHEN</span>
        {DATE_RANGES.map((range) => (
          <FilterChip
            key={range}
            label={DATE_RANGE_LABELS[range]}
            active={dateFilter === range}
            onClick={() => setDateFilter(range)}
            disabled={deleting}
          />
        ))}
      </div>

      {manage && (
        <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-6 py-3 lg:px-10">
          <button onClick={selectJunk} className="btn-ghost px-3 py-1.5 text-sm" disabled={deleting}>
            Select file-index junk
          </button>
          <button onClick={selectAllFiltered} className="btn-ghost px-3 py-1.5 text-sm" disabled={deleting}>
            Select all {filterActive ? 'matching' : ''} ({filtered.length})
          </button>
          <button onClick={clearSel} className="btn-ghost px-3 py-1.5 text-sm" disabled={deleting || !selected.size}>
            Clear
          </button>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setConfirming(true)}
              disabled={deleting || selected.size === 0}
              className="btn-primary px-4 py-1.5 text-sm disabled:opacity-40"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Forget selected ({selected.size})
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {error && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">Failed to load memories: {error}</div>
        )}

        {!manage && !filterActive && brainGraph.nodes.length > 0 && (
          <div className="mx-auto mb-6 max-w-4xl">
            {/* Flat background (no .glass backdrop-filter): layering a WebGL
                canvas over a blurred surface forces the compositor to re-blend
                the graph on every unrelated UI repaint, pinning GPU at 50-60%.
                Keeps the card look via a solid tint + hairline border. */}
            <div className="relative h-80 overflow-hidden rounded-2xl border border-white/[0.08] bg-black/40 p-0">
              <BrainGraph
                graph={brainGraph}
                centerNodeId={centerNodeId}
                interactive={false}
                pauseWhenHidden
                frameLoop="demand"
              />
            </div>
          </div>
        )}

        {!manage && !loading && (
          <KnowsBand memories={memories} activeSource={srcFilter} onPickSource={setSrcFilter} />
        )}

        {manage && confirming && !deleting && !loadingAll && (
          <ForgetPreviewPanel
            selected={selectedMemories}
            filters={filters}
            onCancel={() => setConfirming(false)}
            onConfirm={() => void deleteSelected()}
          />
        )}

        {manage && deleting && (
          <ForgetProgressPanel
            deleted={tally.deleted}
            failed={tally.failed}
            total={deleteTotal}
            waitSeconds={waitSeconds}
            onStop={() => (stopRef.stop = true)}
          />
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
                <button onClick={save} disabled={saving || !draft.trim()} className="btn-primary px-4 py-2 disabled:opacity-40">
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
            return (
              <li
                key={m.id}
                onClick={manage ? () => toggle(m.id) : () => setDetail(m)}
                title={manage ? undefined : 'See where this memory came from'}
                className={`surface-card-interactive cursor-pointer p-5 ${isSel ? 'ring-2 ring-white/40' : ''}`}
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
                      <p className="mt-2.5 line-clamp-3 text-sm leading-relaxed text-text-tertiary">{m.content}</p>
                    )}
                    <ProvenanceLine memory={m} />
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
        {manage && filtered.length > RENDER_CAP && (
          <p className="mx-auto mt-4 max-w-4xl text-center text-sm text-text-tertiary">
            Showing first {RENDER_CAP} of {filtered.length}. Selection and forget still apply to all{' '}
            {filterActive ? 'matching' : ''} {filtered.length}.
          </p>
        )}
      </div>
    </div>
  )
}
