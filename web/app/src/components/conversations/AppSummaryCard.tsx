'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getApp } from '@/lib/api';
import type { AppResponse } from '@/types/conversation';
import type { App } from '@/types/apps';

interface AppSummaryCardProps {
  appResponse: AppResponse;
  className?: string;
}

export function AppSummaryCard({ appResponse, className }: AppSummaryCardProps) {
  const [app, setApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAppInfo() {
      if (!appResponse.app_id) {
        setLoading(false);
        return;
      }

      try {
        const appInfo = await getApp(appResponse.app_id);
        setApp(appInfo);
      } catch (error) {
        console.error('Failed to fetch app info:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchAppInfo();
  }, [appResponse.app_id]);

  if (!appResponse.content) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'p-4 rounded-xl',
        'bg-bg-tertiary border border-bg-quaternary/50',
        className
      )}
    >
      {/* App Header */}
      <div className="flex items-center gap-3 mb-3">
        {loading ? (
          <div className="w-8 h-8 rounded-lg bg-bg-quaternary animate-pulse" />
        ) : app?.image ? (
          <img
            src={app.image}
            alt={app.name}
            className="w-8 h-8 rounded-lg object-cover"
          />
        ) : (
          <div className="w-8 h-8 rounded-lg bg-purple-primary/20 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-purple-primary" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-text-primary truncate">
            {loading ? (
              <span className="text-text-tertiary">Loading...</span>
            ) : (
              app?.name || 'App Summary'
            )}
          </h4>
          {app?.description && (
            <p className="text-xs text-text-tertiary truncate">
              {app.description}
            </p>
          )}
        </div>
      </div>

      {/* Summary Content */}
      <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
        {appResponse.content}
      </p>
    </motion.div>
  );
}

/**
 * Loading skeleton for AppSummaryCard
 */
export function AppSummaryCardSkeleton() {
  return (
    <div className="p-4 rounded-xl bg-bg-tertiary border border-bg-quaternary/50 animate-pulse">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-bg-quaternary" />
        <div className="flex-1">
          <div className="h-4 w-24 bg-bg-quaternary rounded" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full bg-bg-quaternary rounded" />
        <div className="h-3 w-5/6 bg-bg-quaternary rounded" />
        <div className="h-3 w-4/6 bg-bg-quaternary rounded" />
      </div>
    </div>
  );
}
