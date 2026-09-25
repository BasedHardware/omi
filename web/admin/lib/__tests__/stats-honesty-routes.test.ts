import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type Stripe from 'stripe';
import { OMI_PLAN_PRODUCTS } from '../stripe-subscriptions';

/**
 * Honesty coverage for the Stripe-backed stats routes: every number these payloads publish must
 * either be real or be absent. A zero that means "the fetch failed" is the defect class here.
 */

const listMock = vi.fn();
const stripe = { subscriptions: { list: listMock } } as unknown as Stripe;

vi.mock('@/lib/auth', () => ({ verifyAdmin: vi.fn(async () => ({ uid: 'test' })) }));
vi.mock('@/lib/payload-cache', () => ({
  getPayload: vi.fn(async () => null),
  setPayload: vi.fn(async () => undefined),
}));
vi.mock('@/lib/stripe', () => ({
  getOptionalStripe: () => stripe,
  getStripe: () => stripe,
}));

const PLAN_PRODUCT = Object.keys(OMI_PLAN_PRODUCTS)[0];

function sub(
  overrides: {
    id?: string;
    product?: string;
    unit_amount?: number;
    currency?: string;
    interval?: string;
    metadata?: Record<string, string>;
    created?: number;
    canceled_at?: number | null;
  } = {},
): Stripe.Subscription {
  return {
    id: overrides.id ?? 'sub_test',
    customer: 'cus_test',
    metadata: overrides.metadata ?? {},
    created: overrides.created ?? Math.floor(Date.now() / 1000) - 60 * 60 * 24 * 365,
    canceled_at: overrides.canceled_at ?? null,
    items: {
      data: [
        {
          id: 'si_0',
          quantity: 1,
          price: {
            id: 'price_0',
            unit_amount: overrides.unit_amount ?? 2000,
            currency: overrides.currency ?? 'usd',
            product: overrides.product ?? PLAN_PRODUCT,
            recurring: { interval: overrides.interval ?? 'month', interval_count: 1 },
          },
        },
      ],
    },
  } as unknown as Stripe.Subscription;
}

/** One page per status; a status mapped to `null` throws, standing in for a Stripe failure. */
function byStatus(pages: Record<string, Stripe.Subscription[] | null>) {
  listMock.mockImplementation(async (params: Stripe.SubscriptionListParams) => {
    const status = String(params.status);
    const page = pages[status];
    if (page === undefined) throw new Error(`unexpected status ${status}`);
    if (page === null) throw new Error(`stripe down for ${status}`);
    return { data: page, has_more: false };
  });
}

beforeEach(() => {
  vi.resetModules();
  listMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('revenue route', () => {
  it('reports trialing as null when the trial fetch fails, never as a plausible zero', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    byStatus({ active: [sub()], past_due: [], trialing: null });

    const { computeRevenue } = await import('@/app/api/omi/stats/revenue/route');
    const payload = await computeRevenue();

    expect(payload.mrr).toBeCloseTo(20);
    expect(payload.trialingSubscriptions).toBeNull();
    expect(payload.partial).toBe(true);
  });

  it('reports a real zero as zero when the trial fetch succeeds with no trials', async () => {
    byStatus({ active: [sub()], past_due: [], trialing: [] });

    const { computeRevenue } = await import('@/app/api/omi/stats/revenue/route');
    const payload = await computeRevenue();

    expect(payload.trialingSubscriptions).toBe(0);
    expect(payload.partial).toBe(false);
  });

  it('surfaces the non-USD subscriptions it left out of MRR', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    byStatus({
      active: [sub({ id: 'sub_usd' }), sub({ id: 'sub_eur', currency: 'eur', unit_amount: 9900 })],
      past_due: [],
      trialing: [],
    });

    const { computeRevenue } = await import('@/app/api/omi/stats/revenue/route');
    const payload = await computeRevenue();

    expect(payload.mrr).toBeCloseTo(20);
    expect(payload.nonUsdSkipped).toBe(1);
  });
});

describe('subscriptions route', () => {
  it('reports trialing as null when the trial fetch fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    byStatus({ active: [sub()], past_due: [], trialing: null });

    const { computeSubscriptions } = await import('@/app/api/omi/stats/subscriptions/route');
    const payload = await computeSubscriptions();

    expect(payload.totalSubscriptions).toBe(1);
    expect(payload.trialing).toBeNull();
    expect(payload.partial).toBe(true);
  });

  it('keeps a genuine zero distinguishable from a failure', async () => {
    byStatus({ active: [sub()], past_due: [], trialing: [] });

    const { computeSubscriptions } = await import('@/app/api/omi/stats/subscriptions/route');
    const payload = await computeSubscriptions();

    expect(payload.trialing).toBe(0);
    expect(payload.partial).toBe(false);
  });

  it('counts the non-USD subscriptions excluded from the MRR breakdown', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    byStatus({
      active: [sub({ id: 'sub_usd' }), sub({ id: 'sub_gbp', currency: 'gbp' })],
      past_due: [],
      trialing: [],
    });

    const { computeSubscriptions } = await import('@/app/api/omi/stats/subscriptions/route');
    const payload = await computeSubscriptions();

    expect(payload.nonUsdSkipped).toBe(1);
  });
});

describe('mrr-trends route', () => {
  it('labels the series with the pricing basis it actually used', async () => {
    byStatus({ all: [sub()] });

    const { computeMrrTrends } = await import('@/app/api/omi/stats/mrr-trends/route');
    const payload = await computeMrrTrends(3);

    // Current prices, not price-at-time: the payload says so rather than implying real history.
    expect(payload.pricingBasis).toBe('current_prices');
    expect(payload.data.length).toBeGreaterThan(0);
    expect(payload.data.every((point) => point.mrr === 20)).toBe(true);
  });
});

describe('app-subscriptions route', () => {
  it('counts past_due alongside active, matching every other MRR route', async () => {
    byStatus({
      active: [sub({ id: 'sub_a', metadata: { app_id: 'app_1' } })],
      past_due: [sub({ id: 'sub_b', metadata: { app_id: 'app_2' } })],
    });

    const { computeAppSubscriptions } = await import('@/app/api/omi/stats/app-subscriptions/route');
    const payload = await computeAppSubscriptions();

    expect(payload.totalAppSubscriptions).toBe(2);
    expect(listMock.mock.calls.map((call) => call[0].status).sort()).toEqual(['active', 'past_due']);
    expect(payload.partial).toBe(false);
  });

  it('degrades to partial when one status leg fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    byStatus({ active: [sub({ metadata: { app_id: 'app_1' } })], past_due: null });

    const { computeAppSubscriptions } = await import('@/app/api/omi/stats/app-subscriptions/route');
    const payload = await computeAppSubscriptions();

    expect(payload.totalAppSubscriptions).toBe(1);
    expect(payload.partial).toBe(true);
  });

  it('answers 502 rather than zero when every status leg fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    byStatus({ active: null, past_due: null });

    const { GET } = await import('@/app/api/omi/stats/app-subscriptions/route');
    const response = await GET({ nextUrl: new URL('http://localhost/api/omi/stats/app-subscriptions') } as never);

    expect(response.status).toBe(502);
  });
});
