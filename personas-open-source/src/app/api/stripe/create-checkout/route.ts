import { auth } from "@/lib/firebase";
import { db } from "@/lib/firebase";
import { collection, addDoc, getDocs, query, where } from 'firebase/firestore';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';
import { getFirestore, doc, setDoc, getDoc } from 'firebase/firestore';
import { NextResponse } from "next/server";
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2025-01-27.acacia',
});

export async function POST(req: Request) {
  try {
    const { plan } = await req.json();

    const priceId = plan === 'pro' ? 'price_1Oq31zSH7OyZUDbz045emwvv' : 'price_1Oq2zSSH7OyZUDbzKUM96x36';

    const session = await stripe.checkout.sessions.create({
      line_items: [
        {
          price: priceId,
          quantity: 1,
        },
      ],
      mode: 'subscription',
      success_url: `${process.env.NEXT_PUBLIC_APP_URL}/checkout/success`,
      cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/checkout/cancel`,
    });

    return NextResponse.json({ url: session.url });
  } catch (error: any) {
    console.error(error);
    return new NextResponse(error.message || 'Something went wrong', { status: 500 });
  }
}
