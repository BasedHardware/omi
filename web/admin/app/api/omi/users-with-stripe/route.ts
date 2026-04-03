import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const { searchParams } = new URL(request.url);
    const appId = searchParams.get('app_id');

    if (!appId) {
      return NextResponse.json(
        { error: 'app_id is required' },
        { status: 400 }
      );
    }

    // First, get the app to find the user ID
    const appDoc = await db.collection('plugins_data').doc(appId).get();
    
    if (!appDoc.exists) {
      return NextResponse.json(
        { error: 'App not found' },
        { status: 404 }
      );
    }

    const appData = appDoc.data();
    const userId = appData?.uid;

    if (!userId) {
      return NextResponse.json(
        { error: 'App has no associated user' },
        { status: 400 }
      );
    }

    // Get the user document to find the Stripe account ID
    const userDoc = await db.collection('users').doc(userId).get();
    
    if (!userDoc.exists) {
      return NextResponse.json(
        { error: 'User not found' },
        { status: 404 }
      );
    }

    const userData = userDoc.data();
    const stripeAccountId = userData?.stripe_account_id;

    if (!stripeAccountId) {
      return NextResponse.json(
        { 
          error: 'User has no connected Stripe account',
          code: 'NO_STRIPE_ACCOUNT',
          message: 'This app owner has not connected their Stripe account yet. No payouts are available.'
        },
        { status: 404 }
      );
    }

    return NextResponse.json({
      userId,
      stripeAccountId,
      appName: appData?.name,
      userName: userData?.name || userData?.email,
    });
  } catch (error) {
    console.error('Error fetching user with Stripe account:', error);
    return NextResponse.json(
      { error: 'Failed to fetch user data' },
      { status: 500 }
    );
  }
}
