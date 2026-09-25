'use client';

import { useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DeleteConversationsDialogProps {
  isOpen: boolean;
  count: number;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  isLoading?: boolean;
}

export function DeleteConversationsDialog({
  isOpen,
  count,
  onClose,
  onConfirm,
  isLoading = false,
}: DeleteConversationsDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) {
        onClose();
      }
    },
    [onClose, isLoading],
  );

  // Focus trap and escape key handler
  useEffect(() => {
    if (!isOpen) return;

    // Focus the cancel button when dialog opens
    cancelButtonRef.current?.focus();

    // Add escape key listener
    document.addEventListener('keydown', handleKeyDown);

    // Trap focus within dialog
    const dialog = dialogRef.current;
    const focusableElements = dialog?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const firstElement = focusableElements?.[0];
    const lastElement = focusableElements?.[focusableElements.length - 1];

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    document.addEventListener('keydown', handleTabKey);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keydown', handleTabKey);
    };
  }, [isOpen, handleKeyDown]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          aria-describedby="delete-dialog-description"
        >
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={!isLoading ? onClose : undefined}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />

          {/* Dialog */}
          <motion.div
            ref={dialogRef}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'relative z-10',
              'mx-4 w-full max-w-sm rounded-2xl p-6',
              'border border-bg-tertiary bg-bg-secondary',
              'shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
            )}
          >
            {/* Icon */}
            <div
              className={cn(
                'mb-4 h-12 w-12 rounded-xl',
                'flex items-center justify-center bg-error/20',
              )}
            >
              <Trash2 className="h-6 w-6 text-error" />
            </div>

            {/* Title */}
            <h2
              id="delete-dialog-title"
              className="mb-2 text-lg font-semibold text-text-primary"
            >
              Delete {count} conversation{count !== 1 ? 's' : ''}?
            </h2>

            {/* Description */}
            <p
              id="delete-dialog-description"
              className="mb-6 text-sm text-text-secondary"
            >
              This will permanently delete the selected conversation
              {count !== 1 ? 's' : ''}. This action cannot be undone.
            </p>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                ref={cancelButtonRef}
                onClick={onClose}
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
                  'text-sm font-medium text-white',
                  'bg-error hover:bg-error/90',
                  'transition-colors duration-150',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                <span>{isLoading ? 'Deleting...' : 'Delete'}</span>
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
