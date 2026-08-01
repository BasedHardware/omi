import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getOptionalStripe } from '@/lib/stripe';
import { getPayload, setPayload } from '@/lib/payload-cache';
import {
  AllSubscriptionSourcesFailedError,
  MRR_STATUSES,
  PIPELINE_STATUSES,
  fetchOmiSubscriptions,
  groupByProduct,
  monthlyAmount,
  OMI_PLAN_PRODUCTS,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  return `revenue:v2`;
}

export { cacheKey as revenueCacheKey };

export async function computeRevenue() {
  const stripe = getOptionalStripe();

  if (!stripe) {
    return { mrr: 0, arr: 0, trialingSubscriptions: 0, byProduct: [], unavailable: true };
  }

  const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, MRR_STATUSES);

  const mrr = subscriptions.reduce((sum, subscription) => sum + monthlyAmount(subscription), 0);

  // Trials are pipeline, not revenue: reported alongside MRR, never inside it. A failure here
  // must not cost the MRR figure that already succeeded.
  let trialingSubscriptions = 0;
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
      return NextResponse.json(cached.data);
    }

    const payload = await computeRevenue();
    await setPayload(key, payload);
    return NextResponse.json(payload);
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
