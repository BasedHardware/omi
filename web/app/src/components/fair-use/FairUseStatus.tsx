'use client';

import { useState, useEffect } from 'react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import { ArrowLeft, RefreshCw, Loader2, Info, Copy, Check } from 'lucide-react';
import { getFairUseStatus } from '@/lib/api';
import type { FairUseStatus as FairUseStatusType } from '@/lib/api';
import { cn } from '@/lib/utils';

const STAGE_META: Record<
  string,
  { label: string; dot: string; text: string; bg: string }
> = {
  warning: {
    label: 'Warning',
    dot: 'bg-amber-400',
    text: 'text-amber-400',
    bg: 'bg-amber-500/[0.08]',
  },
  throttle: {
    label: 'Throttled',
    dot: 'bg-orange-400',
    text: 'text-orange-400',
    bg: 'bg-orange-500/[0.08]',
  },
  restrict: {
    label: 'Restricted',
    dot: 'bg-red-400',
    text: 'text-red-400',
    bg: 'bg-red-500/[0.08]',
  },
};

function UsageBar({
  label,
  hours,
  limit,
  pct,
}: {
  label: string;
  hours: number;
  limit: number;
  pct: number;
}) {
  const barColor =
    pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-text-primary';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-tertiary">{label}</span>
        <span className="text-sm font-medium text-text-primary">
          {hours.toFixed(1)}h / {limit.toFixed(0)}h
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-bg-tertiary">
        <div
          className={cn('h-full rounded-full transition-all', barColor)}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

export function FairUseStatus() {
  const router = useRouter();
  const [status, setStatus] = useState<FairUseStatusType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await getFairUseStatus();
      if (!result) {
        setError('Unable to load fair use status');
        return;
      }
      setStatus(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load status');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const copyRef = async (ref: string) => {
    try {
      await navigator.clipboard.writeText(ref);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may not be available in all contexts
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-text-tertiary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <div className="mb-6 flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
          >
            <ArrowLeft className="h-5 w-5 text-text-secondary" />
          </button>
          <h1 className="text-xl font-semibold text-text-primary">Fair Use</h1>
        </div>
        <div className="py-8 text-center">
          <p className="mb-4 text-text-tertiary">Unable to load fair use status.</p>
          <button
            onClick={loadStatus}
            className="inline-flex items-center gap-2 rounded-lg bg-white/[0.08] px-4 py-2 text-text-secondary transition-colors hover:bg-white/[0.14]"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  const stage = status?.stage ?? 'none';
  const isElevated = stage !== 'none';
  const meta = STAGE_META[stage];

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
          >
            <ArrowLeft className="h-5 w-5 text-text-secondary" />
          </button>
          <h1 className="text-xl font-semibold text-text-primary">Fair Use</h1>
        </div>
        <button
          onClick={loadStatus}
          className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
          title="Refresh"
        >
          <RefreshCw className="h-4 w-4 text-text-tertiary" />
        </button>
      </div>

      {/* Status Banner — only for elevated stages */}
      {isElevated && meta && (
        <div
          className={cn('flex items-center gap-2.5 rounded-xl px-3.5 py-2.5', meta.bg)}
        >
          <div className={cn('h-2 w-2 rounded-full', meta.dot)} />
          <span className={cn('text-sm font-medium', meta.text)}>{meta.label}</span>
          {status?.case_ref && (
            <>
              <div className="flex-1" />
              <button
                onClick={() => copyRef(status.case_ref)}
                className="inline-flex items-center gap-1.5 font-mono text-xs text-text-tertiary transition-colors hover:text-text-secondary"
              >
                {status.case_ref}
                {copied ? (
                  <Check className="h-3 w-3 text-green-400" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </button>
            </>
          )}
        </div>
      )}

      {/* Usage */}
      {status && (
        <div
          className={cn(
            'rounded-2xl p-5',
            'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
          )}
        >
          <h3 className="mb-4 text-xs font-medium uppercase tracking-wide text-text-tertiary">
            Speech Usage
          </h3>
          <div className="space-y-4">
            <UsageBar
              label="Today"
              hours={status.speech_hours_today}
              limit={status.limits.daily_hours}
              pct={status.usage_pct.daily}
            />
            <UsageBar
              label="3-Day Rolling"
              hours={status.speech_hours_3day}
              limit={status.limits.three_day_hours}
              pct={status.usage_pct.three_day}
            />
            <UsageBar
              label="Weekly Rolling"
              hours={status.speech_hours_weekly}
              limit={status.limits.weekly_hours}
              pct={status.usage_pct.weekly}
            />
          </div>
        </div>
      )}

      {/* Daily Transcription Budget — only for restricted users */}
      {status?.stage === 'restrict' &&
        status?.dg_budget &&
        status.dg_budget.daily_limit_ms > 0 &&
        (() => {
          const { daily_limit_ms, used_ms, exhausted, resets_at } = status.dg_budget;
          const usedMin = Math.round(used_ms / 60000);
          const limitMin = Math.round(daily_limit_ms / 60000);
          const pct = Math.min((used_ms / daily_limit_ms) * 100, 100);
          const barColor = exhausted ? 'bg-red-500' : 'bg-text-primary';

          let resetLabel = '';
          if (resets_at) {
            try {
              const diff = new Date(resets_at).getTime() - Date.now();
              if (diff > 0) {
                const hours = Math.floor(diff / 3600000);
                const mins = Math.floor((diff % 3600000) / 60000);
                resetLabel = hours > 0 ? `Resets in ${hours}h` : `Resets in ${mins}m`;
              }
            } catch {}
          }

          return (
            <div
              className={cn(
                'rounded-2xl p-4',
                exhausted
                  ? 'bg-red-500/[0.06]'
                  : 'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
                'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
              )}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Daily Transcription
                </span>
                <span className="text-sm font-medium text-text-primary">
                  {usedMin}m / {limitMin}m
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-bg-tertiary">
                <div
                  className={cn('h-full rounded-full transition-all', barColor)}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              {exhausted && (
                <p className="mt-2 text-xs font-medium text-red-400">
                  Budget exhausted — transcription paused
                </p>
              )}
              {resetLabel && (
                <p className="mt-1 text-xs text-text-quaternary">{resetLabel}</p>
              )}
            </div>
          );
        })()}

      {/* Message — only when present */}
      {status?.message && (
        <div className="flex gap-2.5 px-1">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-text-quaternary" />
          <p className="text-sm leading-relaxed text-text-tertiary">{status.message}</p>
        </div>
      )}

      {/* About footnote */}
      <div className="px-1 pt-2">
        <h4 className="mb-1 text-xs font-medium text-text-quaternary">About Fair Use</h4>
        <p className="text-xs leading-relaxed text-text-quaternary/70">
          Omi is designed for personal conversations, meetings, and live interactions.
          Usage is measured by real speech time detected, not connection time. If usage
          significantly exceeds normal patterns for non-personal content, adjustments may
          apply.
        </p>
      </div>
    </div>
  );
}
