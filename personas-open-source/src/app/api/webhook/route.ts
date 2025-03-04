import { NextRequest, NextResponse } from 'next/server';
import { getStripeInstance } from '@/lib/stripe';
import { db } from '@/lib/firebase-admin';
import { headers } from 'next/headers';
import Stripe from 'stripe';

// This is your Stripe webhook secret for testing your endpoint locally.
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET!;

// Disable body parsing for this route
export const config = {
  api: {
    bodyParser: false,
  },
};

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();
    const headersList = await headers();
    const signature = headersList.get('stripe-signature')!;
    const stripe = getStripeInstance();

    let event: Stripe.Event;

    try {
      event = stripe.webhooks.constructEvent(body, signature, webhookSecret);
    } catch (err: any) {
      console.error(`Webhook signature verification failed: ${err.message}`);
      return NextResponse.json({ error: `Webhook Error: ${err.message}` }, { status: 400 });
    }

    // Handle the event
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        
        // Get the subscription
        const subscription = await stripe.subscriptions.retrieve(session.subscription as string);
        
        // Get the customer
        const customer = await stripe.customers.retrieve(session.customer as string);
        
        // Get the user ID from the subscription metadata
        const userId = subscription.metadata.userId;
        
        if (!userId) {
          console.error('No user ID found in subscription metadata');
          return NextResponse.json({ error: 'No user ID found' }, { status: 400 });
        }
        
        // Store the subscription in Firestore
        await db.collection('users').doc(userId).collection('subscriptions').doc('active').set({
          status: subscription.status,
          priceId: subscription.items.data[0].price.id,
          stripeSubscriptionId: subscription.id,
          stripeCustomerId: subscription.customer,
          createdAt: new Date(),
          currentPeriodStart: new Date(subscription.current_period_start * 1000),
          currentPeriodEnd: new Date(subscription.current_period_end * 1000),
          cancelAtPeriodEnd: subscription.cancel_at_period_end,
        });
        
        break;
      }
      
      case 'invoice.payment_succeeded': {
        const invoice = event.data.object as Stripe.Invoice;
        
        if (invoice.subscription) {
          // Get the subscription
          const subscription = await stripe.subscriptions.retrieve(invoice.subscription as string);
          
          // Get the user ID from the subscription metadata
          const userId = subscription.metadata.userId;
          
          if (!userId) {
            console.error('No user ID found in subscription metadata');
            return NextResponse.json({ error: 'No user ID found' }, { status: 400 });
          }
          
          // Update the subscription in Firestore
          await db.collection('users').doc(userId).collection('subscriptions').doc('active').update({
            status: subscription.status,
            currentPeriodStart: new Date(subscription.current_period_start * 1000),
            currentPeriodEnd: new Date(subscription.current_period_end * 1000),
            cancelAtPeriodEnd: subscription.cancel_at_period_end,
          });
        }
        
        break;
      }
      
      case 'customer.subscription.updated': {
        const subscription = event.data.object as Stripe.Subscription;
        
        // Get the user ID from the subscription metadata
        const userId = subscription.metadata.userId;
        
        if (!userId) {
          console.error('No user ID found in subscription metadata');
          return NextResponse.json({ error: 'No user ID found' }, { status: 400 });
        }
        
        // Update the subscription in Firestore
        await db.collection('users').doc(userId).collection('subscriptions').doc('active').update({
          status: subscription.status,
          currentPeriodStart: new Date(subscription.current_period_start * 1000),
          currentPeriodEnd: new Date(subscription.current_period_end * 1000),
          cancelAtPeriodEnd: subscription.cancel_at_period_end,
        });
        
        break;
      }
      
      case 'customer.subscription.deleted': {
        const subscription = event.data.object as Stripe.Subscription;
        
        // Get the user ID from the subscription metadata
        const userId = subscription.metadata.userId;
        
        if (!userId) {
          console.error('No user ID found in subscription metadata');
          return NextResponse.json({ error: 'No user ID found' }, { status: 400 });
        }
        
        // Delete the subscription from Firestore
        await db.collection('users').doc(userId).collection('subscriptions').doc('active').delete();
        
        break;
      }
      
      default:
        console.log(`Unhandled event type: ${event.type}`);
    }

    return NextResponse.json({ received: true });
  } catch (error: any) {
    console.error('Webhook error:', error);
    return NextResponse.json(
      { error: error.message || 'Something went wrong' },
      { status: 500 }
    );
  }
} 