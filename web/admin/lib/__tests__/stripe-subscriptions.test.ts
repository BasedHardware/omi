import { afterEach, describe, expect, it, vi } from 'vitest';
import type Stripe from 'stripe';
import {
  AllSubscriptionSourcesFailedError,
  MRR_STATUSES,
  PIPELINE_STATUSES,
  annualAmount,
  countNonUsdSubscriptions,
  isNonUsdSubscription,
  fetchOmiSubscriptions,
  groupByProduct,
  isAnnual,
  OMI_PLAN_PRODUCTS,
  isAppSubscription,
  isOmiPlanSubscription,
  listSubscriptions,
  monthlyAmount,
  productIdOf,
} from '../stripe-subscriptions';

type PriceShape = {
  id?: string;
  unit_amount: number | null;
  product?: string | { id: string };
  currency?: string;
  recurring?: { interval: string; interval_count?: number } | null;
};

function sub(
  prices: PriceShape[],
  extra: { id?: string; metadata?: Record<string, string>; status?: string } = {},
): Stripe.Subscription {
  return {
    id: extra.id ?? 'sub_test',
    status: extra.status ?? 'active',
    metadata: extra.metadata ?? {},
    items: {
      data: prices.map((price, index) => ({
        id: `si_${index}`,
        quantity: 1,
        price: {
          id: price.id ?? `price_${index}`,
          unit_amount: price.unit_amount,
          currency: price.currency ?? 'usd',
          product: price.product ?? 'prod_default',
          recurring: price.recurring === undefined ? { interval: 'month', interval_count: 1 } : price.recurring,
        },
      })),
    },
  } as unknown as Stripe.Subscription;
}

describe('monthlyAmount', () => {
  it('takes a monthly price as-is', () => {
    expect(monthlyAmount(sub([{ unit_amount: 1999 }]))).toBeCloseTo(19.99);
  });

  it('divides an annual price by twelve', () => {
    expect(monthlyAmount(sub([{ unit_amount: 12000, recurring: { interval: 'year' } }]))).toBeCloseTo(10);
  });

  it('normalises a multi-month interval', () => {
    // Quarterly: $30 per 3 months is $10/mo, not $30/mo.
    const quarterly = sub([{ unit_amount: 3000, recurring: { interval: 'month', interval_count: 3 } }]);
    expect(monthlyAmount(quarterly)).toBeCloseTo(10);
  });

  it('normalises weekly and daily intervals', () => {
    expect(monthlyAmount(sub([{ unit_amount: 100, recurring: { interval: 'week' } }]))).toBeCloseTo(1 * (52 / 12));
    expect(monthlyAmount(sub([{ unit_amount: 100, recurring: { interval: 'day' } }]))).toBeCloseTo(1 * (365 / 12));
  });

  it('multiplies by quantity', () => {
    const seats = sub([{ unit_amount: 1000 }]);
    seats.items.data[0].quantity = 5;
    expect(monthlyAmount(seats)).toBeCloseTo(50);
  });

  it('sums multiple items', () => {
    const bundle = sub([{ unit_amount: 1000 }, { unit_amount: 12000, recurring: { interval: 'year' } }]);
    expect(monthlyAmount(bundle)).toBeCloseTo(20);
  });

  it('ignores one-off items with no recurring interval', () => {
    expect(monthlyAmount(sub([{ unit_amount: 5000, recurring: null }]))).toBe(0);
  });

  it('treats a missing unit amount as zero rather than NaN', () => {
    expect(monthlyAmount(sub([{ unit_amount: null }]))).toBe(0);
  });

  it('annualises through the same normalisation', () => {
    expect(annualAmount(sub([{ unit_amount: 12000, recurring: { interval: 'year' } }]))).toBeCloseTo(120);
  });
});

