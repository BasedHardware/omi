'use client';

import * as Dialog from '@radix-ui/react-dialog';
import {
  ArrowLeftRight,
  BatteryLow,
  Check,
  Clock,
  Loader2,
  Mic,
  MoreHorizontal,
  Puzzle,
  Wallet,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  acceptRetentionOffer,
  cancelSubscription,
  getRetentionOffer,
  type RetentionOfferResponse,
} from '@/lib/api';
import {
  trackCancelAbandoned,
  trackCancelConfirmed,
  trackCancelFlowStarted,
  trackCancelKeptPlan,
  trackCancelReasonSelected,
} from '@/lib/analytics/subscriptionFunnel';
import { CANCEL_REASONS, type CancelReason } from '@/lib/cancelReasons';
import { cn } from '@/lib/utils';

// Copy is the shipped mobile English copy (cancel_subscription_sheet.dart and
// app_localizations_en.dart), so the three clients match word for word.
const REASON_LABELS: Record<CancelReason, string> = {
  too_expensive: 'Too expensive',
  not_using_enough: 'Not using it enough',
  missing_features: 'Missing features',
  audio_quality: 'Audio/transcription quality',
  battery_drain: 'Battery drain concerns',
  found_alternative: 'Found an alternative',
  other: 'Other',
};

const REASON_ICONS: Record<CancelReason, typeof Wallet> = {
  too_expensive: Wallet,
  not_using_enough: Clock,
  missing_features: Puzzle,
  audio_quality: Mic,
  battery_drain: BatteryLow,
  found_alternative: ArrowLeftRight,
  other: MoreHorizontal,
};

const FEEDBACK_TITLE: Record<CancelReason, string> = {
  too_expensive: 'What price would work for you?',
  not_using_enough: 'What would make you use Omi more?',
  missing_features: 'What features are you missing?',
  audio_quality: 'What issues did you experience?',
  battery_drain: 'Tell us about the battery issues',
  found_alternative: 'What are you switching to?',
  other: 'Tell us more (optional)',
};

const FEEDBACK_SUBTITLE: Record<CancelReason, string> = {
  too_expensive: 'Your feedback helps us find the right balance.',
  not_using_enough: 'We want to make Omi more useful for you.',
  missing_features: 'We’re always building — this helps us prioritize.',
  audio_quality: 'We’d love to understand what went wrong.',
  battery_drain: 'This helps our hardware team improve.',
  found_alternative: 'We’d love to learn what caught your eye.',
  other: 'We appreciate any feedback…',
};

const CONSEQUENCES = [
  'No longer have unlimited access at the end of your billing period.',
  '7x more battery usage (on-device processing)',
  '30% lower transcription quality (on-device models)',
  '5-7 second processing delay (on-device models)',
  'Cannot identify speakers.',
  'No real-time phone call transcription',
];

const ZERO_DECIMAL = new Set([
  'BIF',
  'CLP',
  'DJF',
  'GNF',
  'JPY',
  'KMF',
  'KRW',
  'MGA',
  'PYG',
  'RWF',
  'VND',
  'VUV',
  'XAF',
  'XOF',
  'XPF',
]);
const THREE_DECIMAL = new Set(['BHD', 'JOD', 'KWD', 'OMR', 'TND']);

/** Stripe minor units with the same currency presentation mobile uses. */
export function formatOfferPrice(
  amountMinor: number,
  currency: string | null | undefined,
): string {
  const code = (currency ?? 'usd').trim().toUpperCase() || 'USD';
  const digits = ZERO_DECIMAL.has(code) ? 0 : THREE_DECIMAL.has(code) ? 3 : 2;
  const symbol = code === 'USD' ? 'US$' : code === 'JPY' ? '¥' : `${code} `;
  return `${symbol}${(amountMinor / 10 ** digits).toFixed(digits)}`;
}

function formatBillingDate(seconds: number | null | undefined): string | null {
  if (!seconds) return null;
  return new Date(seconds * 1000).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

type Step = 'reason' | 'feedback' | 'confirm' | 'done';

interface CancelSubscriptionFlowProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Unix seconds for the end of the paid period, if the server sent one. */
  currentPeriodEnd?: number | null;
  /** Refresh the caller's subscription after a cancel or an accepted offer. */
  onSubscriptionUpdate: () => void;
}

/**
 * The mobile cancel flow on web: reason, optional feedback, then the
 * consequences step with the existing 50%-off retention offer and the
 * destructive confirm. The cancel entry point always stays reachable: closing
 * or keeping the plan is one click away, and a failed request keeps the
 * destructive button enabled for a retry.
 */
