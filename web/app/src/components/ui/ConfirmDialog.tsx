'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence } from 'framer-motion';
import { X, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'default';
  onConfirm: () => void;
  isLoading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  isLoading = false,
}: ConfirmDialogProps) {
  const handleConfirm = () => {
    onConfirm();
    if (!isLoading) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="fixed inset-0 bg-black/50 z-[100]"
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15, ease: 'easeOut' }}
                className={cn(
                  'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[101]',
                  'w-[90vw] max-w-[400px]',
                  'bg-bg-secondary rounded-2xl',
                  'border border-bg-tertiary',
                  'shadow-2xl',
                  'p-6',
                  'focus:outline-none'
                )}
              >
                {/* Close button */}
                <Dialog.Close asChild>
                  <button
                    className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-bg-tertiary transition-colors"
                    aria-label="Close"
                  >
                    <X className="w-4 h-4 text-text-quaternary" />
                  </button>
                </Dialog.Close>

                {/* Icon */}
                <div
                  className={cn(
                    'w-12 h-12 rounded-full flex items-center justify-center mb-4',
                    variant === 'danger'
                      ? 'bg-error/10'
                      : 'bg-purple-primary/10'
                  )}
                >
                  <AlertTriangle
                    className={cn(
                      'w-6 h-6',
                      variant === 'danger' ? 'text-error' : 'text-purple-primary'
                    )}
                  />
                </div>

                {/* Title */}
                <Dialog.Title className="text-lg font-semibold text-text-primary mb-2">
                  {title}
                </Dialog.Title>

                {/* Description */}
                <Dialog.Description className="text-sm text-text-tertiary mb-6">
                  {description}
                </Dialog.Description>

                {/* Actions */}
                <div className="flex gap-3">
                  <Dialog.Close asChild>
                    <button
                      className={cn(
                        'flex-1 px-4 py-2.5 rounded-xl',
                        'bg-bg-tertiary hover:bg-bg-quaternary',
                        'text-text-secondary text-sm font-medium',
                        'transition-colors'
                      )}
                    >
                      {cancelLabel}
                    </button>
                  </Dialog.Close>
                  <button
                    onClick={handleConfirm}
                    disabled={isLoading}
                    className={cn(
                      'flex-1 px-4 py-2.5 rounded-xl',
                      'text-white text-sm font-medium',
                      'transition-colors',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      variant === 'danger'
                        ? 'bg-error hover:bg-error/90'
                        : 'bg-purple-primary hover:bg-purple-secondary'
                    )}
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        <span>Clearing...</span>
                      </span>
                    ) : (
                      confirmLabel
                    )}
                  </button>
                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
