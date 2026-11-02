'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Check, Crown, CreditCard, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useState, useEffect, useRef } from 'react';
import {
  getAvailablePlans,
  createCheckoutSession,
  upgradeSubscription,
  cancelSubscription,
  getCustomerPortal,
  getUserSubscription,
} from '@/lib/api';
import type {
  UserSubscription,
  PricingOption,
  AvailablePlansResponse,
} from '@/types/user';
import { decodePlan, planDisplayName, planGrantsPaidCapability } from '@/types/user';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { TranscriptionUsageMeter } from './TranscriptionUsageMeter';
import { DEFAULT_PLAN_FEATURES } from '@/lib/planFeatures';
import {
  RESUBSCRIBE_FIRST,
  purchaseErrorMessage,
  renewalDateSeconds,
  yourPlanEndsOn,
  yourPlanWillRenewOn,
} from '@/lib/cancelPending';
import {
  trackPaywallOpened,
  trackUpgradePlanSelected,
  trackUpgradeSucceeded,
} from '@/lib/analytics/subscriptionFunnel';

interface PlansSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subscription: UserSubscription | null;
  onSubscriptionUpdate: () => void;
  cachedPlans?: PricingOption[] | null;
}

export function PlansSheet({
  open,
  onOpenChange,
  subscription,
  onSubscriptionUpdate,
  cachedPlans,
}: PlansSheetProps) {
  const [pricingOptions, setPricingOptions] = useState<PricingOption[]>([]);
  const [selectedPriceId, setSelectedPriceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingPlans, setIsLoadingPlans] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [renewalConfirmation, setRenewalConfirmation] = useState<string | null>(null);
  const paywallWasOpen = useRef(false);

  const planIdentity = subscription
    ? subscription.plan_identity ?? decodePlan(subscription.plan)
    : null;
  const isPaid = planIdentity ? planGrantsPaidCapability(planIdentity) : false;
  const currentPlanName = planIdentity
    ? planDisplayName(planIdentity)
    : 'Plan unavailable';
  const isUnknownPlan = planIdentity?.kind === 'unknown';
  const isCanceling_ = subscription?.cancel_at_period_end;

  useEffect(() => {
    if (open && !paywallWasOpen.current) {
      const current =
        planIdentity == null
          ? 'unknown'
          : planIdentity.kind === 'known'
          ? planIdentity.id
          : planIdentity.raw ?? 'unknown';
      trackPaywallOpened('web_plans', current);
    }
    paywallWasOpen.current = open;
  }, [open, planIdentity]);

  useEffect(() => {
    let cancelled = false;

    if (open) {
      if (isUnknownPlan) {
        setPricingOptions([]);
        setSelectedPriceId(null);
        setError(null);
        setIsLoadingPlans(false);
        return () => {
          cancelled = true;
        };
      }

      // Use cached plans if available, otherwise fetch
      if (cachedPlans && cachedPlans.length > 0) {
        if (cancelled) return;
        setPricingOptions(cachedPlans);
        const activePlan = cachedPlans.find(
          (p) => p.is_active || p.id === subscription?.current_price_id,
        );
        if (activePlan) {
          setSelectedPriceId(activePlan.id);
        } else {
          setSelectedPriceId(cachedPlans[0].id);
        }
        setIsLoadingPlans(false);
      } else {
        loadPlans(cancelled);
      }
    }
    return () => {
      cancelled = true;
    };
  }, [open, cachedPlans, subscription?.current_price_id, isUnknownPlan]);

  const loadPlans = async (cancelled = false) => {
    setIsLoadingPlans(true);
    setError(null);
    try {
      const response = await getAvailablePlans();
      if (cancelled) return;
      if (response && response.plans) {
        setPricingOptions(response.plans);
        // Pre-select current active plan or first plan
        const activePlan = response.plans.find(
          (p) => p.is_active || p.id === subscription?.current_price_id,
        );
        if (activePlan) {
          setSelectedPriceId(activePlan.id);
        } else if (response.plans.length > 0) {
          setSelectedPriceId(response.plans[0].id);
        }
      }
    } catch (err) {
      setError('Failed to load plans');
    } finally {
      setIsLoadingPlans(false);
    }
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const handleSubscribe = async () => {
    if (isUnknownPlan || !selectedPriceId) return;

    setIsLoading(true);
    setError(null);

    let purchaseRoute: 'upgrade' | 'checkout' = 'checkout';
    try {
      const selectedOption = pricingOptions.find((p) => p.id === selectedPriceId);
      const isCurrentPlan = selectedOption?.is_active;
      const priceId =
        isCanceling_ && subscription?.current_price_id
          ? subscription.current_price_id
          : selectedPriceId;
      const option = pricingOptions.find((p) => p.id === priceId) ?? selectedOption;

      if (isCanceling_ && selectedPriceId !== subscription?.current_price_id) {
        setError(RESUBSCRIBE_FIRST);
        return;
      }

      const tier = option?.plan_id ?? 'unknown';
      const interval = option?.interval ?? option?.title ?? 'unknown';
      trackUpgradePlanSelected(tier, interval, 'web_plans');

      // If already subscribed and selecting a different plan, use upgrade endpoint
      if (isPaid && !isCanceling_ && !isCurrentPlan) {
        purchaseRoute = 'upgrade';
        const result = await upgradeSubscription(priceId);
        if (result?.status === 'success' || result?.scheduled_start) {
          trackUpgradeSucceeded(tier, interval);
          onSubscriptionUpdate();
          onOpenChange(false);
        } else {
          setError(result?.message || 'Failed to upgrade plan');
        }
      } else {
        // New subscription or reactivation
        purchaseRoute = 'checkout';
        const result = await createCheckoutSession(priceId);
        if (result?.url) {
          // Stripe Checkout opens in a new tab. The parent page never sees the
          // cancel URL Stripe returns to, so Upgrade Cancelled is not emitted
          // here. trackUpgradeCancelled exists for a client that can observe it.
          window.open(result.url, '_blank');
          onOpenChange(false);
          // Listen for window focus to refresh subscription
          const handleFocus = () => {
            onSubscriptionUpdate();
            window.removeEventListener('focus', handleFocus);
          };
          window.addEventListener('focus', handleFocus);
        } else if (result?.status === 'reactivated') {
          const seconds = renewalDateSeconds(
            result.next_billing_date,
            subscription?.current_period_end,
          );
          const message =
            seconds == null
              ? 'Your plan will renew.'
              : yourPlanWillRenewOn(currentPlanName, formatDate(seconds));
          setRenewalConfirmation(message);
          setError(null);
          trackUpgradeSucceeded(tier, interval);
          onSubscriptionUpdate();
        } else {
          setError('Failed to create checkout session');
        }
      }
    } catch (err) {
      setError(purchaseErrorMessage(err, purchaseRoute));
    } finally {
      setIsLoading(false);
    }
  };

  const handleManagePayment = async () => {
    setIsLoading(true);
    try {
      const result = await getCustomerPortal();
      if (result?.url) {
        window.open(result.url, '_blank');
      } else {
        setError('Failed to open payment portal');
      }
    } catch (err) {
      setError('Failed to open payment portal');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelSubscription = async () => {
    setIsCanceling(true);
    try {
      const result = await cancelSubscription();
      if (result?.status === 'success' || result?.cancel_at_period_end) {
        onSubscriptionUpdate();
        setShowCancelConfirm(false);
        onOpenChange(false);
      } else {
        setError(result?.message || 'Failed to cancel subscription');
      }
    } catch (err) {
      setError('Failed to cancel subscription');
    } finally {
      setIsCanceling(false);
    }
  };

  // Sort pricing options: monthly first, then annual
  const sortedOptions = [...pricingOptions].sort((a, b) => {
    const aIsAnnual = a.interval === 'year' || a.title?.toLowerCase().includes('annual');
    const bIsAnnual = b.interval === 'year' || b.title?.toLowerCase().includes('annual');
    return (aIsAnnual ? 1 : 0) - (bIsAnnual ? 1 : 0);
  });

  // Get the selected option
  const selectedOption = pricingOptions.find((p) => p.id === selectedPriceId);

  return (
    <>
      <Dialog.Root open={open} onOpenChange={onOpenChange}>
        <AnimatePresence>
          {open && (
            <Dialog.Portal forceMount>
              <Dialog.Overlay asChild>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="fixed inset-0 z-[100] bg-black/50"
                />
              </Dialog.Overlay>
              <Dialog.Content asChild>
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: 10 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: 10 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  className={cn(
                    'fixed left-1/2 top-1/2 z-[101] -translate-x-1/2 -translate-y-1/2',
                    'max-h-[85vh] w-[90vw] max-w-[500px] overflow-y-auto',
                    'rounded-2xl bg-bg-secondary',
                    'border border-bg-tertiary',
                    'shadow-2xl',
                    'focus:outline-none',
                  )}
                >
                  {/* Header */}
                  <div className="sticky top-0 z-10 border-b border-bg-tertiary bg-bg-secondary px-6 pb-4 pt-6">
                    <Dialog.Close asChild>
                      <button
                        className="absolute right-4 top-4 rounded-lg p-1.5 transition-colors hover:bg-bg-tertiary"
                        aria-label="Close"
                      >
                        <X className="h-4 w-4 text-text-quaternary" />
                      </button>
                    </Dialog.Close>

                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/[0.08]">
                        <Crown className="h-5 w-5 text-text-primary" />
                      </div>
                      <div>
                        <Dialog.Title className="text-lg font-semibold text-text-primary">
                          {isUnknownPlan
                            ? 'Plan unavailable'
                            : isPaid && !isCanceling_
                            ? currentPlanName
                            : 'Choose Your Plan'}
                        </Dialog.Title>
                        {renewalConfirmation ? (
                          <p className="text-xs text-green-400">{renewalConfirmation}</p>
                        ) : isPaid && subscription?.current_period_end ? (
                          <p className="text-xs text-text-quaternary">
                            {isCanceling_
                              ? yourPlanEndsOn(
                                  currentPlanName,
                                  formatDate(subscription.current_period_end),
                                )
                              : `Renews ${formatDate(subscription.current_period_end)}`}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="space-y-6 p-6">
                    {isUnknownPlan ? (
                      <div className="py-8 text-center">
                        <p className="text-sm text-text-secondary">
                          This account uses a plan that this version of Omi does not
                          recognize yet. Plan options are unavailable until the plan can
                          be identified.
                        </p>
                      </div>
                    ) : isLoadingPlans ? (
                      <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-6 w-6 animate-spin text-text-primary" />
                      </div>
                    ) : (
                      <>
                        {/* Plan Selection */}
                        <div className="grid grid-cols-2 gap-3">
                          {sortedOptions.map((option) => {
                            const isSelected = selectedPriceId === option.id;
                            const isCurrent =
                              option.is_active ||
                              option.id === subscription?.current_price_id;
                            const isAnnual =
                              option.interval === 'year' ||
                              option.title?.toLowerCase().includes('annual');

                            return (
                              <button
                                key={option.id}
                                onClick={() => setSelectedPriceId(option.id)}
                                className={cn(
                                  'relative rounded-xl border-2 p-4 text-left transition-all',
                                  isSelected
                                    ? 'border-white/25 bg-white/[0.08]'
                                    : 'border-bg-tertiary bg-bg-tertiary/50 hover:border-bg-quaternary',
                                )}
                              >
                                {isAnnual && (
                                  <span className="absolute -top-2 right-2 rounded-full bg-text-primary px-2 py-0.5 text-[10px] font-medium text-bg-primary">
                                    POPULAR
                                  </span>
                                )}

                                <h4 className="mb-1 font-medium text-text-primary">
                                  {option.title}
                                </h4>
                                <p className="text-lg font-bold text-text-primary">
                                  {option.price_string}
                                </p>
                                {option.description && (
                                  <p className="mt-1 text-xs text-text-primary">
                                    {option.description}
                                  </p>
                                )}

                                {isCurrent && (
                                  <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs text-success">
                                    <Check className="h-3 w-3" />
                                    Current
                                  </span>
                                )}
                              </button>
                            );
                          })}
                        </div>

                        {isCanceling_ &&
                          selectedPriceId !== subscription?.current_price_id && (
                            <p className="text-sm text-text-tertiary">
                              {RESUBSCRIBE_FIRST}
                            </p>
                          )}

                        <TranscriptionUsageMeter subscription={subscription} />

                        {/* Features List */}
                        <div className="space-y-2">
                          <h4 className="text-sm font-medium text-text-secondary">
                            Features:
                          </h4>
                          <ul className="space-y-2">
                            {DEFAULT_PLAN_FEATURES.map((feature, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-text-primary" />
                                <span className="text-sm text-text-tertiary">
                                  {feature}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        {/* Error Message */}
                        {error && (
                          <div className="flex items-center gap-2 rounded-lg bg-error/10 p-3">
                            <AlertCircle className="h-4 w-4 flex-shrink-0 text-error" />
                            <p className="text-sm text-error">{error}</p>
                          </div>
                        )}

                        {/* Primary Action */}
                        <button
                          onClick={handleSubscribe}
                          disabled={
                            isLoading ||
                            !selectedPriceId ||
                            (isPaid && !isCanceling_ && selectedOption?.is_active)
                          }
                          className={cn(
                            'w-full rounded-xl py-3 font-medium transition-colors',
                            'bg-text-primary text-bg-primary',
                            'hover:bg-text-primary/90',
                            'disabled:cursor-not-allowed disabled:opacity-50',
                          )}
                        >
                          {isLoading ? (
                            <span className="flex items-center justify-center gap-2">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Processing...
                            </span>
                          ) : isCanceling_ ? (
                            'Resubscribe'
                          ) : isPaid ? (
                            selectedOption?.is_active ? (
                              'Current Plan'
                            ) : (
                              'Change Plan'
                            )
                          ) : (
                            'Continue to Payment'
                          )}
                        </button>

                        {!isPaid && subscription?.stripe_subscription_id && (
                          <button
                            onClick={handleManagePayment}
                            disabled={isLoading}
                            className="flex w-full items-center justify-center gap-2 py-2.5 text-text-secondary transition-colors hover:text-text-primary"
                          >
                            <CreditCard className="h-4 w-4" />
                            <span className="text-sm">Manage Billing &amp; Invoices</span>
                          </button>
                        )}

                        {/* Secondary Actions */}
                        {isPaid && (
                          <div className="space-y-3 border-t border-bg-tertiary pt-4">
                            <button
                              onClick={handleManagePayment}
                              disabled={isLoading}
                              className="flex w-full items-center justify-center gap-2 py-2.5 text-text-secondary transition-colors hover:text-text-primary"
                            >
                              <CreditCard className="h-4 w-4" />
                              <span className="text-sm">
                                Manage Billing &amp; Invoices
                              </span>
                            </button>

                            {!isCanceling_ && (
                              <button
                                onClick={() => setShowCancelConfirm(true)}
                                disabled={isLoading}
                                className="w-full py-2.5 text-sm text-error/70 transition-colors hover:text-error"
                              >
                                Cancel Subscription
                              </button>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </motion.div>
              </Dialog.Content>
            </Dialog.Portal>
          )}
        </AnimatePresence>
      </Dialog.Root>

      {/* Cancel Confirmation Dialog */}
      <ConfirmDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title="Cancel Subscription?"
        description={
          subscription?.current_period_end
            ? `Your subscription will remain active until ${formatDate(
                subscription.current_period_end,
              )}. After that, you'll be moved to the Free plan.`
            : "Are you sure you want to cancel your subscription? You'll lose access to unlimited features."
        }
        confirmLabel="Cancel Subscription"
        cancelLabel="Keep Subscription"
        variant="danger"
        onConfirm={handleCancelSubscription}
        isLoading={isCanceling}
      />
    </>
  );
}
