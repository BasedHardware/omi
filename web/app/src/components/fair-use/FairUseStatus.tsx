'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, RefreshCw, Loader2, Info, Copy, Check } from 'lucide-react';
import { getFairUseStatus } from '@/lib/api';
import type { FairUseStatus as FairUseStatusType } from '@/lib/api';
import { cn } from '@/lib/utils';

const STAGE_META: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  warning: { label: 'Warning', dot: 'bg-amber-400', text: 'text-amber-400', bg: 'bg-amber-500/[0.08]' },
  throttle: { label: 'Throttled', dot: 'bg-orange-400', text: 'text-orange-400', bg: 'bg-orange-500/[0.08]' },
  restrict: { label: 'Restricted', dot: 'bg-red-400', text: 'text-red-400', bg: 'bg-red-500/[0.08]' },
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
  const barColor = pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-purple-500';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-tertiary">{label}</span>
        <span className="text-sm font-medium text-text-primary">
          {hours.toFixed(1)}h / {limit.toFixed(0)}h
        </span>
      </div>
      <div className="h-1 rounded-full bg-bg-tertiary overflow-hidden">
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
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-text-tertiary animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-secondary" />
          </button>
          <h1 className="text-xl font-semibold text-text-primary">Fair Use</h1>
        </div>
        <div className="text-center py-8">
          <p className="text-text-tertiary mb-4">Unable to load fair use status.</p>
          <button
            onClick={loadStatus}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
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
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => router.back()} className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-secondary" />
          </button>
          <h1 className="text-xl font-semibold text-text-primary">Fair Use</h1>
        </div>
        <button
          onClick={loadStatus}
          className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-text-tertiary" />
        </button>
      </div>

      {/* Status Banner — only for elevated stages */}
      {isElevated && meta && (
        <div className={cn('flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl', meta.bg)}>
          <div className={cn('w-2 h-2 rounded-full', meta.dot)} />
          <span className={cn('text-sm font-medium', meta.text)}>{meta.label}</span>
          {status?.case_ref && (
            <>
              <div className="flex-1" />
              <button
                onClick={() => copyRef(status.case_ref)}
                className="inline-flex items-center gap-1.5 text-text-tertiary text-xs font-mono hover:text-text-secondary transition-colors"
              >
                {status.case_ref}
                {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
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
            'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]'
          )}
        >
          <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-4">Speech Usage</h3>
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
      {status?.stage === 'restrict' && status?.dg_budget && status.dg_budget.daily_limit_ms > 0 && (() => {
        const { daily_limit_ms, used_ms, exhausted, resets_at } = status.dg_budget;
        const usedMin = Math.round(used_ms / 60000);
        const limitMin = Math.round(daily_limit_ms / 60000);
        const pct = Math.min((used_ms / daily_limit_ms) * 100, 100);
        const barColor = exhausted ? 'bg-red-500' : 'bg-purple-500';

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
              exhausted ? 'bg-red-500/[0.06]' : 'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
              'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-text-tertiary uppercase tracking-wide">Daily Transcription</span>
              <span className="text-sm font-medium text-text-primary">{usedMin}m / {limitMin}m</span>
            </div>
            <div className="h-1 rounded-full bg-bg-tertiary overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', barColor)}
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            {exhausted && (
              <p className="text-xs font-medium text-red-400 mt-2">Budget exhausted — transcription paused</p>
            )}
            {resetLabel && (
              <p className="text-xs text-text-quaternary mt-1">{resetLabel}</p>
            )}
          </div>
        );
      })()}

      {/* Message — only when present */}
      {status?.message && (
        <div className="flex gap-2.5 px-1">
          <Info className="w-4 h-4 text-text-quaternary flex-shrink-0 mt-0.5" />
          <p className="text-sm text-text-tertiary leading-relaxed">{status.message}</p>
        </div>
      )}

      {/* About footnote */}
      <div className="px-1 pt-2">
        <h4 className="text-xs font-medium text-text-quaternary mb-1">About Fair Use</h4>
        <p className="text-xs text-text-quaternary/70 leading-relaxed">
          Omi is designed for personal conversations, meetings, and live interactions. Usage is measured by real speech
          time detected, not connection time. If usage significantly exceeds normal patterns for non-personal content,
          adjustments may apply.
        </p>
      </div>
    </div>
  );
}
