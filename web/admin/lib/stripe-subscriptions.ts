import type Stripe from "stripe";

/**
 * Shared Stripe subscription reads for the revenue dashboards.
 *
 * Every route used to list subscriptions for two hardcoded price IDs, so products launched after
 * Omi Unlimited were invisible to every metric. These helpers list subscriptions by status and
 * group them by product, so a product added in Stripe shows up without a code or env change.
 */

/** Payment is still being retried on `past_due`; the subscription is intact, so it counts. */
export const MRR_STATUSES: Stripe.SubscriptionListParams.Status[] = [
  "active",
  "past_due",
];

/** Reported separately: a trial is pipeline, not revenue. */
export const PIPELINE_STATUSES: Stripe.SubscriptionListParams.Status[] = [
  "trialing",
];

/** Stripe's complete set of recurring intervals. Anything else is a Stripe change, not a gap. */
const MONTHS_PER_INTERVAL: Record<string, number> = {
  day: 12 / 365,
  week: 12 / 52,
  month: 1,
  year: 12,
};

/**
 * Every dashboard figure is dollars. Stripe prices carry their own currency, and summing a EUR
 * price into a USD total would report a number that is not money in any currency, so non-USD
 * prices are excluded and counted separately rather than silently blended.
 */
const REPORTING_CURRENCY = "usd";

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

/**
 * The Omi subscription plans. Metrics count these products and nothing else: the same Stripe
 * account also holds marketplace apps and internal test products. Launching a plan adds a line.
 */
export const OMI_PLAN_PRODUCTS: Record<string, string> = {
  prod_SmpevIU38nIEUO: "Omi Unlimited",
  prod_Uu6nrHIKWnnTWL: "Omi Unlimited v2",
  prod_Uu5HDt3sygCK8N: "Omi Plus",
  prod_ULep5SEo0pSdaM: "Operator",
  prod_U8x5HNGnTF50X1: "Omi Architect",
  prod_UM0IIpZ4iOgfk5: "Neo",
};

export function isOmiPlanSubscription(
  subscription: Stripe.Subscription
): boolean {
  return subscription.items.data.some((item) => {
    const productId = productIdOf(item);
    return productId !== null && productId in OMI_PLAN_PRODUCTS;
  });
}

/** Thrown when every status leg fails, so callers never publish a fabricated zero. */
export class AllSubscriptionSourcesFailedError extends Error {}

function priceOf(item: Stripe.SubscriptionItem): Stripe.Price | null {
  return typeof item.price === "string" ? null : item.price;
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
  return typeof product === "string" ? product : product.id;
}

/**
 * Monthly-normalised amount for one subscription, in dollars.
 *
 * Annual plans divide by 12; any other interval normalises through its own month count, so a
 * quarterly or weekly price is not silently counted as a monthly one.
 *
 * Only USD prices are counted — see `isNonUsdPrice` / `countNonUsdSubscriptions`.
 */
export function monthlyAmount(subscription: Stripe.Subscription): number {
  return subscription.items.data.reduce((sum, item) => {
    const price = priceOf(item);
    if (!price) return sum;

    if (isNonUsd(price)) {
      console.warn(
        `Excluding non-USD price ${price.id} (${price.currency}) on subscription ${subscription.id} from MRR: dashboard totals are USD-only`
      );
      return sum;
    }

    const amount = ((price.unit_amount ?? 0) * (item.quantity ?? 1)) / 100;
    const recurring = price.recurring;
    if (!recurring) return sum;

    const monthsPerInterval = MONTHS_PER_INTERVAL[recurring.interval];
    if (!monthsPerInterval) {
      // MONTHS_PER_INTERVAL covers Stripe's whole interval set, so this means Stripe added one.
      // Loud rather than a silent $0 contribution that reads as a real number on the dashboard.
      console.warn(
        `Unknown recurring interval "${recurring.interval}" on price ${price.id}; excluded from MRR`
      );
      return sum;
    }

    const months = monthsPerInterval * (recurring.interval_count || 1);
    return sum + amount / months;
  }, 0);
}

function isNonUsd(price: Stripe.Price): boolean {
  // Stripe always sets `currency`; a fixture without one is treated as the reporting currency.
  return Boolean(price.currency) && price.currency !== REPORTING_CURRENCY;
}

/** True when any item on the subscription is priced in a currency the dashboard cannot total. */
export function isNonUsdSubscription(
  subscription: Stripe.Subscription
): boolean {
  return subscription.items.data.some((item) => {
    const price = priceOf(item);
    return price !== null && isNonUsd(price);
  });
}

/** How many subscriptions `monthlyAmount` left out of the totals for being non-USD. */
export function countNonUsdSubscriptions(
  subscriptions: Stripe.Subscription[]
): number {
  return subscriptions.filter(isNonUsdSubscription).length;
}

/** Annualised amount for one subscription, in dollars. */
export function annualAmount(subscription: Stripe.Subscription): number {
  return monthlyAmount(subscription) * 12;
}

/** True when every item on the subscription bills yearly. */
export function isAnnual(subscription: Stripe.Subscription): boolean {
  const items = subscription.items.data;
  if (items.length === 0) return false;
  return items.every((item) => priceOf(item)?.recurring?.interval === "year");
}

