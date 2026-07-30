import type Stripe from 'stripe';

/**
 * Shared Stripe subscription reads for the revenue dashboards.
 *
 * Every route used to list subscriptions for two hardcoded price IDs, so products launched after
 * Omi Unlimited were invisible to every metric. These helpers list subscriptions by status and
 * group them by product, so a product added in Stripe shows up without a code or env change.
 */

/** Payment is still being retried on `past_due`; the subscription is intact, so it counts. */
export const MRR_STATUSES: Stripe.SubscriptionListParams.Status[] = ['active', 'past_due'];

/** Reported separately: a trial is pipeline, not revenue. */
export const PIPELINE_STATUSES: Stripe.SubscriptionListParams.Status[] = ['trialing'];

const MONTHS_PER_INTERVAL: Record<string, number> = {
  day: 12 / 365,
  week: 12 / 52,
  month: 1,
  year: 12,
};

export interface ProductGroup {
  productId: string;
  productName: string;
  subscriptionCount: number;
  mrr: number;
}

export interface SubscriptionFetch {
  subscriptions: Stripe.Subscription[];
  /** True when at least one status leg failed but others succeeded. */
  partial: boolean;
}

/** Thrown when every status leg fails, so callers never publish a fabricated zero. */
export class AllSubscriptionSourcesFailedError extends Error {}

function priceOf(item: Stripe.SubscriptionItem): Stripe.Price | null {
  return typeof item.price === 'string' ? null : item.price;
}

/**
 * Marketplace app subscriptions carry `metadata.app_id`, set by the backend when it creates the
 * app checkout session (`backend/utils/stripe.py`). First-party Omi plans never do. This is the
 * only durable split: both kinds live in one Stripe account and neither product naming nor tax
 * code is reliable.
 */
export function isAppSubscription(subscription: Stripe.Subscription): boolean {
  return Boolean(subscription.metadata?.app_id);
}

export function productIdOf(item: Stripe.SubscriptionItem): string | null {
  const price = priceOf(item);
  if (!price) return null;
  const product = price.product;
  if (!product) return null;
  return typeof product === 'string' ? product : product.id;
}

/**
 * Monthly-normalised amount for one subscription, in dollars.
 *
 * Annual plans divide by 12; any other interval normalises through its own month count, so a
 * quarterly or weekly price is not silently counted as a monthly one.
 */
export function monthlyAmount(subscription: Stripe.Subscription): number {
  return subscription.items.data.reduce((sum, item) => {
    const price = priceOf(item);
    if (!price) return sum;

    const amount = ((price.unit_amount ?? 0) * (item.quantity ?? 1)) / 100;
    const recurring = price.recurring;
    if (!recurring) return sum;

    const monthsPerInterval = MONTHS_PER_INTERVAL[recurring.interval];
    if (!monthsPerInterval) return sum;

    const months = monthsPerInterval * (recurring.interval_count || 1);
    return sum + amount / months;
  }, 0);
}

/** Annualised amount for one subscription, in dollars. */
export function annualAmount(subscription: Stripe.Subscription): number {
  return monthlyAmount(subscription) * 12;
}

/** True when every item on the subscription bills yearly. */
export function isAnnual(subscription: Stripe.Subscription): boolean {
  const items = subscription.items.data;
  if (items.length === 0) return false;
  return items.every((item) => priceOf(item)?.recurring?.interval === 'year');
}

export async function listSubscriptions(
  stripe: Stripe,
  params: Stripe.SubscriptionListParams,
): Promise<Stripe.Subscription[]> {
  const all: Stripe.Subscription[] = [];
  let startingAfter: string | undefined;

  for (;;) {
    const page: Stripe.ApiList<Stripe.Subscription> = await stripe.subscriptions.list({
      limit: 100,
      expand: ['data.items.data.price'],
      ...params,
      ...(startingAfter ? { starting_after: startingAfter } : {}),
    });
    all.push(...page.data);
    if (!page.has_more || page.data.length === 0) break;
    startingAfter = page.data[page.data.length - 1].id;
  }

  return all;
}

/**
 * List first-party Omi subscriptions across `statuses`, dropping marketplace app subscriptions.
 *
 * Status legs run through `Promise.allSettled`: one failing status degrades to `partial` rather
 * than losing the whole payload, and only a total failure throws.
 */
export async function fetchOmiSubscriptions(
  stripe: Stripe,
  statuses: Stripe.SubscriptionListParams.Status[] = MRR_STATUSES,
  params: Omit<Stripe.SubscriptionListParams, 'status'> = {},
): Promise<SubscriptionFetch> {
  const results = await Promise.allSettled(
    statuses.map((status) => listSubscriptions(stripe, { ...params, status })),
  );

  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      console.error(`Error fetching ${statuses[index]} subscriptions:`, result.reason);
    }
  });

  if (results.length > 0 && results.every((result) => result.status === 'rejected')) {
    throw new AllSubscriptionSourcesFailedError('All subscription data sources failed');
  }

  const subscriptions = results
    .flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
    .filter((subscription) => !isAppSubscription(subscription));

  return { subscriptions, partial: results.some((result) => result.status === 'rejected') };
}

export function groupByProduct(
  subscriptions: Stripe.Subscription[],
  productNames: Record<string, string> = {},
): ProductGroup[] {
  const groups = new Map<string, ProductGroup>();

  for (const subscription of subscriptions) {
    const productId = subscription.items.data.map(productIdOf).find(Boolean) ?? 'unknown';
    const group = groups.get(productId) ?? {
      productId,
      productName: productNames[productId] ?? productId,
      subscriptionCount: 0,
      mrr: 0,
    };
    group.subscriptionCount += 1;
    group.mrr += monthlyAmount(subscription);
    groups.set(productId, group);
  }

  return Array.from(groups.values()).sort((a, b) => b.mrr - a.mrr);
}

/**
 * Best-effort product id → name map. Names are presentation only, so a failure here degrades to
 * bare ids rather than failing the metric.
 */
export async function resolveProductNames(
  stripe: Stripe,
  productIds: string[],
): Promise<Record<string, string>> {
  const ids = Array.from(new Set(productIds)).filter((id) => id && id !== 'unknown');
  if (ids.length === 0) return {};

  const names: Record<string, string> = {};
  for (let i = 0; i < ids.length; i += 100) {
    try {
      const page = await stripe.products.list({ ids: ids.slice(i, i + 100), limit: 100 });
      for (const product of page.data) {
        names[product.id] = product.name;
      }
    } catch (error) {
      console.error('Error resolving Stripe product names:', error);
    }
  }
  return names;
}
