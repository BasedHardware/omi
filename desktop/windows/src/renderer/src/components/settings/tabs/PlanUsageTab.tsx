import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useSearchableRow } from '../searchContext'
import { toast } from '../../../lib/toast'
import { CurrentPlanCard } from '../billing/CurrentPlanCard'
import { ChatUsageCard } from '../billing/ChatUsageCard'
import { OverageCard } from '../billing/OverageCard'
import { TrialCard } from '../billing/TrialCard'
import { PlanGrid } from '../billing/PlanGrid'
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
  openCustomerPortal
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
  useSearchableRow(
    'plan usage billing subscription upgrade quota trial overage payment neo operator architect'
  )

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
          return // user abandoned — no toast
        case 'refresh_lagging':
          toast('Payment received', { tone: 'warn', body: REFRESH_LAGGING_MSG })
          break
        case 'upgraded':
          toast('Plan updated', { tone: 'success' })
          break
        case 'reactivated':
          toast('Subscription reactivated', { tone: 'success' })
          break
        default:
          toast("You're all set", { tone: 'success' })
      }
      setSelectedPlanId(null)
      await load()
    } catch (e) {
      toast('Checkout failed', { tone: 'error', body: apiError(e) })
    } finally {
      setActivePriceId(null)
    }
  }

  // Deprecation "Try Operator" + trial "View Plans": select the Operator card
  // (or first available) and scroll the grid into view.
  const jumpToOperator = (): void => {
    const operator =
      catalog.find((p) => p.id === 'operator' || p.title === 'Operator') ?? catalog[0]
    if (operator) setSelectedPlanId(operator.id)
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

  if (!sub || !subscription) return <></>

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
        <div className="surface-card border border-amber-400/25 p-5">
          <div className="flex items-start gap-3.5">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-400/10">
              <AlertTriangle className="h-[18px] w-[18px] text-amber-400" strokeWidth={1.9} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold text-text-primary">Plan Retiring</div>
              <p className="mt-1 text-sm text-text-tertiary">
                {subscription.deprecation_message ??
                  'Your Unlimited plan is being retired. Try the new Operator plan — same great features at $49/mo.'}
              </p>
            </div>
            {showCatalog ? (
              <button onClick={jumpToOperator} className="btn-ghost ml-2 shrink-0">
                Try Operator
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {quota ? <ChatUsageCard quota={quota} isOveragePlan={isOveragePlan} /> : null}

      {overage?.is_overage_plan ? <OverageCard overage={overage} /> : null}

      {trial && isTrialActive(trial) ? (
        <TrialCard trial={trial} onViewPlans={jumpToOperator} />
      ) : trial?.trial_expired ? (
        <TrialCard trial={trial} onViewPlans={jumpToOperator} />
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