export async function listSubscriptions(
  stripe: Stripe,
  params: Stripe.SubscriptionListParams
): Promise<Stripe.Subscription[]> {
  const all: Stripe.Subscription[] = [];
  let startingAfter: string | undefined;

  for (;;) {
    const page: Stripe.ApiList<Stripe.Subscription> =
      await stripe.subscriptions.list({
        limit: 100,
        expand: ["data.items.data.price"],
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
  params: Omit<Stripe.SubscriptionListParams, "status"> = {}
): Promise<SubscriptionFetch> {
  const results = await Promise.allSettled(
    statuses.map((status) => listSubscriptions(stripe, { ...params, status }))
  );

  results.forEach((result, index) => {
    if (result.status === "rejected") {
      console.error(
        `Error fetching ${statuses[index]} subscriptions:`,
        result.reason
      );
    }
  });

  if (
    results.length > 0 &&
    results.every((result) => result.status === "rejected")
  ) {
    throw new AllSubscriptionSourcesFailedError(
      "All subscription data sources failed"
    );
  }

  const subscriptions = results
    .flatMap((result) => (result.status === "fulfilled" ? result.value : []))
    .filter(
      (subscription) =>
        !isAppSubscription(subscription) && isOmiPlanSubscription(subscription)
    );

  return {
    subscriptions,
    partial: results.some((result) => result.status === "rejected"),
  };
}

export function groupByProduct(
  subscriptions: Stripe.Subscription[],
  productNames: Record<string, string> = {}
): ProductGroup[] {
  const groups = new Map<string, ProductGroup>();

  for (const subscription of subscriptions) {
    const productId =
      subscription.items.data.map(productIdOf).find(Boolean) ?? "unknown";
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

/** FinOps plan keys used by `omi_finops.plan_revenue_daily`; Neo books with Unlimited. */
export const WALL_PLAN_KEYS: Record<string, string> = {
  prod_SmpevIU38nIEUO: "unlimited",
  prod_UM0IIpZ4iOgfk5: "unlimited",
  prod_Uu6nrHIKWnnTWL: "unlimited_v2",
  prod_Uu5HDt3sygCK8N: "plus",
  prod_ULep5SEo0pSdaM: "operator",
  prod_U8x5HNGnTF50X1: "architect",
};

/** Wall audit: product-scoped, including every new price. Unknown products stay visible as gaps.
 * Currency values are never added without an explicit USD exchange rate. JPY has no cents.
 */
export function wallSubscriptionBook(
  subscriptions: Stripe.Subscription[],
  fx: Record<string, number> = { usd: 1 }
) {
  const zeroDecimal = new Set([
    "bif",
    "clp",
    "djf",
    "gnf",
    "jpy",
    "kmf",
    "krw",
    "mga",
    "pyg",
    "rwf",
    "ugx",
    "vnd",
    "vuv",
    "xaf",
    "xof",
    "xpf",
  ]);
  const extra = (process.env.OMI_TV_PLAN_PRODUCT_IDS || "")
    .split(",")
    .filter(Boolean);
  let usd = 0,
    unmappedProducts = 0,
    unsupportedItems = 0;
  const monthlyByCurrency: Record<string, number> = {};
  /** USD MRR by FinOps plan key; explicit extra products are "other". */
  const byPlan: Record<string, number> = {};
  for (const subscription of subscriptions) {
    if (
      isAppSubscription(subscription) ||
      !MRR_STATUSES.includes(subscription.status)
    )
      continue;
    for (const item of subscription.items.data) {
      const product = productIdOf(item);
      if (
        !product ||
        (!(product in OMI_PLAN_PRODUCTS) && !extra.includes(product))
      ) {
        unmappedProducts++;
        continue;
      }
      const price = priceOf(item);
      if (
        !price?.recurring ||
        price.unit_amount == null ||
        price.billing_scheme === "tiered"
      ) {
        unsupportedItems++;
        continue;
      }
      const currency = price.currency || "usd";
      const months =
        MONTHS_PER_INTERVAL[price.recurring.interval] *
        (price.recurring.interval_count || 1);
      if (!months) {
        unsupportedItems++;
        continue;
      }
      const amount =
        (price.unit_amount * (item.quantity ?? 1)) /
        (zeroDecimal.has(currency) ? 1 : 100) /
        months;
      monthlyByCurrency[currency] = (monthlyByCurrency[currency] || 0) + amount;
      if (!Number.isFinite(fx[currency]) || fx[currency] <= 0) {
        unsupportedItems++;
        continue;
      }
      usd += amount * fx[currency];
      const plan = WALL_PLAN_KEYS[product] || "other";
      byPlan[plan] = (byPlan[plan] || 0) + amount * fx[currency];
    }
  }
  return { usd, byPlan, monthlyByCurrency, unmappedProducts, unsupportedItems };
}

export async function fetchWallSubscriptionBook(stripe: Stripe) {
  const results = await Promise.allSettled(
    MRR_STATUSES.map((status) => listSubscriptions(stripe, { status }))
  );
  if (results.every((r) => r.status === "rejected"))
    throw new AllSubscriptionSourcesFailedError("Stripe unavailable");
  const book = wallSubscriptionBook(
    results.flatMap((r) => (r.status === "fulfilled" ? r.value : []))
  );
  return { ...book, partial: results.some((r) => r.status === "rejected") };
}
