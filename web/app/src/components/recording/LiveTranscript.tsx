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

// Colors for different speakers
const speakerColors = [
  'bg-purple-primary/20 text-purple-primary border-purple-primary/30',
  'bg-blue-500/20 text-blue-400 border-blue-500/30',
  'bg-green-500/20 text-green-400 border-green-500/30',
  'bg-orange-500/20 text-orange-400 border-orange-500/30',
  'bg-pink-500/20 text-pink-400 border-pink-500/30',
];

function getSpeakerColor(speakerId: number): string {
  return speakerColors[speakerId % speakerColors.length];
}

function getSpeakerLabel(isUser: boolean, speakerId: number): string {
  if (isUser) return 'You';
  return `Speaker ${speakerId + 1}`;
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
      className="overflow-y-auto scrollbar-thin scrollbar-thumb-bg-tertiary scrollbar-track-transparent"
      style={{ maxHeight }}
    >
      {segments.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <div className="w-12 h-12 rounded-full bg-bg-tertiary flex items-center justify-center mb-3">
            <Users className="w-6 h-6 text-text-quaternary" />
          </div>
          <p className="text-sm text-text-tertiary">{emptyMessage}</p>
        </div>
      ) : (
        <div className="space-y-3 p-1">
          <AnimatePresence mode="popLayout">
            {segments.map((segment) => (
              <motion.div
                key={segment.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="flex gap-3"
              >
                {/* Speaker indicator */}
                <div
                  className={cn(
                    'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border',
                    getSpeakerColor(segment.isUser ? 0 : segment.speaker)
                  )}
                >
                  {segment.isUser ? (
                    <User className="w-4 h-4" />
                  ) : (
                    <span className="text-xs font-medium">{segment.speaker + 1}</span>
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span
                      className={cn(
                        'text-xs font-medium',
                        segment.isUser ? 'text-purple-primary' : 'text-text-secondary'
                      )}
                    >
                      {getSpeakerLabel(segment.isUser, segment.speaker)}
                    </span>
                  </div>
                  <p className="text-sm text-text-primary leading-relaxed">{segment.text}</p>
                </div>
              </motion.div>
            ))}
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
      <p className="text-xs text-text-quaternary text-center py-2">
        Waiting for speech...
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <AnimatePresence mode="popLayout">
        {recentSegments.map((segment) => (
          <motion.div
            key={segment.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            className="flex items-start gap-2"
          >
            <div
              className={cn(
                'flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium border',
                getSpeakerColor(segment.isUser ? 0 : segment.speaker)
              )}
            >
              {segment.isUser ? 'Y' : segment.speaker + 1}
            </div>
            <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
              {segment.text}
            </p>
          </motion.div>
        ))}
      </AnimatePresence>

      {segments.length > maxItems && (
        <p className="text-[10px] text-text-quaternary text-center">
          +{segments.length - maxItems} more segments
        </p>
      )}
    </div>
  );
}
