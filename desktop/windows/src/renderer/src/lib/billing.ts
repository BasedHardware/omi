import { omiApi } from './apiClient'
import type {
  UserSubscriptionResponse,
  Subscription,
  SubscriptionPlan,
  PricingOption,
  ChatUsageQuota,
  TrialMetadata,
  OverageInfoResponse,
  PaymentCheckoutSessionResponse,
  PaymentUpgradeSubscriptionResponse,
  CustomerPortalSessionResponse
} from './omiApi.generated'
import type { CheckoutOutcome } from '../../../shared/types'

// Billing model + logic for the Plan & Usage tab. Ported from the macOS app
// (SettingsContentView+AccountBilling.swift / +BillingHelpers.swift) — same
// resolution rules, copy, and checkout flow — with one mandated deviation: no
// purple (Mac accents Architect purple / Neo+Operator green; here Architect is
// neutral white, the green stays, and the usage bar warns in amber, never purple).

// ── Data layer ──────────────────────────────────────────────────────────────
// axios client auto-injects the Firebase token + X-App-Platform: windows header
// (the backend version-gates the plan catalog on it).

export function fetchSubscription(): Promise<UserSubscriptionResponse> {
  return omiApi.get('/v1/users/me/subscription').then((r) => r.data as UserSubscriptionResponse)
}

export function fetchChatQuota(): Promise<ChatUsageQuota> {
  return omiApi.get('/v1/users/me/usage-quota').then((r) => r.data as ChatUsageQuota)
}

export function fetchTrial(): Promise<TrialMetadata> {
  return omiApi.get('/v1/users/me/trial').then((r) => r.data as TrialMetadata)
}

export function fetchOverageInfo(): Promise<OverageInfoResponse> {
  return omiApi.get('/v1/payments/overage-info').then((r) => r.data as OverageInfoResponse)
}

// ── Plan-name resolution (BillingHelpers.currentPlanTitle) ──────────────────

/**
 * Whether the current subscription is really Operator. The backend serializes
 * Operator as plan='unlimited' for old-mobile compatibility; Mac disambiguates
 * by checking whether current_price_id belongs to the catalog plan titled
 * "Operator". (BillingHelpers.isCurrentSubscriptionOperator.)
 */
export function isCurrentSubscriptionOperator(
  sub: Pick<Subscription, 'plan' | 'current_price_id'>,
  availablePlans: SubscriptionPlan[] | undefined
): boolean {
  const priceId = sub.current_price_id
  if (!priceId) return false
  return (availablePlans ?? [])
    .filter((p) => p.title === 'Operator')
    .some((p) => (p.prices ?? []).some((price) => price.id === priceId))
}

/**
 * Display name for the current subscription. BYOK always wins (checked first,
 * as on Mac). Then CATALOG-FIRST: if the current price belongs to a catalog
 * plan, show THAT plan's title — the exact name the user bought and sees in the
 * grid (the Windows catalog titles plans "Unlimited Plan"/"Omi Pro", so the
 * enum names would mismatch). This price-id match also subsumes Mac's
 * Operator-as-unlimited disambiguation. Fall back to the Mac enum names only
 * when there's no catalog match (empty catalog / legacy price id).
 */
export function resolvePlanTitle(
  sub: Pick<Subscription, 'plan' | 'current_price_id' | 'features'>,
  availablePlans: SubscriptionPlan[] | undefined
): string {
  if ((sub.features ?? []).includes('byok')) return 'Free (BYOK)'
  const owning = owningCatalogPlan(sub, availablePlans)
  if (owning) return owning.title
  switch (sub.plan) {
    case 'basic':
      return 'Free'
    case 'unlimited':
      return 'Neo'
    case 'architect':
      return 'Architect'
    case 'operator':
      return 'Operator'
    default:
      return 'Free'
  }
}

/** BillingHelpers.hasPaidSubscription — BYOK is never "paid". */
export function hasPaidSubscription(
  sub: Pick<Subscription, 'plan' | 'status' | 'features'>
): boolean {
  if ((sub.features ?? []).includes('byok')) return false
  return sub.plan !== 'basic' && sub.status === 'active'
}

/** The catalog plan that owns the current price (for the billing-detail subtitle). */
function owningCatalogPlan(
  sub: Pick<Subscription, 'current_price_id'>,
  availablePlans: SubscriptionPlan[] | undefined
): SubscriptionPlan | undefined {
  const priceId = sub.current_price_id
  if (!priceId) return undefined
  return (availablePlans ?? []).find((p) => (p.prices ?? []).some((price) => price.id === priceId))
}

/**
 * Current-plan card subtitle (BillingHelpers.currentPlanSubtitle): the paid
 * billing detail ("<plan> <interval> • <price>") when resolvable, else a plain
 * paid/free line.
 */
