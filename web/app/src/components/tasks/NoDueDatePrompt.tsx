'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Calendar, AlertCircle, ChevronRight, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

interface NoDueDatePromptProps {
  items: ActionItem[];
  onSetAllToday: () => void;
  onSetAllTomorrow: () => void;
  onSetAllToDate: (date: Date) => void;
  onShowItems: () => void;
}

export function NoDueDatePrompt({
  items,
  onSetAllToday,
  onSetAllTomorrow,
  onSetAllToDate,
  onShowItems,
}: NoDueDatePromptProps) {
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const count = items.length;

  if (count === 0 || dismissed) {
    return null;
  }

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.value) {
      const date = new Date(e.target.value + 'T12:00:00');
      onSetAllToDate(date);
      setShowDatePicker(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'relative bg-gradient-to-br from-amber-500/10 to-orange-500/10',
        'overflow-hidden rounded-xl border border-amber-500/20 p-4',
      )}
    >
      {/* Dismiss button */}
      <button
        onClick={() => setDismissed(true)}
        className="absolute right-2 top-2 rounded p-1 text-text-quaternary transition-colors hover:bg-white/10 hover:text-text-secondary"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>

      {/* Header */}
      <div className="mb-3 flex items-start gap-3 pr-6">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-amber-500/20">
          <AlertCircle className="h-4 w-4 text-amber-500" />
        </div>
        <div>
          <h3 className="text-sm font-medium text-text-primary">
            {count} task{count !== 1 ? 's' : ''} need{count === 1 ? 's' : ''} a date
          </h3>
          <p className="mt-0.5 text-xs text-text-tertiary">
            Set due dates to stay organized
          </p>
        </div>
      </div>

      {/* Quick actions */}
      <div className="mb-3 flex flex-wrap gap-2">
        <button
          onClick={onSetAllToday}
          className={cn(
            'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium',
            'bg-white/20 text-white',
            'transition-colors hover:bg-white/30',
          )}
        >
          <Calendar className="h-3.5 w-3.5" />
          Set all to Today
        </button>
        <button
          onClick={onSetAllTomorrow}
          className={cn(
            'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium',
            'bg-bg-tertiary text-text-secondary',
            'transition-colors hover:bg-bg-quaternary',
          )}
        >
          Tomorrow
        </button>
        <div className="relative">
          <button
            onClick={() => setShowDatePicker(!showDatePicker)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium',
              'bg-bg-tertiary text-text-secondary',
              'transition-colors hover:bg-bg-quaternary',
            )}
          >
            Pick date...
          </button>

          <AnimatePresence>
            {showDatePicker && (
              <motion.div
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                className={cn(
                  'absolute left-0 top-full z-50 mt-1',
                  'rounded-lg border border-bg-tertiary bg-bg-secondary',
                  'p-2 shadow-lg shadow-black/30',
                )}
              >
                <input
                  type="date"
                  onChange={handleDateChange}
                  className={cn(
                    'rounded border border-bg-quaternary bg-bg-tertiary px-2 py-1',
                    'text-xs text-text-primary outline-none',
                    'focus:border-white',
                  )}
                  autoFocus
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* View items link */}
      <button
        onClick={onShowItems}
        className={cn(
          'flex items-center gap-1 text-xs text-text-tertiary',
          'transition-colors hover:text-white',
        )}
      >
        View these tasks
        <ChevronRight className="h-3 w-3" />
      </button>

      {/* Task previews */}
      {items.length > 0 && (
        <div className="mt-3 border-t border-white/5 pt-3">
          <div className="space-y-1">
            {items.slice(0, 3).map((item) => (
              <div
                key={item.id}
                className="border-l-2 border-amber-500/30 pl-2 text-xs text-text-quaternary"
              >
                {item.description}
              </div>
            ))}
            {items.length > 3 && (
              <div className="pl-2 text-xs text-text-quaternary">
                +{items.length - 3} more
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
