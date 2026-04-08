import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
import type Stripe from 'stripe';
import { getStripe } from '@/lib/stripe';
export const dynamic = 'force-dynamic';

interface PayoutWithAppInfo {
  payout: Stripe.Payout;
  appName: string;
  userName: string;
  userId: string;
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const stripe = getStripe();
  const db = getDb();

  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '50');
    const startingAfter = searchParams.get('starting_after');

    // 1. Get all paid apps
    const appsSnapshot = await db.collection('plugins_data')
      .where('is_paid', '==', true)
      .get();

    const apps = appsSnapshot.docs.map(doc => {
      const data = doc.data();
      return {
        id: doc.id,
        name: data.name || 'Unknown App',
        uid: data.uid || '',
        ...data
      };
    });

    // 2. Get all users with Stripe accounts
    const usersWithStripe: { [userId: string]: { stripeAccountId: string, name: string, email: string } } = {};
    const userIds = Array.from(new Set(apps.map(app => app.uid)));

    for (const userId of userIds) {
      const userDoc = await db.collection('users').doc(userId).get();
      if (userDoc.exists) {
        const userData = userDoc.data();
        if (userData?.stripe_account_id) {
          usersWithStripe[userId] = {
            stripeAccountId: userData.stripe_account_id,
            name: userData.name || userData.displayName || 'Unknown',
            email: userData.email || 'No email'
          };
        }
      }
    }

    // 3. Fetch payouts for each connected account
    const allPayoutsWithAppInfo: PayoutWithAppInfo[] = [];

    for (const app of apps) {
      const userStripeData = usersWithStripe[app.uid];
      if (!userStripeData) {
        continue; // Skip apps without connected Stripe accounts
      }

      try {
        const params: Stripe.PayoutListParams = {
          limit: Math.min(limit, 100), // Stripe max is 100
        };

        if (startingAfter) {
          params.starting_after = startingAfter;
        }

        const payouts = await stripe.payouts.list(params, {
          stripeAccount: userStripeData.stripeAccountId,
        });

        // Add app info to each payout
        const payoutsWithAppInfo = payouts.data.map(payout => ({
          payout,
          appName: app.name,
          userName: userStripeData.name,
          userId: app.uid,
        }));

        allPayoutsWithAppInfo.push(...payoutsWithAppInfo);
      } catch (error) {
        console.error(`Error fetching payouts for app ${app.name}:`, error);
        // Continue with other apps even if one fails
      }
    }

    // 4. Sort all payouts by creation date (most recent first)
    allPayoutsWithAppInfo.sort((a, b) => b.payout.created - a.payout.created);

    // 5. Apply pagination if needed
    const paginatedPayouts = startingAfter 
      ? allPayoutsWithAppInfo.slice(0, limit)
      : allPayoutsWithAppInfo.slice(0, limit);

    // Transform payouts to remove owner field and add uid field
    const transformedPayouts = paginatedPayouts.map(payoutData => {
      const { payout, appName, userName, userId } = payoutData;
      return {
        payout,
        appName,
        uid: userId, // Add uid field
        // Remove userName (owner field)
      };
    });

    const response = NextResponse.json({
      payouts: transformedPayouts,
      hasMore: allPayoutsWithAppInfo.length > limit,
      totalCount: allPayoutsWithAppInfo.length,
    });

    // Set caching headers for better performance
    response.headers.set('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600');

    return response;
  } catch (error) {
    console.error('Error fetching all payouts:', error);
    return NextResponse.json(
      { error: 'Failed to fetch payouts' },
      { status: 500 }
    );
  }
}
