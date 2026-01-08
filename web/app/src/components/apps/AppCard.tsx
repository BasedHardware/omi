'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
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
      href={`/apps/${app.id}`}
      className={cn(
        'noise-overlay block p-4 rounded-xl',
        'bg-white/[0.02] border border-white/[0.06]',
        'hover:bg-white/[0.05] hover:border-purple-primary/30',
        'transition-all group'
      )}
    >
      <div className="flex gap-3">
        {/* App icon */}
        <div className="flex-shrink-0 w-14 h-14 rounded-xl overflow-hidden bg-bg-tertiary">
          {app.image ? (
            <Image
              src={app.image}
              alt={app.name}
              width={56}
              height={56}
              className="object-cover w-full h-full"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-text-tertiary text-xl font-medium">
              {app.name.charAt(0)}
            </div>
          )}
        </div>

        {/* App info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-medium text-text-primary truncate flex items-center gap-1">
                {app.name}
                {app.private && <Lock className="w-3 h-3 text-text-quaternary" />}
              </h3>
              <p className="text-sm text-text-tertiary truncate">
                {app.author || 'Unknown'}
              </p>
            </div>

            {/* Action button */}
            <button
              onClick={handleToggle}
              disabled={isLoading}
              className={cn(
                'px-3 py-1.5 rounded-lg text-sm font-medium flex-shrink-0',
                'transition-colors',
                isEnabled
                  ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                  : 'bg-purple-primary text-white hover:bg-purple-secondary',
                'disabled:opacity-50'
              )}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : isEnabled ? (
                <span className="flex items-center gap-1">
                  <Check className="w-3 h-3" />
                  Installed
                </span>
              ) : (
                'Install'
              )}
            </button>
          </div>

          {/* Description */}
          <p className="text-sm text-text-quaternary mt-1 line-clamp-2">
            {app.description}
          </p>

          {/* Stats */}
          <div className="flex items-center gap-3 mt-2 text-xs text-text-tertiary">
            {app.rating_avg !== undefined && app.rating_avg > 0 && (
              <span className="flex items-center gap-1">
                <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                {app.rating_avg.toFixed(1)}
                {app.rating_count ? ` (${app.rating_count})` : ''}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Download className="w-3 h-3" />
              {formatInstalls(app.installs)}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
