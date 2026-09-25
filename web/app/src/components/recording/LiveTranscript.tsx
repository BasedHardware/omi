'use client';

import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TranscriptSegment } from './RecordingContext';

interface LiveTranscriptProps {
  segments: TranscriptSegment[];
  autoScroll?: boolean;
  maxHeight?: string;
  emptyMessage?: string;
}

// Colors for different speakers - subtle badge styles
const speakerColors = [
  { bg: 'bg-white/[0.08]', text: 'text-text-secondary', border: 'border-white/20' },
  { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
  { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/20' },
  { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
];

function getSpeakerColor(speakerId: number) {
  // Handle edge cases: negative, undefined, or NaN
  const safeId = Math.abs(speakerId || 0);
  return speakerColors[safeId % speakerColors.length];
}

function getSpeakerLabel(isUser: boolean, speakerId: number): string {
  if (isUser) return 'You';
  const safeId = Math.abs(speakerId || 0);
  return `Speaker ${safeId + 1}`;
}

export function LiveTranscript({
  segments,
  autoScroll = true,
  maxHeight = '300px',
  emptyMessage = 'Transcript will appear here as you speak...',
}: LiveTranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new segments arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [segments, autoScroll]);

  return (
    <div
      ref={scrollRef}
      className="scrollbar-thin scrollbar-thumb-bg-tertiary scrollbar-track-transparent overflow-y-auto"
      style={{ maxHeight }}
    >
      {segments.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-bg-tertiary">
            <Users className="h-6 w-6 text-text-quaternary" />
          </div>
          <p className="text-sm text-text-tertiary">{emptyMessage}</p>
        </div>
      ) : (
        <div className="space-y-3 p-1">
          <AnimatePresence mode="popLayout">
            {segments.map((segment) => {
              const colors = getSpeakerColor(segment.isUser ? 0 : segment.speaker);
              return (
                <motion.div
                  key={segment.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.2 }}
                  className="flex gap-3"
                >
                  {/* Content with speaker badge */}
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center gap-2">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium',
                          colors.bg,
                          colors.text,
                          colors.border,
                        )}
                      >
                        {segment.isUser ? <User className="h-3 w-3" /> : null}
                        {getSpeakerLabel(segment.isUser, segment.speaker)}
                      </span>
                    </div>
                    <p className="pl-0.5 text-sm leading-relaxed text-text-primary">
                      {segment.text}
                    </p>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

/**
 * Compact version for the floating widget
 */
export function LiveTranscriptCompact({
  segments,
  maxItems = 3,
}: {
  segments: TranscriptSegment[];
  maxItems?: number;
}) {
  const recentSegments = segments.slice(-maxItems);

  if (segments.length === 0) {
    return (
      <p className="py-2 text-center text-xs text-text-quaternary">
        Waiting for speech...
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <AnimatePresence mode="popLayout">
        {recentSegments.map((segment) => {
          const colors = getSpeakerColor(segment.isUser ? 0 : segment.speaker);
          return (
            <motion.div
              key={segment.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="flex items-start gap-2"
            >
              <span
                className={cn(
                  'flex-shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium',
                  colors.bg,
                  colors.text,
                  colors.border,
                )}
              >
                {segment.isUser ? 'You' : `S${segment.speaker + 1}`}
              </span>
              <p className="line-clamp-2 text-xs leading-relaxed text-text-secondary">
                {segment.text}
              </p>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {segments.length > maxItems && (
        <p className="text-center text-[10px] text-text-quaternary">
          +{segments.length - maxItems} more segments
        </p>
      )}
    </div>
  );
}
