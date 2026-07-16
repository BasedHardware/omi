import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutGrid,
  RefreshCw,
  Star,
  Check,
  Plus,
  Loader2,
  Search,
  SlidersHorizontal,
  X,
  AlertTriangle,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { rankSearchResults } from '../lib/appRanking'
import {
  buildCatalog,
  mergeAppPool,
  sectionPreview,
  searchCatalog,
  type CatalogSection
} from '../lib/appCatalog'
import type {
  App as AppEntry,
  AppCatalogItem,
  AppCatalogResponse,
  AppSearchResponse
} from '../lib/omiApi.generated'
import { getCacheUid, readPersistedValue, writePersistedValue } from '../lib/persistentCache'
import { toast } from '../lib/toast'
import { worksExternally, setupUrl, isSetupCompleted, startSetupPolling } from '../lib/appInstall'

// Cap rendered search results so a broad query (e.g. "a") can't mount the whole
// catalog at once. Users refine rather than scroll hundreds of cards.
const SEARCH_LIMIT = 60

// Per-uid cold-start snapshot for the Apps page. Unlike the other surfaces the
// Apps page keeps no in-memory module cache (all component state), so it refetches
// + spins on every open; mirroring the last successful load to localStorage lets a
// cold start paint the grid instantly, then revalidate. `enabled` is a Set at
// runtime, persisted as an array.
type AppsSnapshot = {
  sections: CatalogSection[]
  allApps: AppCatalogItem[]
  installedPool: AppCatalogItem[]
  enabled: string[]
}
const APPS_SURFACE = 'apps'

