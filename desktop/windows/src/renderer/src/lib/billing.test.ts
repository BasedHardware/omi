import { describe, it, expect, vi } from 'vitest'
import {
  isCurrentSubscriptionOperator,
  resolvePlanTitle,
  hasPaidSubscription,
  currentPlanSubtitle,
  currentPlanPeriodText,
  chatQuotaView,
  quotaResetText,
  orderedCatalog,
  isCurrentCatalogPlan,
  planEyebrow,
  planSubtitle,
  planDescription,
  planFeatures,
  sortedPrices,
  planStartingPrice,
  canPurchasePlan,
  planAccent,
  trialCountdownText,
  trialProgress,
  trialTimeTone,
  startCheckout,
  type CheckoutDeps
} from './billing'
import type {
  Subscription,
  SubscriptionPlan,
  ChatUsageQuota,
  TrialMetadata,
  UserSubscriptionResponse
} from './omiApi.generated'

// billing.ts imports the axios client at module load; the pure helpers under
// test never touch it, so a bare stub is enough to let the module import.
vi.mock('./apiClient', () => ({ omiApi: { get: vi.fn(), post: vi.fn() } }))

const CATALOG: SubscriptionPlan[] = [
  {
    id: 'unlimited',
    title: 'Neo',
    prices: [{ id: 'price_neo_m', title: 'Monthly', price_string: '$14/mo' }]
  },
  {
    id: 'operator',
    title: 'Operator',
    prices: [
      { id: 'price_op_m', title: 'Monthly', price_string: '$49/mo' },
      { id: 'price_op_y', title: 'Annual', price_string: '$490/yr' }
    ]
  },
  {
    id: 'architect',
    title: 'Architect',
    prices: [{ id: 'price_arch_m', title: 'Monthly', price_string: '$99/mo' }]
  }
]

function sub(partial: Partial<Subscription>): Subscription {
  return { plan: 'basic', status: 'active', cancel_at_period_end: false, ...partial }
}

describe('resolvePlanTitle', () => {
  it('short-circuits to Free (BYOK) for any plan with the byok feature', () => {
    expect(resolvePlanTitle(sub({ plan: 'basic', features: ['byok'] }), CATALOG)).toBe(
      'Free (BYOK)'
    )
    expect(resolvePlanTitle(sub({ plan: 'unlimited', features: ['byok'] }), CATALOG)).toBe(
      'Free (BYOK)'
    )
  })
  it('maps basic to Free', () => {
    expect(resolvePlanTitle(sub({ plan: 'basic' }), CATALOG)).toBe('Free')
  })
  it('maps unlimited to Neo by default', () => {
    expect(
      resolvePlanTitle(sub({ plan: 'unlimited', current_price_id: 'price_neo_m' }), CATALOG)
    ).toBe('Neo')
  })
  it('remaps unlimited to Operator when the price belongs to the Operator catalog plan', () => {
    expect(
      resolvePlanTitle(sub({ plan: 'unlimited', current_price_id: 'price_op_y' }), CATALOG)
    ).toBe('Operator')
  })
  it('maps operator to Operator and architect to Architect', () => {
    expect(resolvePlanTitle(sub({ plan: 'operator' }), CATALOG)).toBe('Operator')
    expect(resolvePlanTitle(sub({ plan: 'architect' }), CATALOG)).toBe('Architect')
  })
})

// The Windows-served catalog titles its plans differently from the enum names,
// so the catalog-first rule must show what the user actually bought.
const LIVE_CATALOG: SubscriptionPlan[] = [
  {
    id: 'unlimited',
    title: 'Unlimited Plan',
    prices: [
      { id: 'price_u_m', title: 'Monthly', price_string: '$19.99/month' },
      { id: 'price_u_y', title: 'Annual', price_string: '$199.99/year' }
    ]
  },
  {
    id: 'architect',
    title: 'Omi Pro',
    prices: [{ id: 'price_p_m', title: 'Monthly', price_string: '$199.00/month' }]
  }
]

