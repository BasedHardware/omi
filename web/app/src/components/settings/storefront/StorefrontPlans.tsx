'use client';

import { useState } from 'react';
import { AlertCircle, CreditCard, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  initialInterval,
  isCancelScheduled,
  offeredPrice,
  partitionTiers,
  storefrontActionLabel,
  storefrontCheckoutDecision,
  type PlanStorefront,
  type PlanStorefrontPrice,
  type PlanStorefrontTier,
  type PlanStorefrontUsage,
  type StorefrontInterval,
} from '@/lib/planStorefront';

/**
 * Pure presentation of the ladder-v1 plans payload. Every plan name, price,
 * line and button label is the backend's string; the only client words are
 * sheet chrome (badges, the Monthly chip, expand, manage, empty and error),
 * the same set mobile keeps in its l10n bundle.
 */
export interface StorefrontPlansProps {
  data: PlanStorefront | null;
  loading?: boolean;
  failed?: boolean;
  /** Price id whose purchase is in flight; every button is disabled meanwhile. */
  busyPriceId?: string | null;
  error?: string | null;
  livePlanId?: string | null;
  onRetry: () => void;
  onSelect: (tier: PlanStorefrontTier, price: PlanStorefrontPrice) => void;
  onManage: () => void;
}

export function StorefrontPlans({
  data,
  loading = false,
  failed = false,
  busyPriceId = null,
  error = null,
  livePlanId,
  onRetry,
  onSelect,
  onManage,
}: StorefrontPlansProps) {
  if (data && !data.showSubscriptionUi) return null;
  const legacy = data?.current?.legacy === true;
  const showManage = data == null || failed || legacy || data.current?.priceId != null;

  return (
    <div className="space-y-4" data-testid="storefront-plans">
      {data && (
        <div className="space-y-1">
          {data.header && (
            <h3 className="text-xl font-semibold text-text-primary">{data.header}</h3>
          )}
          {data.current && (
            <p
              className="text-sm text-text-tertiary"
              data-testid="storefront-current-line"
            >
              {data.current.line}
            </p>
          )}
          {legacy && data.current?.legacyNote && (
            <p
              className="pt-1 text-sm text-text-secondary"
              data-testid="storefront-legacy-note"
            >
              {data.current.legacyNote}
            </p>
          )}
        </div>
      )}

      {data && <StorefrontUsageMeter usage={data.usage} />}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-text-primary" />
        </div>
      ) : failed ? (
        <div className="space-y-3 rounded-2xl border border-stroke bg-bg-secondary p-5 text-center">
          <p className="text-sm text-text-secondary">
            Couldn&apos;t load plans. Check your connection and try again.
          </p>
          <button
            onClick={onRetry}
            className="rounded-xl border border-bg-quaternary px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            Try again
          </button>
        </div>
      ) : data == null || (data.tiers.length === 0 && !legacy) ? (
        <p className="rounded-2xl border border-stroke bg-bg-secondary p-5 text-center text-sm text-text-secondary">
          Plans aren&apos;t available right now. Try again in a minute.
        </p>
      ) : legacy ? null : (
        <TierList
          data={data}
          busyPriceId={busyPriceId}
          livePlanId={livePlanId}
          onSelect={onSelect}
        />
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-error/10 p-3" role="alert">
          <AlertCircle className="h-4 w-4 flex-shrink-0 text-error" />
          <p className="text-sm text-error">{error}</p>
        </div>
      )}

      {showManage && (
        <button
          onClick={onManage}
          disabled={busyPriceId !== null}
          className="flex w-full items-center justify-center gap-2 py-2.5 text-text-secondary transition-colors hover:text-text-primary disabled:opacity-50"
        >
          <CreditCard className="h-4 w-4" />
          <span className="text-sm">Manage billing</span>
        </button>
      )}
    </div>
  );
}

