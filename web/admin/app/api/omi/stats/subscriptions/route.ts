import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const stripe = getStripe();
  try {
    const priceIdOne = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
    const priceIdTwo = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;

    if (!priceIdOne || !priceIdTwo) {
      return NextResponse.json(
        { error: 'Stripe price IDs not configured' },
        { status: 500 }
      );
    }

    // Fetch all active subscriptions for both price IDs with pagination
    const fetchAllSubscriptions = async (priceId: string) => {
      let allSubscriptions: any[] = [];
      let hasMore = true;
      let startingAfter: string | undefined = undefined;

      while (hasMore) {
        const params: any = {
          status: 'active',
          price: priceId,
          limit: 100, // Stripe's maximum per request
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

    const [subscriptionsOne, subscriptionsTwo] = await Promise.all([
      fetchAllSubscriptions(priceIdOne),
      fetchAllSubscriptions(priceIdTwo),
    ]);

    const totalSubscriptions = subscriptionsOne.length + subscriptionsTwo.length;

    return NextResponse.json({
      totalSubscriptions,
      priceIdOne: {
        count: subscriptionsOne.length,
        priceId: priceIdOne,
      },
      priceIdTwo: {
        count: subscriptionsTwo.length,
        priceId: priceIdTwo,
      },
    });
  } catch (error) {
    console.error('Error fetching subscription stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch subscription data' },
      { status: 500 }
    );
  }
}