describe('monthlyAmount honesty guards', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('warns loudly instead of silently contributing zero for an unknown interval', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const exotic = sub([{ unit_amount: 3000, recurring: { interval: 'fortnight' } }]);
    expect(monthlyAmount(exotic)).toBe(0);

    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('fortnight');
  });

  it('excludes non-USD prices rather than blending currencies, and says so', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const euros = sub([{ unit_amount: 1999, currency: 'eur' }]);
    expect(monthlyAmount(euros)).toBe(0);
    expect(String(warn.mock.calls[0][0])).toContain('eur');

    // A mixed subscription keeps only the USD leg.
    const mixed = sub([{ unit_amount: 1000 }, { unit_amount: 5000, currency: 'gbp' }]);
    expect(monthlyAmount(mixed)).toBeCloseTo(10);
  });

  it('treats a price with no currency field as the reporting currency', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const noCurrency = sub([{ unit_amount: 1000 }]);
    noCurrency.items.data[0].price.currency = undefined as unknown as string;

    expect(monthlyAmount(noCurrency)).toBeCloseTo(10);
    expect(warn).not.toHaveBeenCalled();
  });

  it('counts what it skipped so a route can report it', () => {
    const subscriptions = [
      sub([{ unit_amount: 1000 }], { id: 'sub_usd' }),
      sub([{ unit_amount: 1000, currency: 'eur' }], { id: 'sub_eur' }),
      sub([{ unit_amount: 1000 }, { unit_amount: 1000, currency: 'gbp' }], { id: 'sub_mixed' }),
    ];

    expect(subscriptions.map(isNonUsdSubscription)).toEqual([false, true, true]);
    expect(countNonUsdSubscriptions(subscriptions)).toBe(2);
  });

  it('keeps non-USD money out of grouped MRR', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const groups = groupByProduct([
      sub([{ unit_amount: 2000, product: 'prod_a' }]),
      sub([{ unit_amount: 9900, product: 'prod_a', currency: 'eur' }]),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].subscriptionCount).toBe(2);
    expect(groups[0].mrr).toBeCloseTo(20);
  });
});


describe('isOmiPlanSubscription', () => {
  it('returns true if the subscription has an item with an Omi plan product', () => {
    const planProduct = Object.keys(OMI_PLAN_PRODUCTS)[0];
    expect(isOmiPlanSubscription(sub([{ unit_amount: 1000, product: planProduct }]))).toBe(true);
  });

  it('returns false if no items match an Omi plan product', () => {
    expect(isOmiPlanSubscription(sub([{ unit_amount: 1000, product: 'prod_other' }]))).toBe(false);
  });

  it('returns false if the subscription has no items', () => {
    expect(isOmiPlanSubscription(sub([]))).toBe(false);
  });

  it('returns true for a mixed subscription where only one item matches an Omi plan product', () => {
    const planProduct = Object.keys(OMI_PLAN_PRODUCTS)[0];
    const mixed = sub([
      { unit_amount: 500, product: 'prod_other' },
      { unit_amount: 1000, product: planProduct }
    ]);
    expect(isOmiPlanSubscription(mixed)).toBe(true);
  });
});

describe('isAppSubscription', () => {
  it('is true only when the backend stamped an app_id', () => {
    expect(isAppSubscription(sub([{ unit_amount: 500 }], { metadata: { app_id: 'app_123' } }))).toBe(true);
    expect(isAppSubscription(sub([{ unit_amount: 500 }], { metadata: { uid: 'u1', sub_type: 'unlimited' } }))).toBe(
      false,
    );
    expect(isAppSubscription(sub([{ unit_amount: 500 }]))).toBe(false);
  });
});

describe('isAnnual', () => {
  it('classifies by billing interval, not by price id', () => {
    expect(isAnnual(sub([{ unit_amount: 12000, recurring: { interval: 'year' } }]))).toBe(true);
    expect(isAnnual(sub([{ unit_amount: 1000 }]))).toBe(false);
    // A mixed bundle is not an annual subscription.
    expect(isAnnual(sub([{ unit_amount: 12000, recurring: { interval: 'year' } }, { unit_amount: 1000 }]))).toBe(false);
  });
});

describe('productIdOf', () => {
  it('reads a string or expanded product', () => {
    expect(productIdOf(sub([{ unit_amount: 1, product: 'prod_a' }]).items.data[0])).toBe('prod_a');
    expect(productIdOf(sub([{ unit_amount: 1, product: { id: 'prod_b' } }]).items.data[0])).toBe('prod_b');
  });
});

describe('groupByProduct', () => {
  it('groups every product without a hardcoded list', () => {
    const groups = groupByProduct(
      [
        sub([{ unit_amount: 2000, product: 'prod_unlimited_v2' }]),
        sub([{ unit_amount: 2000, product: 'prod_unlimited_v2' }]),
        sub([{ unit_amount: 12000, product: 'prod_operator', recurring: { interval: 'year' } }]),
      ],
      { prod_unlimited_v2: 'Omi Unlimited v2', prod_operator: 'Operator' },
    );

    expect(groups.map((g) => [g.productName, g.subscriptionCount, g.mrr])).toEqual([
      ['Omi Unlimited v2', 2, 40],
      ['Operator', 1, 10],
    ]);
  });

  it('falls back to the product id when no name is known', () => {
    const [group] = groupByProduct([sub([{ unit_amount: 1000, product: 'prod_new' }])]);
    expect(group.productName).toBe('prod_new');
  });

  it('sorts by MRR descending so the dashboard leads with the biggest product', () => {
    const groups = groupByProduct([
      sub([{ unit_amount: 500, product: 'prod_small' }]),
      sub([{ unit_amount: 9900, product: 'prod_big' }]),
    ]);
    expect(groups.map((g) => g.productId)).toEqual(['prod_big', 'prod_small']);
  });
});

