import { CreditCard, Loader2, RefreshCw } from 'lucide-react'
import { BillingCard } from './BillingCard'
import {
  resolvePlanTitle,
  currentPlanSubtitle,
  currentPlanPeriodText,
  hasPaidSubscription
} from '../../../lib/billing'
import type { UserSubscriptionResponse } from '../../../lib/omiApi.generated'

/**
 * Current-plan card (AccountBilling "planusage.current"): plan title + billing
 * detail, a renew/access-ends caption, and a Manage (paid → Stripe portal) or
 * Refresh (free) action.
 */
export function CurrentPlanCard(props: {
  sub: UserSubscriptionResponse
  portalBusy: boolean
  refreshing: boolean
  onManage: () => void
  onRefresh: () => void
}): React.JSX.Element {
  const { sub, portalBusy, refreshing, onManage, onRefresh } = props
  const subscription = sub.subscription
  const paid = hasPaidSubscription(subscription)
  const periodText = currentPlanPeriodText(subscription)

  return (
    <BillingCard
      icon={CreditCard}
      title={resolvePlanTitle(subscription, sub.available_plans)}
      subtitle={currentPlanSubtitle(subscription, sub.available_plans)}
      trailing={
        paid ? (
          <button
            onClick={onManage}
            disabled={portalBusy}
            className="btn-ghost disabled:opacity-50"
          >
            {portalBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Manage
          </button>
        ) : (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="btn-ghost disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        )
      }
    >
      {periodText ? <div className="text-sm text-text-tertiary">{periodText}</div> : null}
    </BillingCard>
  )
}