describe('resolvePlanTitle — catalog-first with the live Windows catalog', () => {
  it('shows the catalog title the user actually bought, not the enum name', () => {
    expect(
      resolvePlanTitle(sub({ plan: 'unlimited', current_price_id: 'price_u_m' }), LIVE_CATALOG)
    ).toBe('Unlimited Plan')
    expect(
      resolvePlanTitle(sub({ plan: 'architect', current_price_id: 'price_p_m' }), LIVE_CATALOG)
    ).toBe('Omi Pro')
  })
  it('falls back to the enum name when the price id is not in the catalog', () => {
    expect(
      resolvePlanTitle(sub({ plan: 'unlimited', current_price_id: 'legacy_price' }), LIVE_CATALOG)
    ).toBe('Neo')
  })
  it('still short-circuits to Free (BYOK) even with a catalog price match', () => {
    expect(
      resolvePlanTitle(
        sub({ plan: 'unlimited', current_price_id: 'price_u_m', features: ['byok'] }),
        LIVE_CATALOG
      )
    ).toBe('Free (BYOK)')
  })
  it('filters the subscriber’s own plan out of the grid even when titles differ from enum names', () => {
    const s = sub({ plan: 'unlimited', current_price_id: 'price_u_m' })
    expect(isCurrentCatalogPlan(LIVE_CATALOG[0], s, LIVE_CATALOG)).toBe(true)
    expect(orderedCatalog(s, LIVE_CATALOG).map((p) => p.title)).toEqual(['Omi Pro'])
  })
})

describe('isCurrentSubscriptionOperator', () => {
  it('is true only when the price belongs to the Operator plan', () => {
    expect(isCurrentSubscriptionOperator(sub({ current_price_id: 'price_op_m' }), CATALOG)).toBe(
      true
    )
    expect(isCurrentSubscriptionOperator(sub({ current_price_id: 'price_neo_m' }), CATALOG)).toBe(
      false
    )
    expect(isCurrentSubscriptionOperator(sub({}), CATALOG)).toBe(false)
    expect(isCurrentSubscriptionOperator(sub({ current_price_id: 'price_op_m' }), undefined)).toBe(
      false
    )
  })
})

describe('hasPaidSubscription', () => {
  it('treats byok as unpaid even on a paid plan', () => {
    expect(hasPaidSubscription(sub({ plan: 'operator', features: ['byok'] }))).toBe(false)
  })
  it('is false for basic and inactive paid plans', () => {
    expect(hasPaidSubscription(sub({ plan: 'basic' }))).toBe(false)
    expect(hasPaidSubscription(sub({ plan: 'operator', status: 'inactive' }))).toBe(false)
  })
  it('is true for an active paid plan', () => {
    expect(hasPaidSubscription(sub({ plan: 'operator', status: 'active' }))).toBe(true)
  })
})

describe('currentPlanSubtitle', () => {
  it('shows the billing detail for a paid plan', () => {
    expect(
      currentPlanSubtitle(
        sub({ plan: 'operator', status: 'active', current_price_id: 'price_op_m' }),
        CATALOG
      )
    ).toBe('Operator Monthly • $49/mo')
  })
  it('shows the free-tier line otherwise', () => {
    expect(currentPlanSubtitle(sub({ plan: 'basic' }), CATALOG)).toBe(
      'You are currently on the free tier.'
    )
  })
})

describe('currentPlanPeriodText', () => {
  const end = Math.floor(new Date('2026-08-01T00:00:00').getTime() / 1000)
  it('says Renews on <date> for an active paid plan', () => {
    const t = currentPlanPeriodText(
      sub({ plan: 'operator', status: 'active', current_period_end: end })
    )
    expect(t).toMatch(/^Renews on /)
    expect(t).toContain('2026')
  })
  it('says Access ends on <date> when cancelling', () => {
    const t = currentPlanPeriodText(
      sub({
        plan: 'operator',
        status: 'active',
        current_period_end: end,
        cancel_at_period_end: true
      })
    )
    expect(t).toMatch(/^Access ends on /)
  })
  it('is empty for a free plan', () => {
    expect(currentPlanPeriodText(sub({ plan: 'basic' }))).toBe('')
  })
})

describe('chatQuotaView', () => {
  const q = (p: Partial<ChatUsageQuota>): ChatUsageQuota => ({
    plan: 'basic',
    plan_type: 'free',
    unit: 'questions',
    used: 0,
    ...p
  })

  it('formats questions as used / limit', () => {
    expect(chatQuotaView(q({ used: 30, limit: 30, percent: 100 })).valueText).toBe('30 / 30')
  })
  it('formats an unlimited question quota with ∞', () => {
    expect(chatQuotaView(q({ used: 12, limit: null })).valueText).toBe('12 / ∞')
  })
  it('formats a cost quota as dollars', () => {
    expect(chatQuotaView(q({ unit: 'cost_usd', used: 2.5, limit: 10 })).valueText).toBe(
      '$2.50 / $10'
    )
  })
  it('describes the quota by unit', () => {
    expect(chatQuotaView(q({ plan: 'Neo' })).description).toBe('Chat questions on Neo plan')
    expect(chatQuotaView(q({ plan: 'Neo', unit: 'cost_usd' })).description).toBe(
      'Chat spend on Neo plan'
    )
  })
  it('warns at 80% and when not allowed', () => {
    expect(chatQuotaView(q({ percent: 79 })).warning).toBe(false)
    expect(chatQuotaView(q({ percent: 80 })).warning).toBe(true)
    expect(chatQuotaView(q({ percent: 10, allowed: false })).warning).toBe(true)
  })
  it('picks the right below-bar caption', () => {
    expect(chatQuotaView(q({ percent: 85, allowed: true })).belowBarWarning).toBe(
      "You're close to your monthly limit."
    )
    expect(chatQuotaView(q({ allowed: false })).belowBarWarning).toBe(
      "You've reached this month's limit. Upgrade your plan or wait until the next reset."
    )
    expect(chatQuotaView(q({ allowed: false }), true).belowBarWarning).toBe(
      "You're past your included limit — extra usage is billed as overage at end of cycle."
    )
    expect(chatQuotaView(q({ percent: 20, allowed: true })).belowBarWarning).toBe('')
  })
})

