'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  createCheckoutSession,
  getCustomerPortal,
  getStorefront,
  upgradeSubscription,
} from '@/lib/api';
import {
  budgetExhausted,
  showBudgetNudge,
  storefrontCheckoutDecision,
  type PlanStorefront,
  type PlanStorefrontPrice,
  type PlanStorefrontTier,
  type StorefrontTrigger,
} from '@/lib/planStorefront';
import { PlanStorefrontGate } from '@/lib/planStorefrontGate';
import {
  trackPaywallOpened,
  trackUpgradePlanSelected,
  trackUpgradeSucceeded,
} from '@/lib/analytics/subscriptionFunnel';
import { StorefrontPlans, StorefrontUsageMeter } from './StorefrontPlans';

function browserLocale(): string | undefined {
  return typeof navigator === 'undefined' ? undefined : navigator.language;
}

/** Load the payload for one surface. `initial` skips the first request. */
export function useStorefront(
  source: string,
  trigger: StorefrontTrigger | null,
  enabled: boolean,
  initial: PlanStorefront | null = null,
) {
  const [data, setData] = useState<PlanStorefront | null>(initial);
  const [loading, setLoading] = useState(enabled && initial === null);
  const [failed, setFailed] = useState(false);
  const generation = useRef(0);

  const reload = useCallback(async () => {
    const run = ++generation.current;
    setLoading(true);
    setFailed(false);
    try {
      const next = await getStorefront({ source, trigger, locale: browserLocale() });
      if (run === generation.current) setData(next);
    } catch {
      if (run === generation.current) {
        setData(null);
        setFailed(true);
      }
    } finally {
      if (run === generation.current) setLoading(false);
    }
  }, [source, trigger]);

  useEffect(() => {
    if (enabled && initial === null) void reload();
    return () => {
      generation.current += 1;
    };
  }, [enabled, initial, reload]);

  return { data, loading, failed, reload };
}

/**
 * Purchase one rendered price through the existing payment rails: a paid,
 * non-cancelled subscriber changes plan with `upgrade-subscription`; Free
 * starts Stripe Checkout; resubscribe reactivates on the current price.
 */
async function purchase(
  data: PlanStorefront,
  tier: PlanStorefrontTier,
  price: PlanStorefrontPrice,
  source: string,
  livePlanId: string | null | undefined,
  onSubscriptionUpdate: () => void,
): Promise<string | null> {
  const decision = storefrontCheckoutDecision(data, tier, price, livePlanId);
  if (decision === 'refuse' || price.id === null) return null;
  trackUpgradePlanSelected(tier.planId, price.interval, source);
  const paid = data.current?.priceId != null;
  if (decision === 'checkout' && paid) {
    const result = await upgradeSubscription(price.id);
    if (result?.status === 'success' || result?.scheduled_start) {
      trackUpgradeSucceeded(tier.planId, price.interval);
      onSubscriptionUpdate();
      return null;
    }
    return result?.message || 'Couldn’t change your plan. Try again.';
  }
  const result = await createCheckoutSession(price.id);
  if (result?.url) {
    window.open(result.url, '_blank');
    const handleFocus = () => {
      onSubscriptionUpdate();
      window.removeEventListener('focus', handleFocus);
    };
    window.addEventListener('focus', handleFocus);
    return null;
  }
  if (result?.status === 'reactivated') {
    trackUpgradeSucceeded(tier.planId, price.interval);
    onSubscriptionUpdate();
    return null;
  }
  return 'Couldn’t start checkout. Try again.';
}

export interface StorefrontPanelProps {
  source: string;
  trigger?: StorefrontTrigger | null;
  livePlanId?: string | null;
  initial?: PlanStorefront | null;
  onSubscriptionUpdate: () => void;
}

