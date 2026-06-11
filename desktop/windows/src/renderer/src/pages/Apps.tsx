import { useEffect, useMemo, useRef, useState } from 'react'
import { LayoutGrid, RefreshCw, Star, Check, Plus, Loader2, Search, SlidersHorizontal, X } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'

type AppEntry = {
  id: string
  name?: string
  description?: string
  image?: string | null
  author?: string | null
  category?: string | null
  rating_avg?: number | null
  installs?: number | null
  is_paid?: boolean
  price?: number | null
}

// Turns raw API categories like "chat-assistants" into "Chat Assistants".
function formatCategory(raw: string): string {
  return raw
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}

function AppCard({ app, isOn, isBusy, onToggle }: { app: AppEntry; isOn: boolean; isBusy: boolean; onToggle: (a: AppEntry) => void }): React.JSX.Element {
  return (
    <div className="surface-card flex flex-col p-5 animate-fade-in">
      <div className="mb-3 flex items-start gap-3">
        {app.image ? (
          <img
            src={app.image}
            alt=""
            className="h-12 w-12 shrink-0 rounded-2xl border border-white/10 object-cover"
            onError={(e) => {
              ;(e.target as HTMLImageElement).style.visibility = 'hidden'
            }}
          />
        ) : (
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
            <LayoutGrid className="h-5 w-5 text-white/60" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-display font-semibold text-white/95">{app.name}</div>
          {app.author && (
            <div className="text-[11px] text-white/45">{app.author}</div>
          )}
        </div>
      </div>
      <p className="mb-4 line-clamp-3 flex-1 text-xs leading-relaxed text-white/65">
        {app.description}
      </p>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] text-white/45">
          {app.rating_avg ? (
            <span className="flex items-center gap-1">
              <Star className="h-3 w-3" />
              {app.rating_avg.toFixed(1)}
            </span>
          ) : null}
          {app.category && <span className="badge">{formatCategory(app.category)}</span>}
        </div>
        <button
          onClick={() => onToggle(app)}
          disabled={isBusy}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
            isOn
              ? 'border-white/20 bg-white/10 text-white'
              : 'border-white/15 bg-transparent text-white/70 hover:bg-white/5 hover:text-white'
          } ${isBusy ? 'opacity-60' : ''}`}
        >
          {isBusy ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : isOn ? (
            <Check className="h-3 w-3" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          {isOn ? 'Installed' : 'Install'}
        </button>
      </div>
    </div>
  )
}

export function Apps(): React.JSX.Element {
  const [apps, setApps] = useState<AppEntry[]>([])
  const [enabled, setEnabled] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [tab, setTab] = useState<'all' | 'installed'>('all')
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const [selectedCats, setSelectedCats] = useState<Set<string>>(new Set())
  const [filterOpen, setFilterOpen] = useState(false)
  const filterRef = useRef<HTMLDivElement>(null)

  const load = async (): Promise<void> => {
    setError(null)
    try {
      const [appsRes, enabledRes] = await Promise.all([
        omiApi.get<AppEntry[]>('/v1/apps', { params: { include_reviews: false } }),
        omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
      ])
      setApps(Array.isArray(appsRes.data) ? appsRes.data : [])
      setEnabled(new Set(Array.isArray(enabledRes.data) ? enabledRes.data : []))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  // Debounce search so filtering doesn't run on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 500)
    return () => clearTimeout(t)
  }, [query])

  // Close the filter dropdown when clicking outside of it.
  useEffect(() => {
    if (!filterOpen) return
    const onClick = (e: MouseEvent): void => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setFilterOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [filterOpen])

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  const toggle = async (a: AppEntry): Promise<void> => {
    if (busy.has(a.id)) return
    setBusy((s) => new Set(s).add(a.id))
    const wasEnabled = enabled.has(a.id)
    // Optimistic
    setEnabled((s) => {
      const next = new Set(s)
      if (wasEnabled) next.delete(a.id)
      else next.add(a.id)
      return next
    })
    try {
      if (wasEnabled) {
        await omiApi.post('/v1/apps/disable', null, { params: { app_id: a.id } })
      } else {
        await omiApi.post('/v1/apps/enable', null, { params: { app_id: a.id } })
      }
    } catch (e) {
      console.error('Toggle app failed:', e)
      // Revert
      setEnabled((s) => {
        const next = new Set(s)
        if (wasEnabled) next.add(a.id)
        else next.delete(a.id)
        return next
      })
    } finally {
      setBusy((s) => {
        const next = new Set(s)
        next.delete(a.id)
        return next
      })
    }
  }

  const LIMIT_PER_CATEGORY = 7

  // Unique categories present in the catalog, sorted by their display name.
  const allCategories = useMemo(() => {
    const set = new Set<string>()
    for (const a of apps) set.add(a.category || 'Other')
    return Array.from(set).sort((x, y) => formatCategory(x).localeCompare(formatCategory(y)))
  }, [apps])

  const toggleCat = (cat: string): void => {
    setSelectedCats((s) => {
      const next = new Set(s)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  const categorized = useMemo(() => {
    const installed = apps.filter((a) => enabled.has(a.id))
    let base = tab === 'installed' ? installed : apps
    if (selectedCats.size > 0) {
      base = base.filter((a) => selectedCats.has(a.category || 'Other'))
    }

    if (debouncedQuery.trim()) {
      const q = debouncedQuery.trim().toLowerCase()
      return {
        search: base.filter(
          (a) =>
            a.name?.toLowerCase().includes(q) ||
            a.description?.toLowerCase().includes(q) ||
            a.category?.toLowerCase().includes(q) ||
            a.author?.toLowerCase().includes(q)
        )
      }
    }

    const categories: Record<string, AppEntry[]> = {}
    const sortedByPopularity = [...base].sort((a, b) => {
      const aScore = (a.rating_avg ?? 0) * Math.log((a.installs ?? 1) + 1)
      const bScore = (b.rating_avg ?? 0) * Math.log((b.installs ?? 1) + 1)
      return bScore - aScore
    })

    for (const app of sortedByPopularity) {
      const cat = app.category || 'Other'
      if (!categories[cat]) categories[cat] = []
      if (categories[cat].length < LIMIT_PER_CATEGORY) {
        categories[cat].push(app)
      }
    }

    return categories
  }, [apps, enabled, debouncedQuery, tab, selectedCats])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Apps"
        subtitle={loading ? 'Loading…' : `${apps.length} available · ${enabled.size} installed`}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
              <button
                onClick={() => setTab('all')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'all'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Marketplace
              </button>
              <button
                onClick={() => setTab('installed')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'installed'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Installed
              </button>
            </div>
            <button
              onClick={onRefresh}
              disabled={refreshing || loading}
              className="btn-ghost px-3 py-2 disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {loading && (
          <div className="mx-auto grid max-w-5xl grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="surface-card p-5">
                <div className="mb-3 flex items-start gap-3">
                  <div className="skeleton h-12 w-12 shrink-0 rounded-2xl" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-4 w-3/4" />
                    <div className="skeleton h-3 w-1/3" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <div className="skeleton h-3 w-full" />
                  <div className="skeleton h-3 w-5/6" />
                  <div className="skeleton h-3 w-2/3" />
                </div>
              </div>
            ))}
          </div>
        )}
        {error && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">{error}</div>
        )}
        {!loading && !error && (
          <div className="mx-auto max-w-5xl space-y-5">
            <div className="flex items-center gap-2">
              <div className="glass-subtle flex flex-1 items-center gap-2 px-4 py-2.5">
                <Search className="h-4 w-4 text-white/45" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search apps…"
                  className="flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
                />
                {query && (
                  <button
                    onClick={() => setQuery('')}
                    className="text-xs text-white/45 hover:text-white"
                  >
                    Clear
                  </button>
                )}
              </div>

              <div ref={filterRef} className="relative">
                <button
                  onClick={() => setFilterOpen((o) => !o)}
                  className={`glass-subtle flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-200 ${
                    filterOpen || selectedCats.size > 0
                      ? 'text-white'
                      : 'text-white/55 hover:text-white/80'
                  }`}
                  title="Filter by category"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  <span className="hidden sm:inline">Filter</span>
                  {selectedCats.size > 0 && (
                    <span className="flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-white/20 px-1.5 text-[11px] font-semibold text-white">
                      {selectedCats.size}
                    </span>
                  )}
                </button>

                {filterOpen && (
                  <div className="surface-card absolute right-0 z-30 mt-2 max-h-80 w-60 overflow-y-auto p-2 shadow-xl">
                    <div className="flex items-center justify-between px-2 py-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-white/45">
                        Categories
                      </span>
                      {selectedCats.size > 0 && (
                        <button
                          onClick={() => setSelectedCats(new Set())}
                          className="text-[11px] text-white/45 hover:text-white"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                    {allCategories.length === 0 ? (
                      <div className="px-2 py-2 text-xs text-white/45">No categories</div>
                    ) : (
                      allCategories.map((cat) => {
                        const checked = selectedCats.has(cat)
                        return (
                          <button
                            key={cat}
                            onClick={() => toggleCat(cat)}
                            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left text-sm text-white/75 transition-colors duration-150 hover:bg-white/5"
                          >
                            <span
                              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-md border transition-colors duration-150 ${
                                checked
                                  ? 'border-white/30 bg-white/20 text-white'
                                  : 'border-white/20 bg-transparent'
                              }`}
                            >
                              {checked && <Check className="h-3 w-3" />}
                            </span>
                            <span className="truncate">{formatCategory(cat)}</span>
                          </button>
                        )
                      })
                    )}
                  </div>
                )}
              </div>
            </div>

            {selectedCats.size > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                {Array.from(selectedCats).map((cat) => (
                  <button
                    key={cat}
                    onClick={() => toggleCat(cat)}
                    className="badge flex items-center gap-1 hover:text-white"
                  >
                    {formatCategory(cat)}
                    <X className="h-3 w-3" />
                  </button>
                ))}
              </div>
            )}

            {query.trim() && categorized.search && categorized.search.length === 0 && (
              <EmptyState
                icon={LayoutGrid}
                title="No apps match"
                description="Try a different search."
              />
            )}

            {!query.trim() && Object.keys(categorized).length === 0 && (
              <EmptyState
                icon={LayoutGrid}
                title={tab === 'installed' ? 'No apps installed' : 'No apps available'}
                description={
                  tab === 'installed'
                    ? 'Browse the Marketplace tab to find apps to install.'
                    : 'Try again later.'
                }
              />
            )}

            {query.trim() ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {categorized.search?.map((a) => <AppCard key={a.id} app={a} isOn={enabled.has(a.id)} isBusy={busy.has(a.id)} onToggle={toggle} />)}
              </div>
            ) : (
              Object.entries(categorized)
                .sort(([catA], [catB]) => {
                  const order = ['Most Popular', 'Featured', 'Integrations', 'Chat Assistants', 'Summary Apps', 'Notifications']
                  const aIdx = order.indexOf(formatCategory(catA))
                  const bIdx = order.indexOf(formatCategory(catB))
                  return (aIdx === -1 ? Infinity : aIdx) - (bIdx === -1 ? Infinity : bIdx)
                })
                .map(([category, categoryApps]) => (
                  <div key={category} className="space-y-3">
                    <h2 className="text-sm font-semibold text-white/80">{formatCategory(category)}</h2>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {categoryApps.map((a) => (
                        <AppCard key={a.id} app={a} isOn={enabled.has(a.id)} isBusy={busy.has(a.id)} onToggle={toggle} />
                      ))}
                    </div>
                  </div>
                ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
