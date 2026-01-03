'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Clock, X, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BulkActionBarProps {
  selectedCount: number;
  onComplete: () => void;
  onDelete: () => void;
  onSnooze: (days: number) => void;
  onClear: () => void;
}

export function BulkActionBar({
  selectedCount,
  onComplete,
  onDelete,
  onSnooze,
  onClear,
}: BulkActionBarProps) {
  const [showSnoozeMenu, setShowSnoozeMenu] = useState(false);

  if (selectedCount === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={cn(
          'fixed bottom-4 left-1/2 -translate-x-1/2',
          'bg-bg-secondary border border-bg-tertiary',
          'rounded-xl shadow-lg shadow-black/30',
          'px-4 py-3',
          'flex items-center gap-4',
          'z-50'
        )}
      >
        {/* Selection count */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary">
            {selectedCount} task{selectedCount !== 1 ? 's' : ''} selected
          </span>
          <button
            onClick={onClear}
            className="p-1 rounded hover:bg-bg-tertiary text-text-quaternary hover:text-text-secondary transition-colors"
            title="Clear selection"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Divider */}
        <div className="w-px h-6 bg-bg-tertiary" />

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Snooze dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowSnoozeMenu(!showSnoozeMenu)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'text-text-secondary text-sm',
                'transition-colors'
              )}
            >
              <Clock className="w-4 h-4" />
              <span>Snooze</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {/* Dropdown menu */}
            <AnimatePresence>
              {showSnoozeMenu && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    'absolute bottom-full mb-2 left-0',
                    'bg-bg-secondary border border-bg-tertiary rounded-lg',
                    'shadow-lg shadow-black/20',
                    'py-1 min-w-[120px]'
                  )}
                >
                  <button
                    onClick={() => {
                      onSnooze(0);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Today
                  </button>
                  <button
                    onClick={() => {
                      onSnooze(1);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Tomorrow
                  </button>
                  <button
                    onClick={() => {
                      onSnooze(7);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Next week
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Complete button */}
          <button
            onClick={onComplete}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-success/20 hover:bg-success/30',
              'text-success text-sm',
              'transition-colors'
            )}
          >
            <Check className="w-4 h-4" />
            <span>Complete</span>
          </button>

          {/* Delete button */}
          <button
            onClick={onDelete}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-error/20 hover:bg-error/30',
              'text-error text-sm',
              'transition-colors'
            )}
          >
            <Trash2 className="w-4 h-4" />
            <span>Delete</span>
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
