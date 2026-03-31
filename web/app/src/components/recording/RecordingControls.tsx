'use client';

import { motion } from 'framer-motion';
import { Pause, Play, Square, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { RecordingState, AudioMode } from './RecordingContext';

interface RecordingControlsProps {
  state: RecordingState;
  duration: number;
  micLevel: number;
  systemLevel: number;
  audioMode: AudioMode;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  compact?: boolean;
}

/**
 * Format duration in seconds to MM:SS format
 */
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Audio level meter component
 */
function LevelMeter({ level, label }: { level: number; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground w-12">{label}</span>
      <div className="flex-1 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-primary rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, level * 100)}%` }}
          transition={{ duration: 0.1 }}
        />
      </div>
    </div>
  );
}

export function RecordingControls({
  state,
  duration,
  micLevel,
  systemLevel,
  audioMode,
  onPause,
  onResume,
  onStop,
  compact = false,
}: RecordingControlsProps) {
  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const isProcessing = state === 'processing';
  const isInitializing = state === 'initializing';

  if (compact) {
    return (
      <div className="flex items-center gap-3">
        {/* Recording indicator */}
        <div className="flex items-center gap-2">
          {isRecording && (
            <motion.div
              className="w-2 h-2 rounded-full bg-error"
              animate={{ opacity: [1, 0.5, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
            />
          )}
          {isPaused && <div className="w-2 h-2 rounded-full bg-yellow-500" />}
          <span className="text-sm font-mono text-text-secondary tabular-nums">
            {formatDuration(duration)}
          </span>
        </div>

        {/* Pause/Resume button */}
        <button
          onClick={isPaused ? onResume : onPause}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-2 rounded-lg transition-colors',
            'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
        </button>

        {/* Stop button */}
        <button
          onClick={onStop}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-2 rounded-lg transition-colors',
            'text-error hover:bg-error/10',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Square className="w-4 h-4 fill-current" />
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4">
      {/* Recording dot + timer */}
      <div className="flex items-center gap-2">
        {isRecording && (
          <motion.div
            className="w-2 h-2 rounded-full bg-destructive"
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
        )}
        {isPaused && <div className="w-2 h-2 rounded-full bg-yellow-500" />}
        {(isInitializing || isProcessing) && (
          <Loader2 className="w-4 h-4 text-primary animate-spin" />
        )}
        <span className="text-sm font-mono text-foreground tabular-nums">
          {formatDuration(duration)}
        </span>
        <span className="text-xs text-muted-foreground">
          {isInitializing ? 'Starting...' : isPaused ? 'Paused' : isProcessing ? 'Saving...' : ''}
        </span>
      </div>

      {/* Level meter — inline */}
      {(isRecording || isPaused) && (
        <div className="flex items-center gap-2 w-32">
          <span className="text-[10px] text-muted-foreground uppercase">Mic</span>
          <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-primary rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, micLevel * 100)}%` }}
              transition={{ duration: 0.1 }}
            />
          </div>
        </div>
      )}

      {/* Controls — small pill buttons */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={isPaused ? onResume : onPause}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-2 rounded-lg transition-colors',
            'bg-secondary text-foreground hover:bg-accent',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          title={isPaused ? 'Resume' : 'Pause'}
        >
          {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
        </button>

        <button
          onClick={onStop}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-2 rounded-lg transition-colors',
            'bg-destructive/10 text-destructive hover:bg-destructive/20',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          title="Stop"
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Square className="w-4 h-4 fill-current" />
          )}
        </button>
      </div>
    </div>
  );
}
