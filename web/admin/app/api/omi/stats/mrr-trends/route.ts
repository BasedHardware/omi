import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getOptionalStripe } from '@/lib/stripe';
import { getPayload, setPayload } from '@/lib/payload-cache';
import {
  AllSubscriptionSourcesFailedError,
  fetchOmiSubscriptions,
  monthlyAmount,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(months: number): string {
  return `mrr-trends:v2:${months}`;
}

export { cacheKey as mrrTrendsCacheKey };

function buildEmptyMrrData(months: number) {
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
      mrr: 0,
    };
  });
}

export async function computeMrrTrends(months: number) {
    const stripe = getOptionalStripe();

    if (!stripe) {
      return { data: buildEmptyMrrData(months), unavailable: true };
    }

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - months);

    // Historical MRR needs cancelled subscriptions too, so this reads every status rather than
    // the MRR set, and the per-month filter below decides what was live in each month.
    const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, ['all']);

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

      subscriptions.forEach((subscription) => {
        const createdDate = new Date(subscription.created * 1000);
        const cancelDate = subscription.canceled_at ? new Date(subscription.canceled_at * 1000) : null;

        // Live during this month: created on or before its end, and not cancelled before its start.
        if (createdDate <= monthEnd && (!cancelDate || cancelDate >= monthStart)) {
          monthMRR += monthlyAmount(subscription);
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

    return { data, partial };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const searchParams = request.nextUrl.searchParams;
    const months = parseInt(searchParams.get('months') || '12', 10);
    const key = cacheKey(months);

    const cached = await getPayload<Awaited<ReturnType<typeof computeMrrTrends>>>(key);
    if (cached) {
      return NextResponse.json(cached.data);
    }

    const payload = await computeMrrTrends(months);
    await setPayload(key, payload);
    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof AllSubscriptionSourcesFailedError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error('Error fetching MRR trends:', error);
    return NextResponse.json(
      { error: 'Failed to fetch MRR trends' },
      { status: 500 }
    );
  }
}
