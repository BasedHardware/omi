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
  isAnnual,
  OMI_PLAN_PRODUCTS,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  // v3: `trialing` can now be null, and `nonUsdSkipped` was added.
  return `subscriptions:v3`;
}

export { cacheKey as subscriptionsCacheKey };

export async function computeSubscriptions() {
  const stripe = getOptionalStripe();

  if (!stripe) {
    return {
      totalSubscriptions: 0,
      monthly: 0,
      annual: 0,
      trialing: null,
      nonUsdSkipped: 0,
      byProduct: [],
      unavailable: true,
    };
  }

  const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, MRR_STATUSES);

  const annual = subscriptions.filter(isAnnual).length;

  // A trial is pipeline, not a paid subscription: counted, but never mixed into the paid totals.
  // Null on failure, so a fetch error can never render as a real "0 trials".
  let trialing: number | null = null;
  let trialPartial = false;
  try {
    const trials = await fetchOmiSubscriptions(stripe, PIPELINE_STATUSES);
    trialing = trials.subscriptions.length;
    trialPartial = trials.partial;
  } catch (error) {
    console.error('Error fetching trialing subscriptions:', error);
    trialPartial = true;
  }

  return {
    totalSubscriptions: subscriptions.length,
    monthly: subscriptions.length - annual,
    annual,
    trialing,
    /** Subscriptions whose prices are non-USD, so they are excluded from every MRR total. */
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

    const cached = await getPayload<Awaited<ReturnType<typeof computeSubscriptions>>>(key);
    if (cached) {
      return NextResponse.json(withFreshness(cached.data, cached.freshAt));
    }

    const payload = await computeSubscriptions();
    await setPayload(key, payload);
    return NextResponse.json(withFreshness(payload, Date.now()));
  } catch (error) {
    if (error instanceof AllSubscriptionSourcesFailedError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error('Error fetching subscription stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch subscription data' },
      { status: 500 }
    );
  }
}
