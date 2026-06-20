import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutGrid,
  Star,
  Download,
  Plus,
  Check,
  Loader2,
  Share2,
  Blocks,
  MessageSquare,
  Brain,
  Bell,
  Sparkles,
  ExternalLink,
  Zap
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { Spinner } from '../components/ui/Spinner'
import { toast } from '../lib/toast'
import { fetchAppCatalog, fetchAppsFull } from '../lib/chatApps'
import {
  capabilityLabel,
  triggerLabel,
  formatInstalls,
  setupUrl,
  reviewerName,
  reviewsWithText,
  filledStars,
  previewUrls,
  type AppDetailEntry,
  type AppReview
} from '../lib/appDetail'

// Icon per capability tag (falls back to a generic block).
const CAPABILITY_ICONS: Record<string, typeof Blocks> = {
  external_integration: Blocks,
  chat: MessageSquare,
  persona: Sparkles,
  memories: Brain,
  proactive_notification: Bell
}

function Stars({ score, className = '' }: { score: number; className?: string }): React.JSX.Element {
  const filled = filledStars(score)
  return (
    <span className={`inline-flex items-center gap-0.5 ${className}`} aria-label={`${score} out of 5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`h-3.5 w-3.5 ${i < filled ? 'fill-amber-400 text-amber-400' : 'text-white/25'}`}
        />
      ))}
    </span>
  )
}

function Section({
  title,
  children
}: {
  title: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <section className="animate-fade-in">
      <h2 className="mb-3 text-base font-semibold text-white">{title}</h2>
      {children}
    </section>
  )
}

export function AppDetail({ appId }: { appId: string }): React.JSX.Element {
  const navigate = useNavigate()
  const [app, setApp] = useState<AppDetailEntry | null>(null)
  const [installed, setInstalled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    setApp(null)
    setError(null)
    void (async () => {
      try {
        // The single GET /v1/apps/:id can hang (→ 12s axios timeout), which is
        // what broke this page. Drive it from the cached apps list instead — the
        // reduced list carries everything we render EXCEPT reviews, and the cache
        // is shared with the Apps tab so opening an app is instant once loaded
        // (api.omi.me's /v1/apps is slow, so re-fetching it per open crawled).
        const [list, enabledRes] = await Promise.all([
          fetchAppsFull(),
          omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
        ])
        if (!active) return
        const found = list.find((a) => a.id === appId)
        if (!found) {
          setError('App not found')
          return
        }
        setApp(found)
        setInstalled(Array.isArray(enabledRes.data) && enabledRes.data.includes(appId))

        // Reviews live only on the dedicated endpoint (reduced list omits them).
        // Async + non-blocking with a generous timeout — api.omi.me is slow, and
        // the default 12s axios timeout was silently dropping them. Reviews just
        // stream in late instead of breaking the page.
        void omiApi
          .get<AppReview[]>(`/v1/apps/${appId}/reviews`, { timeout: 30_000 })
          .then((r) => {
            if (active && Array.isArray(r.data)) setApp((p) => (p ? { ...p, reviews: r.data } : p))
          })
          .catch(() => {})

        // Preview screenshots: thumbnail_urls is computed server-side ONLY by the
        // single-app endpoint, which also returns reviews inline. Fetch it
        // best-effort with a generous timeout, fully non-blocking — if it hangs,
        // the page just shows no Preview. Doubles as a reviews fallback.
        void omiApi
          .get<AppDetailEntry>(`/v1/apps/${appId}`, { timeout: 25000 })
          .then((r) => {
            if (!active || !r.data) return
            setApp((p) =>
              p
                ? {
                    ...p,
                    thumbnail_urls: r.data.thumbnail_urls?.length
                      ? r.data.thumbnail_urls
                      : p.thumbnail_urls,
                    external_integration: p.external_integration ?? r.data.external_integration,
                    reviews: p.reviews?.length ? p.reviews : (r.data.reviews ?? p.reviews),
                    // Prompts only come from the single-app endpoint.
                    memory_prompt: p.memory_prompt ?? r.data.memory_prompt,
                    chat_prompt: p.chat_prompt ?? r.data.chat_prompt
                  }
                : p
            )
          })
          .catch(() => {})
      } catch (e) {
        if (active) setError((e as Error).message)
      }
    })()
    return () => {
      active = false
    }
  }, [appId])

  const onToggle = async (): Promise<void> => {
    if (!app || busy) return
    setBusy(true)
    const wasInstalled = installed
    setInstalled(!wasInstalled) // optimistic
    try {
      await omiApi.post(`/v1/apps/${wasInstalled ? 'disable' : 'enable'}`, null, {
        params: { app_id: app.id }
      })
      // The chat persona picker / conversation views cache the catalog — drop it
      // so the new enabled state is reflected without a relaunch.
      void fetchAppCatalog(true)
      toast(wasInstalled ? 'App uninstalled' : 'App installed', { tone: 'info' })
    } catch (e) {
      setInstalled(wasInstalled) // revert
      toast(wasInstalled ? 'Uninstall failed' : 'Install failed', {
        tone: 'error',
        body: (e as Error).message
      })
    } finally {
      setBusy(false)
    }
  }

  const onShare = async (): Promise<void> => {
    if (!app) return
    const text = `${app.name}${app.description ? ` — ${app.description}` : ''}`
    try {
      await navigator.clipboard.writeText(text)
      toast('Copied to clipboard', { tone: 'info' })
    } catch {
      /* clipboard unavailable — no-op */
    }
  }

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="App" onBack={() => navigate('/apps')} />
        <div className="px-10 py-8 text-sm text-white/60">{error}</div>
      </div>
    )
  }
  if (!app) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="App" onBack={() => navigate('/apps')} />
        <div className="flex flex-1 items-center justify-center">
          <Spinner label="Loading app…" />
        </div>
      </div>
    )
  }

  const caps = app.capabilities ?? []
  const reviews = reviewsWithText(app.reviews)
  const installs = formatInstalls(app.installs)
  const ext = app.external_integration
  const trigger = triggerLabel(ext?.triggers_on)
  const setup = setupUrl(ext)
  const previews = previewUrls(app)
  const prompt = (app.memory_prompt || app.chat_prompt || '').trim()

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="App" onBack={() => navigate('/apps')} />
      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-2xl space-y-8">
          {/* Header: icon, name, author, rating + installs, actions */}
          <div className="flex items-start gap-4 animate-fade-in">
            {app.image ? (
              <img
                src={app.image}
                alt=""
                className="h-16 w-16 shrink-0 rounded-2xl border border-white/10 object-cover"
                onError={(e) => {
                  ;(e.target as HTMLImageElement).style.visibility = 'hidden'
                }}
              />
            ) : (
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                <LayoutGrid className="h-7 w-7 text-white/60" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <h1 className="font-display text-2xl font-bold leading-tight text-white">{app.name}</h1>
              {app.author && <div className="mt-0.5 text-sm text-white/55">{app.author}</div>}
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/55">
                {app.rating_avg ? (
                  <span className="flex items-center gap-1">
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    {app.rating_avg.toFixed(1)}
                    {app.rating_count
                      ? ` (${app.rating_count} review${app.rating_count === 1 ? '' : 's'})`
                      : ''}
                  </span>
                ) : null}
                {installs && (
                  <span className="flex items-center gap-1">
                    <Download className="h-3.5 w-3.5" />
                    {installs} installs
                  </span>
                )}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button
                  onClick={onToggle}
                  disabled={busy}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 ${
                    installed
                      ? 'border border-white/15 bg-transparent text-white/75 hover:border-red-400/30 hover:bg-red-500/10 hover:text-red-200'
                      : 'bg-[color:var(--accent)] text-white hover:opacity-90'
                  }`}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : installed ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  {busy ? 'Working…' : installed ? 'Installed' : 'Install'}
                </button>
                <button
                  onClick={onShare}
                  className="btn-ghost rounded-xl border border-white/10 p-2.5"
                  title="Share"
                  aria-label="Share"
                >
                  <Share2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {/* About */}
          {app.description && (
            <Section title="About">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/75">
                {app.description}
              </p>
            </Section>
          )}

          {/* Prompt — the instruction the app runs over your conversations.
              Only the single-app endpoint returns it, so it streams in best-effort. */}
          {prompt && (
            <Section title="Prompt">
              <div className="surface-card p-4">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/70">{prompt}</p>
              </div>
            </Section>
          )}

          {/* Preview */}
          {previews.length > 0 && (
            <Section title="Preview">
              <div className="flex gap-3 overflow-x-auto pb-1">
                {previews.map((src, i) => (
                  <img
                    key={i}
                    src={src}
                    alt=""
                    className="h-48 shrink-0 rounded-xl border border-white/10 object-cover"
                    onError={(e) => {
                      ;(e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                ))}
              </div>
            </Section>
          )}

          {/* Capabilities */}
          {caps.length > 0 && (
            <Section title="Capabilities">
              <div className="flex flex-wrap gap-2">
                {caps.map((c) => {
                  const Icon = CAPABILITY_ICONS[c] ?? Blocks
                  return (
                    <span
                      key={c}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-white/12 bg-white/5 px-2.5 py-1.5 text-xs text-white/80"
                    >
                      <Icon className="h-3.5 w-3.5 text-white/60" />
                      {capabilityLabel(c)}
                    </span>
                  )
                })}
              </div>
            </Section>
          )}

          {/* Integration: trigger + setup steps */}
          {(trigger || setup) && (
            <Section title="Integration">
              <div className="space-y-3">
                {trigger && (
                  <div className="flex items-center gap-2 text-sm text-white/70">
                    <Zap className="h-4 w-4 text-white/45" />
                    <span className="text-white/50">Triggers on:</span>
                    <span className="text-white/85">{trigger}</span>
                  </div>
                )}
                {setup && (
                  <div>
                    <div className="mb-2 text-sm text-white/50">Setup Steps:</div>
                    <button
                      onClick={() => window.open(setup, '_blank', 'noopener')}
                      className="surface-card flex w-full items-center justify-between gap-3 p-4 text-left transition-colors duration-200 hover:border-white/20"
                    >
                      <span className="flex items-center gap-3 text-sm text-white/85">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/20 text-[11px] text-white/60">
                          1
                        </span>
                        Setup {app.name}
                      </span>
                      <ExternalLink className="h-4 w-4 shrink-0 text-white/45" />
                    </button>
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* Reviews — only when the app actually has some. */}
          {reviews.length > 0 && (
            <Section title={`Reviews (${reviews.length})`}>
              <ul className="space-y-5">
                {reviews.map((r, i) => (
                  <li key={i} className="border-b border-white/[0.06] pb-5 last:border-0 last:pb-0">
                    <div className="mb-1.5 flex items-center gap-2">
                      <Stars score={r.score ?? 0} />
                      <span className="text-xs text-white/55">{reviewerName(r)}</span>
                    </div>
                    {r.review && (
                      <p className="text-sm leading-relaxed text-white/75">{r.review}</p>
                    )}
                    {r.response && r.response.trim() && (
                      <div className="mt-2.5 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-white/40">
                          Developer response
                        </div>
                        <p className="text-sm leading-relaxed text-white/70">{r.response}</p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
