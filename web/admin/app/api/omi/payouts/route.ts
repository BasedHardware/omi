import { NextRequest, NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin';
import type Stripe from 'stripe';
import { getStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const stripe = getStripe();
  // 1. Get token from Authorization header
  const authorization = request.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized: Missing or invalid token' }, { status: 401 });
  }
  const token = authorization.split('Bearer ')[1];

  // 2. Verify the token using Firebase Admin SDK
  const decodedToken = await verifyFirebaseToken(token);
  if (!decodedToken) {
    return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
  }

  try {
    const { searchParams } = new URL(request.url);
    const connectedAccountId = searchParams.get('connected_account_id');
    const limit = parseInt(searchParams.get('limit') || '100');
    const startingAfter = searchParams.get('starting_after');

    if (!connectedAccountId) {
      return NextResponse.json(
        { error: 'connected_account_id is required' },
        { status: 400 }
      );
    }

    const params: Stripe.PayoutListParams = {
      limit,
    };

    if (startingAfter) {
      params.starting_after = startingAfter;
    }

    const payouts = await stripe.payouts.list(params, {
      stripeAccount: connectedAccountId,
    });

    return NextResponse.json({
      payouts: payouts.data,
      hasMore: payouts.has_more,
      totalCount: payouts.data.length,
    });
  } catch (error) {
    console.error('Error fetching payouts:', error);
    return NextResponse.json(
      { error: 'Failed to fetch payouts' },
      { status: 500 }
    );
  }
}
