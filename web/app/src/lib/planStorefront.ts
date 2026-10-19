/**
 * Ladder-v1 plans sheet presentation (`GET /v2/payments/plans`, schema 2).
 *
 * The backend owns rank, recommendation, every plan string, prices and
 * entitlements; see `backend/docs/storefront-contract.md`. This module only
 * decodes the payload defensively and decides whether a rendered price may
 * start a purchase. It mirrors the mobile model in
 * `app/lib/models/plan_storefront.dart`.
 */
import type {
  StorefrontCurrent,
  ChatAtCap,
  StorefrontPrice,
  StorefrontResponse,
  StorefrontTier,
  StorefrontUsage,
} from '@/lib/omiApi.generated';
import { decodePlan, type CatalogPlanId } from '@/types/user';

export type StorefrontTrigger =
  | 'usage_budget'
  | 'proactive_agent'
  | 'screen_context'
  | 'mcp_daily_cap';

export type StorefrontAction = 'checkout' | 'current' | 'none';
export type StorefrontInterval = 'month' | 'year';

export interface PlanStorefrontPrice {
  /** Exact checkout price id; never rebuilt from tier or interval. Null for Free. */
  id: string | null;
  interval: StorefrontInterval;
  amountMinor: number;
  currency: string;
  headline: string;
  subline: string | null;
  renewalLine: string | null;
  monthsFree: number | null;
  ctaLabel: string | null;
  confirmLines?: string[];
}

export interface PlanStorefrontTier {
  tierId: string;
  planId: string;
  name: string;
  recommended: boolean;
  isCurrent: boolean;
  hoursLine: string;
  bullets: string[];
  action: StorefrontAction;
  ctaLabel: string | null;
  blockedLine: string | null;
  compact: boolean;
  prices: PlanStorefrontPrice[];
}

export interface PlanStorefrontCurrent {
  planId: string;
  name: string;
  priceId: string | null;
  interval: StorefrontInterval | null;
  legacy: boolean;
  cancelAtPeriodEnd: boolean;
  line: string;
  legacyNote: string | null;
}

export interface PlanStorefrontUsage {
  kind: 'usage_budget' | 'transcription' | 'unavailable';
  percent: number | null;
  periodId: string | null;
  resetLabel: string | null;
  meterLine: string | null;
  nudgeLine: string | null;
  proGates: string[];
}

export interface PlanStorefront {
  chatAtCap?: ChatAtCap | null;
  catalogRevision: number;
  showSubscriptionUi: boolean;
  header: string | null;
  current: PlanStorefrontCurrent | null;
  usage: PlanStorefrontUsage;
  tiers: PlanStorefrontTier[];
  yearlyToggleLabel: string | null;
}

export type StorefrontCheckoutDecision = 'refuse' | 'checkout' | 'resubscribe';

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

function interval(value: unknown): StorefrontInterval | null {
  return value === 'month' || value === 'year' ? value : null;
}

function decodePrice(raw: StorefrontPrice): PlanStorefrontPrice | null {
  const priceInterval = interval(raw?.interval);
  const headline = text(raw?.headline);
  const amount = raw?.amount_minor;
  if (!priceInterval || !headline || !Number.isInteger(amount) || amount < 0) return null;
  return {
    id: text(raw.price_id),
    interval: priceInterval,
    amountMinor: amount,
    currency: text(raw.currency) ?? '',
    headline,
    subline: text(raw.subline),
    renewalLine: text(raw.renewal_line),
    monthsFree: Number.isInteger(raw.months_free) ? (raw.months_free as number) : null,
    ctaLabel: text(raw.cta_label),
    confirmLines: (raw.confirm_lines ?? []).filter(
      (line): line is string => text(line) !== null,
    ),
  };
}

function decodeTier(raw: StorefrontTier): PlanStorefrontTier | null {
  const tierId = text(raw?.tier_id);
  const planId = text(raw?.plan_id);
  const name = text(raw?.name);
  if (!tierId || !planId || !name) return null;
  const prices: PlanStorefrontPrice[] = [];
  for (const row of Array.isArray(raw.prices) ? raw.prices : []) {
    const price = decodePrice(row);
    // One price per interval; a duplicate would make the toggle ambiguous.
    if (price && !prices.some((p) => p.interval === price.interval)) prices.push(price);
  }
  // An action this client does not know is not purchasable.
  const action: StorefrontAction =
    raw.action === 'checkout' || raw.action === 'current' ? raw.action : 'none';
  return {
    tierId,
    planId,
    name,
    recommended: raw.recommended === true,
    isCurrent: raw.is_current === true,
    hoursLine: typeof raw.hours_line === 'string' ? raw.hours_line : '',
    bullets: (Array.isArray(raw.bullets) ? raw.bullets : []).filter(
      (b): b is string => text(b) !== null,
    ),
    action,
    ctaLabel: text(raw.cta_label),
    blockedLine: text(raw.blocked_line),
    compact: raw.compact === true,
    prices,
  };
}

