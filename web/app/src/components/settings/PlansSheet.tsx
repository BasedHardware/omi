'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Check, Crown, CreditCard, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useState, useEffect } from 'react';
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
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

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

  const isUnlimited = subscription?.is_unlimited;
  const isCanceling_ = subscription?.cancel_at_period_end;

  useEffect(() => {
    if (open) {
      // Use cached plans if available, otherwise fetch
      if (cachedPlans && cachedPlans.length > 0) {
        setPricingOptions(cachedPlans);
        const activePlan = cachedPlans.find((p) => p.is_active);
        if (activePlan) {
          setSelectedPriceId(activePlan.id);
        } else {
          setSelectedPriceId(cachedPlans[0].id);
        }
        setIsLoadingPlans(false);
      } else {
        loadPlans();
      }
    }
  }, [open, cachedPlans]);

  const loadPlans = async () => {
    setIsLoadingPlans(true);
    setError(null);
    try {
      const response = await getAvailablePlans();
      if (response && response.plans) {
        setPricingOptions(response.plans);
        // Pre-select current active plan or first plan
        const activePlan = response.plans.find((p) => p.is_active);
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

  const handleSubscribe = async () => {
    if (!selectedPriceId) return;

    setIsLoading(true);
    setError(null);

    try {
      // Find if selected plan is the currently active one
      const selectedOption = pricingOptions.find((p) => p.id === selectedPriceId);
      const isCurrentPlan = selectedOption?.is_active;

      // If already subscribed and selecting a different plan, use upgrade endpoint
      if (isUnlimited && !isCanceling_ && !isCurrentPlan) {
        const result = await upgradeSubscription(selectedPriceId);
        if (result?.status === 'success' || result?.scheduled_start) {
          onSubscriptionUpdate();
          onOpenChange(false);
        } else {
          setError(result?.message || 'Failed to upgrade plan');
        }
      } else {
        // New subscription or reactivation
        const result = await createCheckoutSession(selectedPriceId);
        if (result?.url) {
          // Open Stripe checkout in new tab
          window.open(result.url, '_blank');
          onOpenChange(false);
          // Listen for window focus to refresh subscription
          const handleFocus = () => {
            onSubscriptionUpdate();
            window.removeEventListener('focus', handleFocus);
          };
          window.addEventListener('focus', handleFocus);
        } else if (result?.status === 'reactivated') {
          // Subscription was reactivated
          onSubscriptionUpdate();
          onOpenChange(false);
        } else {
          setError('Failed to create checkout session');
        }
      }
    } catch (err) {
      setError('An error occurred. Please try again.');
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

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Sort pricing options: monthly first, then annual
  const sortedOptions = [...pricingOptions].sort((a, b) => {
    const aIsAnnual = a.interval === 'year' || a.title?.toLowerCase().includes('annual');
    const bIsAnnual = b.interval === 'year' || b.title?.toLowerCase().includes('annual');
    return (aIsAnnual ? 1 : 0) - (bIsAnnual ? 1 : 0);
  });

  // Get the selected option
  const selectedOption = pricingOptions.find((p) => p.id === selectedPriceId);

  // Default features for unlimited plan
  const defaultFeatures = [
    'Unlimited conversations',
    'Unlimited memories',
    'Priority processing',
    'Advanced insights',
  ];

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
                  className="fixed inset-0 bg-black/50 z-[100]"
                />
              </Dialog.Overlay>
              <Dialog.Content asChild>
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: 10 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: 10 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  className={cn(
                    'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[101]',
                    'w-[90vw] max-w-[500px] max-h-[85vh] overflow-y-auto',
                    'bg-bg-secondary rounded-2xl',
                    'border border-bg-tertiary',
                    'shadow-2xl',
                    'focus:outline-none'
                  )}
                >
                  {/* Header */}
                  <div className="sticky top-0 bg-bg-secondary z-10 px-6 pt-6 pb-4 border-b border-bg-tertiary">
                    <Dialog.Close asChild>
                      <button
                        className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-bg-tertiary transition-colors"
                        aria-label="Close"
                      >
                        <X className="w-4 h-4 text-text-quaternary" />
                      </button>
                    </Dialog.Close>

                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-purple-primary/10 flex items-center justify-center">
                        <Crown className="w-5 h-5 text-purple-primary" />
                      </div>
                      <div>
                        <Dialog.Title className="text-lg font-semibold text-text-primary">
                          {isUnlimited && !isCanceling_ ? 'Manage Your Plan' : 'Choose Your Plan'}
                        </Dialog.Title>
                        {isUnlimited && subscription?.current_period_end && (
                          <p className="text-xs text-text-quaternary">
                            {isCanceling_
                              ? `Cancels on ${formatDate(subscription.current_period_end)}`
                              : `Renews ${formatDate(subscription.current_period_end)}`
                            }
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="p-6 space-y-6">
                    {isLoadingPlans ? (
                      <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-6 h-6 text-purple-primary animate-spin" />
                      </div>
                    ) : (
                      <>
                        {/* Plan Selection */}
                        <div className="grid grid-cols-2 gap-3">
                          {sortedOptions.map((option) => {
                            const isSelected = selectedPriceId === option.id;
                            const isCurrent = option.is_active;
                            const isAnnual = option.interval === 'year' || option.title?.toLowerCase().includes('annual');

                            return (
                              <button
                                key={option.id}
                                onClick={() => setSelectedPriceId(option.id)}
                                className={cn(
                                  'relative p-4 rounded-xl border-2 text-left transition-all',
                                  isSelected
                                    ? 'border-purple-primary bg-purple-primary/5'
                                    : 'border-bg-tertiary hover:border-bg-quaternary bg-bg-tertiary/50'
                                )}
                              >
                                {isAnnual && (
                                  <span className="absolute -top-2 right-2 px-2 py-0.5 bg-purple-primary text-white text-[10px] font-medium rounded-full">
                                    POPULAR
                                  </span>
                                )}

                                <h4 className="font-medium text-text-primary mb-1">
                                  {option.title}
                                </h4>
                                <p className="text-lg font-bold text-text-primary">
                                  {option.price_string}
                                </p>
                                {option.description && (
                                  <p className="text-xs text-purple-primary mt-1">
                                    {option.description}
                                  </p>
                                )}

                                {isCurrent && (
                                  <span className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 bg-success/10 text-success text-xs rounded-full">
                                    <Check className="w-3 h-3" />
                                    Current
                                  </span>
                                )}
                              </button>
                            );
                          })}
                        </div>

                        {/* Features List */}
                        <div className="space-y-2">
                          <h4 className="text-sm font-medium text-text-secondary">Features:</h4>
                          <ul className="space-y-2">
                            {defaultFeatures.map((feature, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <Check className="w-4 h-4 text-purple-primary flex-shrink-0 mt-0.5" />
                                <span className="text-sm text-text-tertiary">{feature}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        {/* Error Message */}
                        {error && (
                          <div className="flex items-center gap-2 p-3 bg-error/10 rounded-lg">
                            <AlertCircle className="w-4 h-4 text-error flex-shrink-0" />
                            <p className="text-sm text-error">{error}</p>
                          </div>
                        )}

                        {/* Primary Action */}
                        <button
                          onClick={handleSubscribe}
                          disabled={isLoading || !selectedPriceId || (isUnlimited && !isCanceling_ && selectedOption?.is_active)}
                          className={cn(
                            'w-full py-3 rounded-xl font-medium transition-colors',
                            'bg-purple-primary text-white',
                            'hover:bg-purple-secondary',
                            'disabled:opacity-50 disabled:cursor-not-allowed'
                          )}
                        >
                          {isLoading ? (
                            <span className="flex items-center justify-center gap-2">
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Processing...
                            </span>
                          ) : isCanceling_ ? (
                            'Reactivate Subscription'
                          ) : isUnlimited ? (
                            selectedOption?.is_active
                              ? 'Current Plan'
                              : 'Change Plan'
                          ) : (
                            'Continue to Payment'
                          )}
                        </button>

                        {/* Secondary Actions */}
                        {isUnlimited && (
                          <div className="pt-4 border-t border-bg-tertiary space-y-3">
                            <button
                              onClick={handleManagePayment}
                              disabled={isLoading}
                              className="w-full flex items-center justify-center gap-2 py-2.5 text-text-secondary hover:text-text-primary transition-colors"
                            >
                              <CreditCard className="w-4 h-4" />
                              <span className="text-sm">Manage Payment Method</span>
                            </button>

                            {!isCanceling_ && (
                              <button
                                onClick={() => setShowCancelConfirm(true)}
                                disabled={isLoading}
                                className="w-full py-2.5 text-sm text-error/70 hover:text-error transition-colors"
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
            ? `Your subscription will remain active until ${formatDate(subscription.current_period_end)}. After that, you'll be moved to the Free plan.`
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
