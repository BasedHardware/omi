import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useSearchableRow } from '../searchContext'
import { toast } from '../../../lib/toast'
import { BillingCard } from '../billing/BillingCard'
import { CurrentPlanCard } from '../billing/CurrentPlanCard'
import { ChatUsageCard } from '../billing/ChatUsageCard'
import { OverageCard } from '../billing/OverageCard'
import { TrialCard } from '../billing/TrialCard'
import { PlanGrid } from '../billing/PlanGrid'
import { canonicalPlanId } from '../../../lib/billingPlans'
import {
  trackPaywallOpened,
  trackUpgradeCancelled,
  trackUpgradePlanSelected,
  trackUpgradeSucceeded
} from '../../../lib/analytics'
import {
  fetchSubscription,
  fetchChatQuota,
  fetchTrial,
  fetchOverageInfo,
  orderedCatalog,
  isTrialActive,
  startCheckout,
  createCheckoutSession,
  upgradeSubscription,
  openCustomerPortal,
  OMI_PRO_DEPRECATION_FALLBACK_PRICE,
  RESUBSCRIBE_FIRST,
  EXISTING_SUBSCRIPTION
} from '../../../lib/billing'
import type {
  UserSubscriptionResponse,
  ChatUsageQuota,
  TrialMetadata,
  OverageInfoResponse
} from '../../../lib/omiApi.generated'

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

const REFRESH_LAGGING_MSG =
  'Payment completed, but plan refresh is still catching up. Please try reloading this page in a moment.'

