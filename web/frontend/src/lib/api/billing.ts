import { browserApiBase as apiBase } from '@/src/lib/api/browser-base';

export type PlanId =
  | 'basic'
  | 'unlimited'
  | 'architect'
  | 'operator'
  | 'plus'
  | 'unlimited_v2';

export const PLAN_DISPLAY_NAMES: Record<PlanId, string> = {
  basic: 'Free',
  unlimited: 'Neo',
  architect: 'Architect',
  operator: 'Operator',
  plus: 'Plus',
  unlimited_v2: 'Unlimited',
};

export interface PricingOption {
  id: string;
  plan_id: string;
  title: string;
  price_string: string;
  description?: string | null;
  subtitle?: string | null;
  eyebrow?: string | null;
  interval: string;
  unit_amount: number;
  is_active: boolean;
}

export interface OverageInfo {
  plan: string;
  plan_type: string;
  is_overage_plan: boolean;
  included_questions?: number | null;
  used_questions: number;
  excess_questions: number;
  overage_usd: number;
  reset_at?: number | null;
  explainer_title: string;
  explainer_body: string;
}

/** Mirrors backend `MemoryPlatformQuota`. `limit`/`remaining` are null when uncapped. */
export interface PlatformApiQuota {
  plan: string;
  plan_type: string;
  unit: 'requests';
  used: number;
  limit: number | null;
  remaining: number | null;
  allowed: boolean;
  reset_at: number;
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });
  if (!response.ok)
    throw new Error(`${init.method ?? 'GET'} ${path} failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * LIVE: GET /v1/payments/available-plans
 *
 * The platform header is required, not decorative. `should_show_new_plans`
 * returns false for an absent platform, so an unidentified caller is treated as
 * a legacy client: the catalog drops Operator and exposes the deprecated Neo
 * entry. This storefront is always current, so it identifies itself as web.
 */
export async function getAvailablePlans(token: string): Promise<PricingOption[]> {
  const data = await request<{ plans: PricingOption[] }>(
    '/v1/payments/available-plans',
    token,
    { headers: { 'X-App-Platform': 'web' } },
  );
  return data?.plans ?? [];
}

/** LIVE: GET /v1/payments/overage-info */
export function getOverageInfo(token: string) {
  return request<OverageInfo>('/v1/payments/overage-info', token);
}

/**
 * The checkout route has two outcomes. A new subscription returns a Stripe
 * `url` to redirect to; reactivating a subscription that was scheduled to
 * cancel returns no url at all, only `status: 'reactivated'` and a `message`.
 * A caller that models only `url` silently does nothing in that second case.
 */
export interface CheckoutSessionResponse {
  url?: string;
  session_id?: string;
  status?: string;
  message?: string;
  next_billing_date?: number;
}

/** LIVE: POST /v1/payments/checkout-session */
export function createCheckoutSession(token: string, priceId: string) {
  return request<CheckoutSessionResponse>('/v1/payments/checkout-session', token, {
    method: 'POST',
    body: JSON.stringify({ price_id: priceId }),
  });
}

/** LIVE: POST /v1/payments/customer-portal */
export function createCustomerPortalSession(token: string) {
  return request<{ url?: string }>('/v1/payments/customer-portal', token, {
    method: 'POST',
  });
}

/** LIVE: GET /v1/memory/platform/quota */
export function getPlatformApiQuota(token: string) {
  return request<PlatformApiQuota>('/v1/memory/platform/quota', token);
}
