'use client';

import { useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Pause, Play, Square } from 'lucide-react';
import type { TranscriptSegment } from '@/components/recording/RecordingContext';
import { OmiPulseMark } from '@/components/ui/OmiPulseMark';
import { cn } from '@/lib/utils';

/**
 * What a live capture looks like from inside the chat.
 *
 * The mark itself is the level meter: in `listening` the ring flattens into a
 * travelling wave whose amplitude and flattening are both driven by the input
 * level, so silence leaves the brand standing and speech turns it into a
 * waveform. That is why this shows no separate bar meter — a waveform beside
 * the mark would be a second thing saying what the mark already says.
 */

/** Formats elapsed seconds as MM:SS. */
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

interface RecordingStageProps {
  segments: TranscriptSegment[];
  duration: number;
  level: number;
  isPaused: boolean;
  /**
   * Capture has been asked for but has not started yet — the permission prompt
   * or the socket handshake is still outstanding. Both handlers no-op until it
   * clears, so the stage must not offer them.
   */
  isInitializing?: boolean;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

export function RecordingStage({
  segments,
  duration,
  level,
  isPaused,
  isInitializing = false,
  onPause,
  onResume,
  onStop,
}: RecordingStageProps) {
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();

  // The transcript is capped, so without an anchor the stage keeps showing the
  // first thing that was said instead of the thing being said now.
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: 'end' });
  }, [segments]);

  const status = isInitializing ? 'Starting...' : isPaused ? 'Paused' : 'Listening';

  return (
    <motion.div
      initial={{ opacity: 0, y: reducedMotion ? 0 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: reducedMotion ? 0 : 6 }}
      transition={{ duration: reducedMotion ? 0 : 0.16, ease: 'easeOut' }}
      className={cn(
        'pointer-events-auto overflow-hidden rounded-card',
        'border border-stroke bg-bg-raised/95 backdrop-blur-xl',
        'shadow-[0_18px_40px_-12px_rgba(0,0,0,0.6)]',
      )}
    >
      <div className="flex items-center gap-4 px-5 py-4">
        <OmiPulseMark
          size={42}
          level={level}
          active={!isPaused && !isInitializing}
          label="Omi live"
          testId="omi-live-mark"
        />

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-text-primary">{status}</p>
          <p className="text-xs tabular-nums text-text-quaternary">
            {formatDuration(duration)}
          </p>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={isPaused ? onResume : onPause}
            disabled={isInitializing}
            className="flex h-9 w-9 items-center justify-center rounded-full text-text-tertiary transition-colors hover:bg-white/[0.08] hover:text-text-primary disabled:pointer-events-none disabled:opacity-40"
            aria-label={isPaused ? 'Resume recording' : 'Pause recording'}
          >
            {isPaused ? (
              <Play className="h-4 w-4 fill-current" />
            ) : (
              <Pause className="h-4 w-4 fill-current" />
            )}
          </button>
          <button
            onClick={onStop}
            disabled={isInitializing}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-red-500/15 text-red-400 transition-colors hover:bg-red-500/25 disabled:pointer-events-none disabled:opacity-40"
            aria-label="Stop recording"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        </div>
      </div>

      {/* The transcript sits under the wave, newest last, capped so the stage
          never grows past the chat it is overlaying. */}
      <div
        className="max-h-40 overflow-y-auto border-t border-stroke/60 px-5 py-3"
        role="status"
        aria-live="polite"
        aria-atomic="false"
      >
        {segments.length === 0 ? (
          <p className="text-sm text-text-quaternary">
            {isInitializing
              ? 'Starting capture...'
              : isPaused
                ? 'Paused.'
                : 'Listening for speech...'}
          </p>
        ) : (
          <div className="space-y-1.5">
            {segments.map((segment) => (
              <p key={segment.id} className="text-sm leading-relaxed text-text-secondary">
                {segment.text}
              </p>
            ))}
            <div ref={transcriptEndRef} data-testid="transcript-end" />
          </div>
        )}
      </div>
    </motion.div>
  );
}
