import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import type Stripe from 'stripe';
import { getOptionalStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

function buildEmptySubscriptionTrendData(months: number) {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setMonth(startDate.getMonth() - months);

  const monthKeys: string[] = [];
  const currentDate = new Date(startDate);
  while (currentDate <= endDate) {
    const monthKey = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}`;
    monthKeys.push(monthKey);
    currentDate.setMonth(currentDate.getMonth() + 1);
  }

  return monthKeys.map((monthKey) => {
    const [year, month] = monthKey.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return {
      month: date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
      monthKey,
      monthly: 0,
      annual: 0,
    };
  });
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const searchParams = request.nextUrl.searchParams;
    const months = parseInt(searchParams.get('months') || '12', 10);
    const stripe = getOptionalStripe();
    const monthlyPriceId = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
    const annualPriceId = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;

    if (!stripe || !monthlyPriceId || !annualPriceId) {
      return NextResponse.json({ data: buildEmptySubscriptionTrendData(months), unavailable: true });
    }

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - months);

    // Fetch all subscriptions (not just active) for both price IDs with pagination
    const fetchAllSubscriptions = async (priceId: string) => {
      let allSubscriptions: Stripe.Subscription[] = [];
      let hasMore = true;
      let startingAfter: string | undefined = undefined;

      while (hasMore) {
        const params: Stripe.SubscriptionListParams = {
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
      console.error('Error fetching monthly subscription trends:', results[0].reason);
    }
    if (results[1].status === 'rejected') {
      console.error('Error fetching annual subscription trends:', results[1].reason);
    }

    if (results.every((r) => r.status === 'rejected')) {
      return NextResponse.json(
        { error: 'All subscription trend data sources failed' },
        { status: 502 }
      );
    }

    // Group subscriptions by month created
    const monthlyTrends: Record<string, number> = {};
    const annualTrends: Record<string, number> = {};

    // Initialize all months in range with 0
    const monthKeys: string[] = [];
    const currentDate = new Date(startDate);
    while (currentDate <= endDate) {
      const monthKey = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}`;
      monthKeys.push(monthKey);
      monthlyTrends[monthKey] = 0;
      annualTrends[monthKey] = 0;
      currentDate.setMonth(currentDate.getMonth() + 1);
    }

    // Count monthly subscriptions by creation month
    monthlySubscriptions.forEach((subscription) => {
      const createdDate = new Date(subscription.created * 1000);
      if (createdDate >= startDate && createdDate <= endDate) {
        const monthKey = `${createdDate.getFullYear()}-${String(createdDate.getMonth() + 1).padStart(2, '0')}`;
        if (monthlyTrends[monthKey] !== undefined) {
          monthlyTrends[monthKey]++;
        }
      }
    });

    // Count annual subscriptions by creation month
    annualSubscriptions.forEach((subscription) => {
      const createdDate = new Date(subscription.created * 1000);
      if (createdDate >= startDate && createdDate <= endDate) {
        const monthKey = `${createdDate.getFullYear()}-${String(createdDate.getMonth() + 1).padStart(2, '0')}`;
        if (annualTrends[monthKey] !== undefined) {
          annualTrends[monthKey]++;
        }
      }
    });

    // Format data for chart
    const partial = results.some((r) => r.status === 'rejected');
    const data = monthKeys.map((monthKey) => {
      const [year, month] = monthKey.split('-');
      const date = new Date(parseInt(year), parseInt(month) - 1);
      return {
        month: date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
        monthKey,
        monthly: monthlyTrends[monthKey] || 0,
        annual: annualTrends[monthKey] || 0,
      };
    });

    return NextResponse.json({ data, partial });
  } catch (error) {
    console.error('Error fetching subscription trends:', error);
    return NextResponse.json(
      { error: 'Failed to fetch subscription trends' },
      { status: 500 }
    );
  }
}
