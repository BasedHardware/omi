'use client';

import { useState } from 'react';
import { Bell, AlertTriangle, X, ExternalLink } from 'lucide-react';
import { useNotificationContext } from './NotificationContext';
import { cn } from '@/lib/utils';
import { t } from '@/lib/i18n';

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
      <div className="px-4 py-3 bg-white/[0.08] border-b border-white/25">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-white/[0.14] flex items-center justify-center flex-shrink-0">
            <Bell className="w-4 h-4 text-text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary">
              {t('Enable push notifications')}
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              {t('Get notified about tasks, daily summaries, and more even when you\'re not using Omi')}
            </p>
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={handleRequestPermission}
                disabled={isLoading || isRequesting}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium',
                  'bg-text-primary text-bg-primary',
                  'hover:bg-text-primary/90 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {isRequesting ? t('Enabling...') : t('Enable notifications')}
              </button>
              <button
                onClick={() => setIsDismissed(true)}
                className="px-3 py-1.5 rounded-lg text-sm text-text-tertiary hover:text-text-secondary transition-colors"
              >
                {t('Not now')}
              </button>
            </div>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
            aria-label={t('Dismiss')}
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
              {t('Notifications are blocked')}
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              {t('To enable notifications, you\'ll need to update your browser settings:')}
            </p>
            <ol className="text-xs text-text-tertiary mt-2 space-y-1 list-decimal list-inside">
              <li>{t('Click the lock icon in your browser address bar')}</li>
              <li>{t('Find "Notifications" and set to "Allow"')}</li>
              <li>{t('Refresh this page')}</li>
            </ol>
            <a
              href="https://support.google.com/chrome/answer/3220216"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                'inline-flex items-center gap-1 mt-2',
                'text-xs text-text-primary hover:text-text-secondary',
                'transition-colors',
              )}
            >
              {t('Learn more')}<ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <button
            onClick={() => setIsDismissed(true)}
            className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
            aria-label={t('Dismiss')}
          >
            <X className="w-4 h-4 text-text-quaternary" />
          </button>
        </div>
      </div>
    );
  }

  return null;
}
