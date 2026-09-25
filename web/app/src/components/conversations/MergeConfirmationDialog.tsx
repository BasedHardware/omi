'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Merge, X, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Conversation } from '@/types/conversation';

interface MergeConfirmationDialogProps {
  isOpen: boolean;
  conversations: Conversation[];
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

/**
 * Detect time gaps between conversations
 * Returns a warning message if gaps > 1 hour are found
 */
function detectTimeGaps(conversations: Conversation[]): string | null {
  if (conversations.length < 2) return null;

  // Sort by started_at
  const sorted = [...conversations].sort((a, b) => {
    const aTime = new Date(a.started_at || a.created_at).getTime();
    const bTime = new Date(b.started_at || b.created_at).getTime();
    return aTime - bTime;
  });

  const oneHour = 60 * 60 * 1000; // 1 hour in ms
  let maxGapHours = 0;

  for (let i = 1; i < sorted.length; i++) {
    const prevEnd = sorted[i - 1].finished_at
      ? new Date(sorted[i - 1].finished_at!).getTime()
      : new Date(sorted[i - 1].started_at || sorted[i - 1].created_at).getTime();
    const currStart = new Date(sorted[i].started_at || sorted[i].created_at).getTime();
    const gap = currStart - prevEnd;

    if (gap > oneHour) {
      const gapHours = Math.round(gap / oneHour);
      maxGapHours = Math.max(maxGapHours, gapHours);
    }
  }

  if (maxGapHours > 0) {
    return `These conversations have gaps of up to ${maxGapHours} hour${
      maxGapHours > 1 ? 's' : ''
    } between them.`;
  }

  return null;
}

export function MergeConfirmationDialog({
  isOpen,
  conversations,
  onConfirm,
  onCancel,
  isLoading = false,
}: MergeConfirmationDialogProps) {
  const timeGapWarning = detectTimeGaps(conversations);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
              'w-full max-w-md rounded-2xl p-6',
              'border border-bg-tertiary bg-bg-secondary',
              'shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
            )}
          >
            {/* Close button */}
            <button
              onClick={onCancel}
              disabled={isLoading}
              className={cn(
                'absolute right-4 top-4 rounded-lg p-2',
                'text-text-quaternary hover:text-text-primary',
                'transition-colors hover:bg-bg-tertiary',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              <X className="h-4 w-4" />
            </button>

            {/* Icon */}
            <div
              className={cn(
                'mb-4 h-12 w-12 rounded-xl',
                'flex items-center justify-center bg-white/[0.14]',
              )}
            >
              <Merge className="h-6 w-6 text-text-primary" />
            </div>

            {/* Title */}
            <h2 className="mb-2 text-lg font-semibold text-text-primary">
              Merge {conversations.length} conversations?
            </h2>

            {/* Description */}
            <p className="mb-4 text-sm text-text-secondary">
              The selected conversations will be combined into a single conversation. This
              action is processed in the background.
            </p>

            {/* Time gap warning */}
            {timeGapWarning && (
              <div
                className={cn(
                  'mb-4 flex items-start gap-3 rounded-xl p-3',
                  'border border-warning/20 bg-warning/10',
                )}
              >
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-warning" />
                <p className="text-sm text-warning">{timeGapWarning}</p>
              </div>
            )}

            {/* Conversation list preview */}
            <div className="mb-6 max-h-40 space-y-2 overflow-y-auto">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-3 py-2',
                    'bg-bg-tertiary',
                  )}
                >
                  <span className="text-lg">{conv.structured.emoji || '💬'}</span>
                  <span className="flex-1 truncate text-sm text-text-primary">
                    {conv.structured.title || 'Untitled'}
                  </span>
                </div>
              ))}
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onCancel}
                disabled={isLoading}
                className={cn(
                  'flex-1 rounded-xl px-4 py-2.5',
                  'text-sm font-medium text-text-secondary',
                  'bg-bg-tertiary hover:bg-bg-quaternary',
                  'transition-colors duration-150',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2',
                  'rounded-xl px-4 py-2.5',
                  'text-sm font-medium text-bg-primary',
                  'bg-text-primary hover:bg-text-primary/90',
                  'transition-colors duration-150',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Merge className="h-4 w-4" />
                )}
                <span>{isLoading ? 'Merging...' : 'Merge'}</span>
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
