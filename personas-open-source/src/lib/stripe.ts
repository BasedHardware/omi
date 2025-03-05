import { loadStripe } from '@stripe/stripe-js';
import Stripe from 'stripe';

// Initialize Stripe on the client side
export const getStripe = async () => {
  const stripePublishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY as string;
  
  if (!stripePublishableKey) {
    throw new Error('Stripe publishable key is not defined');
  }
  
  const stripePromise = loadStripe(stripePublishableKey);
  return stripePromise;
};

// Initialize Stripe with the secret key
export const getStripeInstance = (): Stripe => {
  const secretKey = process.env.STRIPE_SECRET_KEY!;
  return new Stripe(secretKey, {
    apiVersion: '2025-02-24.acacia',
  });
};

// Helper function to format price
export const formatPrice = (price: number, interval?: 'month' | 'year') => {
  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  });
  
  const formattedPrice = formatter.format(price);
  
  if (interval) {
    return `${formattedPrice}/${interval === 'month' ? 'mo' : 'yr'}`;
  }
  
  return formattedPrice;
};