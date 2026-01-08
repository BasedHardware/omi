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
        'border border-amber-500/20 rounded-xl p-4 overflow-hidden'
      )}
    >
      {/* Dismiss button */}
      <button
        onClick={() => setDismissed(true)}
        className="absolute top-2 right-2 p-1 rounded text-text-quaternary hover:text-text-secondary hover:bg-white/10 transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>

      {/* Header */}
      <div className="flex items-start gap-3 mb-3 pr-6">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center">
          <AlertCircle className="w-4 h-4 text-amber-500" />
        </div>
        <div>
          <h3 className="text-sm font-medium text-text-primary">
            {count} task{count !== 1 ? 's' : ''} need{count === 1 ? 's' : ''} a date
          </h3>
          <p className="text-xs text-text-tertiary mt-0.5">
            Set due dates to stay organized
          </p>
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2 mb-3">
        <button
          onClick={onSetAllToday}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
            'bg-purple-primary/20 text-purple-primary',
            'hover:bg-purple-primary/30 transition-colors'
          )}
        >
          <Calendar className="w-3.5 h-3.5" />
          Set all to Today
        </button>
        <button
          onClick={onSetAllTomorrow}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-bg-quaternary transition-colors'
          )}
        >
          Tomorrow
        </button>
        <div className="relative">
          <button
            onClick={() => setShowDatePicker(!showDatePicker)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
              'bg-bg-tertiary text-text-secondary',
              'hover:bg-bg-quaternary transition-colors'
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
                  'absolute top-full left-0 mt-1 z-50',
                  'bg-bg-secondary border border-bg-tertiary rounded-lg',
                  'shadow-lg shadow-black/30 p-2'
                )}
              >
                <input
                  type="date"
                  onChange={handleDateChange}
                  className={cn(
                    'bg-bg-tertiary border border-bg-quaternary rounded px-2 py-1',
                    'text-xs text-text-primary outline-none',
                    'focus:border-purple-primary'
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
          'hover:text-purple-primary transition-colors'
        )}
      >
        View these tasks
        <ChevronRight className="w-3 h-3" />
      </button>

      {/* Task previews */}
      {items.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/5">
          <div className="space-y-1">
            {items.slice(0, 3).map(item => (
              <div
                key={item.id}
                className="text-xs text-text-quaternary truncate pl-2 border-l-2 border-amber-500/30"
              >
                {item.description}
              </div>
            ))}
            {items.length > 3 && (
              <div className="text-xs text-text-quaternary pl-2">
                +{items.length - 3} more
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