// Surfaces the backend `detail` on an enable/disable failure ONLY when it is
// user-appropriate and actionable — currently just the disabled-app "…currently
// unavailable…" 400. The other backend details are deliberately omitted: the
// private/paid 403 "You are not authorized…" is non-actionable (and ambiguous —
// same message for both cases) and the external-app 400 "App setup is not completed"
// is handled by the dedicated setup flow, not this quick toggle. macOS swallows ALL
// of these (its bound `errorMessage` has zero read sites); Windows surfaces the
// failure via a toast, and shows the raw detail only where it helps the user.
function userSafeDetail(e: unknown): string | undefined {
  const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
  if (typeof detail === 'string' && /unavailable/i.test(detail)) return detail
  return undefined
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

// Memoized so typing in the search box (which re-renders the Apps page every
// keystroke) doesn't reconcile every card. Relies on a stable `onToggle`
// (useCallback) and primitive isOn/isBusy props.
const AppCard = memo(function AppCard({
  app,
  isOn,
  isBusy,
  isSettingUp,
  onToggle
}: {
  app: AppCatalogItem
  isOn: boolean
  isBusy: boolean
  isSettingUp: boolean
  onToggle: (a: AppCatalogItem) => void
}): React.JSX.Element {
  return (
    <div className="surface-card-flat flex flex-col p-5 animate-fade-in">
      <div className="mb-3 flex items-start gap-3">
        {app.image ? (
          <img
            src={app.image}
            alt=""
            width={48}
            height={48}
            loading="lazy"
            decoding="async"
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
          {app.author && <div className="text-[11px] text-white/45">{app.author}</div>}
        </div>
      </div>
      <p
        className="mb-4 line-clamp-3 flex-1 text-xs leading-relaxed text-white/65"
        title={app.description}
      >
        {app.description}
      </p>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2 text-[11px] text-white/45">
          {app.rating_avg ? (
            <span className="flex shrink-0 items-center gap-1">
              <Star className="h-3 w-3" />
              {app.rating_avg.toFixed(1)}
            </span>
          ) : null}
          {app.category && (
            <span className="badge min-w-0 max-w-full" title={formatCategory(app.category)}>
              <span className="min-w-0 truncate">{formatCategory(app.category)}</span>
            </span>
          )}
        </div>
        <button
          onClick={() => onToggle(app)}
          disabled={isBusy || isSettingUp}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
            isOn
              ? 'border-white/20 bg-white/10 text-white'
              : 'border-white/15 bg-transparent text-white/70 hover:bg-white/5 hover:text-white'
          } ${isBusy || isSettingUp ? 'opacity-60' : ''}`}
        >
          {isBusy || isSettingUp ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : isOn ? (
            <Check className="h-3 w-3" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          {isSettingUp ? 'Setting up…' : isOn ? 'Installed' : 'Install'}
        </button>
      </div>
    </div>
  )
})

// Shared grid wrapper so every list surface (sections, search, filter) renders
// cards identically.
function AppGrid({
  apps,
  enabled,
  busy,
  settingUp,
  onToggle
}: {
  apps: AppCatalogItem[]
  enabled: Set<string>
  busy: Set<string>
  settingUp: Set<string>
  onToggle: (a: AppCatalogItem) => void
}): React.JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {apps.map((a) => (
        <AppCard
          key={a.id}
          app={a}
          isOn={enabled.has(a.id)}
          isBusy={busy.has(a.id)}
          isSettingUp={settingUp.has(a.id)}
          onToggle={onToggle}
        />
      ))}
    </div>
  )
}

export function Apps(): React.JSX.Element {
  // Cold-start snapshot: read once (before initial state) so the grid paints the
  // last-known catalog immediately on app restart instead of a spinner. The
  // revalidating load() below still runs and overwrites with fresh data.
  const [snapshot] = useState<AppsSnapshot | null>(() => {
    const s = readPersistedValue<AppsSnapshot>(APPS_SURFACE)
    if (!s) return null
    // Coerce each field to an array so a malformed snapshot can never seed a
    // non-array into state (which would crash allApps.filter(...) downstream).
    return {
      sections: Array.isArray(s.sections) ? s.sections : [],
      allApps: Array.isArray(s.allApps) ? s.allApps : [],
      installedPool: Array.isArray(s.installedPool) ? s.installedPool : [],
      enabled: Array.isArray(s.enabled) ? s.enabled : []
    }
  })
  const [allApps, setAllApps] = useState<AppCatalogItem[]>(() => snapshot?.allApps ?? [])
  // Merged v2-union + per-user v1 /apps pool, deduped (v1 wins). Backs the Installed
  // view + count so a user's private/unapproved/tester apps (absent from the
  // approved-only v2 catalog) still render.
  const [installedPool, setInstalledPool] = useState<AppCatalogItem[]>(
    () => snapshot?.installedPool ?? []
  )
  const [sections, setSections] = useState<CatalogSection[]>(() => snapshot?.sections ?? [])
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(snapshot?.enabled ?? []))
  // No spinner when a snapshot already paints the grid; load() revalidates silently.
  const [loading, setLoading] = useState(() => !snapshot)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [tab, setTab] = useState<'all' | 'installed'>('all')
  const [busy, setBusy] = useState<Set<string>>(new Set())
  // Apps mid-setup (external-integration install: browser opened, polling the
  // developer's setup-completed webhook). Renders an inline "Setting up…" on the
  // card. Per-app cancel functions are held in a ref so unmount can stop every poll.
  const [settingUp, setSettingUp] = useState<Set<string>>(new Set())
  const pollCancels = useRef<Map<string, () => void>>(new Map())
  const [selectedCats, setSelectedCats] = useState<Set<string>>(new Set())
  const [filterOpen, setFilterOpen] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [searchResults, setSearchResults] = useState<AppCatalogItem[] | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchFallback, setSearchFallback] = useState(false)
  const filterRef = useRef<HTMLDivElement>(null)

  const load = async (): Promise<void> => {
    setError(null)
    const originUid = getCacheUid()
    try {
      // v2 = approved-only capability catalog (marketplace sections). v1 /apps is the
      // per-user list (includes the user's private/unapproved/tester apps) and backs
      // the Installed view; enabled is the per-user install set. The grouped v2 cache
      // is uid-less, so its per-app `enabled` flag is unreliable — enabled stays the
      // install source of truth.
      const [catalogRes, v1Res, enabledRes] = await Promise.all([
        omiApi.get<AppCatalogResponse>('/v2/apps', {
          params: { limit: 100, include_reviews: false }
        }),
        omiApi
          .get<AppEntry[]>('/v1/apps', { params: { include_reviews: false } })
          .catch(() => ({ data: [] as AppEntry[] })),
        omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
      ])
      const { sections: nextSections, allApps: nextApps } = buildCatalog(catalogRes.data?.groups)
      // A capped fetch must not silently drop apps: the limit applies per group, so
      // warn when any rendered section was truncated on the server (repo rule).
      for (const s of nextSections) {
        if (s.truncated) {
          console.warn(
            `[apps] "${s.title}" section truncated: showing ${s.apps.length} of ${s.total} — refine via search`
          )
        }
      }
      // Account-switch guard: if the account changed while this fetch was in flight,
      // drop the result — persisting here would write it under the new account's uid.
      if (getCacheUid() !== originUid) return
      const v1Apps = Array.isArray(v1Res.data) ? v1Res.data : []
      const nextInstalledPool = mergeAppPool(nextApps, v1Apps)
      const nextEnabled = Array.isArray(enabledRes.data) ? enabledRes.data : []
      setSections(nextSections)
      setAllApps(nextApps)
      setInstalledPool(nextInstalledPool)
      setEnabled(new Set(nextEnabled))
      // Mirror the successful load to the per-uid cold-start snapshot for next launch.
      writePersistedValue<AppsSnapshot>(APPS_SURFACE, {
        sections: nextSections,
        allApps: nextApps,
        installedPool: nextInstalledPool,
        enabled: nextEnabled
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount; not a self-retriggering loop
    void load()
  }, [])

  // Debounce search so the network/filter doesn't run on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 500)
    return () => clearTimeout(t)
  }, [query])

  // Latest-value ref for the search fallback's local corpus, so `allApps` changing
  // (e.g. after a refresh) doesn't re-trigger the search effect and re-issue a
  // request for the same query.
  const allAppsRef = useRef(allApps)
  useEffect(() => {
    allAppsRef.current = allApps
  }, [allApps])

  // Run a remote search (with client fallback) whenever the debounced query changes
  // on the Marketplace tab. The Installed tab searches its small local set inline.
  // Intentional data-fetching effect: it syncs search state to the debounced query,
  // so the setState calls here are expected (same pattern as the mount load above).
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const q = debouncedQuery.trim()
    if (tab !== 'all' || !q) {
      setSearchResults(null)
      setSearchLoading(false)
      setSearchFallback(false)
      return
    }
    let stale = false
    // Clear stale results so the spinner shows for the NEW query instead of the
    // previous query's cards lingering until this request resolves.
    setSearchResults(null)
    setSearchFallback(false)
    setSearchLoading(true)
    void searchCatalog(
      q,
      async (query) => {
        const res = await omiApi.get<AppSearchResponse>('/v2/apps/search', {
          params: { q: query, limit: SEARCH_LIMIT }
        })
        return res.data?.data ?? []
      },
      allAppsRef.current
    ).then(({ apps, usedFallback }) => {
      if (stale) return
      setSearchResults(apps)
      setSearchFallback(usedFallback)
      setSearchLoading(false)
    })
    return () => {
      stale = true
    }
  }, [debouncedQuery, tab])
  /* eslint-enable react-hooks/set-state-in-effect */

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

  // Latest-value refs so `toggle` can read current busy/enabled without listing
  // them as deps. `busy`/`enabled` are new Sets on every toggle, so depending on
  // them would give `toggle` a fresh identity each time and re-render every
  // memoized AppCard. Synced in an effect (never during render) and read only from
  // the click handler, so `toggle` can keep empty deps and a stable identity.
  const busyRef = useRef(busy)
  const enabledRef = useRef(enabled)
  useEffect(() => {
    busyRef.current = busy
  }, [busy])
  useEffect(() => {
    enabledRef.current = enabled
  }, [enabled])

  // Stop every in-flight setup poll on unmount so a resolved check can't call
  // setState after the page is gone (and no orphaned 3s webhook loop survives a
  // navigation away from Apps).
  useEffect(() => {
    const cancels = pollCancels.current
    return () => {
      for (const cancel of cancels.values()) cancel()
      cancels.clear()
    }
  }, [])

  // External-integration setup flow (port of macOS navigateToSetup + startSetupPolling).
  // Reached when an install attempt fails on an app whose capabilities include
  // 'external_integration': open the developer's setup URL in the browser, mark the
  // card "Setting up…", and poll `setup_completed_url` every 3s (≤100 ticks / 5 min).
  // On completion, enable again; on timeout, silently revert to Install (macOS does
  // the same — no error). Stable identity (empty deps): reads only setters/refs.
  const beginSetupFlow = useCallback((a: AppCatalogItem): void => {
    const uid = getCacheUid() ?? ''
    const integration = a.external_integration ?? null
    const url = setupUrl(integration, uid)
    if (url) void window.omi.openExternalUrl(url)
    const completedUrl = integration?.setup_completed_url
    // No webhook to poll → macOS just opens the browser and leaves the app as
    // Install (the user re-attempts after finishing in the browser). Nothing else.
    if (!completedUrl) return
    setSettingUp((s) => new Set(s).add(a.id))
    const finish = (): void => {
      pollCancels.current.delete(a.id)
      setSettingUp((s) => {
        const next = new Set(s)
        next.delete(a.id)
        return next
      })
    }
    const cancel = startSetupPolling({
      setupCompletedUrl: completedUrl,
      uid,
      check: isSetupCompleted,
      onSuccess: () => {
        finish()
        void (async () => {
          try {
            await omiApi.post('/v1/apps/enable', null, { params: { app_id: a.id } })
            setEnabled((s) => new Set(s).add(a.id))
            toast(`${a.name} is set up`, { tone: 'success' })
          } catch {
            toast(`Couldn’t finish setting up ${a.name}`, { tone: 'error' })
          }
        })()
      },
      onTimeout: finish
    })
    pollCancels.current.set(a.id, cancel)
  }, [])

  // Stable identity (empty deps) so memoized AppCards skip reconciliation while the
  // user types in search or toggles another app.
  const toggle = useCallback(
    async (a: AppCatalogItem): Promise<void> => {
      if (busyRef.current.has(a.id) || pollCancels.current.has(a.id)) return
      const wasEnabled = enabledRef.current.has(a.id)

      if (wasEnabled) {
        // Uninstall: optimistic flip → POST disable → revert + toast on failure.
        setBusy((s) => new Set(s).add(a.id))
        setEnabled((s) => {
          const next = new Set(s)
          next.delete(a.id)
          return next
        })
        try {
          await omiApi.post('/v1/apps/disable', null, { params: { app_id: a.id } })
        } catch (e) {
          console.error('Disable app failed:', e)
          setEnabled((s) => new Set(s).add(a.id))
          toast(`Couldn’t uninstall ${a.name}`, { tone: 'error', body: userSafeDetail(e) })
        } finally {
          setBusy((s) => {
            const next = new Set(s)
            next.delete(a.id)
            return next
          })
        }
        return
      }

      // Install — attempt-first (macOS handleInstall): POST enable, and only if it
      // fails route an external-integration app into its setup flow (open browser +
      // poll) instead of surfacing the 400. A non-external failure toasts the error
      // (surfacing what macOS swallows: paid/private 403, "currently unavailable" 400,
      // or a network failure). No optimistic flip here — the button spins until the
      // real outcome is known, so it never flickers Installed→Install→Setting up.
      setBusy((s) => new Set(s).add(a.id))
      try {
        await omiApi.post('/v1/apps/enable', null, { params: { app_id: a.id } })
        setEnabled((s) => new Set(s).add(a.id))
      } catch (e) {
        if (worksExternally(a)) {
          beginSetupFlow(a)
        } else {
          console.error('Enable app failed:', e)
          toast(`Couldn’t install ${a.name}`, { tone: 'error', body: userSafeDetail(e) })
        }
      } finally {
        setBusy((s) => {
          const next = new Set(s)
          next.delete(a.id)
          return next
        })
      }
    },
    [beginSetupFlow]
  )

  // Unique categories present across the catalog, sorted by their display name.
  const allCategories = useMemo(() => {
    const set = new Set<string>()
    for (const a of allApps) set.add(a.category || 'other')
    return Array.from(set).sort((x, y) => formatCategory(x).localeCompare(formatCategory(y)))
  }, [allApps])

  const toggleCat = (cat: string): void => {
    setSelectedCats((s) => {
      const next = new Set(s)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  const toggleExpanded = (capabilityId: string): void => {
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(capabilityId)) next.delete(capabilityId)
      else next.add(capabilityId)
      return next
    })
  }

  const catFilter = useCallback(
    (a: AppCatalogItem): boolean => selectedCats.has(a.category || 'other'),
    [selectedCats]
  )

  const isSearching = debouncedQuery.trim().length > 0

  // The user's installed apps, resolved from the merged v1+v2 pool (so private/
  // tester apps still appear) filtered to the enabled set. Drives both the Installed
  // view and the header count, so the count always equals what is renderable.
  const installedApps = useMemo(
    () => installedPool.filter((a) => enabled.has(a.id)),
    [installedPool, enabled]
  )

  // What to render in the content area, derived from tab/search/filter state:
  //   - 'sections': macOS-style capability sections (Marketplace browse, no search/filter)
  //   - 'grid': a flat card grid (search results, category filter, or the Installed list)
  const view = useMemo<{ kind: 'sections' } | { kind: 'grid'; apps: AppCatalogItem[] }>(() => {
    if (tab === 'installed') {
      let base = installedApps
      if (isSearching) base = rankSearchResults(base, debouncedQuery)
      else if (selectedCats.size > 0) base = base.filter(catFilter)
      return { kind: 'grid', apps: base }
    }
    if (isSearching) {
      let base = searchResults ?? []
      if (selectedCats.size > 0) base = base.filter(catFilter)
      return { kind: 'grid', apps: base }
    }
    if (selectedCats.size > 0) {
      return { kind: 'grid', apps: allApps.filter(catFilter) }
    }
    return { kind: 'sections' }
  }, [
    tab,
    allApps,
    installedApps,
    isSearching,
    debouncedQuery,
    selectedCats,
    catFilter,
    searchResults
  ])

  const showSearchSpinner = tab === 'all' && isSearching && searchLoading && searchResults === null

  // Cache-first: when a snapshot (or a prior load) has already painted the grid, a
  // FAILED revalidation must not replace it with the full-page "Couldn't load apps"
  // screen. Show that screen only when there's genuinely nothing cached to display;
  // otherwise keep the grid on screen even while `error` is set (silent failure).
  const hasCachedData = sections.length > 0 || allApps.length > 0 || installedPool.length > 0

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Apps"
        subtitle={
          loading ? 'Loading…' : `${allApps.length} available · ${installedApps.length} installed`
        }
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
        {!loading && error && !hasCachedData && (
          <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
              <AlertTriangle className="h-5 w-5 text-white/60" />
            </div>
            <div className="space-y-1">
              <div className="font-display font-semibold text-white/90">Couldn’t load apps</div>
              <p className="text-sm text-white/55">
                Something went wrong reaching the marketplace. Check your connection and try again.
              </p>
            </div>
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="btn-secondary flex items-center gap-2 px-4 py-2"
            >
              {refreshing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Retry
            </button>
          </div>
        )}
        {!loading && (!error || hasCachedData) && (
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

            {showSearchSpinner ? (
              <div className="flex items-center justify-center gap-2 py-10 text-sm text-white/45">
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching…
              </div>
            ) : view.kind === 'grid' ? (
              <>
                {searchFallback && isSearching && tab === 'all' && (
                  <div className="glass-subtle px-4 py-2.5 text-xs text-white/55">
                    Showing local results — search is temporarily unavailable.
                  </div>
                )}
                {view.apps.length === 0 ? (
                  <EmptyState
                    icon={LayoutGrid}
                    title={
                      isSearching
                        ? 'No apps match'
                        : tab === 'installed'
                          ? 'No apps installed'
                          : 'No apps available'
                    }
                    description={
                      isSearching
                        ? 'Try a different search.'
                        : tab === 'installed'
                          ? 'Browse the Marketplace tab to find apps to install.'
                          : 'Try again later.'
                    }
                  />
                ) : (
                  <>
                    <AppGrid
                      apps={view.apps.slice(0, SEARCH_LIMIT)}
                      enabled={enabled}
                      busy={busy}
                      settingUp={settingUp}
                      onToggle={toggle}
                    />
                    {view.apps.length > SEARCH_LIMIT && (
                      <p className="mt-3 text-center text-xs text-white/45">
                        Showing the first {SEARCH_LIMIT} of {view.apps.length}. Narrow with search
                        or filters.
                      </p>
                    )}
                  </>
                )}
              </>
            ) : sections.length === 0 ? (
              <EmptyState
                icon={LayoutGrid}
                title="No apps available"
                description="Try again later."
              />
            ) : (
              sections.map((section) => {
                const isExpanded = expanded.has(section.capabilityId)
                return (
                  <div key={section.capabilityId} className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-semibold text-white/80">{section.title}</h2>
                      {section.hasMore && (
                        <button
                          onClick={() => toggleExpanded(section.capabilityId)}
                          className="flex items-center gap-1 text-xs text-white/45 transition-colors duration-150 hover:text-white/80"
                        >
                          {isExpanded ? (
                            <>
                              Show less
                              <ChevronUp className="h-3.5 w-3.5" />
                            </>
                          ) : (
                            <>
                              See more
                              <ChevronDown className="h-3.5 w-3.5" />
                            </>
                          )}
                        </button>
                      )}
                    </div>
                    <AppGrid
                      apps={sectionPreview(section.apps, isExpanded)}
                      enabled={enabled}
                      busy={busy}
                      settingUp={settingUp}
                      onToggle={toggle}
                    />
                    {isExpanded && section.truncated && (
                      <p className="text-xs text-white/45">
                        Showing {section.apps.length} of {section.total}. Use search to find the
                        rest.
                      </p>
                    )}
                  </div>
                )
              })
            )}
          </div>
        )}
      </div>
    </div>
  )
}
