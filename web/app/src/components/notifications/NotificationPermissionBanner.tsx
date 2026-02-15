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
      <div className="px-4 py-3 bg-purple-primary/10 border-b border-purple-primary/20">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
            <Bell className="w-4 h-4 text-purple-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary">
              Enable push notifications
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Get notified about tasks, daily summaries, and more even when
              you&apos;re not using Omi
            </p>
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={handleRequestPermission}
                disabled={isLoading || isRequesting}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium',
                  'bg-purple-primary text-white',
                  'hover:bg-purple-secondary transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {isRequesting ? 'Enabling...' : 'Enable notifications'}
              </button>
              <button
                onClick={() => setIsDismissed(true)}
                className="px-3 py-1.5 rounded-lg text-sm text-text-tertiary hover:text-text-secondary transition-colors"
              >
                Not now
              </button>
            </div>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4 text-text-quaternary" />
          </button>
        </div>
      </div>
    );
  }

  // Permission denied - show instructions
  if (permission === 'denied') {
    return (
      <div className="px-4 py-3 bg-warning/10 border-b border-warning/20">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-warning/20 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4 h-4 text-warning" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary">
              Notifications are blocked
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              To enable notifications, you&apos;ll need to update your browser
              settings:
            </p>
            <ol className="text-xs text-text-tertiary mt-2 space-y-1 list-decimal list-inside">
              <li>Click the lock icon in your browser address bar</li>
              <li>Find &quot;Notifications&quot; and set to &quot;Allow&quot;</li>
              <li>Refresh this page</li>
            </ol>
            <a
              href="https://support.google.com/chrome/answer/3220216"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                'inline-flex items-center gap-1 mt-2',
                'text-xs text-purple-primary hover:text-purple-secondary',
                'transition-colors'
              )}
            >
              Learn more
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4 text-text-quaternary" />
          </button>
        </div>
      </div>
    );
  }

  return null;
}
