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
    const monthlyPriceId = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
    const annualPriceId = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;

    if (!monthlyPriceId || !annualPriceId) {
      return NextResponse.json(
        { error: 'Stripe price IDs not configured' },
        { status: 500 }
      );
    }

    // Get query params for date range (default to last 12 months)
    const searchParams = request.nextUrl.searchParams;
    const months = parseInt(searchParams.get('months') || '12', 10);

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - months);

    // Fetch all subscriptions with pagination
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

    const [monthlySubscriptions, annualSubscriptions] = await Promise.all([
      fetchAllSubscriptions(monthlyPriceId),
      fetchAllSubscriptions(annualPriceId),
    ]);

    // Group MRR by month
    const mrrByMonth: Record<string, number> = {};

    // Initialize all months in range with 0
    const monthKeys: string[] = [];
    const currentDate = new Date(startDate);
    while (currentDate <= endDate) {
      const monthKey = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}`;
      monthKeys.push(monthKey);
      mrrByMonth[monthKey] = 0;
      currentDate.setMonth(currentDate.getMonth() + 1);
    }

    // Calculate MRR for each month based on active subscriptions
    monthKeys.forEach((monthKey) => {
      const [year, month] = monthKey.split('-');
      const monthStart = new Date(parseInt(year), parseInt(month) - 1, 1);
      const monthEnd = new Date(parseInt(year), parseInt(month), 0, 23, 59, 59);

      let monthMRR = 0;

      // Process monthly subscriptions
      monthlySubscriptions.forEach((subscription) => {
        const createdDate = new Date(subscription.created * 1000);
        const cancelDate = subscription.canceled_at 
          ? new Date(subscription.canceled_at * 1000)
          : null;
        
        // Subscription is active during this month if:
        // - Created before or during this month
        // - Not canceled or canceled after this month
        if (createdDate <= monthEnd && (!cancelDate || cancelDate >= monthStart)) {
          subscription.items.data.forEach((item) => {
            const price = typeof item.price === 'string' ? null : item.price;
            if (!price) return;

            const amount = price.unit_amount || 0;
            const quantity = item.quantity || 1;
            const totalAmount = (amount * quantity) / 100; // Convert from cents to dollars
            monthMRR += totalAmount;
          });
        }
      });

      // Process annual subscriptions (convert to monthly equivalent)
      annualSubscriptions.forEach((subscription) => {
        const createdDate = new Date(subscription.created * 1000);
        const cancelDate = subscription.canceled_at 
          ? new Date(subscription.canceled_at * 1000)
          : null;
        
        // Subscription is active during this month if:
        // - Created before or during this month
        // - Not canceled or canceled after this month
        if (createdDate <= monthEnd && (!cancelDate || cancelDate >= monthStart)) {
          subscription.items.data.forEach((item) => {
            const price = typeof item.price === 'string' ? null : item.price;
            if (!price) return;

            const amount = price.unit_amount || 0;
            const quantity = item.quantity || 1;
            const totalAmount = (amount * quantity) / 100; // Convert from cents to dollars
            monthMRR += totalAmount / 12; // Convert annual to monthly equivalent
          });
        }
      });

      mrrByMonth[monthKey] = monthMRR;
    });

    // Format data for chart
    const data = monthKeys.map((monthKey) => {
      const [year, month] = monthKey.split('-');
      const date = new Date(parseInt(year), parseInt(month) - 1);
      return {
        month: date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
        monthKey,
        mrr: Math.round(mrrByMonth[monthKey] * 100) / 100, // Round to 2 decimal places
      };
    });

    return NextResponse.json({ data });
  } catch (error) {
    console.error('Error fetching MRR trends:', error);
    return NextResponse.json(
      { error: 'Failed to fetch MRR trends' },
      { status: 500 }
    );
  }
}

