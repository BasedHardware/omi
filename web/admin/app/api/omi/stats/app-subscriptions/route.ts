import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getStripe } from '@/lib/stripe';
import { getPayload, setPayload, withFreshness } from '@/lib/payload-cache';
import {
  AllSubscriptionSourcesFailedError,
  MRR_STATUSES,
  isAppSubscription,
  listSubscriptions,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  // v3: past_due subscriptions now count, and the payload gained `partial`.
  return `app-subscriptions:v3`;
}

export { cacheKey as appSubscriptionsCacheKey };

export async function computeAppSubscriptions() {
    const stripe = getStripe();

    // Same status set as every other subscription metric (MRR_STATUSES): a `past_due` marketplace
    // subscription is still a live subscription, and counting only `active` here made this route
    // disagree with the Omi-plan routes on what a subscription is.
    //
    // Status legs run through `Promise.allSettled` like `fetchOmiSubscriptions`: one failing leg
    // degrades to `partial` rather than silently undercounting, and a total failure throws.
    const results = await Promise.allSettled(
      MRR_STATUSES.map((status) => listSubscriptions(stripe, { status })),
    );

    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        console.error(`Error fetching ${MRR_STATUSES[index]} app subscriptions:`, result.reason);
      }
    });

    if (results.every((result) => result.status === 'rejected')) {
      throw new AllSubscriptionSourcesFailedError('All subscription data sources failed');
    }

    const allSubscriptions = results.flatMap((result) =>
      result.status === 'fulfilled' ? result.value : [],
    );
    const partial = results.some((result) => result.status === 'rejected');

    // Marketplace subscriptions are the ones the backend stamped with an app_id. Selecting them
    // by "not one of two Omi price IDs" put every other first-party plan in this bucket.
    const appSubscriptions = allSubscriptions.filter(isAppSubscription);

    // Group by customer to handle multiple subscriptions per user
    const customerSubscriptions: Record<string, true> = {};
    appSubscriptions.forEach((subscription) => {
      const customerId = typeof subscription.customer === 'string' ? subscription.customer : subscription.customer.id;
      customerSubscriptions[customerId] = true;
    });

    // Group by price ID to show breakdown
    const priceBreakdown: Record<string, number> = {};
    appSubscriptions.forEach((subscription) => {
      subscription.items.data.forEach((item) => {
        const priceId = typeof item.price === 'string' ? item.price : item.price.id;
        priceBreakdown[priceId] = (priceBreakdown[priceId] || 0) + 1;
      });
    });

    return {
      totalAppSubscriptions: appSubscriptions.length,
      uniqueCustomers: Object.keys(customerSubscriptions).length,
      priceBreakdown,
      uniquePriceIds: Object.keys(priceBreakdown).length,
      partial,
    };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const key = cacheKey();

    const cached = await getPayload<Awaited<ReturnType<typeof computeAppSubscriptions>>>(key);
    if (cached) {
      return NextResponse.json(withFreshness(cached.data, cached.freshAt));
    }

    const payload = await computeAppSubscriptions();
    await setPayload(key, payload);
    return NextResponse.json(withFreshness(payload, Date.now()));
  } catch (error) {
    if (error instanceof AllSubscriptionSourcesFailedError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error('Error fetching app subscription stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch app subscription data' },
      { status: 500 }
    );
  }
}
