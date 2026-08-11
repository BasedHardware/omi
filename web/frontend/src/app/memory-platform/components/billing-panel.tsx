'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/src/components/ui/button';
import { Progress } from '@/src/components/ui/progress';
import {
  PLAN_DISPLAY_NAMES,
  createCheckoutSession,
  createCustomerPortalSession,
  getAvailablePlans,
  getOverageInfo,
  getPlatformApiQuota,
  type OverageInfo,
  type PlanId,
  type PlatformApiQuota,
  type PricingOption,
} from '@/src/lib/api/billing';
import { useSessionToken } from '../hooks/use-session-token';
import { HairlineCard } from './section';

function planLabel(planId?: string) {
  if (!planId) return 'Free';
  return PLAN_DISPLAY_NAMES[planId as PlanId] ?? planId;
}

export default function BillingPanel() {
  const { user, loading, getToken } = useSessionToken();
  const [overage, setOverage] = useState<OverageInfo | null>(null);
  const [plans, setPlans] = useState<PricingOption[]>([]);
  const [quota, setQuota] = useState<PlatformApiQuota | null>(null);
  const [quotaPending, setQuotaPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = await getToken();
    if (!token) return;
    try {
      const [info, available] = await Promise.all([
        getOverageInfo(token),
        getAvailablePlans(token),
      ]);
      setOverage(info);
      setPlans(available);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load billing.');
    }
    // Platform-API quota is a separate, still-landing endpoint: a failure here
    // must not blank out the plan and usage the user can already see.
    try {
      setQuota(await getPlatformApiQuota(token));
      setQuotaPending(false);
    } catch {
      setQuota(null);
      setQuotaPending(true);
    }
  }, [getToken]);

  useEffect(() => {
    if (!loading && user) void load();
  }, [loading, user, load]);

  const upgrade = async (priceId: string) => {
    const token = await getToken();
    if (!token) return;
    setBusy(true);
    try {
      const session = await createCheckoutSession(token, priceId);
      if (session?.url) window.location.href = session.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start checkout.');
    } finally {
      setBusy(false);
    }
  };

  const openPortal = async () => {
    const token = await getToken();
    if (!token) return;
    setBusy(true);
    try {
      const session = await createCustomerPortalSession(token);
      if (session?.url) window.location.href = session.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the billing portal.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="text-sm text-neutral-500">Checking your session…</p>;

  if (!user) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-8 text-center text-sm text-neutral-300">
        Sign in to Omi to see your plan and platform-API usage.
      </div>
    );
  }

  const included = quota?.included_requests ?? null;
  const used = quota?.used_requests ?? 0;
  const percent = included && included > 0 ? Math.min((used / included) * 100, 100) : 0;

  return (
    <div className="flex flex-col gap-8">
      {error ? <p className="text-xs text-[#ff806a]">{error}</p> : null}

      <div className="grid gap-4 md:grid-cols-3">
        <HairlineCard eyebrow="current plan" title={planLabel(overage?.plan_type)}>
          {overage?.explainer_title ?? 'Your Omi subscription tier.'}
        </HairlineCard>
        <HairlineCard eyebrow="questions" title={`${overage?.used_questions ?? 0}`}>
          {overage?.included_questions
            ? `of ${overage.included_questions} included this period`
            : 'used this period'}
        </HairlineCard>
        <HairlineCard
          eyebrow="overage"
          title={`$${(overage?.overage_usd ?? 0).toFixed(2)}`}
        >
          {overage?.excess_questions ?? 0} question(s) beyond the included amount.
        </HairlineCard>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
        <div className="flex items-baseline justify-between">
          <h3 className="text-base font-semibold tracking-tight text-white">
            Platform API quota
          </h3>
          <span className="font-mono text-xs text-neutral-500">
            {quotaPending
              ? 'pending backend rollout'
              : `${used} / ${included ?? '∞'} requests`}
          </span>
        </div>
        <Progress value={percent} className="mt-4 h-1.5 bg-white/10" />
        <p className="mt-3 text-sm text-neutral-400">
          {quotaPending
            ? 'Per-plan platform-API quota is being added to plan limits. Search and ingest remain bounded by their per-request limits in the meantime.'
            : `${
                quota?.remaining_requests ?? '∞'
              } requests remaining on /v1/memory/platform.`}
        </p>
      </div>

      <div>
        <h3 className="text-base font-semibold tracking-tight text-white">Upgrade</h3>
        <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className="flex flex-col rounded-xl border border-white/10 bg-white/[0.02] p-5"
            >
              {plan.eyebrow ? (
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[#b9f36b]">
                  {plan.eyebrow}
                </span>
              ) : null}
              <h4 className="mt-2 text-base font-semibold text-white">
                {planLabel(plan.plan_id)} · {plan.title}
              </h4>
              <p className="mt-1 text-2xl font-semibold tracking-tight text-white">
                {plan.price_string}
              </p>
              {plan.subtitle ? (
                <p className="mt-2 text-sm text-neutral-400">{plan.subtitle}</p>
              ) : null}
              <Button
                className="mt-5"
                variant={plan.is_active ? 'outline' : 'default'}
                disabled={busy || plan.is_active}
                onClick={() => void upgrade(plan.id)}
              >
                {plan.is_active ? 'Current plan' : 'Upgrade'}
              </Button>
            </div>
          ))}
          {plans.length === 0 ? (
            <p className="text-sm text-neutral-500">No upgrade options available.</p>
          ) : null}
        </div>
        <Button
          variant="ghost"
          className="mt-6"
          onClick={() => void openPortal()}
          disabled={busy}
        >
          Manage billing in Stripe
        </Button>
      </div>
    </div>
  );
}
