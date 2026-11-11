'use client';

import { useCallback, useEffect } from 'react';
import Image from '@tschk/moonshine-next/image';
import { ChevronLeft, ChevronRight, Loader2, Trash2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { stepFrameIndex } from '@/lib/screenFrames';
import type { ConversationScreenFrame } from '@/types/conversation';

interface ScreenFrameLightboxProps {
  open: boolean;
  frames: ConversationScreenFrame[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  /** Asks the parent to confirm-and-delete this frame; this component never deletes directly. */
  onRequestDeleteFrame: (frameId: string) => void;
  deletingFrameId?: string | null;
  className?: string;
}

/**
 * Full-size screenshot view. Left/right arrow keys step through the strip
 * with wraparound; Escape closes (Radix Dialog's default behaviour, since
 * this is built on `ui/dialog.tsx`). Delete is available from inside it, but
 * only *requests* deletion — the caller owns confirmation (see
 * `ConversationDetailPanel`).
 */
export function ScreenFrameLightbox({
  open,
  frames,
  index,
  onIndexChange,
  onClose,
  onRequestDeleteFrame,
  deletingFrameId = null,
  className,
}: ScreenFrameLightboxProps) {
  const frame = frames[index] ?? null;
  const canStep = frames.length > 1;

  const goTo = useCallback(
    (delta: 1 | -1) => {
      onIndexChange(stepFrameIndex(index, frames.length, delta));
    },
    [index, frames.length, onIndexChange],
  );

  useEffect(() => {
    if (!open || !canStep) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        goTo(-1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        goTo(1);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, canStep, goTo]);

  if (!open || !frame) return null;

  const isDeleting = deletingFrameId === frame.id;

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogPortal>
        <DialogOverlay />
        <DialogContent
          className={cn(
            'w-[92vw] max-w-5xl border-none bg-transparent p-0 shadow-none',
            className,
          )}
        >
          <DialogTitle className="sr-only">{frame.caption || 'Screenshot'}</DialogTitle>

          <div className="relative flex flex-col gap-3">
            <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-bg-tertiary bg-bg-primary">
              <Image
                src={frame.content_url}
                alt={frame.caption}
                fill
                className="object-contain"
              />

              {canStep && (
                <>
                  <button
                    type="button"
                    onClick={() => goTo(-1)}
                    aria-label="Previous screenshot"
                    className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 text-white transition-colors hover:bg-black/70"
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => goTo(1)}
                    aria-label="Next screenshot"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 text-white transition-colors hover:bg-black/70"
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                </>
              )}
            </div>

            <div className="flex items-center justify-between gap-3 px-1">
              <div className="min-w-0">
                {frame.caption && (
                  <p className="truncate text-sm text-text-secondary">{frame.caption}</p>
                )}
                {canStep && (
                  <p className="text-xs text-text-quaternary">
                    {index + 1} / {frames.length}
                  </p>
                )}
              </div>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => onRequestDeleteFrame(frame.id)}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                {isDeleting ? 'Deleting…' : 'Delete'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogPortal>
    </Dialog>
  );
}
