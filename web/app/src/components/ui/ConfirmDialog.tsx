'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { X, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { OpenSurface } from '@/components/ui/OpenSurface';

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
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/50 duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[101] w-[90vw] max-w-[400px] -translate-x-1/2 -translate-y-1/2',
            'focus:outline-none',
            'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          )}
        >
          <OpenSurface
            className={cn(
              't-modal relative',
              'rounded-2xl bg-bg-secondary',
              'border border-bg-tertiary',
              'shadow-2xl',
              'p-6',
            )}
          >
            {/* Close button */}
            <Dialog.Close asChild>
              <button
                className="absolute right-4 top-4 rounded-lg p-1.5 transition-colors hover:bg-bg-tertiary"
                aria-label="Close"
              >
                <X className="h-4 w-4 text-text-quaternary" />
              </button>
            </Dialog.Close>

            {/* Icon */}
            <div
              className={cn(
                'mb-4 flex h-12 w-12 items-center justify-center rounded-full',
                variant === 'danger' ? 'bg-error/10' : 'bg-white/[0.08]',
              )}
            >
              <AlertTriangle
                className={cn(
                  'h-6 w-6',
                  variant === 'danger' ? 'text-error' : 'text-text-primary',
                )}
              />
            </div>

            {/* Title */}
            <Dialog.Title className="mb-2 text-lg font-semibold text-text-primary">
              {title}
            </Dialog.Title>

            {/* Description */}
            <Dialog.Description className="mb-6 text-sm text-text-tertiary">
              {description}
            </Dialog.Description>

            {/* Actions */}
            <div className="flex gap-3">
              <Dialog.Close asChild>
                <button
                  className={cn(
                    'flex-1 rounded-xl px-4 py-2.5',
                    'bg-bg-tertiary hover:bg-bg-quaternary',
                    'text-sm font-medium text-text-secondary',
                    'transition-colors',
                  )}
                >
                  {cancelLabel}
                </button>
              </Dialog.Close>
              <button
                onClick={handleConfirm}
                disabled={isLoading}
                className={cn(
                  'flex-1 rounded-xl px-4 py-2.5',
                  'text-sm font-medium text-white',
                  'transition-colors',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  variant === 'danger'
                    ? 'bg-error hover:bg-error/90'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    <span>Clearing...</span>
                  </span>
                ) : (
                  confirmLabel
                )}
              </button>
            </div>
          </OpenSurface>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
