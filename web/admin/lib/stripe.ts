import Stripe from 'stripe';

let _stripe: Stripe | null = null;

export function getOptionalStripe(): Stripe | null {
  if (!process.env.STRIPE_SECRET_KEY) {
    return null;
  }

  if (!_stripe) {
    _stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
      apiVersion: '2025-07-30.basil',
    });
  }

  return _stripe;
}

export function getStripe(): Stripe {
  const stripe = getOptionalStripe();
  if (!stripe) {
    throw new Error('STRIPE_SECRET_KEY environment variable is not set');
  }
  return stripe;
}