export function currentPlanSubtitle(
  sub: Subscription,
  availablePlans: SubscriptionPlan[] | undefined
): string {
  const paid = hasPaidSubscription(sub)
  if (paid && sub.current_price_id) {
    const plan = owningCatalogPlan(sub, availablePlans)
    const price = (plan?.prices ?? []).find((p) => p.id === sub.current_price_id)
    if (plan && price) return `${plan.title} ${price.title} • ${price.price_string}`
  }
  return paid ? 'Your paid plan is active.' : 'You are currently on the free tier.'
}

/**
 * "Renews on <date>" / "Access ends on <date>" for paid plans with a period end
 * (BillingHelpers.currentPlanPeriodText). Medium date style, no time.
 */
export function currentPlanPeriodText(sub: Subscription): string {
  if (!hasPaidSubscription(sub) || !sub.current_period_end) return ''
  const prefix = sub.cancel_at_period_end ? 'Access ends' : 'Renews'
  return `${prefix} on ${formatMediumDate(sub.current_period_end)}`
}

export function formatMediumDate(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return ''
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

// ── Chat usage / quota (AccountBilling chat-usage card) ─────────────────────

export const QUOTA_WARNING_PERCENT = 80

export type QuotaView = {
  /** "30 / 30", "$2.50 / $10", "999 / ∞". */
  valueText: string
  /** "Chat questions on <plan> plan" / "Chat spend on <plan> plan". */
  description: string
  /** 0–1, clamped, for the bar width. */
  fraction: number
  percent: number
  allowed: boolean
  resetAt: number | null
  /** Bar/warning tint on: !allowed, or percent ≥ 80 (Mac uses purple; we use amber). */
  warning: boolean
  /** Below-bar caption when limited/near-limit, or '' when fine. */
  belowBarWarning: string
}

function formatUsageValue(quota: ChatUsageQuota): string {
  if (quota.unit === 'cost_usd') {
    const limit = quota.limit == null ? '—' : `$${quota.limit.toFixed(0)}`
    return `$${(quota.used ?? 0).toFixed(2)} / ${limit}`
  }
  const limit = quota.limit == null ? '∞' : String(Math.round(quota.limit))
  return `${Math.round(quota.used ?? 0)} / ${limit}`
}

/** Derive the chat-usage card view model. `isOveragePlan` picks the overage
 *  variant of the limit-reached caption. */
export function chatQuotaView(quota: ChatUsageQuota, isOveragePlan = false): QuotaView {
  const percent = quota.percent ?? 0
  const allowed = quota.allowed ?? true
  const warning = !allowed || percent >= QUOTA_WARNING_PERCENT
  let belowBarWarning = ''
  if (!allowed) {
    belowBarWarning = isOveragePlan
      ? "You're past your included limit — extra usage is billed as overage at end of cycle."
      : "You've reached this month's limit. Upgrade your plan or wait until the next reset."
  } else if (percent >= QUOTA_WARNING_PERCENT) {
    belowBarWarning = "You're close to your monthly limit."
  }
  return {
    valueText: formatUsageValue(quota),
    description:
      quota.unit === 'cost_usd'
        ? `Chat spend on ${quota.plan} plan`
        : `Chat questions on ${quota.plan} plan`,
    fraction: Math.max(0, Math.min(1, percent / 100)),
    percent,
    allowed,
    resetAt: quota.reset_at ?? null,
    warning,
    belowBarWarning
  }
}

/**
 * "Resets today/tomorrow/in N days" (BillingHelpers.chatUsageQuotaResetText).
 * Day count is Int-truncated elapsed days (floor), matching Mac exactly.
 */
export function quotaResetText(resetAtSeconds: number | null, now: Date = new Date()): string {
  if (!resetAtSeconds) return ''
  const days = Math.max(0, Math.floor((resetAtSeconds * 1000 - now.getTime()) / 86_400_000))
  if (days <= 0) return 'Resets today'
  if (days === 1) return 'Resets tomorrow'
  return `Resets in ${days} days`
}

// ── Plan catalog (AccountBilling plan grid) ─────────────────────────────────

// Mac ordering: Neo(unlimited) → Operator → Architect. Unknown ids sort last.
const PLAN_ORDER: Record<string, number> = { unlimited: 0, operator: 1, architect: 2 }

/** True if this catalog plan is the one the user is currently on (operator↔
 *  unlimited aliasing + current-price ownership). */
export function isCurrentCatalogPlan(
  plan: SubscriptionPlan,
  sub: Pick<Subscription, 'plan' | 'current_price_id'>,
  availablePlans: SubscriptionPlan[] | undefined
): boolean {
  if (sub.current_price_id && (plan.prices ?? []).some((p) => p.id === sub.current_price_id)) {
    return true
  }
  const operator = isCurrentSubscriptionOperator(sub, availablePlans)
  const effectivePlanId = sub.plan === 'unlimited' && operator ? 'operator' : sub.plan
  return plan.id === effectivePlanId
}

/** Order the catalog (Neo→Operator→Architect, unknown last, stable) and drop the
 *  plan the user is already on. */
export function orderedCatalog(
  sub: Pick<Subscription, 'plan' | 'current_price_id'>,
  availablePlans: SubscriptionPlan[] | undefined
): SubscriptionPlan[] {
  return (availablePlans ?? [])
    .filter((p) => !isCurrentCatalogPlan(p, sub, availablePlans))
    .map((p, i) => ({ p, i }))
    .sort((a, b) => {
      const oa = PLAN_ORDER[a.p.id] ?? 99
      const ob = PLAN_ORDER[b.p.id] ?? 99
      return oa - ob || a.i - b.i
    })
    .map(({ p }) => p)
}

// Per-plan-id fallbacks (BillingHelpers planEyebrow/planSubtitle/planDescription/
// fallback features), used only when the catalog omits the field.
const PLAN_FALLBACKS: Record<
  string,
  { eyebrow: string; subtitle: string; description: string; features: string[] }
> = {
  unlimited: {
    eyebrow: 'Starter',
    subtitle: '200 questions per month',
    description: '100 chat questions per month. Shared with mobile and web.',
    features: [
      '200 chat questions per month',
      'Unlimited listening and transcription',
      'Unlimited memories and insights',
      'Shared with mobile and web'
    ]
  },
  operator: {
    eyebrow: 'Most popular',
    subtitle: '500 questions per month',
    description: '500 chat questions per month. Shared with mobile and web.',
    features: [
      '500 chat questions per month',
      'Unlimited listening and transcription',
      'Unlimited memories and insights',
      'Shared with mobile and web'
    ]
  },
  architect: {
    eyebrow: 'Automation + coding',
    subtitle: 'Power-user AI — thousands of chats + agentic automations',
    description: 'Power-user AI for heavy agentic workflows and vibe coding.',
    features: [
      'Automations and vibe coding',
      'Unlimited listening, memories, and insights',
      'Priority desktop AI features',
      '~$400 of monthly AI compute included (fair-use cap)'
    ]
  }
}

export function planEyebrow(plan: SubscriptionPlan): string {
  return (plan.eyebrow ?? PLAN_FALLBACKS[plan.id]?.eyebrow ?? 'Plan').toUpperCase()
}
export function planSubtitle(plan: SubscriptionPlan): string {
  return plan.subtitle ?? PLAN_FALLBACKS[plan.id]?.subtitle ?? ''
}
export function planDescription(plan: SubscriptionPlan): string {
  return plan.description ?? PLAN_FALLBACKS[plan.id]?.description ?? ''
}
export function planFeatures(plan: SubscriptionPlan): string[] {
  const feats =
    plan.features && plan.features.length > 0
      ? plan.features
      : (PLAN_FALLBACKS[plan.id]?.features ?? [])
  return feats.slice(0, 4)
}

/** Prices sorted month-first (BillingHelpers.sortedPrices): the interval whose
 *  title/id doesn't mention "year" comes first. */
export function sortedPrices(plan: SubscriptionPlan): PricingOption[] {
  const isYearly = (p: PricingOption): boolean => /year|annual/i.test(`${p.title} ${p.id}`)
  return (plan.prices ?? []).slice().sort((a, b) => Number(isYearly(a)) - Number(isYearly(b)))
}

/** "starting price" summary: the monthly (or first) price string. */
export function planStartingPrice(plan: SubscriptionPlan): string {
  return sortedPrices(plan)[0]?.price_string ?? ''
}

/**
 * Whether the user may purchase this plan. Mac blocks an Architect/Operator user
 * from "downgrading" to unlimited (Neo) via the grid (canPurchase=false).
 */
export function canPurchasePlan(plan: SubscriptionPlan, sub: Pick<Subscription, 'plan'>): boolean {
  if (plan.id === 'unlimited' && (sub.plan === 'architect' || sub.plan === 'operator')) return false
  return true
}

/** Architect stays neutral (Mac purple → white per INV-UI-1); others green. */
export function planAccent(plan: SubscriptionPlan): 'neutral' | 'green' {
  return plan.id === 'architect' ? 'neutral' : 'green'
}

// ── Trial (AccountBilling trial card) ────────────────────────────────────────

export function isTrialActive(trial: TrialMetadata): boolean {
  return !trial.trial_expired && trial.trial_started_at != null
}

/** BillingHelpers.trialCountdownText — d/h/m thresholds. */
export function trialCountdownText(remainingSeconds: number): string {
  if (remainingSeconds <= 0) return 'Expired'
  const hours = Math.floor(remainingSeconds / 3600)
  if (hours >= 24) {
    const days = Math.floor(hours / 24)
    return `${days}d ${hours % 24}h remaining`
  }
  if (hours > 0) {
    const minutes = Math.floor((remainingSeconds % 3600) / 60)
    return `${hours}h ${minutes}m remaining`
  }
  return `${Math.floor(remainingSeconds / 60)}m remaining`
}

/** 0–1 progress through the trial. */
export function trialProgress(trial: TrialMetadata): number {
  const total = trial.trial_duration_seconds ?? 0
  if (total <= 0) return 0
  return Math.max(0, Math.min(1, (trial.trial_remaining_seconds ?? 0) / total))
}

/** Trial urgency tone: amber ≤1h (Mac warning), yellow ≤24h, else green. */
export function trialTimeTone(remainingSeconds: number): 'amber' | 'yellow' | 'green' {
  if (remainingSeconds <= 3600) return 'amber'
  if (remainingSeconds <= 86_400) return 'yellow'
  return 'green'
}

// ── Checkout orchestration (BillingHelpers.startCheckout) ───────────────────

export type StartCheckoutResult =
  | { kind: 'upgraded' }
  | { kind: 'reactivated' }
  | { kind: 'completed' }
  | { kind: 'refresh_lagging' }
  | { kind: 'cancelled' }

export type CheckoutDeps = {
  createCheckoutSession: (
    priceId: string,
    promotionCode?: string
  ) => Promise<PaymentCheckoutSessionResponse>
  upgradeSubscription: (
    priceId: string,
    promotionCode?: string
  ) => Promise<PaymentUpgradeSubscriptionResponse>
  openCheckout: (url: string) => Promise<CheckoutOutcome>
  fetchSubscription: () => Promise<UserSubscriptionResponse>
  wait: (ms: number) => Promise<void>
}

const POLL_ATTEMPTS = 8
const POLL_INTERVAL_MS = 1000

/**
 * Drive a purchase for `priceId`. macOS parity (BillingHelpers.startCheckout):
 *  - Active paid sub NOT scheduled to cancel → upgrade in place (no browser).
 *  - Else create a checkout session; 'reactivated' means the sub was un-cancelled
 *    (no browser); otherwise open the Stripe URL in the in-app window.
 *  - On success, poll the subscription (8 × 1s, fixed) until current_price_id
 *    matches AND the plan is a paid active plan. If it never catches up, return
 *    'refresh_lagging' so the caller can show the "catching up" message.
 */
export async function startCheckout(
  args: { priceId: string; promotionCode?: string; currentSubscription: Subscription },
  deps: CheckoutDeps
): Promise<StartCheckoutResult> {
  const { priceId, promotionCode, currentSubscription: sub } = args

  const upgradeInPlace = hasPaidSubscription(sub) && sub.cancel_at_period_end === false
  if (upgradeInPlace) {
    await deps.upgradeSubscription(priceId, promotionCode)
    return { kind: 'upgraded' }
  }

  const session = await deps.createCheckoutSession(priceId, promotionCode)
  if (session.status === 'reactivated') return { kind: 'reactivated' }
  if (!session.url) return { kind: 'cancelled' }

  const outcome = await deps.openCheckout(session.url)
  if (outcome !== 'success') return { kind: 'cancelled' }

  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
    const fresh = await deps.fetchSubscription()
    const s = fresh.subscription
    const matched = s.current_price_id === priceId
    const paidActive = s.plan !== 'basic' && s.status === 'active'
    if (matched && paidActive) return { kind: 'completed' }
    if (attempt < POLL_ATTEMPTS - 1) await deps.wait(POLL_INTERVAL_MS)
  }
  return { kind: 'refresh_lagging' }
}

// ── API-bound checkout deps (tests inject fakes instead) ────────────────────

export function createCheckoutSession(
  priceId: string,
  promotionCode?: string
): Promise<PaymentCheckoutSessionResponse> {
  return omiApi
    .post('/v1/payments/checkout-session', {
      price_id: priceId,
      ...(promotionCode ? { promotion_code: promotionCode } : {})
    })
    .then((r) => r.data as PaymentCheckoutSessionResponse)
}

export function upgradeSubscription(
  priceId: string,
  promotionCode?: string
): Promise<PaymentUpgradeSubscriptionResponse> {
  return omiApi
    .post('/v1/payments/upgrade-subscription', {
      price_id: priceId,
      ...(promotionCode ? { promotion_code: promotionCode } : {})
    })
    .then((r) => r.data as PaymentUpgradeSubscriptionResponse)
}

/** Open the Stripe customer portal in the system browser (Mac parity). */
export function openCustomerPortal(): Promise<void> {
  return omiApi
    .post('/v1/payments/customer-portal')
    .then((r) => (r.data as CustomerPortalSessionResponse).url)
    .then((url) => {
      if (url) void window.omi.openExternalUrl(url)
    })
}
