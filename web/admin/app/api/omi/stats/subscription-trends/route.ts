import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getOptionalStripe } from '@/lib/stripe';
import { getPayload, setPayload, withFreshness } from '@/lib/payload-cache';
import {
  AllSubscriptionSourcesFailedError,
  fetchOmiSubscriptions,
  isAnnual,
} from '@/lib/stripe-subscriptions';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(months: number): string {
  return `subscription-trends:v2:${months}`;
}

export { cacheKey as subscriptionTrendsCacheKey };

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

export async function computeSubscriptionTrends(months: number) {
    const stripe = getOptionalStripe();

    if (!stripe) {
      return { data: buildEmptySubscriptionTrendData(months), unavailable: true };
    }

    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - months);

    // New-subscription counts include ones later cancelled, so this reads every status. Only
    // subscriptions created inside the window can land in a bucket, so Stripe filters on that
    // rather than us paging the whole account's history.
    const { subscriptions, partial } = await fetchOmiSubscriptions(stripe, ['all'], {
      created: { gte: Math.floor(startDate.getTime() / 1000) },
    });

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

    // Count by creation month, split on the billing interval rather than a price id.
    subscriptions.forEach((subscription) => {
      const createdDate = new Date(subscription.created * 1000);
      if (createdDate < startDate || createdDate > endDate) return;

      const monthKey = `${createdDate.getFullYear()}-${String(createdDate.getMonth() + 1).padStart(2, '0')}`;
      const bucket = isAnnual(subscription) ? annualTrends : monthlyTrends;
      if (bucket[monthKey] !== undefined) {
        bucket[monthKey]++;
      }
    });

    // Format data for chart
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

    return { data, partial };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const searchParams = request.nextUrl.searchParams;
    const months = parseInt(searchParams.get('months') || '12', 10);
    const key = cacheKey(months);

    const cached = await getPayload<Awaited<ReturnType<typeof computeSubscriptionTrends>>>(key);
    if (cached) {
      return NextResponse.json(withFreshness(cached.data, cached.freshAt));
    }

    const payload = await computeSubscriptionTrends(months);
    await setPayload(key, payload);
    return NextResponse.json(withFreshness(payload, Date.now()));
  } catch (error) {
    if (error instanceof AllSubscriptionSourcesFailedError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error('Error fetching subscription trends:', error);
    return NextResponse.json(
      { error: 'Failed to fetch subscription trends' },
      { status: 500 }
    );
  }
}
