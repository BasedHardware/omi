import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import type Stripe from 'stripe';
import { getOptionalStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const stripe = getOptionalStripe();
    const monthlyPriceId = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
    const annualPriceId = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;

    if (!stripe || !monthlyPriceId || !annualPriceId) {
      return NextResponse.json({ mrr: 0, arr: 0, unavailable: true });
    }

    // Fetch all active subscriptions with pagination
    const fetchAllSubscriptions = async (priceId: string) => {
      let allSubscriptions: Stripe.Subscription[] = [];
      let hasMore = true;
      let startingAfter: string | undefined = undefined;

      while (hasMore) {
        const params: Stripe.SubscriptionListParams = {
          status: 'active',
          price: priceId,
          limit: 100,
          expand: ['data.items.data.price'],
        };

        if (startingAfter) {
          params.starting_after = startingAfter;
        }

        const subscriptions = await stripe.subscriptions.list(params);
        allSubscriptions = allSubscriptions.concat(subscriptions.data);
        
        hasMore = subscriptions.has_more;
        if (hasMore && subscriptions.data.length > 0) {
          startingAfter = subscriptions.data[subscriptions.data.length - 1].id;
        }
      }

      return allSubscriptions;
    };

    const results = await Promise.allSettled([
      fetchAllSubscriptions(monthlyPriceId),
      fetchAllSubscriptions(annualPriceId),
    ]);

    const monthlySubscriptions = results[0].status === 'fulfilled' ? results[0].value : [];
    const annualSubscriptions = results[1].status === 'fulfilled' ? results[1].value : [];

    if (results[0].status === 'rejected') {
      console.error('Error fetching monthly subscriptions:', results[0].reason);
    }
    if (results[1].status === 'rejected') {
      console.error('Error fetching annual subscriptions:', results[1].reason);
    }

    if (results.every((r) => r.status === 'rejected')) {
      return NextResponse.json(
        { error: 'All revenue data sources failed' },
        { status: 502 }
      );
    }

    let monthlyMRR = 0;
    let annualMRR = 0;
    let monthlyARR = 0;
    let annualARR = 0;

    // Calculate MRR from monthly subscriptions using Stripe's subscription amount
    monthlySubscriptions.forEach((subscription) => {
      // Use the subscription's current period amount (which is the MRR for monthly subscriptions)
      const amount = subscription.items.data.reduce((sum, item) => {
        const price = typeof item.price === 'string' ? null : item.price;
        if (!price) return sum;
        
        const unitAmount = price.unit_amount || 0;
        const quantity = item.quantity || 1;
        return sum + (unitAmount * quantity);
      }, 0);
      
      const totalAmount = amount / 100; // Convert from cents to dollars
      monthlyMRR += totalAmount;
      monthlyARR += totalAmount * 12;
    });

    // Calculate MRR from annual subscriptions - convert to monthly equivalent
    annualSubscriptions.forEach((subscription) => {
      // Use the subscription's current period amount and convert to monthly
      const amount = subscription.items.data.reduce((sum, item) => {
        const price = typeof item.price === 'string' ? null : item.price;
        if (!price) return sum;
        
        const unitAmount = price.unit_amount || 0;
        const quantity = item.quantity || 1;
        return sum + (unitAmount * quantity);
      }, 0);
      
      const totalAmount = amount / 100; // Convert from cents to dollars
      annualMRR += totalAmount / 12; // Convert annual to monthly equivalent
      annualARR += totalAmount;
    });

    // Calculate combined totals
    const partial = results.some((r) => r.status === 'rejected');
    const totalMRR = monthlyMRR + annualMRR;
    const totalARR = monthlyARR + annualARR;

    return NextResponse.json({
      mrr: totalMRR,
      arr: totalARR,
      partial,
    });
  } catch (error) {
    console.error('Error calculating revenue metrics:', error);
    return NextResponse.json(
      { error: 'Failed to calculate revenue metrics' },
      { status: 500 }
    );
  }
}
