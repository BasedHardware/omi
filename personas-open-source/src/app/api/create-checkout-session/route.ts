import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/firebase-admin';
import { getStripeInstance } from '@/lib/stripe';
import { cookies } from 'next/headers';

export async function POST(req: NextRequest) {
  // Get the request body
  const { planId, interval = 'month' } = await req.json();

  // Get the session cookie
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get('session')?.value;

  // Debug log
  console.log('Session Cookie:', sessionCookie ? 'Present' : 'Missing');

  if (!sessionCookie) {
    return NextResponse.json(
      { error: 'You must be logged in to create a checkout session' },
      { status: 401 }
    );
  }

  // Verify the session cookie and get the user
  const decodedClaims = await auth.verifySessionCookie(sessionCookie, true); // Added true for checkRevoked
  const userId = decodedClaims.uid;

  console.log('Decoded Claims:', decodedClaims);

  if (!userId) {
    console.log('No user ID in decoded claims');
    return NextResponse.json(
      { error: 'Invalid session' },
      { status: 401 }
    );
  }

  // Get the Stripe instance
  const stripe = getStripeInstance();

  // Get the price ID based on the plan and interval
  let priceId: string;

  if (planId === 'pro' && interval === 'month') {
    priceId = process.env.STRIPE_PRICE_PRO_MONTHLY!;
  } else if (planId === 'pro' && interval === 'year') {
    priceId = process.env.STRIPE_PRICE_PRO_YEARLY!;
  } else {
    return NextResponse.json(
      { error: 'Invalid plan or interval' },
      { status: 400 }
    );
  }

  // Create a checkout session
  const session = await stripe.checkout.sessions.create({
    payment_method_types: ['card'],
    billing_address_collection: 'auto',
    customer_email: decodedClaims.email,
    line_items: [
      {
        price: priceId,
        quantity: 1,
      },
    ],
    mode: 'subscription',
    allow_promotion_codes: true,
    subscription_data: {
      metadata: {
        userId,
      },
    },
    success_url: `${process.env.NEXT_PUBLIC_SITE_URL}/account?success=true`,
    cancel_url: `${process.env.NEXT_PUBLIC_SITE_URL}/pricing?canceled=true`,
  });

  return NextResponse.json({ sessionId: session.id });

} 