describe('quotaResetText', () => {
  const now = new Date('2026-07-13T12:00:00')
  const at = (iso: string): number => Math.floor(new Date(iso).getTime() / 1000)
  it('returns empty for no reset time', () => {
    expect(quotaResetText(null, now)).toBe('')
  })
  it('truncates elapsed days (floor), matching Mac', () => {
    // 23h away → 0 days → today
    expect(quotaResetText(at('2026-07-14T11:00:00'), now)).toBe('Resets today')
    // 25h away → 1 day → tomorrow
    expect(quotaResetText(at('2026-07-14T13:00:00'), now)).toBe('Resets tomorrow')
    // ~5.5 days away → floor 5
    expect(quotaResetText(at('2026-07-19T00:00:00'), now)).toBe('Resets in 5 days')
  })
})

describe('plan catalog helpers', () => {
  it('orders Neo → Operator → Architect and filters the current plan by price', () => {
    const s = sub({ plan: 'unlimited', current_price_id: 'price_neo_m' })
    expect(orderedCatalog(s, CATALOG).map((p) => p.title)).toEqual(['Operator', 'Architect'])
  })
  it('filters the Operator plan for an Operator-as-unlimited subscriber', () => {
    const s = sub({ plan: 'unlimited', current_price_id: 'price_op_m' })
    expect(isCurrentCatalogPlan(CATALOG[1], s, CATALOG)).toBe(true)
    expect(orderedCatalog(s, CATALOG).map((p) => p.title)).toEqual(['Neo', 'Architect'])
  })
  it('uppercases the eyebrow and falls back per plan id', () => {
    expect(planEyebrow({ id: 'operator', title: 'X' })).toBe('MOST POPULAR')
    expect(planEyebrow({ id: 'operator', title: 'X', eyebrow: 'featured' })).toBe('FEATURED')
  })
  it('falls back subtitle/description/features by plan id and caps features at 4', () => {
    const p: SubscriptionPlan = { id: 'architect', title: 'Architect' }
    expect(planSubtitle(p)).toContain('Power-user')
    expect(planDescription(p)).toContain('vibe coding')
    expect(planFeatures(p)).toHaveLength(4)
    expect(planFeatures({ id: 'x', title: 'X', features: ['a', 'b', 'c', 'd', 'e'] })).toEqual([
      'a',
      'b',
      'c',
      'd'
    ])
  })
  it('sorts prices month-first and reads the starting price', () => {
    expect(sortedPrices(CATALOG[1]).map((p) => p.title)).toEqual(['Monthly', 'Annual'])
    expect(planStartingPrice(CATALOG[1])).toBe('$49/mo')
  })
  it('blocks Operator/Architect users from downgrading to Neo', () => {
    expect(canPurchasePlan(CATALOG[0], sub({ plan: 'operator' }))).toBe(false)
    expect(canPurchasePlan(CATALOG[0], sub({ plan: 'basic' }))).toBe(true)
    expect(canPurchasePlan(CATALOG[1], sub({ plan: 'operator' }))).toBe(true)
  })
  it('keeps Architect neutral (no purple) and others green', () => {
    expect(planAccent(CATALOG[2])).toBe('neutral')
    expect(planAccent(CATALOG[1])).toBe('green')
  })
})

