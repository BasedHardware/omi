'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { auth } from '@/lib/firebase';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { useSubscription } from '@/lib/subscription-context';
import { formatPrice, getStripe } from '@/lib/stripe';
import { toast } from 'sonner';
import clsx from 'clsx';

const plans = [
  {
    name: 'Free',
    description: 'Get started with AI personas',
    price: 0,
    features: [
      'Unlimited Twitter personas',
      'Unlimited LinkedIn personas',
      'Unlimited messages',
      'Basic AI models (4o mini, Gemini 1.5 flash)',
      'Standard response time',
    ],
    limitations: [
      'No access to premium AI models',
      'Standard quality responses',
    ]
  },
  {
    name: 'Pro',
    description: 'Premium experience with advanced AI',
    price: 5,
    features: [
      'Unlimited Twitter personas',
      'Unlimited LinkedIn personas',
      'Unlimited messages',
      'Premium AI models (3.5 Sonnet, GPT-4)',
      'Fast response time',
      'Access to Latest AI models',
      'Priority support',
    ],
    limitations: []
  }
];

export default function PricingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const { isSubscribed, currentPlan, isLoading } = useSubscription();
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged((authUser) => {
      setUser(authUser);
    });

    return () => unsubscribe();
  }, []);

  const handleSubscribe = async (planId: string) => {
    try {
      setLoading(true);

      if (!user) {
        router.push('/login');
        return;
      }

      const response = await fetch('/api/create-checkout-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          planId,
          interval: 'month'
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create checkout session');
      }

      const { sessionId } = await response.json();
      const stripe = await getStripe();
      
      if (!stripe) {
        throw new Error('Stripe not initialized');
      }

      const { error } = await stripe.redirectToCheckout({ sessionId });

      if (error) {
        throw error;
      }
    } catch (error: any) {
      console.error('Error:', error);
      toast.error(error.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-16 sm:px-6 lg:px-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold mb-4">Simple, transparent pricing</h1>
          <p className="text-xl text-zinc-400 mb-8">Choose the plan that's right for you</p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={clsx(
                'rounded-2xl p-8 bg-zinc-900 border',
                plan.name === 'Pro' ? 'border-purple-500' : 'border-zinc-800'
              )}
            >
              <div className="mb-6">
                <h2 className="text-2xl font-bold mb-2">{plan.name}</h2>
                <p className="text-zinc-400">{plan.description}</p>
              </div>

              <div className="mb-6">
                <p className="text-4xl font-bold">
                  {plan.price === 0 ? (
                    'Free'
                  ) : (
                    <>
                      ${plan.price}
                      <span className="text-lg text-zinc-400">/mo</span>
                    </>
                  )}
                </p>
              </div>

              <ul className="mb-8 space-y-4">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center text-zinc-300">
                    <svg className="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                    </svg>
                    {feature}
                  </li>
                ))}
                {plan.limitations.map((limitation) => (
                  <li key={limitation} className="flex items-center text-zinc-500">
                    <svg className="w-5 h-5 text-red-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    {limitation}
                  </li>
                ))}
              </ul>

              {plan.name === 'Pro' ? (
                <button
                  onClick={() => handleSubscribe('pro')}
                  disabled={loading || (isSubscribed && currentPlan === 'pro')}
                  className={clsx(
                    'w-full py-3 px-6 rounded-full font-medium transition-colors',
                    isSubscribed && currentPlan === 'pro'
                      ? 'bg-purple-900 text-purple-100 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-700 text-white'
                  )}
                >
                  {isSubscribed && currentPlan === 'pro'
                    ? 'Current Plan'
                    : loading
                    ? 'Processing...'
                    : 'Upgrade to Pro'}
                </button>
              ) : (
                <button
                  disabled={true}
                  className="w-full py-3 px-6 rounded-full font-medium bg-zinc-800 text-zinc-400 cursor-not-allowed"
                >
                  Free Plan
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
      <Footer />
    </div>
  );
} 