'use client';

import { useState } from 'react';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import { Star, Download, Loader2, Check, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { enableApp, disableApp } from '@/lib/api';
import type { App } from '@/types/apps';

interface AppCardProps {
  app: App;
  onUpdate?: () => void;
}

export function AppCard({ app, onUpdate }: AppCardProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isEnabled, setIsEnabled] = useState(app.enabled);

  const handleToggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    setIsLoading(true);
    try {
      if (isEnabled) {
        await disableApp(app.id);
        setIsEnabled(false);
      } else {
        await enableApp(app.id);
        setIsEnabled(true);
      }
      onUpdate?.();
    } catch (err) {
      console.error('Failed to toggle app:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const formatInstalls = (count?: number): string => {
    if (!count) return '0';
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
    return count.toString();
  };

  return (
    <Link
      href={`/connectors/${app.id}`}
      className={cn(
        'noise-overlay block rounded-xl p-4',
        'border border-white/[0.06] bg-white/[0.02]',
        'hover:border-white/30 hover:bg-white/[0.05]',
        'group transition-all',
      )}
    >
      <div className="flex gap-3">
        {/* App icon */}
        <div className="h-14 w-14 flex-shrink-0 overflow-hidden rounded-xl bg-bg-tertiary">
          {app.image ? (
            <Image
              src={app.image}
              alt={app.name}
              width={56}
              height={56}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-xl font-medium text-text-tertiary">
              {app.name.charAt(0)}
            </div>
          )}
        </div>

        {/* App info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="flex items-center gap-1 truncate font-medium text-text-primary">
                {app.name}
                {app.private && <Lock className="h-3 w-3 text-text-quaternary" />}
              </h3>
              <p className="truncate text-sm text-text-tertiary">
                {app.author || 'Unknown'}
              </p>
            </div>

            {/* Action button */}
            <button
              onClick={handleToggle}
              disabled={isLoading}
              className={cn(
                'flex-shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium',
                'transition-colors',
                isEnabled
                  ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                  : 'bg-white text-black hover:bg-white/90',
                'disabled:opacity-50',
              )}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isEnabled ? (
                <span className="flex items-center gap-1">
                  <Check className="h-3 w-3" />
                  Installed
                </span>
              ) : (
                'Install'
              )}
            </button>
          </div>

          {/* Description */}
          <p className="mt-1 line-clamp-2 text-sm text-text-quaternary">
            {app.description}
          </p>

          {/* Stats */}
          <div className="mt-2 flex items-center gap-3 text-xs text-text-tertiary">
            {app.rating_avg !== undefined && app.rating_avg > 0 && (
              <span className="flex items-center gap-1">
                <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
                {app.rating_avg.toFixed(1)}
                {app.rating_count ? ` (${app.rating_count})` : ''}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Download className="h-3 w-3" />
              {formatInstalls(app.installs)}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
