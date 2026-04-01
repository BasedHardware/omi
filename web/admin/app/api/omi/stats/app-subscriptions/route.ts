import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import type Stripe from 'stripe';
import { getStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const stripe = getStripe();
  try {
    const omiMonthlyPriceId = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
    const omiAnnualPriceId = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;

    if (!omiMonthlyPriceId || !omiAnnualPriceId) {
      return NextResponse.json(
        { error: 'OMI price IDs not configured' },
        { status: 500 }
      );
    }

    // Fetch ALL active subscriptions with pagination
    let allSubscriptions: Stripe.Subscription[] = [];
    let hasMore = true;
    let startingAfter: string | undefined = undefined;

    while (hasMore) {
      const page: Stripe.ApiList<Stripe.Subscription> = await stripe.subscriptions.list({
        status: 'active',
        limit: 100, // Stripe max per page
        expand: ['data.items.data.price'], // Include price details
        ...(startingAfter ? { starting_after: startingAfter } : {}),
      });

      allSubscriptions = allSubscriptions.concat(page.data);
      hasMore = page.has_more;
      if (hasMore && page.data.length > 0) {
        startingAfter = page.data[page.data.length - 1].id;
      }
    }

    // Filter out subscriptions that have OMI price IDs
    const appSubscriptions = allSubscriptions.filter((subscription) => {
      // Check if any item in the subscription has the OMI price IDs
      const hasOmiPrice = subscription.items.data.some((item) => {
        const priceId = typeof item.price === 'string' ? item.price : item.price.id;
        return priceId === omiMonthlyPriceId || priceId === omiAnnualPriceId;
      });
      
      // Return subscriptions that DON'T have OMI prices
      return !hasOmiPrice;
    });

    // Group by customer to handle multiple subscriptions per user
    const customerSubscriptions: Record<string, any[]> = {};
    appSubscriptions.forEach((subscription) => {
      const customerId = typeof subscription.customer === 'string' ? subscription.customer : subscription.customer.id;
      if (!customerSubscriptions[customerId]) {
        customerSubscriptions[customerId] = [];
      }
      customerSubscriptions[customerId].push(subscription);
    });

    // Group by price ID to show breakdown
    const priceBreakdown: Record<string, number> = {};
    appSubscriptions.forEach((subscription) => {
      subscription.items.data.forEach((item) => {
        const priceId = typeof item.price === 'string' ? item.price : item.price.id;
        if (priceId !== omiMonthlyPriceId && priceId !== omiAnnualPriceId) {
          priceBreakdown[priceId] = (priceBreakdown[priceId] || 0) + 1;
        }
      });
    });

    return NextResponse.json({
      totalAppSubscriptions: appSubscriptions.length,
      uniqueCustomers: Object.keys(customerSubscriptions).length,
      priceBreakdown,
      uniquePriceIds: Object.keys(priceBreakdown).length,
    });
  } catch (error) {
    console.error('Error fetching app subscription stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch app subscription data' },
      { status: 500 }
    );
  }
}
