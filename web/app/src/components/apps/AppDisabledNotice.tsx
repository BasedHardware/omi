'use client';

import { AlertTriangle, Loader2, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { App } from '@/types/apps';

interface AppDisabledNoticeProps {
  app: App;
  isOwner: boolean;
  onReEnable: () => void;
  isReEnabling: boolean;
  error: string | null;
}

/**
 * Shown when an app carries the backend's `disabled` flag.
 *
 * Nothing surfaced this state before, so a disabled app looked healthy in the
 * dashboard while every install returned 400, and the only control that clears
 * the flag was unreachable from any shipped client.
 */
export function AppDisabledNotice({
  app,
  isOwner,
  onReEnable,
  isReEnabling,
  error,
}: AppDisabledNoticeProps) {
  return (
    <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-text-primary">
            This app is disabled and cannot be installed
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            {app.disabled_reason === 'webhook_failures'
              ? 'Its endpoint failed for 72 hours in a row, so deliveries were stopped.'
              : 'It was disabled by Omi.'}
            {app.disabled_at && ` Disabled on ${app.disabled_at.slice(0, 10)}.`}
            {app.disabled_error && ` Last error: ${app.disabled_error}.`}
          </p>
          {isOwner ? (
            <>
              <p className="mt-2 text-sm text-text-tertiary">
                Fix the endpoint first — re-enabling re-checks every configured URL.
              </p>
              <button
                onClick={onReEnable}
                disabled={isReEnabling}
                className={cn(
                  'mt-3 rounded-lg px-4 py-2 text-sm font-medium',
                  'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary',
                  'flex items-center gap-2 transition-colors disabled:opacity-50',
                )}
              >
                {isReEnabling ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )}
                Re-enable
              </button>
              {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
            </>
          ) : (
            <p className="mt-2 text-sm text-text-tertiary">
              Its developer has to re-enable it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