function decodeCurrent(
  raw: StorefrontCurrent | null | undefined,
): PlanStorefrontCurrent | null {
  const planId = text(raw?.plan_id);
  const name = text(raw?.name);
  const line = text(raw?.line);
  if (!raw || !planId || !name || !line || typeof raw.legacy !== 'boolean') return null;
  return {
    planId,
    name,
    priceId: text(raw.price_id),
    interval: interval(raw.interval),
    legacy: raw.legacy,
    cancelAtPeriodEnd: raw.cancel_at_period_end === true,
    line,
    legacyNote: raw.legacy ? text(raw.legacy_note) : null,
  };
}

function decodeUsage(raw: StorefrontUsage | undefined): PlanStorefrontUsage {
  const kind =
    raw?.kind === 'usage_budget' || raw?.kind === 'transcription'
      ? raw.kind
      : 'unavailable';
  const percent =
    typeof raw?.percent === 'number' && Number.isFinite(raw.percent) && raw.percent >= 0
      ? raw.percent
      : null;
  return {
    kind,
    percent,
    periodId: text(raw?.period_id),
    resetLabel: text(raw?.reset_label),
    meterLine: text(raw?.meter_line),
    nudgeLine: text(raw?.nudge_line),
    proGates: (Array.isArray(raw?.pro_gates) ? raw.pro_gates : []).filter(
      (g): g is string => text(g) !== null,
    ),
  };
}

/**
 * Decode a schema-2 payload. Unknown fields are ignored; unknown actions,
 * intervals and usage kinds degrade to their inert value. A different schema
 * version or a missing revision throws so the caller shows its error state.
 */
export function parseStorefront(raw: unknown): PlanStorefront {
  const json = raw as Partial<StorefrontResponse> | null;
  if (!json || typeof json !== 'object' || json.schema_version !== 2) {
    throw new Error('Unsupported storefront schema');
  }
  if (!Number.isInteger(json.catalog_revision)) {
    throw new Error('Invalid storefront catalog revision');
  }
  const tiers: PlanStorefrontTier[] = [];
  for (const row of Array.isArray(json.tiers) ? json.tiers : []) {
    const tier = decodeTier(row);
    if (
      tier &&
      !tiers.some((t) => t.tierId === tier.tierId || t.planId === tier.planId)
    ) {
      tiers.push(tier);
    }
  }
  return {
    chatAtCap:
      json.chat_at_cap?.state === 'paused' && json.chat_at_cap.trigger === 'usage_budget'
        ? json.chat_at_cap
        : null,
    catalogRevision: json.catalog_revision as number,
    showSubscriptionUi: json.show_subscription_ui === true,
    header: text(json.header),
    current: decodeCurrent(json.current),
    usage: decodeUsage(json.usage),
    tiers,
    yearlyToggleLabel: text(json.yearly_toggle_label),
  };
}

const LADDER: readonly CatalogPlanId[] = ['basic', 'plus', 'operator', 'architect'];

/** basic < plus < operator < architect; null off the ladder or unknown. */
function ladderRank(planId: string | null | undefined): number | null {
  if (!planId) return null;
  const plan = decodePlan(planId);
  if (plan.kind !== 'known') return null;
  const index = LADDER.indexOf(plan.id);
  return index < 0 ? null : index;
}

/** True for Neo/Unlimited and for ids this client does not recognize. */
function offLadder(planId: string | null | undefined): boolean {
  return planId != null && ladderRank(planId) === null;
}

function samePlan(a: string, b: string): boolean {
  const left = decodePlan(a);
  const right = decodePlan(b);
  return left.kind === 'known' && right.kind === 'known' && left.id === right.id;
}

export function isCancelScheduled(data: PlanStorefront | null | undefined): boolean {
  return data?.current?.cancelAtPeriodEnd === true;
}

/**
 * The single checkout boundary for rendering and every click.
 *
 * Paid subscribers may move up the ladder. The only same-tier purchase is
 * monthly to yearly from a monthly price. Legacy prices, off-ladder plans and
 * unknown plan ids never check out. While a cancellation is scheduled the only
 * purchase is resubscribing on the current price.
 */
