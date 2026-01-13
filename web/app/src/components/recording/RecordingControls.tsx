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
      <span className="text-xs text-text-quaternary w-12">{label}</span>
      <div className="flex-1 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-purple-primary rounded-full"
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
    <div className="flex flex-col items-center gap-6">
      {/* Status */}
      <div className="flex items-center gap-3">
        {isRecording && (
          <motion.div
            className="w-3 h-3 rounded-full bg-error"
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
        )}
        {isPaused && <div className="w-3 h-3 rounded-full bg-yellow-500" />}
        {isInitializing && <Loader2 className="w-5 h-5 text-purple-primary animate-spin" />}
        {isProcessing && <Loader2 className="w-5 h-5 text-purple-primary animate-spin" />}

        <span className="text-2xl font-mono text-text-primary tabular-nums">
          {formatDuration(duration)}
        </span>
      </div>

      {/* Status text */}
      <p className="text-sm text-text-tertiary">
        {isInitializing && 'Initializing...'}
        {isRecording && 'Recording'}
        {isPaused && 'Paused'}
        {isProcessing && 'Processing...'}
      </p>

      {/* Level meters */}
      {(isRecording || isPaused) && (
        <div className="w-full max-w-xs space-y-2">
          <LevelMeter level={micLevel} label="Mic" />
          {audioMode === 'mic-and-system' && (
            <LevelMeter level={systemLevel} label="System" />
          )}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-4">
        {/* Pause/Resume button */}
        <button
          onClick={isPaused ? onResume : onPause}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-4 rounded-full transition-all',
            'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {isPaused ? <Play className="w-6 h-6" /> : <Pause className="w-6 h-6" />}
        </button>

        {/* Stop button */}
        <button
          onClick={onStop}
          disabled={isProcessing || isInitializing}
          className={cn(
            'p-5 rounded-full transition-all',
            'bg-error text-white hover:bg-error/80',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {isProcessing ? (
            <Loader2 className="w-8 h-8 animate-spin" />
          ) : (
            <Square className="w-8 h-8 fill-current" />
          )}
        </button>

        {/* Placeholder for symmetry */}
        <div className="p-4 w-14" />
      </div>
    </div>
  );
}
