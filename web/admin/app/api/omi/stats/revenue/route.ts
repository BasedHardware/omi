import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getOptionalStripe } from '@/lib/stripe';
import { getPayload, setPayload, withFreshness } from '@/lib/payload-cache';
import {
  AllSubscriptionSourcesFailedError,
  MRR_STATUSES,
  PIPELINE_STATUSES,
  countNonUsdSubscriptions,
  fetchOmiSubscriptions,
  groupByProduct,
  monthlyAmount,
  OMI_PLAN_PRODUCTS,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  // v3: `trialingSubscriptions` can now be null, and `nonUsdSkipped` was added.
  return `revenue:v3`;
}

export { cacheKey as revenueCacheKey };

export async function computeRevenue() {
  const stripe = getOptionalStripe();

  if (!stripe) {
    return {
      mrr: 0,
      arr: 0,
      trialingSubscriptions: null,
      nonUsdSkipped: 0,
      byProduct: [],
      unavailable: true,
    };
  }

  const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, MRR_STATUSES);

  const mrr = subscriptions.reduce((sum, subscription) => sum + monthlyAmount(subscription), 0);

  // Trials are pipeline, not revenue: reported alongside MRR, never inside it. A failure here
  // must not cost the MRR figure that already succeeded — but it stays null rather than 0, so a
  // fetch failure can never render as "no trials".
  let trialingSubscriptions: number | null = null;
  let trialPartial = false;
  try {
    const trials = await fetchOmiSubscriptions(stripe, PIPELINE_STATUSES);
    trialingSubscriptions = trials.subscriptions.length;
    trialPartial = trials.partial;
  } catch (error) {
    console.error('Error fetching trialing subscriptions:', error);
    trialPartial = true;
  }

  return {
    mrr,
    arr: mrr * 12,
    trialingSubscriptions,
    /** Subscriptions left out of `mrr` because they are priced in a non-USD currency. */
    nonUsdSkipped: countNonUsdSubscriptions(subscriptions),
    byProduct: groupByProduct(subscriptions, OMI_PLAN_PRODUCTS),
    partial: partial || trialPartial,
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const key = cacheKey();

    const cached = await getPayload<Awaited<ReturnType<typeof computeRevenue>>>(key);
    if (cached) {
      return NextResponse.json(withFreshness(cached.data, cached.freshAt));
    }

    const payload = await computeRevenue();
    await setPayload(key, payload);
    return NextResponse.json(withFreshness(payload, Date.now()));
  } catch (error) {
    if (error instanceof AllSubscriptionSourcesFailedError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error('Error calculating revenue metrics:', error);
    return NextResponse.json(
      { error: 'Failed to calculate revenue metrics' },
      { status: 500 }
    );
  }
}