describe('status selection', () => {
  it('counts active and past_due toward MRR and keeps trialing out of it', () => {
    expect(MRR_STATUSES).toEqual(['active', 'past_due']);
    expect(PIPELINE_STATUSES).toEqual(['trialing']);
    expect(MRR_STATUSES).not.toContain('trialing');
  });
});

function stripeWithPages(pages: Record<string, Stripe.Subscription[][]>) {
  const list = vi.fn(async (params: Stripe.SubscriptionListParams) => {
    const status = String(params.status);
    const queue = pages[status];
    if (!queue) throw new Error(`unexpected status ${status}`);
    const index = params.starting_after ? Number(String(params.starting_after).split('#')[1]) + 1 : 0;
    const data = queue[index] ?? [];
    return { data, has_more: index < queue.length - 1 };
  });
  return { stripe: { subscriptions: { list } } as unknown as Stripe, list };
}

describe('listSubscriptions', () => {
  it('follows pagination to the last page', async () => {
    const page = (n: number) => [sub([{ unit_amount: 1000 }], { id: `sub#${n}` })];
    const { stripe, list } = stripeWithPages({ active: [page(0), page(1), page(2)] });

    const all = await listSubscriptions(stripe, { status: 'active' });

    expect(all).toHaveLength(3);
    expect(list).toHaveBeenCalledTimes(3);
    expect(list.mock.calls[0][0]).toMatchObject({ limit: 100, expand: ['data.items.data.price'] });
  });
});

describe('omi plan scoping', () => {
  it('counts the plan products and nothing else', async () => {
    const planProduct = Object.keys(OMI_PLAN_PRODUCTS)[0];
    const { stripe } = stripeWithPages({
      active: [
        [
          sub([{ unit_amount: 2000, product: planProduct }], { id: 'sub#0' }),
          // First-party but not a plan: an internal test product is not revenue.
          sub([{ unit_amount: 9900, product: 'prod_internal_test' }], { id: 'sub#1' }),
          sub([{ unit_amount: 500, product: planProduct }], { id: 'sub#2', metadata: { app_id: 'app_1' } }),
        ],
      ],
      past_due: [[]],
    });

    const { subscriptions } = await fetchOmiSubscriptions(stripe);

    expect(subscriptions).toHaveLength(1);
    expect(productIdOf(subscriptions[0].items.data[0])).toBe(planProduct);
  });

  it('names every plan it counts', () => {
    expect(Object.values(OMI_PLAN_PRODUCTS).sort()).toEqual([
      'Neo',
      'Omi Architect',
      'Omi Plus',
      'Omi Unlimited',
      'Omi Unlimited v2',
      'Operator',
    ]);
  });
});

describe('fetchOmiSubscriptions', () => {
  it('merges the status legs and drops marketplace app subscriptions', async () => {
    const plan = Object.keys(OMI_PLAN_PRODUCTS)[0];
    const { stripe } = stripeWithPages({
      active: [
        [
          sub([{ unit_amount: 2000, product: plan }], { id: 'sub#0' }),
          sub([{ unit_amount: 500, product: plan }], { id: 'sub#1', metadata: { app_id: 'app_1' } }),
        ],
      ],
      past_due: [[sub([{ unit_amount: 2000, product: plan }], { id: 'sub#0' })]],
    });

    const { subscriptions, partial } = await fetchOmiSubscriptions(stripe);

    expect(subscriptions).toHaveLength(2);
    expect(subscriptions.every((s) => !isAppSubscription(s))).toBe(true);
    expect(partial).toBe(false);
  });

  it('degrades to partial when one status leg fails', async () => {
    const list = vi.fn(async (params: Stripe.SubscriptionListParams) => {
      if (params.status === 'past_due') throw new Error('stripe down');
      return {
        data: [sub([{ unit_amount: 2000, product: Object.keys(OMI_PLAN_PRODUCTS)[0] }], { id: 'sub#0' })],
        has_more: false,
      };
    });
    const stripe = { subscriptions: { list } } as unknown as Stripe;

    const { subscriptions, partial } = await fetchOmiSubscriptions(stripe);

    expect(subscriptions).toHaveLength(1);
    expect(partial).toBe(true);
  });

  it('throws rather than reporting zero when every leg fails', async () => {
    const list = vi.fn(async () => {
      throw new Error('stripe down');
    });
    const stripe = { subscriptions: { list } } as unknown as Stripe;

    await expect(fetchOmiSubscriptions(stripe)).rejects.toBeInstanceOf(AllSubscriptionSourcesFailedError);
  });
});
