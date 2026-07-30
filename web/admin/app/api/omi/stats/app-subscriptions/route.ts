import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getStripe } from '@/lib/stripe';
import { getPayload, setPayload } from '@/lib/payload-cache';
import { isAppSubscription, listSubscriptions } from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(): string {
  return `app-subscriptions:v2`;
}

export { cacheKey as appSubscriptionsCacheKey };

export async function computeAppSubscriptions() {
    const stripe = getStripe();

    const allSubscriptions = await listSubscriptions(stripe, { status: 'active' });

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
    };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const key = cacheKey();

    const cached = await getPayload<Awaited<ReturnType<typeof computeAppSubscriptions>>>(key);
    if (cached) {
      return NextResponse.json(cached.data);
    }

    const payload = await computeAppSubscriptions();
    await setPayload(key, payload);
    return NextResponse.json(payload);
  } catch (error) {
    console.error('Error fetching app subscription stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch app subscription data' },
      { status: 500 }
    );
  }
}
