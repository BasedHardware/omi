'use client';

import { useState, useEffect } from 'react';
import {
  Crown,
  CreditCard,
  Loader2,
  Zap,
  AlertTriangle,
  Clock,
  Check,
  Mic,
  MessageSquare,
  Lightbulb,
  Brain,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { decodePlan, planGrantsPaidCapability } from '@/types/user';
import type {
  AllUsageData,
  UserSubscription,
  PricingOption,
  UsageHistoryPoint,
  UserUsage,
} from '@/types/user';
import {
  getAvailablePlans,
  createCheckoutSession,
  upgradeSubscription,
  cancelSubscription,
  getCustomerPortal,
} from '../api';
import { Card, ConfirmDialog } from './settingsPrimitives';

type UsagePeriod = 'today' | 'monthly' | 'yearly' | 'all_time';

const PERIOD_LABELS: Record<UsagePeriod, string> = {
  today: 'Today',
  monthly: 'This Month',
  yearly: 'This Year',
  all_time: 'All Time',
};

function UsageChart({
  history,
  period,
}: {
  history?: UsageHistoryPoint[];
  period: UsagePeriod;
}) {
  const [selectedMetric, setSelectedMetric] = useState<
    'listening' | 'words' | 'insights' | 'memories'
  >('listening');

  if (!history || history.length === 0) {
    return (
      <Card className="h-48 flex items-center justify-center">
        <p className="text-text-quaternary">No activity data available</p>
      </Card>
    );
  }

  // For all_time with many data points, aggregate by year
  let dataToProcess = history;
  if (period === 'all_time' && history.length > 12) {
    // Group by year and aggregate
    const yearlyData = new Map<string, UsageHistoryPoint>();
    history.forEach((point) => {
      const date = new Date(point.date);
      const key = String(date.getFullYear());
      const existing = yearlyData.get(key);
      if (existing) {
        yearlyData.set(key, {
          date: `${key}-01-01`,
          transcription_seconds:
            existing.transcription_seconds + point.transcription_seconds,
          words_transcribed: existing.words_transcribed + point.words_transcribed,
          insights_gained: existing.insights_gained + point.insights_gained,
          memories_created: existing.memories_created + point.memories_created,
        });
      } else {
        yearlyData.set(key, { ...point, date: `${key}-01-01` });
      }
    });
    dataToProcess = Array.from(yearlyData.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
  }

  // Process history data for display
  const processedData = dataToProcess.map((point, index) => {
    // Parse date string - handles both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SSZ" formats
    let label = '';

    if (period === 'today') {
      // For today, extract hour from ISO format "2026-01-02T00:00:00Z"
      const timeMatch = point.date.match(/T(\d{2}):/);
      const hour = timeMatch ? parseInt(timeMatch[1], 10) : 0;
      label = `${hour}:00`;
    } else {
      // For other periods, parse the date portion "YYYY-MM-DD"
      const datePart = point.date.split('T')[0]; // Get date part before 'T'
      const [year, month, day] = datePart.split('-').map(Number);

      if (period === 'monthly') {
        label = `${day}`;
      } else if (period === 'yearly') {
        label = [
          'Jan',
          'Feb',
          'Mar',
          'Apr',
          'May',
          'Jun',
          'Jul',
          'Aug',
          'Sep',
          'Oct',
          'Nov',
          'Dec',
        ][month - 1];
      } else {
        // For all_time, show year
        label = String(year);
      }
    }
    return { ...point, label, index };
  });

  // Get value based on selected metric
  const getValue = (d: UsageHistoryPoint) => {
    switch (selectedMetric) {
      case 'listening':
        return d.transcription_seconds / 60; // Convert to minutes
      case 'words':
        return d.words_transcribed;
      case 'insights':
        return d.insights_gained;
      case 'memories':
        return d.memories_created;
    }
  };

  // Format value for display
  const formatValue = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
    return Math.round(value).toLocaleString();
  };

  // Format value with unit
  const formatValueWithUnit = (value: number) => {
    const formatted = formatValue(value);
    switch (selectedMetric) {
      case 'listening':
        return `${formatted} min`;
      case 'words':
        return formatted;
      case 'insights':
        return formatted;
      case 'memories':
        return formatted;
    }
  };

  // Find max value for scaling
  const maxValue = Math.max(...processedData.map((d) => getValue(d)), 1);

  const metricConfig = [
    { key: 'listening' as const, color: 'rgb(96, 165, 250)', label: 'Listening' },
    { key: 'words' as const, color: 'rgb(74, 222, 128)', label: 'Words' },
    { key: 'insights' as const, color: 'rgb(251, 146, 60)', label: 'Insights' },
    { key: 'memories' as const, color: 'rgb(192, 132, 252)', label: 'Memories' },
  ];

  const currentMetric = metricConfig.find((m) => m.key === selectedMetric)!;

  return (
    <Card>
      {/* Header with metric selector */}
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-semibold text-text-secondary">Activity Over Time</h4>
        <div className="flex gap-1">
          {metricConfig.map((metric) => (
            <button
              key={metric.key}
              onClick={() => setSelectedMetric(metric.key)}
              className={cn(
                'px-2.5 py-1 rounded-md text-xs font-medium transition-all',
                selectedMetric === metric.key
                  ? 'opacity-100'
                  : 'opacity-40 hover:opacity-60',
              )}
              style={{
                backgroundColor:
                  selectedMetric === metric.key ? `${metric.color}20` : 'transparent',
                color: metric.color,
              }}
            >
              {metric.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bar Chart */}
      <div className="flex items-end gap-4 pt-2">
        {processedData.map((d, i) => {
          const value = getValue(d);
          // Calculate height in pixels (max 100px), with minimum 8px for visibility
          const maxBarHeight = 100;
          const barHeight = Math.max((value / maxValue) * maxBarHeight, 8);
          // Convert rgb(r,g,b) to rgba format for opacity
          const rgbMatch = currentMetric.color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
          const rgba = rgbMatch
            ? `rgba(${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}, 0.5)`
            : currentMetric.color;
          return (
            <div key={i} className="flex-1 flex flex-col items-center">
              {/* Value on top */}
              <span
                className="text-xs font-bold mb-2 whitespace-nowrap"
                style={{ color: currentMetric.color }}
              >
                {formatValueWithUnit(value)}
              </span>
              {/* Bar with fixed pixel height */}
              <div
                className="w-full max-w-[80px] rounded-t-lg transition-all duration-300"
                style={{
                  height: `${barHeight}px`,
                  backgroundColor: rgba,
                }}
              />
              {/* Label */}
              <span className="text-xs text-text-quaternary mt-2 font-medium">
                {d.label}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

type PlanUsageTab = 'plan' | 'usage';

function UnknownPlanCard() {
  return (
    <Card>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-white/[0.08] flex items-center justify-center flex-shrink-0">
          <AlertTriangle className="w-5 h-5 text-text-secondary" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Plan unavailable</h3>
          <p className="text-sm text-text-tertiary mt-1">
            This account uses a plan that this version of Omi does not recognize yet. Plan
            features are unavailable until the plan can be identified.
          </p>
        </div>
      </div>
    </Card>
  );
}

export function UsageSectionContent({
  allUsage,
  subscription,
  onSubscriptionUpdate,
  cachedPlans,
}: {
  allUsage: AllUsageData | null;
  subscription: UserSubscription | null;
  onSubscriptionUpdate: () => void;
  cachedPlans: PricingOption[] | null;
}) {
  const [activeTab, setActiveTab] = useState<PlanUsageTab>('plan');
  const [selectedPeriod, setSelectedPeriod] = useState<UsagePeriod>('all_time');
  const [selectedPriceId, setSelectedPriceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [showUpgradeOptions, setShowUpgradeOptions] = useState(false);

  // Set initial selected price when plans load, and keep it in sync when the
  // subscription's current price changes (e.g. after a plan change or
  // cancellation) so a pending-cancellation user isn't left on a stale option.
  const currentPriceId = subscription?.current_price_id;
  useEffect(() => {
    if (cachedPlans && cachedPlans.length > 0) {
      const activePlan = cachedPlans.find((p) => p.is_active || p.id === currentPriceId);
      if (activePlan) {
        setSelectedPriceId(activePlan.id);
      } else if (!selectedPriceId) {
        setSelectedPriceId(cachedPlans[0].id);
      }
    }
  }, [cachedPlans, currentPriceId]);

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatNumber = (num: number) => {
    if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}k`;
    }
    return num.toString();
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Get usage for selected period
  const usage = allUsage ? allUsage[selectedPeriod] : null;
  const monthlyUsage = allUsage?.monthly;
  const periods: UsagePeriod[] = ['today', 'monthly', 'yearly', 'all_time'];

  // Default limits for basic plan (1200 minutes = 72000 seconds)
  const limits = {
    transcription_seconds: 72000, // 1200 minutes
    words_transcribed: 50000,
    insights_gained: 100,
    memories_created: 50,
  };

  const planIdentity = subscription
    ? (subscription.plan_identity ?? decodePlan(subscription.plan))
    : null;
  const isUnlimited = planIdentity ? planGrantsPaidCapability(planIdentity) : false;
  const isUnknownPlan = planIdentity?.kind === 'unknown';
  const isCancelingSubscription = subscription?.cancel_at_period_end;

  // Calculate usage percentages for basic plan
  const getUsagePercent = (used: number, limit: number) => {
    if (limit <= 0) return 0;
    return Math.min((used / limit) * 100, 100);
  };

  // Sort pricing options: monthly first, then annual
  const sortedOptions = cachedPlans
    ? [...cachedPlans].sort((a, b) => {
        const aIsAnnual =
          a.interval === 'year' || a.title?.toLowerCase().includes('annual');
        const bIsAnnual =
          b.interval === 'year' || b.title?.toLowerCase().includes('annual');
        return (aIsAnnual ? 1 : 0) - (bIsAnnual ? 1 : 0);
      })
    : [];

  const selectedOption = cachedPlans?.find((p) => p.id === selectedPriceId);

  // Default features for unlimited plan
  const defaultFeatures = [
    'Unlimited conversations',
    'Unlimited memories',
    'Priority processing',
    'Advanced insights',
  ];

  const handleSubscribe = async () => {
    if (!selectedPriceId) return;

    setIsLoading(true);
    setError(null);

    try {
      const isCurrentPlan =
        selectedOption?.is_active ||
        selectedOption?.id === subscription?.current_price_id;

      if (isCancelingSubscription && selectedPriceId !== subscription?.current_price_id) {
        setError('Plan changes are available after your current subscription ends.');
        return;
      }

      if (isUnlimited && !isCancelingSubscription && !isCurrentPlan) {
        const result = await upgradeSubscription(selectedPriceId);
        if (result?.status === 'success' || result?.scheduled_start) {
          onSubscriptionUpdate();
        } else {
          setError(result?.message || 'Failed to upgrade plan');
        }
      } else {
        const result = await createCheckoutSession(selectedPriceId);
        if (result?.url) {
          window.open(result.url, '_blank');
          const handleFocus = () => {
            onSubscriptionUpdate();
            window.removeEventListener('focus', handleFocus);
          };
          window.addEventListener('focus', handleFocus);
        } else if (result?.status === 'reactivated') {
          onSubscriptionUpdate();
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
        const handleFocus = () => {
          onSubscriptionUpdate();
          window.removeEventListener('focus', handleFocus);
        };
        window.addEventListener('focus', handleFocus);
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
      } else {
        setError(result?.message || 'Failed to cancel subscription');
      }
    } catch (err) {
      setError('Failed to cancel subscription');
    } finally {
      setIsCanceling(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Tab Switcher */}
      <div className="flex gap-1 p-1 bg-bg-tertiary rounded-xl w-fit">
        <button
          onClick={() => setActiveTab('plan')}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-all',
            activeTab === 'plan'
              ? 'bg-text-primary text-bg-primary shadow-md'
              : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary',
          )}
        >
          Plan
        </button>
        <button
          onClick={() => setActiveTab('usage')}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-all',
            activeTab === 'usage'
              ? 'bg-text-primary text-bg-primary shadow-md'
              : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary',
          )}
        >
          Usage
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'plan' ? (
        /* PLAN TAB - Unknown plans remain neutral; known plans choose Basic vs paid. */
        <div className="space-y-6">
          {isUnknownPlan ? (
            <UnknownPlanCard />
          ) : !isUnlimited ? (
            /* BASIC PLAN VIEW */
            <>
              {/* Current Plan Card */}
              <Card className="relative overflow-hidden">
                {/* Header */}
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-2xl bg-white/[0.08] flex items-center justify-center">
                      <Zap className="w-6 h-6 text-text-secondary" />
                    </div>
                    <div>
                      <h3 className="text-xl font-semibold text-text-primary">
                        Basic Plan
                      </h3>
                      <p className="text-sm text-text-tertiary">Free tier</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowUpgradeOptions(true)}
                      className="px-5 py-2.5 bg-text-primary hover:bg-text-primary/90 text-bg-primary text-sm font-semibold rounded-xl transition-all shadow-lg shadow-black/40"
                    >
                      Upgrade to Unlimited
                    </button>
                    {subscription?.stripe_subscription_id && (
                      <button
                        onClick={handleManagePayment}
                        disabled={isLoading}
                        className="px-4 py-2.5 border border-bg-quaternary text-text-secondary hover:text-text-primary text-sm font-medium rounded-xl transition-colors disabled:opacity-50"
                      >
                        Billing &amp; Invoices
                      </button>
                    )}
                  </div>
                </div>

                {/* Monthly Listening Usage */}
                <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-xl mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <Clock className="w-4 h-4 text-amber-400" />
                    <span className="text-sm font-semibold text-amber-400">
                      Monthly Listening Limit
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-2xl font-bold text-text-primary">
                      {monthlyUsage
                        ? Math.round(monthlyUsage.transcription_seconds / 60)
                        : 0}
                      <span className="text-sm font-normal text-text-tertiary ml-1">
                        / 1,200 min
                      </span>
                    </span>
                    <span className="text-sm text-text-tertiary">
                      {monthlyUsage
                        ? 1200 - Math.round(monthlyUsage.transcription_seconds / 60)
                        : 1200}{' '}
                      min left
                    </span>
                  </div>
                  <div className="h-2.5 bg-bg-quaternary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
                      style={{
                        width: `${monthlyUsage ? getUsagePercent(monthlyUsage.transcription_seconds, limits.transcription_seconds) : 0}%`,
                      }}
                    />
                  </div>
                </div>

                {/* What's Included - Checklist */}
                <div>
                  <h4 className="text-sm font-semibold text-text-secondary mb-3">
                    What&apos;s included
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 rounded bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                        <Clock className="w-3 h-3 text-amber-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">
                          1,200 minutes
                        </span>{' '}
                        of listening per month
                        <span className="text-amber-400 text-xs ml-1">(limited)</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                        <Check className="w-3 h-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        words transcribed
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                        <Check className="w-3 h-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        insights
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                        <Check className="w-3 h-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        memories
                      </span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Billing error surfaced in the Basic view (not only the upgrade panel) */}
              {error && !showUpgradeOptions && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-xl border border-red-500/20">
                  <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Upgrade Options (shown when clicked) */}
              {showUpgradeOptions && (
                <Card className="border-white/25">
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <h4 className="text-lg font-semibold text-text-primary">
                        Choose a Plan
                      </h4>
                      <p className="text-sm text-text-tertiary">
                        Unlock unlimited listening time
                      </p>
                    </div>
                    <button
                      onClick={() => setShowUpgradeOptions(false)}
                      className="p-2 hover:bg-bg-tertiary rounded-lg transition-colors"
                    >
                      <X className="w-5 h-5 text-text-quaternary" />
                    </button>
                  </div>

                  {/* Plan Selection */}
                  {sortedOptions.length > 0 ? (
                    <div className="grid grid-cols-2 gap-4 mb-5">
                      {sortedOptions.map((option) => {
                        const isSelected = selectedPriceId === option.id;
                        const isAnnual =
                          option.interval === 'year' ||
                          option.title?.toLowerCase().includes('annual');

                        return (
                          <button
                            key={option.id}
                            onClick={() => setSelectedPriceId(option.id)}
                            className={cn(
                              'relative p-5 rounded-2xl border-2 text-left transition-all',
                              isSelected
                                ? 'border-white/25 bg-white/[0.08] shadow-lg shadow-black/40'
                                : 'border-bg-tertiary hover:border-white/25 bg-bg-tertiary/30',
                            )}
                          >
                            {isAnnual && (
                              <span className="absolute -top-2.5 right-3 px-3 py-1 bg-text-primary text-bg-primary text-[10px] font-bold rounded-full uppercase tracking-wide">
                                Best Value
                              </span>
                            )}
                            <h4 className="font-semibold text-text-primary mb-1">
                              {option.title}
                            </h4>
                            <p className="text-2xl font-bold text-text-primary">
                              {option.price_string}
                            </p>
                            {option.description && (
                              <p className="text-xs text-text-secondary mt-2 font-medium">
                                {option.description}
                              </p>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-6 h-6 text-text-primary animate-spin" />
                    </div>
                  )}

                  {/* Error Message */}
                  {error && (
                    <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-xl mb-4 border border-red-500/20">
                      <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                      <p className="text-sm text-red-400">{error}</p>
                    </div>
                  )}

                  <button
                    onClick={handleSubscribe}
                    disabled={isLoading || !selectedPriceId}
                    className={cn(
                      'w-full py-3.5 rounded-xl font-semibold transition-all',
                      'bg-text-primary text-bg-primary',
                      'hover:bg-text-primary/90',
                      'shadow-lg shadow-black/40',
                      'disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none',
                    )}
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Processing...
                      </span>
                    ) : (
                      'Continue to Payment'
                    )}
                  </button>
                </Card>
              )}

              {/* This Month Stats - Compact Single Row */}
              <Card>
                <h4 className="text-sm font-semibold text-text-secondary mb-4">
                  This month
                </h4>
                <div className="grid grid-cols-4 gap-3">
                  <div className="text-center">
                    <div className="w-10 h-10 mx-auto rounded-xl bg-blue-500/10 flex items-center justify-center mb-2">
                      <Mic className="w-5 h-5 text-blue-400" />
                    </div>
                    <p className="text-xl font-bold text-blue-400">
                      {monthlyUsage
                        ? formatDuration(monthlyUsage.transcription_seconds)
                        : '0m'}
                    </p>
                    <p className="text-xs text-text-quaternary">Listening</p>
                  </div>
                  <div className="text-center">
                    <div className="w-10 h-10 mx-auto rounded-xl bg-green-500/10 flex items-center justify-center mb-2">
                      <MessageSquare className="w-5 h-5 text-green-400" />
                    </div>
                    <p className="text-xl font-bold text-green-400">
                      {monthlyUsage ? formatNumber(monthlyUsage.words_transcribed) : '0'}
                    </p>
                    <p className="text-xs text-text-quaternary">Words</p>
                  </div>
                  <div className="text-center">
                    <div className="w-10 h-10 mx-auto rounded-xl bg-orange-500/10 flex items-center justify-center mb-2">
                      <Lightbulb className="w-5 h-5 text-orange-400" />
                    </div>
                    <p className="text-xl font-bold text-orange-400">
                      {monthlyUsage?.insights_gained || 0}
                    </p>
                    <p className="text-xs text-text-quaternary">Insights</p>
                  </div>
                  <div className="text-center">
                    <div className="w-10 h-10 mx-auto rounded-xl bg-white/[0.08] flex items-center justify-center mb-2">
                      <Brain className="w-5 h-5 text-text-secondary" />
                    </div>
                    <p className="text-xl font-bold text-text-secondary">
                      {monthlyUsage?.memories_created || 0}
                    </p>
                    <p className="text-xs text-text-quaternary">Memories</p>
                  </div>
                </div>
              </Card>
            </>
          ) : (
            /* UNLIMITED PLAN VIEW */
            <>
              {/* Header */}
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-white/[0.14] flex items-center justify-center">
                  <Crown className="w-5 h-5 text-text-secondary" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">
                    {isCancelingSubscription ? 'Your Plan' : 'Manage Your Plan'}
                  </h3>
                  {subscription?.current_period_end && (
                    <p className="text-xs text-text-quaternary">
                      {isCancelingSubscription
                        ? `Cancels on ${formatDate(subscription.current_period_end)}`
                        : `Renews ${formatDate(subscription.current_period_end)}`}
                    </p>
                  )}
                </div>
              </div>

              {/* Plan Selection */}
              {sortedOptions.length > 0 ? (
                <div className="grid grid-cols-2 gap-3">
                  {sortedOptions.map((option) => {
                    const isSelected = selectedPriceId === option.id;
                    const isCurrent =
                      option.is_active || option.id === subscription?.current_price_id;
                    const isAnnual =
                      option.interval === 'year' ||
                      option.title?.toLowerCase().includes('annual');

                    return (
                      <button
                        key={option.id}
                        onClick={() => setSelectedPriceId(option.id)}
                        disabled={isCancelingSubscription && !isCurrent}
                        className={cn(
                          'relative p-4 rounded-xl border-2 text-left transition-all',
                          isSelected
                            ? 'border-white/25 bg-white/[0.08]'
                            : 'border-bg-tertiary hover:border-bg-quaternary bg-bg-tertiary/50',
                          isCancelingSubscription &&
                            !isCurrent &&
                            'cursor-not-allowed opacity-50',
                        )}
                      >
                        {isAnnual && (
                          <span className="absolute -top-2 right-2 px-2 py-0.5 bg-text-primary text-bg-primary text-[10px] font-medium rounded-full">
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
                          <p className="text-xs text-text-secondary mt-1">
                            {option.description}
                          </p>
                        )}

                        {isCurrent && (
                          <span className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 bg-green-500/10 text-green-400 text-xs rounded-full">
                            <Check className="w-3 h-3" />
                            Current
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 text-text-primary animate-spin" />
                </div>
              )}

              {isCancelingSubscription && subscription?.current_period_end && (
                <p className="text-sm text-text-tertiary">
                  You can reactivate your current plan now. Plan changes are available
                  after {formatDate(subscription.current_period_end)}.
                </p>
              )}

              {/* Features List */}
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-text-secondary">Features:</h4>
                <ul className="space-y-2">
                  {defaultFeatures.map((feature, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <Check className="w-4 h-4 text-text-secondary flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-text-tertiary">{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Error Message */}
              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-lg">
                  <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Primary Action Button */}
              <button
                onClick={handleSubscribe}
                disabled={
                  isLoading ||
                  !selectedPriceId ||
                  (!isCancelingSubscription &&
                    (selectedOption?.is_active ||
                      selectedOption?.id === subscription?.current_price_id)) ||
                  (isCancelingSubscription &&
                    selectedPriceId !== subscription?.current_price_id)
                }
                className={cn(
                  'w-full py-3 rounded-xl font-medium transition-colors',
                  'bg-text-primary text-bg-primary',
                  'hover:bg-text-primary/90',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Processing...
                  </span>
                ) : isCancelingSubscription ? (
                  'Reactivate Subscription'
                ) : selectedOption?.is_active ||
                  selectedOption?.id === subscription?.current_price_id ? (
                  'Current Plan'
                ) : (
                  'Change Plan'
                )}
              </button>

              {/* Secondary Actions */}
              <div className="pt-4 border-t border-bg-tertiary space-y-3">
                <button
                  onClick={handleManagePayment}
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-2 py-2.5 text-text-secondary hover:text-text-primary transition-colors"
                >
                  <CreditCard className="w-4 h-4" />
                  <span className="text-sm">Manage Billing &amp; Invoices</span>
                </button>

                {!isCancelingSubscription && (
                  <button
                    onClick={() => setShowCancelConfirm(true)}
                    disabled={isLoading}
                    className="w-full py-2.5 text-sm text-red-400/70 hover:text-red-400 transition-colors"
                  >
                    Cancel Subscription
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      ) : (
        /* USAGE TAB */
        <div className="space-y-6">
          {/* Period Tabs */}
          <div className="flex gap-1 p-1 bg-bg-tertiary rounded-xl">
            {periods.map((period) => (
              <button
                key={period}
                onClick={() => setSelectedPeriod(period)}
                className={cn(
                  'flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                  selectedPeriod === period
                    ? 'bg-text-primary text-bg-primary shadow-md'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary',
                )}
              >
                {PERIOD_LABELS[period]}
              </button>
            ))}
          </div>

          {/* Stats Summary - Compact Single Row */}
          <Card>
            <div className="grid grid-cols-4 gap-3">
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-blue-500/10 flex items-center justify-center mb-2">
                  <Mic className="w-5 h-5 text-blue-400" />
                </div>
                <p className="text-xl font-bold text-blue-400">
                  {usage ? formatDuration(usage.transcription_seconds) : '0m'}
                </p>
                <p className="text-xs text-text-quaternary">Listening</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-green-500/10 flex items-center justify-center mb-2">
                  <MessageSquare className="w-5 h-5 text-green-400" />
                </div>
                <p className="text-xl font-bold text-green-400">
                  {usage ? formatNumber(usage.words_transcribed) : '0'}
                </p>
                <p className="text-xs text-text-quaternary">Words</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-orange-500/10 flex items-center justify-center mb-2">
                  <Lightbulb className="w-5 h-5 text-orange-400" />
                </div>
                <p className="text-xl font-bold text-orange-400">
                  {usage?.insights_gained || 0}
                </p>
                <p className="text-xs text-text-quaternary">Insights</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-white/[0.08] flex items-center justify-center mb-2">
                  <Brain className="w-5 h-5 text-text-secondary" />
                </div>
                <p className="text-xl font-bold text-text-secondary">
                  {usage?.memories_created || 0}
                </p>
                <p className="text-xs text-text-quaternary">Memories</p>
              </div>
            </div>
          </Card>

          {/* Usage Trends Chart */}
          <UsageChart history={usage?.history} period={selectedPeriod} />
        </div>
      )}

      {/* Cancel Subscription Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showCancelConfirm}
        title="Cancel Subscription?"
        message={
          subscription?.current_period_end
            ? `Your subscription will remain active until ${formatDate(subscription.current_period_end)}. After that, you'll be moved to the Free plan.`
            : "Are you sure you want to cancel your subscription? You'll lose access to unlimited features."
        }
        confirmLabel="Cancel Subscription"
        onConfirm={handleCancelSubscription}
        onCancel={() => setShowCancelConfirm(false)}
        isDestructive={true}
        isLoading={isCanceling}
      />
    </div>
  );
}

// ============================================================================
// Developer Section
// ============================================================================
