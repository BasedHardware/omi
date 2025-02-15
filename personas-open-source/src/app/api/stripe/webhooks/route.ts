import Stripe from 'stripe';
import { headers } from 'next/headers';
import { NextResponse } from 'next/server';

import { db } from '@/lib/firebase';
import { updateDoc, doc } from 'firebase/firestore';
import { stripe } from '@/lib/stripe';

export async function POST(req: Request) {
  const body = await req.text();
  const signature = headers().get('Stripe-Signature') as string;

  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (error: any) {
    return new NextResponse(`Webhook Error: ${error.message}`, { status: 400 });
  }

  const session = event.data.object as Stripe.Checkout.Session;

  if (event.type === 'checkout.session.completed') {
    const subscription = await stripe.subscriptions.retrieve(
      session.subscription as string
    );

    if (
      !session.metadata ||
      typeof session.metadata !== 'object' ||
      !('userId' in session.metadata) ||
      typeof session.metadata.userId !== 'string'
    ) {
      return new NextResponse('Webhook Error: No user id', { status: 400 });
    }

    const userId = session.metadata!.userId;

    await updateDoc(doc(db, 'users', userId), {
      stripeCustomerId: subscription.customer,
      stripeSubscriptionId: subscription.id,
      stripePriceId: subscription.items.data[0].price.id,
      stripeCurrentPeriodEnd: new Date(subscription.current_period_end * 1000),
      stripeSubscriptionStatus: subscription.status,
    });
  }

  if (event.type === 'invoice.payment_succeeded') {
    const subscription = await stripe.subscriptions.retrieve(
      session.subscription as string
    );

    await updateDoc(
      doc(db, 'users', session.metadata!.userId),
      {
        stripePriceId: subscription.items.data[0].price.id,
        stripeCurrentPeriodEnd: new Date(
          subscription.current_period_end * 1000
        ),
        stripeSubscriptionStatus: subscription.status,
      }
    );
  }

  return new NextResponse(null, { status: 200 });
}
