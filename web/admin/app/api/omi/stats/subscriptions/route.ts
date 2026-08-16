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
  isAnnual,
  OMI_PLAN_PRODUCTS,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  return `subscriptions:v2`;
}

export { cacheKey as subscriptionsCacheKey };

export async function computeSubscriptions() {
  const stripe = getOptionalStripe();

  if (!stripe) {
    return {
      totalSubscriptions: 0,
      monthly: 0,
      annual: 0,
      trialing: 0,
      byProduct: [],
      unavailable: true,
    };
  }

  const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, MRR_STATUSES);

  const annual = subscriptions.filter(isAnnual).length;

  // A trial is pipeline, not a paid subscription: counted, but never mixed into the paid totals.
  let trialing = 0;
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
      return NextResponse.json(cached.data);
    }

    const payload = await computeSubscriptions();
    await setPayload(key, payload);
    return NextResponse.json(payload);
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