/** Loads, renders and purchases from the plans payload for one surface. */
export function StorefrontPanel({
  source,
  trigger = null,
  livePlanId,
  initial = null,
  onSubscriptionUpdate,
}: StorefrontPanelProps) {
  const { data, loading, failed, reload } = useStorefront(source, trigger, true, initial);
  const [busyPriceId, setBusyPriceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opened = useRef(false);
  const [confirmation, setConfirmation] = useState<{
    tier: PlanStorefrontTier;
    price: PlanStorefrontPrice;
  } | null>(null);

  useEffect(() => {
    if (opened.current || !data?.showSubscriptionUi) return;
    opened.current = true;
    trackPaywallOpened(source, data.current?.planId ?? 'unknown');
  }, [data, source]);

  const executePurchase = async (
    tier: PlanStorefrontTier,
    price: PlanStorefrontPrice,
  ) => {
    if (!data || busyPriceId !== null) return;
    setBusyPriceId(price.id);
    setError(null);
    try {
      setError(
        await purchase(data, tier, price, source, livePlanId, onSubscriptionUpdate),
      );
    } catch {
      setError('Something went wrong. Try again.');
    } finally {
      setBusyPriceId(null);
      void reload();
    }
  };

  const onSelect = async (tier: PlanStorefrontTier, price: PlanStorefrontPrice) => {
    if (!data || storefrontCheckoutDecision(data, tier, price, livePlanId) === 'refuse')
      return;
    if (price.confirmLines?.length) setConfirmation({ tier, price });
    else await executePurchase(tier, price);
  };

  const onManage = async () => {
    setError(null);
    try {
      const result = await getCustomerPortal();
      if (result?.url) window.open(result.url, '_blank');
      else setError('Couldn’t open billing. Try again.');
    } catch {
      setError('Couldn’t open billing. Try again.');
    }
  };

  return (
    <>
      <StorefrontPlans
        data={data}
        loading={loading}
        failed={failed}
        busyPriceId={busyPriceId}
        error={error}
        livePlanId={livePlanId}
        onRetry={() => void reload()}
        onSelect={onSelect}
        onManage={onManage}
      />
      <Dialog.Root
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmation(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[110] bg-black/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[111] w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-bg-tertiary bg-bg-primary p-6 text-text-primary shadow-2xl">
            <Dialog.Title className="text-lg font-semibold">
              {confirmation?.price.ctaLabel}
            </Dialog.Title>
            <Dialog.Description asChild>
              <div className="my-4 space-y-3 text-sm text-text-secondary">
                {confirmation?.price.confirmLines?.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            </Dialog.Description>
            <div className="flex justify-end gap-3">
              <Dialog.Close className="rounded-lg border border-bg-tertiary px-4 py-2">
                Cancel
              </Dialog.Close>
              <button
                className="rounded-lg bg-text-primary px-4 py-2 text-bg-primary"
                onClick={() => {
                  if (!confirmation) return;
                  const { tier, price } = confirmation;
                  setConfirmation(null);
                  void executePurchase(tier, price);
                }}
              >
                {confirmation?.price.ctaLabel}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

/** Modal host for contextual entry points (budget, Pro gates, MCP cap). */
export function ContextualPlansSheet({
  open,
  onOpenChange,
  ...panel
}: StorefrontPanelProps & { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/50" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[101] -translate-x-1/2 -translate-y-1/2',
            'max-h-[85vh] w-[calc(100vw-32px)] max-w-[520px] overflow-y-auto',
            'rounded-2xl border border-bg-tertiary bg-bg-primary p-6 shadow-2xl focus:outline-none',
          )}
          aria-describedby={undefined}
        >
          <div className="mb-2 flex items-center justify-between">
            <Dialog.Title className="text-sm font-medium text-text-tertiary">
              Plans
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="rounded-lg p-1.5 transition-colors hover:bg-bg-tertiary"
                aria-label="Close"
              >
                <X className="h-4 w-4 text-text-quaternary" />
              </button>
            </Dialog.Close>
          </div>
          {open && <StorefrontPanel {...panel} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const NUDGE_DISMISS_KEY = 'omi.storefront.budgetNudgeDismissedPeriod';

function nudgeDismissed(period: string | null): boolean {
  if (!period) return false;
  try {
    return window.localStorage.getItem(NUDGE_DISMISS_KEY) === period;
  } catch {
    return false;
  }
}

function dismissNudge(period: string | null) {
  if (!period) return;
  try {
    window.localStorage.setItem(NUDGE_DISMISS_KEY, period);
  } catch {
    // A blocked store only means the nudge returns next visit.
  }
}

/**
 * Budget meter, 80% nudge and exhausted-budget entry. Renders nothing unless
 * both flags are on and the backend reports a ladder usage budget. At 100% the
 * sheet opens with `trigger=usage_budget`, the backend's exhausted surface
 * (Pro sees Architect there and nowhere else).
 */
export function BudgetUpsellBanner({
  livePlanId,
  onSubscriptionUpdate,
  showMeter = true,
  readGate = PlanStorefrontGate.contextualEnabled,
}: {
  /** False where the plans panel below already draws the meter. */
  showMeter?: boolean;
  livePlanId?: string | null;
  onSubscriptionUpdate: () => void;
  readGate?: () => Promise<boolean>;
}) {
  const [enabled, setEnabled] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let live = true;
    void readGate().then((on) => live && setEnabled(on));
    return () => {
      live = false;
    };
  }, [readGate]);

  const { data } = useStorefront('web_plans', 'usage_budget', enabled);
  if (
    !enabled ||
    !data ||
    !data.showSubscriptionUi ||
    data.usage.kind !== 'usage_budget'
  ) {
    return null;
  }
  const exhausted = budgetExhausted(data);
  const nudge =
    !dismissed && !nudgeDismissed(data.usage.periodId) && showBudgetNudge(data)
      ? data.usage.nudgeLine
      : null;
  if (!showMeter && !nudge && !exhausted) return null;

  return (
    <div className="space-y-3" data-testid="budget-upsell">
      {showMeter && <StorefrontUsageMeter usage={data.usage} />}
      {(nudge || exhausted) && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-bg-tertiary p-4">
          {/* At 100% there is no nudge line; the exhausted header is the backend's words. */}
          {(nudge ?? (exhausted ? data.header : null)) && (
            <p className="min-w-0 flex-1 text-sm text-text-secondary">
              {nudge ?? data.header}
            </p>
          )}
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => setSheetOpen(true)}
              className="rounded-xl bg-text-primary px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-text-primary/90"
            >
              See plans
            </button>
            {nudge && (
              <button
                onClick={() => {
                  setDismissed(true);
                  dismissNudge(data.usage.periodId);
                }}
                className="rounded-xl px-3 py-2 text-sm font-medium text-text-tertiary hover:text-text-primary"
              >
                Not now
              </button>
            )}
          </div>
        </div>
      )}
      <ContextualPlansSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        source="web_plans"
        trigger="usage_budget"
        livePlanId={livePlanId}
        initial={data}
        onSubscriptionUpdate={onSubscriptionUpdate}
      />
    </div>
  );
}