function TierList({
  data,
  busyPriceId,
  livePlanId,
  onSelect,
}: {
  data: PlanStorefront;
  busyPriceId: string | null;
  livePlanId?: string | null;
  onSelect: StorefrontPlansProps['onSelect'];
}) {
  const [chosen, setChosen] = useState<StorefrontInterval>(() => initialInterval(data));
  const [expanded, setExpanded] = useState(false);
  const cancelScheduled = isCancelScheduled(data);
  // While a cancellation is scheduled the sheet shows the current interval only.
  const selected = cancelScheduled ? data.current?.interval ?? 'month' : chosen;
  const { primary, rest } = partitionTiers(data);
  const showToggle = !cancelScheduled && data.yearlyToggleLabel !== null;

  const card = (tier: PlanStorefrontTier) => (
    <TierCard
      key={tier.tierId}
      tier={tier}
      data={data}
      interval={selected}
      busyPriceId={busyPriceId}
      livePlanId={livePlanId}
      onSelect={onSelect}
    />
  );

  return (
    <div className="space-y-3">
      {showToggle && (
        <div className="flex w-fit gap-1 rounded-xl bg-bg-tertiary p-1" role="radiogroup">
          {(['month', 'year'] as const).map((value) => (
            <button
              key={value}
              role="radio"
              aria-checked={chosen === value}
              onClick={() => setChosen(value)}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-medium transition-all',
                chosen === value
                  ? 'bg-text-primary text-bg-primary shadow-md'
                  : 'text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
              )}
            >
              {value === 'month' ? 'Monthly' : data.yearlyToggleLabel}
            </button>
          ))}
        </div>
      )}
      {primary.map(card)}
      {rest.length > 0 && (
        <>
          <button
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}
            className="w-full py-2.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            See all plans
          </button>
          {expanded && rest.map(card)}
        </>
      )}
    </div>
  );
}

function TierCard({
  tier,
  data,
  interval,
  busyPriceId,
  livePlanId,
  onSelect,
}: {
  tier: PlanStorefrontTier;
  data: PlanStorefront;
  interval: StorefrontInterval;
  busyPriceId: string | null;
  livePlanId?: string | null;
  onSelect: StorefrontPlansProps['onSelect'];
}) {
  const price = offeredPrice(tier, interval);
  const decision = price
    ? storefrontCheckoutDecision(data, tier, price, livePlanId)
    : 'refuse';
  const cta = price ? storefrontActionLabel(tier, price, decision) : null;
  const highlight = tier.recommended && !isCancelScheduled(data);
  const busy = busyPriceId !== null;

  return (
    <div
      data-testid={`storefront-tier-${tier.planId}`}
      className={cn(
        'rounded-2xl bg-bg-secondary p-5',
        highlight ? 'border-2 border-text-primary/70' : 'border border-stroke',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-lg font-semibold text-text-primary">{tier.name}</h4>
        <div className="flex flex-wrap justify-end gap-1.5">
          {highlight && <Badge>Recommended</Badge>}
          {tier.isCurrent && <Badge>Your plan</Badge>}
        </div>
      </div>

      {price && (
        <div className="mt-1">
          <p className="text-xl font-semibold text-text-primary">{price.headline}</p>
          {price.subline && (
            <p className="mt-0.5 text-sm text-text-tertiary">{price.subline}</p>
          )}
        </div>
      )}

      {tier.hoursLine && (
        <p className="mt-3 text-sm text-text-secondary">{tier.hoursLine}</p>
      )}

      {!tier.compact && tier.bullets.length > 0 && (
        <ul className="mt-2 space-y-1">
          {tier.bullets.map((bullet) => (
            <li key={bullet} className="flex gap-2 text-sm text-text-tertiary">
              <span aria-hidden className="text-text-quaternary">
                •
              </span>
              <span>{bullet}</span>
            </li>
          ))}
        </ul>
      )}

      {tier.blockedLine ? (
        <p
          className="mt-3 text-sm text-text-tertiary"
          data-testid={`storefront-blocked-${tier.planId}`}
        >
          {tier.blockedLine}
        </p>
      ) : price && cta ? (
        <div className="mt-4">
          <button
            onClick={() => onSelect(tier, price)}
            disabled={busy}
            className={cn(
              'w-full rounded-xl py-3 text-sm font-semibold transition-colors',
              'bg-text-primary text-bg-primary hover:bg-text-primary/90',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {busyPriceId === price.id ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                {cta}
              </span>
            ) : (
              cta
            )}
          </button>
          {price.renewalLine && (
            <p className="mt-1.5 text-xs text-text-quaternary">{price.renewalLine}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-bg-tertiary px-2 py-0.5 text-xs font-semibold text-text-secondary">
      {children}
    </span>
  );
}

/** The backend's meter line over a bar; nothing renders without a line. */
export function StorefrontUsageMeter({ usage }: { usage: PlanStorefrontUsage }) {
  if (!usage.meterLine) return null;
  const percent = usage.percent;
  return (
    <div
      className="rounded-2xl border border-stroke bg-bg-secondary p-4"
      data-testid="storefront-usage-meter"
    >
      <p className="text-sm text-text-secondary">{usage.meterLine}</p>
      {percent !== null && (
        <div
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-tertiary"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.min(100, Math.round(percent))}
        >
          <div
            className={cn(
              'h-full rounded-full',
              percent >= 100 ? 'bg-warning' : 'bg-text-primary',
            )}
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
          />
        </div>
      )}
    </div>
  );
}