export function storefrontCheckoutDecision(
  data: PlanStorefront,
  tier: PlanStorefrontTier,
  price: PlanStorefrontPrice,
  livePlanId?: string | null,
): StorefrontCheckoutDecision {
  const current = data.current;
  if (
    !data.showSubscriptionUi ||
    data.usage.kind === 'transcription' ||
    current?.legacy
  ) {
    return 'refuse';
  }
  if (offLadder(current?.planId) || offLadder(livePlanId) || offLadder(tier.planId)) {
    return 'refuse';
  }
  if (tier.action === 'none' || !tier.prices.includes(price) || price.id === null) {
    return 'refuse';
  }
  // `current` is purchasable only through a price-level label (yearly switch).
  if (tier.action === 'current' && price.ctaLabel === null) return 'refuse';
  const sameTier = current != null && samePlan(current.planId, tier.planId);
  if (sameTier && current.interval === 'year' && price.interval === 'month')
    return 'refuse';
  const held = tier.prices.find((p) => p.id !== null && p.id === current?.priceId);
  if (held?.interval === 'year' && price.interval === 'month') return 'refuse';
  const target = ladderRank(tier.planId);
  const liveRank = ladderRank(livePlanId);
  const currentRank = ladderRank(current?.planId);
  const effective =
    liveRank === null
      ? currentRank
      : currentRank === null
      ? liveRank
      : Math.max(liveRank, currentRank);
  if (target !== null && effective !== null && target < effective) return 'refuse';
  const cancelScheduled = isCancelScheduled(data);
  if (price.id === current?.priceId) return cancelScheduled ? 'resubscribe' : 'refuse';
  if (cancelScheduled) return 'refuse';
  if (sameTier && !(current.interval === 'month' && price.interval === 'year'))
    return 'refuse';
  return 'checkout';
}

/** The backend's words for one price's button; a price label replaces the tier label. */
export function storefrontActionLabel(
  tier: PlanStorefrontTier,
  price: PlanStorefrontPrice,
  decision: StorefrontCheckoutDecision,
): string | null {
  if (decision === 'refuse') return null;
  return price.ctaLabel ?? tier.ctaLabel;
}

/** The selected interval's price; a single-price card shows it on either chip. */
export function offeredPrice(
  tier: PlanStorefrontTier,
  selected: StorefrontInterval,
): PlanStorefrontPrice | null {
  return (
    tier.prices.find((p) => p.interval === selected) ??
    (tier.prices.length === 1 ? tier.prices[0] : null)
  );
}

/** Monthly by default; yearly only when the current card publishes nothing else. */
export function initialInterval(data: PlanStorefront): StorefrontInterval {
  if (data.current?.interval !== 'year') return 'month';
  const current = data.tiers.find((t) => t.isCurrent);
  return current &&
    !current.prices.some((p) => p.interval === 'month') &&
    current.prices.some((p) => p.interval === 'year')
    ? 'year'
    : 'month';
}

/**
 * Cards shown before "See all plans". While a cancellation is scheduled the
 * current card leads and every tier is shown (each other card carries the
 * backend's blocked line); otherwise recommended and current cards lead.
 */
export function partitionTiers(data: PlanStorefront): {
  primary: PlanStorefrontTier[];
  rest: PlanStorefrontTier[];
} {
  if (isCancelScheduled(data)) {
    const ordered = [
      ...data.tiers.filter((t) => t.isCurrent),
      ...data.tiers.filter((t) => !t.isCurrent),
    ];
    return { primary: ordered, rest: [] };
  }
  const primary = data.tiers.filter((t) => t.recommended || t.isCurrent);
  return { primary, rest: data.tiers.filter((t) => !primary.includes(t)) };
}

/** 80–99% budget nudge. At 100% the sheet itself is the exhausted surface. */
export function showBudgetNudge(data: PlanStorefront): boolean {
  const { usage } = data;
  return (
    data.showSubscriptionUi &&
    data.current?.legacy === false &&
    usage.kind === 'usage_budget' &&
    usage.percent !== null &&
    usage.percent >= 80 &&
    usage.percent < 100 &&
    usage.nudgeLine !== null
  );
}

/** Budget fully used on a ladder plan: opening the sheet shows the exhausted surface. */
export function budgetExhausted(data: PlanStorefront): boolean {
  return (
    data.showSubscriptionUi &&
    data.current?.legacy === false &&
    data.usage.kind === 'usage_budget' &&
    data.usage.percent !== null &&
    data.usage.percent >= 100
  );
}

/** Pro gates apply only below Pro on the ladder and only when the backend lists them. */
export function shouldGate(
  data: PlanStorefront,
  feature: string,
  livePlanId?: string | null,
): boolean {
  const current = data.current;
  if (!data.showSubscriptionUi || !current || current.legacy) return false;
  if (!data.usage.proGates.includes(feature)) return false;
  if (offLadder(current.planId) || offLadder(livePlanId)) return false;
  const rank = Math.max(ladderRank(current.planId) ?? -1, ladderRank(livePlanId) ?? -1);
  return rank < (ladderRank('operator') as number);
}
