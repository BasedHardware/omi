'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Gauge,
  Ban,
  Info,
  RefreshCw,
  Loader2,
  Copy,
  Check,
} from 'lucide-react';
import { getFairUseStatus } from '@/lib/api';
import type { FairUseStatus as FairUseStatusType } from '@/lib/api';
import { cn } from '@/lib/utils';

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'rounded-2xl p-5',
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
        className
      )}
    >
      {children}
    </div>
  );
}

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
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-tertiary">{label}</span>
        <span className="text-sm font-medium text-text-primary">
          {hours.toFixed(1)}h / {limit.toFixed(0)}h
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', barColor)}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

const STAGE_CONFIG = {
  none: {
    icon: CheckCircle2,
    label: 'Normal',
    color: 'text-green-400',
    bgColor: 'from-green-500/10 to-green-500/5',
    borderColor: 'ring-green-500/20',
  },
  warning: {
    icon: AlertTriangle,
    label: 'Warning',
    color: 'text-amber-400',
    bgColor: 'from-amber-500/10 to-amber-500/5',
    borderColor: 'ring-amber-500/20',
  },
  throttle: {
    icon: Gauge,
    label: 'Throttled',
    color: 'text-orange-400',
    bgColor: 'from-orange-500/10 to-orange-500/5',
    borderColor: 'ring-orange-500/20',
  },
  restrict: {
    icon: Ban,
    label: 'Restricted',
    color: 'text-red-400',
    bgColor: 'from-red-500/10 to-red-500/5',
    borderColor: 'ring-red-500/20',
  },
};

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
    await navigator.clipboard.writeText(ref);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
        <Card className="text-center py-8">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-3" />
          <p className="text-text-secondary mb-4">Unable to load fair use status.</p>
          <button
            onClick={loadStatus}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </Card>
      </div>
    );
  }

  const stage = status?.stage ?? 'none';
  const config = STAGE_CONFIG[stage] ?? STAGE_CONFIG['none'];
  const StageIcon = config.icon;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
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

      {/* Stage Card */}
      <Card className={cn('text-center ring-1', config.borderColor)}>
        <div className={cn('inline-flex p-3 rounded-full bg-gradient-to-b mb-3', config.bgColor)}>
          <StageIcon className={cn('w-8 h-8', config.color)} />
        </div>
        <h2 className={cn('text-lg font-semibold', config.color)}>{config.label}</h2>
        {status?.case_ref && (
          <button
            onClick={() => copyRef(status.case_ref)}
            className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-tertiary text-text-tertiary text-sm font-mono hover:bg-bg-quaternary transition-colors"
          >
            {status.case_ref}
            {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        )}
      </Card>

      {/* Usage Section */}
      {status && (
        <Card>
          <h3 className="text-sm font-medium text-text-secondary mb-4">Speech Usage</h3>
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
        </Card>
      )}

      {/* Message */}
      {status?.message && (
        <Card>
          <div className="flex gap-3">
            <Info className="w-4 h-4 text-text-quaternary flex-shrink-0 mt-0.5" />
            <p className="text-sm text-text-secondary leading-relaxed">{status.message}</p>
          </div>
        </Card>
      )}

      {/* About */}
      <Card>
        <h3 className="text-sm font-medium text-text-secondary mb-2">About Fair Use</h3>
        <p className="text-sm text-text-quaternary leading-relaxed">
          Omi is designed for personal conversations, meetings, and live interactions. Usage is measured by real speech
          time detected, not connection time. If usage significantly exceeds normal patterns for non-personal content,
          adjustments may apply.
        </p>
      </Card>
    </div>
  );
}
