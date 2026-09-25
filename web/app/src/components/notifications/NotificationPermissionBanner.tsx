'use client';

import { useState } from 'react';
import { Bell, AlertTriangle, X, ExternalLink } from 'lucide-react';
import { useNotificationContext } from './NotificationContext';
import { cn } from '@/lib/utils';

export function NotificationPermissionBanner() {
  const { permission, requestPermission, isLoading } = useNotificationContext();
  const [isDismissed, setIsDismissed] = useState(false);
  const [isRequesting, setIsRequesting] = useState(false);

  if (isDismissed) return null;

  const handleRequestPermission = async () => {
    setIsRequesting(true);
    await requestPermission();
    setIsRequesting(false);
  };

  // Permission not yet requested
  if (permission === 'default') {
    return (
      <div className="border-b border-white/25 bg-white/[0.08] px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-white/[0.14]">
            <Bell className="h-4 w-4 text-text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-text-primary">
              Enable push notifications
            </p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              Get notified about tasks, daily summaries, and more even when you&apos;re
              not using Omi
            </p>
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={handleRequestPermission}
                disabled={isLoading || isRequesting}
                className={cn(
                  'rounded-lg px-3 py-1.5 text-sm font-medium',
                  'bg-text-primary text-bg-primary',
                  'transition-colors hover:bg-text-primary/90',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                {isRequesting ? 'Enabling...' : 'Enable notifications'}
              </button>
              <button
                onClick={() => setIsDismissed(true)}
                className="rounded-lg px-3 py-1.5 text-sm text-text-tertiary transition-colors hover:text-text-secondary"
              >
                Not now
              </button>
            </div>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="rounded-md p-1 transition-colors hover:bg-bg-tertiary"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4 text-text-quaternary" />
          </button>
        </div>
      </div>
    );
  }

  // Permission denied - show instructions
  if (permission === 'denied') {
    return (
      <div className="border-b border-warning/20 bg-warning/10 px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-warning/20">
            <AlertTriangle className="h-4 w-4 text-warning" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-text-primary">
              Notifications are blocked
            </p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              To enable notifications, you&apos;ll need to update your browser settings:
            </p>
            <ol className="mt-2 list-inside list-decimal space-y-1 text-xs text-text-tertiary">
              <li>Click the lock icon in your browser address bar</li>
              <li>Find &quot;Notifications&quot; and set to &quot;Allow&quot;</li>
              <li>Refresh this page</li>
            </ol>
            <a
              href="https://support.google.com/chrome/answer/3220216"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                'mt-2 inline-flex items-center gap-1',
                'text-xs text-text-primary hover:text-text-secondary',
                'transition-colors',
              )}
            >
              Learn more
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="rounded-md p-1 transition-colors hover:bg-bg-tertiary"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4 text-text-quaternary" />
          </button>
        </div>
      </div>
    );
  }

  return null;
}
