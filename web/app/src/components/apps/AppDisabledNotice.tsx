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
        <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-text-primary">
            This app is disabled and cannot be installed
          </p>
          <p className="text-sm text-text-secondary mt-1">
            {app.disabled_reason === 'webhook_failures'
              ? 'Its endpoint failed for 72 hours in a row, so deliveries were stopped.'
              : 'It was disabled by Omi.'}
            {app.disabled_at && ` Disabled on ${app.disabled_at.slice(0, 10)}.`}
            {app.disabled_error && ` Last error: ${app.disabled_error}.`}
          </p>
          {isOwner ? (
            <>
              <p className="text-sm text-text-tertiary mt-2">
                Fix the endpoint first — re-enabling re-checks every configured URL.
              </p>
              <button
                onClick={onReEnable}
                disabled={isReEnabling}
                className={cn(
                  'mt-3 px-4 py-2 rounded-lg font-medium text-sm',
                  'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary',
                  'transition-colors flex items-center gap-2 disabled:opacity-50',
                )}
              >
                {isReEnabling ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RotateCcw className="w-4 h-4" />
                )}
                Re-enable
              </button>
              {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
            </>
          ) : (
            <p className="text-sm text-text-tertiary mt-2">
              Its developer has to re-enable it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
