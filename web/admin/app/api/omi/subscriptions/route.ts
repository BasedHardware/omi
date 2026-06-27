import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const stripe = getStripe();
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '100');
    const startingAfter = searchParams.get('starting_after');
    const endingBefore = searchParams.get('ending_before');
    const status = searchParams.get('status');
    const countOnly = searchParams.get('count_only') === 'true';

    if (countOnly) {
      // Get total count by iterating through all pages with status filter
      let totalCount = 0;
      let hasMore = true;
      let lastId: string | undefined = undefined;

      while (hasMore) {
        const params: any = { limit: 100 };
        if (lastId) {
          params.starting_after = lastId;
        }
        if (status && status !== 'all') {
          params.status = status;
        }

        const subscriptions = await stripe.subscriptions.list(params);
        totalCount += subscriptions.data.length;
        hasMore = subscriptions.has_more;
        
        if (hasMore && subscriptions.data.length > 0) {
          lastId = subscriptions.data[subscriptions.data.length - 1].id;
        }
      }

      return NextResponse.json({
        total_count: totalCount,
      });
    }

    // Build parameters for subscription list
    const params: any = {
      limit: limit,
      expand: [
        'data.customer',
        'data.items.data.price'
      ],
    };

    if (startingAfter) {
      params.starting_after = startingAfter;
    }
    if (endingBefore) {
      params.ending_before = endingBefore;
    }
    if (status && status !== 'all') {
      params.status = status;
    }

    // Fetch subscriptions with pagination and status filter
    const subscriptions = await stripe.subscriptions.list(params);

    // Transform the data to include only necessary fields
    const transformedSubscriptions = subscriptions.data.map(subscription => ({
      id: subscription.id,
      customer: {
        id: typeof subscription.customer === 'string' ? subscription.customer : subscription.customer.id,
        email: typeof subscription.customer === 'string' ? 'N/A' : (subscription.customer as any).email || 'N/A',
        name: typeof subscription.customer === 'string' ? 'N/A' : (subscription.customer as any).name || 'N/A',
      },
      status: subscription.status,
      current_period_start: (subscription as any).current_period_start,
      current_period_end: (subscription as any).current_period_end,
      created: subscription.created,
      items: {
        data: subscription.items.data.map(item => ({
          id: item.id,
          price: {
            id: typeof item.price === 'string' ? item.price : item.price.id,
            unit_amount: typeof item.price === 'string' ? 0 : item.price.unit_amount,
            currency: typeof item.price === 'string' ? 'usd' : item.price.currency,
            recurring: {
              interval: typeof item.price === 'string' ? 'month' : item.price.recurring?.interval || 'month',
            },
          },
          quantity: item.quantity,
        })),
      },
      metadata: subscription.metadata,
    }));

    return NextResponse.json({
      subscriptions: transformedSubscriptions,
      total: subscriptions.data.length,
      has_more: subscriptions.has_more,
      has_previous: !!endingBefore,
      next_page: subscriptions.has_more ? subscriptions.data[subscriptions.data.length - 1]?.id : null,
      previous_page: subscriptions.data.length > 0 ? subscriptions.data[0]?.id : null,
    });
  } catch (error) {
    console.error('Error fetching subscriptions:', error);
    return NextResponse.json(
      { error: 'Failed to fetch subscriptions' },
      { status: 500 }
    );
  }
}