describe('trial helpers', () => {
  it('formats the countdown by threshold', () => {
    expect(trialCountdownText(0)).toBe('Expired')
    expect(trialCountdownText(3 * 86400 + 5 * 3600)).toBe('3d 5h remaining')
    expect(trialCountdownText(5 * 3600 + 30 * 60)).toBe('5h 30m remaining')
    expect(trialCountdownText(45 * 60)).toBe('45m remaining')
  })
  it('computes progress and urgency tone', () => {
    const t: TrialMetadata = {
      trial_duration_seconds: 100,
      trial_remaining_seconds: 25,
      trial_started_at: 1
    }
    expect(trialProgress(t)).toBeCloseTo(0.25)
    expect(trialTimeTone(1800)).toBe('amber')
    expect(trialTimeTone(50_000)).toBe('yellow')
    expect(trialTimeTone(200_000)).toBe('green')
  })
})

// ── startCheckout branching ─────────────────────────────────────────────────

function makeDeps(over: Partial<CheckoutDeps> = {}): CheckoutDeps {
  return {
    createCheckoutSession: vi.fn().mockResolvedValue({ url: 'https://checkout.stripe.com/x' }),
    upgradeSubscription: vi.fn().mockResolvedValue({ status: 'ok' }),
    openCheckout: vi.fn().mockResolvedValue('success'),
    fetchSubscription: vi.fn().mockResolvedValue({
      subscription: { current_price_id: 'price_op_m', plan: 'operator', status: 'active' }
    } as UserSubscriptionResponse),
    wait: vi.fn().mockResolvedValue(undefined),
    ...over
  }
}

describe('startCheckout', () => {
  it('upgrades an active paid sub in place (no browser)', async () => {
    const deps = makeDeps()
    const res = await startCheckout(
      {
        priceId: 'price_op_m',
        currentSubscription: sub({
          plan: 'unlimited',
          status: 'active',
          cancel_at_period_end: false
        })
      },
      deps
    )
    expect(res).toEqual({ kind: 'upgraded' })
    expect(deps.upgradeSubscription).toHaveBeenCalledWith('price_op_m', undefined)
    expect(deps.openCheckout).not.toHaveBeenCalled()
  })

  it('does NOT upgrade in place when the paid sub is scheduled to cancel', async () => {
    const deps = makeDeps()
    await startCheckout(
      {
        priceId: 'price_op_m',
        currentSubscription: sub({
          plan: 'unlimited',
          status: 'active',
          cancel_at_period_end: true
        })
      },
      deps
    )
    expect(deps.upgradeSubscription).not.toHaveBeenCalled()
    expect(deps.createCheckoutSession).toHaveBeenCalled()
  })

  it('opens the Stripe URL for a free user and completes on success', async () => {
    const deps = makeDeps()
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(deps.openCheckout).toHaveBeenCalledWith('https://checkout.stripe.com/x')
    expect(res.kind).toBe('completed')
  })

  it('skips the browser when the session reports reactivated', async () => {
    const deps = makeDeps({
      createCheckoutSession: vi.fn().mockResolvedValue({ status: 'reactivated' })
    })
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(res).toEqual({ kind: 'reactivated' })
    expect(deps.openCheckout).not.toHaveBeenCalled()
  })

  it('treats a session with no URL as cancelled', async () => {
    const deps = makeDeps({ createCheckoutSession: vi.fn().mockResolvedValue({}) })
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(res).toEqual({ kind: 'cancelled' })
  })

  it('treats a closed checkout window as cancelled (no poll)', async () => {
    const deps = makeDeps({ openCheckout: vi.fn().mockResolvedValue('closed') })
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(res).toEqual({ kind: 'cancelled' })
    expect(deps.fetchSubscription).not.toHaveBeenCalled()
  })

  it('polls until the price matches and the plan is paid+active', async () => {
    const fetchSubscription = vi
      .fn()
      .mockResolvedValueOnce({
        subscription: { current_price_id: 'old', plan: 'basic', status: 'active' }
      })
      .mockResolvedValueOnce({
        subscription: { current_price_id: 'price_op_m', plan: 'operator', status: 'active' }
      })
    const deps = makeDeps({ fetchSubscription })
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(res.kind).toBe('completed')
    expect(fetchSubscription).toHaveBeenCalledTimes(2)
    expect(deps.wait).toHaveBeenCalledTimes(1)
  })

  it('returns refresh_lagging after the attempt cap if the plan never flips', async () => {
    const fetchSubscription = vi.fn().mockResolvedValue({
      subscription: { current_price_id: 'old', plan: 'basic', status: 'active' }
    })
    const deps = makeDeps({ fetchSubscription })
    const res = await startCheckout(
      { priceId: 'price_op_m', currentSubscription: sub({ plan: 'basic' }) },
      deps
    )
    expect(res).toEqual({ kind: 'refresh_lagging' })
    expect(fetchSubscription).toHaveBeenCalledTimes(8)
  })
})