export function CancelSubscriptionFlow({
  open,
  onOpenChange,
  currentPeriodEnd,
  onSubscriptionUpdate,
}: CancelSubscriptionFlowProps) {
  const [step, setStep] = useState<Step>('reason');
  const [reason, setReason] = useState<CancelReason | null>(null);
  const [details, setDetails] = useState('');
  const [offer, setOffer] = useState<RetentionOfferResponse | null>(null);
  const [offerLoading, setOfferLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isAcceptingOffer, setIsAcceptingOffer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [appliedPercent, setAppliedPercent] = useState<number | null>(null);
  const finished = useRef(false);

  const busy = isCancelling || isAcceptingOffer;

  useEffect(() => {
    if (!open) return;
    setStep('reason');
    setReason(null);
    setDetails('');
    setOffer(null);
    setOfferLoading(false);
    setIsCancelling(false);
    setIsAcceptingOffer(false);
    setError(null);
    setAppliedPercent(null);
    finished.current = false;
    trackCancelFlowStarted();
  }, [open]);

  useEffect(() => {
    if (step !== 'confirm') return;
    let active = true;
    setOfferLoading(true);
    getRetentionOffer()
      .then((value) => {
        if (!active) return;
        setOffer(
          value && value.eligible && value.discounted_amount != null ? value : null,
        );
      })
      .finally(() => {
        if (active) setOfferLoading(false);
      });
    return () => {
      active = false;
    };
  }, [step]);

  const close = (nextOpen: boolean) => {
    if (!nextOpen && !finished.current) {
      const abandonedStep = step === 'reason' ? 1 : step === 'feedback' ? 2 : 3;
      trackCancelAbandoned(abandonedStep, reason);
    }
    onOpenChange(nextOpen);
  };

  const continueFromReason = () => {
    if (!reason) return;
    trackCancelReasonSelected(reason);
    setStep('feedback');
  };

  const confirmCancel = async () => {
    if (!reason || busy) return;
    setError(null);
    setIsCancelling(true);
    const trimmed = details.trim() || null;
    trackCancelConfirmed(reason, Boolean(trimmed));
    try {
      const result = await cancelSubscription({ reason, reasonDetails: trimmed });
      if (result?.status === 'success' || result?.cancel_at_period_end) {
        finished.current = true;
        onSubscriptionUpdate();
        setStep('done');
      } else {
        setError(result?.message || 'Failed to cancel subscription');
      }
    } catch {
      // Cancellation must stay reachable after a failure: keep the destructive
      // button enabled and retry on the same screen.
      setError('Failed to cancel subscription. Please try again.');
    } finally {
      setIsCancelling(false);
    }
  };

  const keepPlan = () => {
    finished.current = true;
    trackCancelKeptPlan(step === 'confirm' ? 3 : 1, reason);
    close(false);
  };

  const acceptOffer = async () => {
    if (!offer || busy) return;
    setError(null);
    setIsAcceptingOffer(true);
    try {
      const applied = await acceptRetentionOffer();
      finished.current = true;
      setAppliedPercent(applied?.percent_off ?? offer.percent_off);
      onSubscriptionUpdate();
      setStep('done');
    } catch {
      setError('Could not apply the offer. You can still cancel below.');
    } finally {
      setIsAcceptingOffer(false);
    }
  };

  const periodText = formatBillingDate(currentPeriodEnd);

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[110] bg-black/50" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[111] -translate-x-1/2 -translate-y-1/2',
            'max-h-[90vh] w-[92vw] max-w-[460px] overflow-y-auto rounded-2xl',
            'border border-bg-tertiary bg-bg-secondary shadow-2xl focus:outline-none',
          )}
          onEscapeKeyDown={(event) => {
            if (busy) event.preventDefault();
          }}
          onInteractOutside={(event) => {
            if (busy) event.preventDefault();
          }}
        >
          <div className="absolute right-4 top-4 z-10">
            <Dialog.Close asChild>
              <button
                className="rounded-lg p-1.5 transition-colors hover:bg-bg-tertiary disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Close"
                disabled={busy}
              >
                <X className="h-4 w-4 text-text-quaternary" />
              </button>
            </Dialog.Close>
          </div>

          <div className="px-6 pb-6 pt-6">
            <StepIndicator step={step} />

            {step === 'reason' && (
              <section aria-labelledby="cancel-reason-title">
                <Dialog.Title
                  id="cancel-reason-title"
                  className="text-xl font-bold text-text-primary"
                >
                  Why are you canceling?
                </Dialog.Title>
                <p className="mt-1 text-sm text-text-secondary">
                  Can you tell us why you&apos;re leaving?
                </p>
                <div className="mt-5 space-y-2">
                  {CANCEL_REASONS.map((key) => {
                    const Icon = REASON_ICONS[key];
                    const selected = reason === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => setReason(key)}
                        className={cn(
                          'flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-colors',
                          selected
                            ? 'border-text-primary/40 bg-white/[0.10] text-text-primary'
                            : 'border-bg-tertiary text-text-secondary hover:bg-bg-tertiary',
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" aria-hidden />
                        <span className="flex-1">{REASON_LABELS[key]}</span>
                        {selected && <Check className="h-4 w-4" aria-hidden />}
                      </button>
                    );
                  })}
                </div>
                <FlowButton
                  className="mt-5"
                  onClick={continueFromReason}
                  disabled={!reason}
                  label="Continue"
                />
              </section>
            )}

            {step === 'feedback' && reason && (
              <section aria-labelledby="cancel-feedback-title">
                <Dialog.Title
                  id="cancel-feedback-title"
                  className="text-xl font-bold text-text-primary"
                >
                  {FEEDBACK_TITLE[reason]}
                </Dialog.Title>
                <p className="mt-1 text-sm text-text-secondary">
                  {FEEDBACK_SUBTITLE[reason]}
                </p>
                <textarea
                  className={cn(
                    'mt-5 min-h-[140px] w-full resize-none rounded-xl border border-bg-tertiary',
                    'bg-bg-primary p-3 text-sm text-text-primary placeholder:text-text-quaternary',
                    'focus:border-text-primary/30 focus:outline-none',
                  )}
                  maxLength={300}
                  value={details}
                  onChange={(event) => setDetails(event.target.value)}
                  aria-label={FEEDBACK_TITLE[reason]}
                />
                <FlowButton
                  className="mt-5"
                  onClick={() => setStep('confirm')}
                  label="Continue"
                />
                <button
                  type="button"
                  onClick={() => setStep('confirm')}
                  className="mt-2 w-full rounded-xl py-2.5 text-sm text-text-secondary transition-colors hover:text-text-primary"
                >
                  Skip for Now
                </button>
              </section>
            )}

            {step === 'confirm' && (
              <section aria-labelledby="cancel-confirm-title">
                <Dialog.Title
                  id="cancel-confirm-title"
                  className="text-xl font-bold text-text-primary"
                >
                  Just a moment, please
                </Dialog.Title>
                <p className="mt-1 text-sm text-text-secondary">
                  We highly recommend exploring your other options instead of canceling.
                </p>

                {offerLoading && (
                  <div
                    className="mt-4 flex items-center gap-2 text-sm text-text-secondary"
                    role="status"
                  >
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Checking for an offer…
                  </div>
                )}

                {offer && (
                  <div className="mt-4 rounded-xl border border-success/30 bg-success/10 p-4 text-sm text-text-primary">
                    <p>
                      Stay and pay{' '}
                      {formatOfferPrice(offer.discounted_amount ?? 0, offer.currency)} a
                      month for the next {offer.duration_months} months.
                    </p>
                  </div>
                )}

                {periodText && (
                  <div className="mt-3 rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-text-primary">
                    Your plan will remain active until {periodText}. After that,
                    you&apos;ll be moved to the free version with limited features.
                  </div>
                )}

                <h3 className="mt-5 text-sm font-semibold text-text-primary">
                  If you cancel:
                </h3>
                <ul className="mt-2 space-y-1.5 text-sm text-text-secondary">
                  {CONSEQUENCES.map((line) => (
                    <li key={line} className="flex gap-2">
                      <span aria-hidden className="text-text-quaternary">
                        •
                      </span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>

                {error && (
                  <p
                    className="mt-4 rounded-lg bg-error/10 p-3 text-sm text-error"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="mt-5 space-y-2">
                  {offer ? (
                    <FlowButton
                      onClick={acceptOffer}
                      isLoading={isAcceptingOffer}
                      disabled={isCancelling}
                      label={`Stay for ${offer.percent_off}% off`}
                    />
                  ) : (
                    <FlowButton
                      onClick={keepPlan}
                      disabled={isCancelling}
                      label="Keep Subscription"
                    />
                  )}
                  <FlowButton
                    variant="destructive"
                    onClick={confirmCancel}
                    isLoading={isCancelling}
                    disabled={isAcceptingOffer}
                    label="Cancel Subscription"
                  />
                </div>
              </section>
            )}

            {step === 'done' && (
              <section aria-labelledby="cancel-done-title" className="py-4 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-success/10">
                  <Check className="h-6 w-6 text-success" aria-hidden />
                </div>
                <Dialog.Title
                  id="cancel-done-title"
                  className="mt-4 text-lg font-semibold text-text-primary"
                >
                  {appliedPercent != null ? 'Offer applied' : 'Subscription cancelled'}
                </Dialog.Title>
                <p className="mt-2 text-sm text-text-secondary">
                  {appliedPercent != null
                    ? `Done. ${appliedPercent}% off your next ${
                        offer?.duration_months ?? 3
                      } months.`
                    : 'Your subscription is set to cancel at the end of the period.'}
                </p>
                <FlowButton className="mt-5" onClick={() => close(false)} label="Done" />
              </section>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function StepIndicator({ step }: { step: Step }) {
  const index = step === 'reason' ? 1 : step === 'feedback' ? 2 : 3;
  return (
    <p
      className="mb-2 text-xs font-medium uppercase tracking-wide text-text-quaternary"
      aria-live="polite"
    >
      Step {index} of 3
    </p>
  );
}

function FlowButton({
  label,
  onClick,
  disabled,
  isLoading,
  variant = 'primary',
  className,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  isLoading?: boolean;
  variant?: 'primary' | 'destructive';
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isLoading}
      className={cn(
        'flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'destructive'
          ? 'bg-error/10 text-error hover:bg-error/20'
          : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
        className,
      )}
    >
      {isLoading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {label}
    </button>
  );
}
