import Stripe from "stripe";

let _stripe: Stripe | null = null;
let _stripeRead: Stripe | null = null;
let _readFallbackWarned = false;

export function getOptionalStripe(): Stripe | null {
  if (!process.env.STRIPE_SECRET_KEY) {
    return null;
  }

  if (!_stripe) {
    _stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
      apiVersion: "2025-07-30.basil",
    });
  }

  return _stripe;
}

export function getStripe(): Stripe {
  const stripe = getOptionalStripe();
  if (!stripe) {
    throw new Error("STRIPE_SECRET_KEY environment variable is not set");
  }
  return stripe;
}

// Read-only Stripe access. Prefers the restricted read-only key
// (STRIPE_READ_API_KEY); only its lack of write scope is guaranteed, so call
// sites that mutate Stripe must use getStripe() instead. Falls back to the
// full key with a one-time warning so a deploy that lands before the secret
// binding cannot take read paths down.
export function getOptionalStripeRead(): Stripe | null {
  const readKey = process.env.STRIPE_READ_API_KEY;
  if (readKey) {
    if (!_stripeRead) {
      _stripeRead = new Stripe(readKey, {
        apiVersion: "2025-07-30.basil",
      });
    }
    return _stripeRead;
  }

  const fallback = getOptionalStripe();
  if (fallback && !_readFallbackWarned) {
    _readFallbackWarned = true;
    console.warn(
      "[stripe] STRIPE_READ_API_KEY is not set; Stripe read paths are using the full STRIPE_SECRET_KEY"
    );
  }
  return fallback;
}

export function getStripeRead(): Stripe {
  const stripe = getOptionalStripeRead();
  if (!stripe) {
    throw new Error(
      "Neither STRIPE_READ_API_KEY nor STRIPE_SECRET_KEY environment variable is set"
    );
  }
  return stripe;
}
