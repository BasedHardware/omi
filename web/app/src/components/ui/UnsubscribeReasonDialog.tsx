'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useState } from 'react';

export const UNSUBSCRIBE_REASONS = [
  { id: 'too_expensive', label: "It's too expensive" },
  { id: 'not_using', label: "I'm not using it enough" },
  { id: 'missing_features', label: 'Missing features I need' },
  { id: 'found_alternative', label: 'Found a better alternative' },
  { id: 'temporary', label: 'Just need a break' },
  { id: 'other', label: 'Other' },
] as const;

export type UnsubscribeReasonId = (typeof UNSUBSCRIBE_REASONS)[number]['id'];

interface UnsubscribeReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (reason: UnsubscribeReasonId, details?: string) => void;
  isLoading?: boolean;
}

export function UnsubscribeReasonDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: UnsubscribeReasonDialogProps) {
  const [selectedReason, setSelectedReason] = useState<UnsubscribeReasonId | null>(null);
  const [details, setDetails] = useState('');

  const handleSubmit = () => {
    if (!selectedReason) return;
    onSubmit(selectedReason, details.trim() || undefined);
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      // Reset state when dialog closes
      setSelectedReason(null);
      setDetails('');
    }
    onOpenChange(open);
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
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
                  'w-[90vw] max-w-[440px]',
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

                {/* Title */}
                <Dialog.Title className="text-lg font-semibold text-text-primary mb-1 pr-6">
                  Help us improve
                </Dialog.Title>
                <Dialog.Description className="text-sm text-text-tertiary mb-5">
                  You're about to cancel your subscription. Would you mind sharing why?
                </Dialog.Description>

                {/* Reason options */}
                <div className="space-y-2 mb-4">
                  {UNSUBSCRIBE_REASONS.map((reason) => (
                    <button
                      key={reason.id}
                      onClick={() => setSelectedReason(reason.id)}
                      className={cn(
                        'w-full px-4 py-3 rounded-xl text-left text-sm transition-all',
                        'border-2',
                        selectedReason === reason.id
                          ? 'border-purple-primary bg-purple-primary/5 text-text-primary'
                          : 'border-bg-tertiary bg-bg-tertiary/50 text-text-secondary hover:border-bg-quaternary hover:text-text-primary'
                      )}
                    >
                      {reason.label}
                    </button>
                  ))}
                </div>

                {/* Optional details */}
                <div className="mb-5">
                  <label className="flex items-center gap-1.5 text-xs text-text-quaternary mb-2">
                    <MessageSquare className="w-3.5 h-3.5" />
                    More details (optional)
                  </label>
                  <textarea
                    value={details}
                    onChange={(e) => setDetails(e.target.value)}
                    placeholder="Anything else you'd like to share..."
                    rows={3}
                    className={cn(
                      'w-full px-3 py-2.5 rounded-xl text-sm',
                      'bg-bg-tertiary/50 border border-bg-tertiary',
                      'text-text-primary placeholder:text-text-quaternary',
                      'focus:outline-none focus:border-purple-primary resize-none'
                    )}
                  />
                </div>

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
                      Skip
                    </button>
                  </Dialog.Close>
                  <button
                    onClick={handleSubmit}
                    disabled={!selectedReason || isLoading}
                    className={cn(
                      'flex-1 px-4 py-2.5 rounded-xl',
                      'bg-error hover:bg-error/90',
                      'text-white text-sm font-medium',
                      'transition-colors',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        <span>Canceling...</span>
                      </span>
                    ) : (
                      'Cancel Subscription'
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
