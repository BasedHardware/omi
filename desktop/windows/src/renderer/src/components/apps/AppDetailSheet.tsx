import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {
  X,
  Star,
  Check,
  Plus,
  Loader2,
  Trash2,
  LayoutGrid,
  ArrowUpRight,
  CreditCard
} from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { getCacheUid } from '../../lib/persistentCache'
import { toast } from '../../lib/toast'
import { startSetupPolling } from '../../lib/appInstall'
import type { App, AppCatalogItem, AppReview } from '../../lib/omiApi.generated'
import { AddReviewDialog } from './AddReviewDialog'

// GET the app's reviews. Returns the list, or null on any failure so the caller can
// leave the current reviews on screen (macOS fails silently the same way).
async function fetchReviews(appId: string): Promise<AppReview[] | null> {
  try {
    const res = await omiApi.get<AppReview[]>(`/v1/apps/${appId}/reviews`)
    return Array.isArray(res.data) ? res.data : []
  } catch {
    return null
  }
}

// Turns raw API strings like "chat-assistants" / "external_integration" into
// "Chat Assistants" / "External Integration" for display.
function titleize(raw: string): string {
  return raw
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}

// Read-only star row for a review score (1-5). Amber/white — never purple.
function StarRow({ score }: { score: number }): React.JSX.Element {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={`h-3.5 w-3.5 ${n <= score ? 'fill-amber-400 text-amber-400' : 'text-white/20'}`}
        />
      ))}
    </div>
  )
}

function ReviewCard({
  review,
  highlight
}: {
  review: AppReview
  highlight?: boolean
}): React.JSX.Element {
  return (
    <div
      className={`rounded-xl border px-4 py-3 ${
        highlight ? 'border-white/15 bg-white/[0.05]' : 'border-white/10 bg-white/[0.02]'
      }`}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-white/55">{review.username || 'Anonymous'}</span>
        <StarRow score={review.score} />
      </div>
      {review.review && <p className="text-sm leading-relaxed text-white/80">{review.review}</p>}
      {review.response && (
        <div className="mt-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <div className="mb-0.5 text-[11px] font-medium text-white/45">Developer response</div>
          <p className="text-xs leading-relaxed text-white/70">{review.response}</p>
        </div>
      )}
    </div>
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
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-white/45">{title}</h3>
      {children}
    </div>
  )
}

type AppDetailSheetProps = {
  // The catalog card that was tapped — rendered immediately for a zero-latency open,
  // then upgraded by the full GET /v1/apps/{id} fetch.
  app: AppCatalogItem
  // Live install state, owned by the Apps page (so the sheet and the card stay in
  // sync). `onToggle` is the page's existing install/uninstall handler: when the app
  // is enabled it disables, otherwise it installs (attempt-first + external setup).
  enabled: boolean
  busy: boolean
  settingUp: boolean
  onToggle: (a: AppCatalogItem) => void
  onClose: () => void
}

