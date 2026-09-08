import { useState } from 'react'
import { Check, Loader2, ChevronDown, Tag } from 'lucide-react'
import { cn } from '../../../lib/utils'
import {
  planEyebrow,
  planSubtitle,
  planDescription,
  planFeatures,
  planStartingPrice,
  sortedPrices,
  canPurchasePlan,
  planAccent
} from '../../../lib/billing'
import type { Subscription, SubscriptionPlan } from '../../../lib/omiApi.generated'

/**
 * Plan catalog grid (AccountBilling): pick one plan to reveal its billing
 * options. Each card shows an eyebrow, title, starting-price, description, and
 * up to four feature bullets; selecting it expands a promo-code field and one
 * button per interval (month-first). Accent green, except Architect (Mac purple
 * → neutral white per INV-UI-1).
 */
export function PlanGrid(props: {
  plans: SubscriptionPlan[]
  sub: Subscription
  selectedId: string | null
  onSelect: (id: string | null) => void
  activePriceId: string | null
  onBuy: (priceId: string, promotionCode?: string) => void
}): React.JSX.Element {
  return (
    <section>
      <h2 className="text-[15px] font-semibold text-text-primary">Choose a plan</h2>
      <p className="mt-1 text-sm text-text-tertiary">
        Pick one plan first. Billing options appear only after the card is selected.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {props.plans.map((plan) => (
          <PlanCard
            key={plan.id}
            plan={plan}
            sub={props.sub}
            selected={props.selectedId === plan.id}
            onSelect={props.onSelect}
            activePriceId={props.activePriceId}
            onBuy={props.onBuy}
          />
        ))}
      </div>
    </section>
  )
}

function PlanCard(props: {
  plan: SubscriptionPlan
  sub: Subscription
  selected: boolean
  onSelect: (id: string | null) => void
  activePriceId: string | null
  onBuy: (priceId: string, promotionCode?: string) => void
}): React.JSX.Element {
  const { plan, sub, selected, onSelect, activePriceId, onBuy } = props
  const [promo, setPromo] = useState('')
  const [promoOpen, setPromoOpen] = useState(false)
  const purchasable = canPurchasePlan(plan, sub)
  const accent = planAccent(plan)
  const checkColor = accent === 'green' ? 'text-emerald-400' : 'text-white/55'
  const anyCheckoutActive = activePriceId != null

  return (
    // h-full + flex column: grid stretches the cards to equal height, and the
    // controls block below carries mt-auto so promo inputs and the price buttons
    // share one baseline across cards no matter how the subtitle/features wrap.
    <div
      className={cn(
        'surface-card flex h-full flex-col gap-3 p-5 text-left transition-all',
        selected && 'ring-1 ring-white/25',
        !purchasable && 'opacity-55'
      )}
    >
      <button
        type="button"
        disabled={!purchasable}
        onClick={() => onSelect(selected ? null : plan.id)}
        className="flex flex-col gap-3 text-left disabled:cursor-not-allowed"
      >
        <div className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
          {planEyebrow(plan)}
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-lg font-semibold text-text-primary">{plan.title}</span>
          <span className="shrink-0 text-right text-xs text-white/45">
            {planStartingPrice(plan)}
            <span className="ml-1 text-white/30">starting</span>
          </span>
        </div>
        <p className="text-sm text-text-tertiary">{planSubtitle(plan)}</p>
        <p className="text-xs leading-relaxed text-white/45">{planDescription(plan)}</p>
        <ul className="space-y-1.5">
          {planFeatures(plan).map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-white/75">
              <Check className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', checkColor)} />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </button>

      {!purchasable ? (
        <p className="mt-auto text-xs text-white/40">Included with your current plan.</p>
      ) : selected ? (
        <div className="mt-auto flex flex-col gap-2 border-t border-white/[0.06] pt-3">
          <button
            type="button"
            onClick={() => setPromoOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs text-white/55 hover:text-white/80"
          >
            <Tag className="h-3.5 w-3.5" />
            Promo code
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform', promoOpen && 'rotate-180')}
            />
          </button>
          {promoOpen ? (
            <input
              value={promo}
              onChange={(e) => setPromo(e.target.value)}
              placeholder="Enter promo code"
              className="input-field py-2 text-sm"
            />
          ) : null}
          <div className="mt-1 text-xs font-medium text-white/45">Choose billing</div>
          {sortedPrices(plan).map((price) => {
            const busy = activePriceId === price.id
            return (
              <button
                key={price.id}
                onClick={() => onBuy(price.id, promo.trim() || undefined)}
                disabled={anyCheckoutActive}
                className="flex w-full items-center justify-between gap-2 rounded-2xl bg-white px-4 py-2.5 text-sm font-semibold text-black transition hover:opacity-90 disabled:opacity-50"
              >
                <span>{price.title}</span>
                <span className="flex items-center gap-2">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {price.price_string}
                </span>
              </button>
            )
          })}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onSelect(plan.id)}
          className="btn-ghost mt-auto w-full"
        >
          Select {plan.title}
        </button>
      )}
    </div>
  )
}
