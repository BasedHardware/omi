'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Sparkles, Loader2, ChevronDown, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getApp, reprocessConversation } from '@/lib/api';
import type { App } from '@/types/apps';
import type { Conversation, AppResponse } from '@/types/conversation';

interface GenerateSummaryButtonProps {
  conversationId: string;
  suggestedAppIds: string[];
  existingAppResults: AppResponse[];
  onGenerateComplete?: (conversation: Conversation) => void;
  className?: string;
}

export function GenerateSummaryButton({
  conversationId,
  suggestedAppIds,
  existingAppResults,
  onGenerateComplete,
  className,
}: GenerateSummaryButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Filter out apps that already have summaries
  const existingAppIds = new Set(existingAppResults.map(r => r.app_id));
  const availableAppIds = suggestedAppIds.filter(id => !existingAppIds.has(id));

  // Fetch app details when dropdown opens
  useEffect(() => {
    if (!isOpen || availableAppIds.length === 0) return;

    async function fetchApps() {
      setLoading(true);
      try {
        const appPromises = availableAppIds.map(id => getApp(id).catch(() => null));
        const results = await Promise.all(appPromises);
        setApps(results.filter((app): app is App => app !== null));
      } catch (err) {
        console.error('Failed to fetch apps:', err);
      } finally {
        setLoading(false);
      }
    }

    fetchApps();
  }, [isOpen, availableAppIds.join(',')]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const handleGenerateSummary = async (appId: string) => {
    setGenerating(appId);
    setError(null);

    try {
      const updatedConversation = await reprocessConversation(conversationId, appId);
      onGenerateComplete?.(updatedConversation);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to generate summary:', err);
      setError('Failed to generate summary. Please try again.');
    } finally {
      setGenerating(null);
    }
  };

  // Don't show button if no apps available
  if (availableAppIds.length === 0) {
    return null;
  }

  return (
    <div ref={dropdownRef} className={cn('relative', className)}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={!!generating}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-lg',
          'text-sm font-medium transition-all duration-150',
          'bg-bg-tertiary hover:bg-bg-quaternary',
          'text-text-secondary hover:text-text-primary',
          'border border-bg-quaternary/50',
          generating && 'opacity-50 cursor-not-allowed'
        )}
      >
        {generating ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Plus className="w-4 h-4" />
        )}
        <span>{generating ? 'Generating...' : 'Generate with another app'}</span>
        {!generating && <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute top-full left-0 mt-2 z-50',
              'w-72 max-h-80 overflow-y-auto',
              'bg-bg-secondary border border-bg-tertiary rounded-xl',
              'shadow-lg'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b border-bg-tertiary">
              <span className="text-sm font-medium text-text-primary">Select an app</span>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-4 h-4 text-text-tertiary" />
              </button>
            </div>

            {/* Error message */}
            {error && (
              <div className="p-3 bg-error/10 border-b border-error/20 text-error text-sm">
                {error}
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="p-4 flex items-center justify-center gap-2 text-text-tertiary">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Loading apps...</span>
              </div>
            )}

            {/* Apps list */}
            {!loading && apps.length > 0 && (
              <div className="p-2">
                {apps.map((app) => (
                  <button
                    key={app.id}
                    onClick={() => handleGenerateSummary(app.id)}
                    disabled={!!generating}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg',
                      'text-left transition-all duration-150',
                      'hover:bg-bg-tertiary',
                      generating === app.id && 'bg-purple-primary/10',
                      generating && generating !== app.id && 'opacity-50'
                    )}
                  >
                    {app.image ? (
                      <img
                        src={app.image}
                        alt={app.name}
                        className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-lg bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
                        <Sparkles className="w-5 h-5 text-purple-primary" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">
                        {app.name}
                      </p>
                      {app.description && (
                        <p className="text-xs text-text-tertiary truncate">
                          {app.description}
                        </p>
                      )}
                    </div>
                    {generating === app.id && (
                      <Loader2 className="w-4 h-4 animate-spin text-purple-primary flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Empty state */}
            {!loading && apps.length === 0 && (
              <div className="p-4 text-center text-text-tertiary text-sm">
                No additional apps available
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