// App detail sheet — faithful port of macOS AppsPage.AppDetailView. Sections in the
// exact macOS order: header → About → Setup steps → Capabilities → Category →
// Reviews. On open it fetches the full app (capabilities, external_integration,
// user_review, rating) and the reviews list in parallel; both fail silently (macOS
// does the same), falling back to the catalog card's fields.
export function AppDetailSheet({
  app,
  enabled,
  busy,
  settingUp,
  onToggle,
  onClose
}: AppDetailSheetProps): React.JSX.Element {
  const [detail, setDetail] = useState<App | null>(null)
  const [reviews, setReviews] = useState<AppReview[]>([])
  const [showAddReview, setShowAddReview] = useState(false)
  const mounted = useRef(true)
  const purchasePoll = useRef<(() => void) | null>(null)
  const currentUid = getCacheUid() ?? ''

  // Prefer freshly fetched detail fields; fall back to the catalog card so the sheet
  // renders instantly before (and even if) the detail fetch resolves.
  const name = detail?.name ?? app.name ?? 'App'
  const author = detail?.author ?? app.author ?? ''
  const image = detail?.image ?? app.image ?? ''
  const description = detail?.description ?? app.description ?? ''
  const category = detail?.category ?? app.category ?? ''
  const capabilities = detail?.capabilities ?? app.capabilities ?? []
  const ratingAvg = detail?.rating_avg ?? app.rating_avg ?? 0
  const ratingCount = detail?.rating_count ?? app.rating_count ?? 0
  const installs = detail?.installs ?? app.installs ?? 0
  const integration = detail?.external_integration ?? app.external_integration ?? null
  const authSteps = integration?.auth_steps ?? []

  // Paid-app state (Windows goes BEYOND macOS, which decodes is_paid but never shows a
  // purchase affordance and silently swallows the paid-gate 403). `is_user_paid` and
  // `payment_link` live only on the full detail fetch; the catalog card carries just
  // `is_paid`/`price`. Until detail resolves, assume the user owns it so we never flash
  // a Purchase CTA (or open payment) for an app they already bought.
  const isPaid = detail?.is_paid ?? app.is_paid ?? false
  const isUserPaid = detail ? (detail.is_user_paid ?? false) : true
  const paymentLink = detail?.payment_link ?? null
  const price = detail?.price ?? app.price ?? null
  const needsPurchase = isPaid && !isUserPaid && !enabled

  // The user's own review: the detail payload's user_review, else the one in the list
  // whose uid matches the current user. Gates the Add/Edit button (no install gate).
  const userReview = detail?.user_review ?? reviews.find((r) => r.uid === currentUid) ?? null
  const otherReviews = reviews.filter((r) => r.uid !== currentUid).slice(0, 3)

  const loadReviews = async (): Promise<void> => {
    const list = await fetchReviews(app.id)
    if (list) setReviews(list)
  }

  useEffect(() => {
    let stale = false
    // Both fetches run behind `await` inside this async IIFE (never a synchronous
    // setState in the effect body) and bail if the sheet unmounted mid-flight.
    void (async () => {
      try {
        const res = await omiApi.get<App>(`/v1/apps/${app.id}`)
        if (!stale) setDetail(res.data)
      } catch {
        // Silent fallback to the catalog card's fields.
      }
    })()
    void (async () => {
      const list = await fetchReviews(app.id)
      if (!stale && list) setReviews(list)
    })()
    return () => {
      stale = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by app.id at the call site; fetch once per mount
  }, [app.id])

  // Optimistically fold the just-submitted review into the list, then re-fetch to
  // reconcile with the server (macOS's loadReviews after submit). The submitted
  // values come from the dialog — we build the review object locally because the
  // POST returns only `{status:'ok'}`, not a review.
  const onReviewSubmitted = ({ score, review }: { score: number; review: string }): void => {
    const local: AppReview = {
      score,
      review,
      uid: currentUid,
      username: userReview?.username ?? null,
      rated_at: new Date().toISOString()
    }
    setReviews((prev) => {
      const others = prev.filter((r) => r.uid !== currentUid)
      return [local, ...others]
    })
    setShowAddReview(false)
    void loadReviews()
  }

  // Self-heal a stale paid state: refetch the full app when the window regains focus —
  // e.g. the user returns from completing a purchase (or setup) in the browser — so the
  // Purchase CTA hides once is_user_paid has flipped server-side.
  useEffect(() => {
    const refetch = (): void => {
      void (async () => {
        try {
          const res = await omiApi.get<App>(`/v1/apps/${app.id}`)
          if (mounted.current) setDetail(res.data)
        } catch {
          // Keep the current detail on any failure (macOS fails silently too).
        }
      })()
    }
    window.addEventListener('focus', refetch)
    return () => window.removeEventListener('focus', refetch)
  }, [app.id])

  // Stop any in-flight purchase poll and mark unmounted on teardown so a resolved tick
  // can't setState after the sheet closes (and no orphaned 3s webhook loop survives).
  useEffect(() => {
    return () => {
      mounted.current = false
      purchasePoll.current?.()
      purchasePoll.current = null
    }
  }, [])

  // After opening the payment link, poll the app every 3s until is_user_paid flips, then
  // enable it via the page's install handler. Reuses the setup-poll state machine (same
  // 3s / 100-tick cadence, same cancel-on-unmount contract).
  const startPurchasePoll = (): void => {
    purchasePoll.current?.()
    const cancel = startSetupPolling({
      setupCompletedUrl: app.id, // opaque token; the check below ignores it
      uid: currentUid,
      check: async () => {
        try {
          const res = await omiApi.get<App>(`/v1/apps/${app.id}`)
          if (mounted.current) setDetail(res.data)
          return res.data.is_user_paid === true
        } catch {
          return false
        }
      },
      onSuccess: () => {
        purchasePoll.current = null
        onToggle(app)
      },
      onTimeout: () => {
        purchasePoll.current = null
      }
    })
    purchasePoll.current = cancel
  }

  // Purchase affordance click. The backend already appends ?client_reference_id=uid_… to
  // payment_link, so we open it verbatim (never re-append uid). No link → the app is only
  // purchasable in the mobile app; say so instead of silently no-op'ing (the macOS bug).
  const onPurchase = (): void => {
    if (paymentLink) {
      void window.omi.openExternalUrl(paymentLink)
      startPurchasePoll()
    } else {
      toast(`${name} is a paid app`, {
        tone: 'info',
        body: 'Purchase it in the Omi mobile app to unlock it here.'
      })
    }
  }

  // Primary button states: "Setting up…" while polling an external setup, "Installed"
  // once enabled (disable is the separate trash icon), a real "Purchase — $x" affordance
  // for an unowned paid app (beyond macOS), else "Install". Disable-in-flight uses `busy`.
  const primaryBusy = busy || settingUp
  const purchaseLabel = typeof price === 'number' ? `Purchase — $${price.toFixed(2)}` : 'Purchase'

  return (
    <>
      <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/50 data-[state=open]:animate-modal-overlay-in" />
          <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center p-6">
            <Dialog.Content
              aria-describedby={undefined}
              className="pointer-events-auto flex max-h-[85vh] w-full max-w-[520px] flex-col rounded-[var(--radius-card)] border border-white/10 bg-[var(--bg-secondary)] shadow-[0_16px_48px_rgba(0,0,0,0.5)] data-[state=open]:animate-modal-in"
            >
              <Dialog.Title className="sr-only">{name} details</Dialog.Title>

              {/* Close affordance pinned top-right over the scroll body. */}
              <div className="flex justify-end px-3 pt-3">
                <Dialog.Close
                  className="rounded-md p-1.5 text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </Dialog.Close>
              </div>

              <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 pb-6">
                {/* 1. Header: 80×80 icon, name/author, rating + installs, primary + trash. */}
                <div className="flex items-start gap-4">
                  {image ? (
                    <img
                      src={image}
                      alt=""
                      width={80}
                      height={80}
                      className="h-20 w-20 shrink-0 rounded-2xl border border-white/10 object-cover"
                      onError={(e) => {
                        ;(e.target as HTMLImageElement).style.visibility = 'hidden'
                      }}
                    />
                  ) : (
                    <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                      <LayoutGrid className="h-7 w-7 text-white/60" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <h2 className="font-display text-lg font-semibold text-white/95">{name}</h2>
                    {author && <div className="text-sm text-white/50">{author}</div>}
                    <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-white/45">
                      {ratingCount > 0 && (
                        <span className="flex items-center gap-1">
                          <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
                          {ratingAvg.toFixed(1)}
                          <span className="text-white/35">({ratingCount})</span>
                        </span>
                      )}
                      {installs > 0 && <span>{installs.toLocaleString()} installs</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {settingUp ? (
                      <button
                        disabled
                        className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 bg-transparent px-4 py-2 text-sm font-medium text-white/80 opacity-60"
                      >
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Setting up…
                      </button>
                    ) : enabled ? (
                      <button
                        disabled
                        className="inline-flex cursor-default items-center gap-1.5 rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium text-white"
                      >
                        <Check className="h-4 w-4" />
                        Installed
                      </button>
                    ) : needsPurchase ? (
                      <button
                        onClick={onPurchase}
                        disabled={primaryBusy}
                        className={`inline-flex items-center gap-1.5 rounded-xl border border-white/25 bg-white/10 px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:bg-white/15 ${
                          primaryBusy ? 'opacity-60' : ''
                        }`}
                      >
                        {primaryBusy ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <CreditCard className="h-4 w-4" />
                        )}
                        {purchaseLabel}
                      </button>
                    ) : (
                      <button
                        onClick={() => onToggle(app)}
                        disabled={primaryBusy}
                        className={`inline-flex items-center gap-1.5 rounded-xl border border-white/15 bg-transparent px-4 py-2 text-sm font-medium text-white/80 transition-all duration-200 hover:bg-white/5 hover:text-white ${
                          primaryBusy ? 'opacity-60' : ''
                        }`}
                      >
                        {primaryBusy ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Plus className="h-4 w-4" />
                        )}
                        Install
                      </button>
                    )}
                    {enabled && !settingUp && (
                      <button
                        onClick={() => onToggle(app)}
                        disabled={busy}
                        className="rounded-xl border border-white/10 p-2 text-white/40 transition-colors hover:bg-white/5 hover:text-error disabled:opacity-50"
                        aria-label="Disable app"
                        title="Disable app"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="border-t border-white/10" />

                {/* 3. About. */}
                {description && (
                  <Section title="About">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/75">
                      {description}
                    </p>
                  </Section>
                )}

                {/* 4. Setup steps — only when the integration defines auth steps. */}
                {authSteps.length > 0 && (
                  <Section title="Setup">
                    <div className="space-y-2">
                      {authSteps.map((step, i) => (
                        <button
                          key={`${step.url}-${i}`}
                          onClick={() =>
                            void window.omi.openExternalUrl(`${step.url}?uid=${currentUid}`)
                          }
                          className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-left transition-colors hover:bg-white/[0.05]"
                        >
                          <span
                            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${
                              enabled
                                ? 'border-success/40 bg-success/15 text-success'
                                : 'border-white/15 bg-white/5 text-white/60'
                            }`}
                          >
                            {enabled ? <Check className="h-3.5 w-3.5" /> : i + 1}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm text-white/85">
                              {step.name || `Step ${i + 1}`}
                            </span>
                            <span className="block text-xs text-white/45">
                              {enabled ? 'Completed' : 'Click to complete'}
                            </span>
                          </span>
                          <ArrowUpRight className="h-4 w-4 shrink-0 text-white/40" />
                        </button>
                      ))}
                    </div>
                  </Section>
                )}

                {/* 5. Capabilities. */}
                {capabilities.length > 0 && (
                  <Section title="Capabilities">
                    <div className="flex flex-wrap gap-2">
                      {capabilities.map((c) => (
                        <span
                          key={c}
                          className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70"
                        >
                          {titleize(c)}
                        </span>
                      ))}
                    </div>
                  </Section>
                )}

                {/* 6. Category. */}
                {category && (
                  <Section title="Category">
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">
                      {titleize(category)}
                    </span>
                  </Section>
                )}

                <div className="border-t border-white/10" />

                {/* 8. Reviews. */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-white/45">
                      Reviews
                    </h3>
                    <button
                      onClick={() => setShowAddReview(true)}
                      className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-white/80 transition-colors hover:bg-white/5 hover:text-white"
                    >
                      {userReview ? 'Edit your review' : 'Add review'}
                    </button>
                  </div>

                  {userReview && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-medium text-white/40">Your review</div>
                      <ReviewCard review={userReview} highlight />
                    </div>
                  )}

                  {otherReviews.length > 0 ? (
                    <div className="space-y-2">
                      {otherReviews.map((r, i) => (
                        <ReviewCard key={`${r.uid}-${i}`} review={r} />
                      ))}
                    </div>
                  ) : (
                    !userReview && (
                      <p className="text-sm text-white/45">
                        No reviews yet. Be the first to review this app.
                      </p>
                    )
                  )}
                </div>
              </div>
            </Dialog.Content>
          </div>
        </Dialog.Portal>
      </Dialog.Root>

      {showAddReview && (
        <AddReviewDialog
          appId={app.id}
          existingReview={userReview}
          onClose={() => setShowAddReview(false)}
          onSubmitted={onReviewSubmitted}
        />
      )}
    </>
  )
}
