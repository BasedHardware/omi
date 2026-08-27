'use client';

import Image from '@tschk/moonshine-next/image';
import { Image as ImageIcon, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ConversationScreenFrame } from '@/types/conversation';

interface ConversationScreenFrameCarouselProps {
  frames: ConversationScreenFrame[];
  onFrameClick: (index: number) => void;
  /** Asks the parent to confirm-and-delete one frame; this component never deletes directly. */
  onRequestDeleteFrame: (frameId: string) => void;
  /** Asks the parent to confirm-and-delete every frame. Omit to hide the affordance. */
  onRequestDeleteAll?: () => void;
  deletingFrameId?: string | null;
  className?: string;
}

/**
 * Horizontal strip of screenshot thumbnails. Hover reveals a delete `X` on
 * each thumbnail, modeled on the same affordance in `chat/FilePreview.tsx`.
 * Renders nothing when there are no frames — no empty state (contract §9).
 */
export function ConversationScreenFrameCarousel({
  frames,
  onFrameClick,
  onRequestDeleteFrame,
  onRequestDeleteAll,
  deletingFrameId = null,
  className,
}: ConversationScreenFrameCarouselProps) {
  if (frames.length === 0) return null;

  return (
    <div className={cn('border-t border-bg-tertiary pt-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ImageIcon className="h-4 w-4 text-text-primary" />
          <h3 className="text-sm font-medium text-text-primary">Screenshots</h3>
          <span className="text-xs text-text-quaternary">{frames.length}</span>
        </div>
        {onRequestDeleteAll && (
          <button
            type="button"
            onClick={onRequestDeleteAll}
            className="text-xs text-text-quaternary transition-colors hover:text-error"
          >
            Clear all
          </button>
        )}
      </div>

      <div className="flex gap-3 overflow-x-auto pb-1">
        {frames.map((frame, index) => {
          const isDeleting = deletingFrameId === frame.id;
          return (
            <div
              key={frame.id}
              className={cn(
                'group relative aspect-video w-32 flex-shrink-0 overflow-hidden rounded-lg',
                'border border-bg-quaternary bg-bg-tertiary',
              )}
            >
              <button
                type="button"
                onClick={() => onFrameClick(index)}
                className="absolute inset-0"
                aria-label={frame.caption || `Screenshot ${index + 1}`}
              >
                <Image
                  src={frame.thumbnail_url}
                  alt={frame.caption}
                  fill
                  className="object-cover"
                />
              </button>

              {isDeleting ? (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                  <Loader2 className="h-5 w-5 animate-spin text-white" />
                </div>
              ) : (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onRequestDeleteFrame(frame.id);
                  }}
                  aria-label="Delete screenshot"
                  className={cn(
                    'absolute -right-1 -top-1 h-5 w-5 rounded-full',
                    'border border-bg-tertiary bg-bg-primary',
                    'flex items-center justify-center',
                    'opacity-0 transition-opacity group-hover:opacity-100',
                    'hover:border-error hover:bg-error hover:text-white',
                  )}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
