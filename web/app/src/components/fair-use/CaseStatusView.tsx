'use client';

import { cn } from '@/lib/utils';
import { t } from '@/lib/i18n';

const STAGE_META: Record<
  string,
  { label: string; dot: string; text: string; bg: string }
> = {
  none: {
    get label() {
      return t('Normal');
    },
    dot: 'bg-green-400',
    text: 'text-green-400',
    bg: 'bg-green-500/[0.06]',
  },
  warning: {
    get label() {
      return t('Warning');
    },
    dot: 'bg-amber-400',
    text: 'text-amber-400',
    bg: 'bg-amber-500/[0.06]',
  },
  throttle: {
    get label() {
      return t('Throttled');
    },
    dot: 'bg-orange-400',
    text: 'text-orange-400',
    bg: 'bg-orange-500/[0.06]',
  },
  restrict: {
    get label() {
      return t('Restricted');
    },
    dot: 'bg-red-400',
    text: 'text-red-400',
    bg: 'bg-red-500/[0.06]',
  },
};

const SUPPORT_EMAIL = 'team@basedhardware.com';

interface CaseStatus {
  case_ref: string;
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
  message: string;
  created_at: string;
  updated_at: string;
  support_email?: string;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function daysSince(iso: string): number {
  try {
    return Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24));
  } catch {
    return 0;
  }
}

export function CaseStatusView({
  caseRef,
  status,
}: {
  caseRef: string;
  status: CaseStatus | null;
}) {
  if (!status) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center">
          <h1 className="text-lg font-semibold text-white mb-2">{t('Case Not Found')}</h1>
          <p className="text-sm text-zinc-400 mb-1">
            {t('No case found for reference')}{' '}
            <span className="font-mono text-zinc-300">{caseRef}</span>
          </p>
          <p className="text-xs text-zinc-500 mt-4">
            {t('If you believe this is an error, contact')}{' '}
            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="text-text-secondary hover:text-text-secondary"
            >
              {SUPPORT_EMAIL}
            </a>
          </p>
        </div>
      </div>
    );
  }

  const meta = STAGE_META[status.stage] ?? STAGE_META['none'];
  const updatedDays = daysSince(status.updated_at);
  const email = status.support_email || SUPPORT_EMAIL;

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="max-w-md w-full space-y-5">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-lg font-semibold text-white">{t('Case Status')}</h1>
          <p className="text-xs text-zinc-500 font-mono mt-1">{status.case_ref}</p>
        </div>

        {/* Status */}
        <div
          className={cn(
            'rounded-2xl p-5',
            'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
          )}
        >
          {/* Stage */}
          <div
            className={cn('flex items-center gap-2.5 px-3 py-2 rounded-xl mb-4', meta.bg)}
          >
            <div className={cn('w-2 h-2 rounded-full', meta.dot)} />
            <span className={cn('text-sm font-medium', meta.text)}>{meta.label}</span>
          </div>

          {/* Details */}
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-zinc-500">{t('Created')}</span>
              <span className="text-sm text-zinc-300">
                {formatDate(status.created_at)}
              </span>
            </div>
            <div className="h-px bg-zinc-800" />
            <div className="flex justify-between items-center">
              <span className="text-xs text-zinc-500">{t('Last Updated')}</span>
              <span className="text-sm text-zinc-300">
                {formatDate(status.updated_at)}
              </span>
            </div>
          </div>

          {/* Message */}
          {status.message && (
            <>
              <div className="h-px bg-zinc-800 my-3" />
              <p className="text-sm text-zinc-400 leading-relaxed">{status.message}</p>
            </>
          )}
        </div>

        {/* Support note */}
        {updatedDays >= 3 && (
          <div className="rounded-xl bg-zinc-900/50 px-4 py-3">
            <p className="text-xs text-zinc-400 leading-relaxed">
              {t('This case hasn\'t been updated in')}{' '}{updatedDays} {t('days. If you need assistance, please contact')}{' '}
              <a
                href={`mailto:${email}`}
                className="text-text-secondary hover:text-text-secondary"
              >
                {email}
              </a>
            </p>
          </div>
        )}

        {/* Footer */}
        <p className="text-center text-xs text-zinc-600">
          {t('Need help?')}{' '}
          <a
            href={`mailto:${email}`}
            className="text-text-secondary hover:text-text-secondary"
          >
            {email}
          </a>
        </p>
      </div>
    </div>
  );
}