export function PlanUsageTab(): React.JSX.Element {
  // Register the tab for cross-tab Settings search (billing content is card-based,
  // not SettingRows, so this one hidden entry surfaces the panel on a match).
  useSearchableRow('plan usage billing subscription upgrade quota trial overage payment omi pro')

  const [sub, setSub] = useState<UserSubscriptionResponse | null>(null)
  const [quota, setQuota] = useState<ChatUsageQuota | null>(null)
  const [trial, setTrial] = useState<TrialMetadata | null>(null)
  const [overage, setOverage] = useState<OverageInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [activePriceId, setActivePriceId] = useState<string | null>(null)
  const [portalBusy, setPortalBusy] = useState(false)
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)
  const plansRef = useRef<HTMLDivElement | null>(null)
  const paywallTracked = useRef(false)

  useEffect(() => {
    if (paywallTracked.current || !sub?.subscription) return
    paywallTracked.current = true
    // The plan grid lives on this settings tab. This is a settings impression,
    // not a blocked purchase gate. The usage-limit popup keeps its own source.
    trackPaywallOpened('windows_settings_view', canonicalPlanId(sub.subscription.plan) ?? 'unknown')
  }, [sub])

  const load = useCallback(async (): Promise<void> => {
    setError(null)
    // Subscription is the core surface; trial/overage are optional cards whose
    // failures degrade silently.
    const [subRes, quotaRes, trialRes, overageRes] = await Promise.allSettled([
      fetchSubscription(),
      fetchChatQuota(),
      fetchTrial(),
      fetchOverageInfo()
    ])
    if (subRes.status === 'fulfilled') setSub(subRes.value)
    else setError(apiError(subRes.reason))
    setQuota(quotaRes.status === 'fulfilled' ? quotaRes.value : null)
    setTrial(trialRes.status === 'fulfilled' ? trialRes.value : null)
    setOverage(overageRes.status === 'fulfilled' ? overageRes.value : null)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      await load()
      if (!cancelled) setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  const subscription = sub?.subscription
  const isOveragePlan = !!overage?.is_overage_plan
  const catalog = useMemo(
    () => (subscription ? orderedCatalog(subscription, sub?.available_plans) : []),
    [subscription, sub?.available_plans]
  )

  const onManage = async (): Promise<void> => {
    setPortalBusy(true)
    try {
      await openCustomerPortal()
    } catch (e) {
      toast('Could not open the billing portal', { tone: 'error', body: apiError(e) })
    } finally {
      setPortalBusy(false)
    }
  }

  const onBuy = async (priceId: string, promotionCode?: string): Promise<void> => {
    if (!subscription || activePriceId) return
    setActivePriceId(priceId)
    const selected = catalog.find((item) =>
      (item.prices ?? []).some((price) => price.id === priceId)
    )
    const priceTitle = selected?.prices?.find((price) => price.id === priceId)?.title ?? 'unknown'
    const tier = selected?.id ?? 'unknown'
    trackUpgradePlanSelected(tier, priceTitle, 'windows_settings_view')
    try {
      const result = await startCheckout(
        { priceId, promotionCode, currentSubscription: subscription },
        {
          createCheckoutSession,
          upgradeSubscription,
          openCheckout: (url) => window.omi.openCheckout(url),
          fetchSubscription,
          wait
        }
      )
      switch (result.kind) {
        case 'cancelled':
          // User abandoned — no toast. Still refresh quietly: if the window was
          // force-closed in the gap AFTER Stripe charged but BEFORE the success
          // redirect fired, the webhook has (or will have) granted the plan
          // server-side, and this pickup keeps the tab from showing stale state.
          trackUpgradeCancelled()
          void load()
          return
        case 'refresh_lagging':
          toast('Payment received', { tone: 'warn', body: REFRESH_LAGGING_MSG })
          setSelectedPlanId(null)
          await load()
          return
        case 'upgraded':
          toast('Plan updated', { tone: 'success' })
          // In-place upgrade: the API accepted a scheduled change. The current
          // price id does not move until the period rolls.
          break
        case 'reactivated':
          toast(result.message ?? 'Your plan will renew.', { tone: 'success' })
          break
        case 'blocked':
          toast(RESUBSCRIBE_FIRST, { tone: 'error' })
          return
        case 'existing_subscription':
          toast(EXISTING_SUBSCRIPTION, { tone: 'error' })
          return
        default:
          toast("You're all set", { tone: 'success' })
      }
      trackUpgradeSucceeded(tier, priceTitle)
      setSelectedPlanId(null)
      await load()
    } catch (e) {
      toast('Checkout failed', { tone: 'error', body: apiError(e) })
    } finally {
      setActivePriceId(null)
    }
  }

  // Deprecation "Try Omi Pro" + trial "View Plans": select the Omi Pro card
  // (or first available) and scroll the grid into view.
  const jumpToOmiPro = (): void => {
    const omiPro = catalog.find((p) => p.id === 'unlimited_v2') ?? catalog[0]
    if (omiPro) setSelectedPlanId(omiPro.id)
    plansRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="surface-card p-5">
            <div className="skeleton mb-3 h-4 w-1/3" />
            <div className="skeleton h-1.5 w-full rounded-full" />
          </div>
        ))}
      </div>
    )
  }

  if (error && !sub) {
    return (
      <div>
        <div className="glass-subtle mb-4 px-4 py-3 text-sm text-white/60">{error}</div>
        <button onClick={onRefresh} disabled={refreshing} className="btn-ghost">
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Try again
        </button>
      </div>
    )
  }

  // A 200 that lacks `.subscription` (or a null body) leaves the tab with nothing
  // renderable — surface a friendly retry instead of a blank panel. Mirrors the
  // `error && !sub` state above.
  if (!sub || !subscription) {
    return (
      <div>
        <div className="glass-subtle mb-4 px-4 py-3 text-sm text-white/60">
          Couldn’t load your plan details.
        </div>
        <button onClick={onRefresh} disabled={refreshing} className="btn-ghost">
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Try again
        </button>
      </div>
    )
  }

  const showCatalog = sub.show_subscription_ui !== false && catalog.length > 0

  return (
    <div className="space-y-4">
      <CurrentPlanCard
        sub={sub}
        portalBusy={portalBusy}
        refreshing={refreshing}
        onManage={onManage}
        onRefresh={onRefresh}
      />

      {subscription.deprecated ? (
        <BillingCard
          icon={AlertTriangle}
          iconTone="amber"
          className="border border-amber-400/25"
          title="Plan Retiring"
          subtitle={
            subscription.deprecation_message ??
            `Your plan is being retired. Try Omi Pro at ${OMI_PRO_DEPRECATION_FALLBACK_PRICE}.`
          }
          trailing={
            showCatalog ? (
              <button onClick={jumpToOmiPro} className="btn-ghost">
                Try Omi Pro
              </button>
            ) : undefined
          }
        />
      ) : null}

      {quota ? <ChatUsageCard quota={quota} isOveragePlan={isOveragePlan} /> : null}

      {overage?.is_overage_plan ? <OverageCard overage={overage} /> : null}

      {trial && (isTrialActive(trial) || trial.trial_expired) ? (
        <TrialCard trial={trial} onViewPlans={jumpToOmiPro} />
      ) : null}

      {showCatalog ? (
        <div ref={plansRef} className="scroll-mt-4">
          <PlanGrid
            plans={catalog}
            sub={subscription}
            selectedId={selectedPlanId}
            onSelect={setSelectedPlanId}
            activePriceId={activePriceId}
            onBuy={onBuy}
          />
        </div>
      ) : null}
    </div>
  )
}
