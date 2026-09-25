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
      <span className="w-12 text-xs text-text-quaternary">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-tertiary">
        <motion.div
          className="h-full rounded-full bg-text-primary"
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
              className="h-2 w-2 rounded-full bg-error"
              animate={{ opacity: [1, 0.5, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
            />
          )}
          {isPaused && <div className="h-2 w-2 rounded-full bg-yellow-500" />}
          <span className="font-mono text-sm tabular-nums text-text-secondary">
            {formatDuration(duration)}
          </span>
        </div>

        {/* Pause/Resume button */}
        <button
          onClick={isPaused ? onResume : onPause}
          disabled={isProcessing || isInitializing}
          className={cn(
            'rounded-lg p-2 transition-colors',
            'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
        </button>

        {/* Stop button */}
        <button
          onClick={onStop}
          disabled={isProcessing || isInitializing}
          className={cn(
            'rounded-lg p-2 transition-colors',
            'text-error hover:bg-error/10',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {isProcessing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Square className="h-4 w-4 fill-current" />
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
            className="h-3 w-3 rounded-full bg-error"
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
        )}
        {isPaused && <div className="h-3 w-3 rounded-full bg-yellow-500" />}
        {isInitializing && <Loader2 className="h-5 w-5 animate-spin text-text-primary" />}
        {isProcessing && <Loader2 className="h-5 w-5 animate-spin text-text-primary" />}

        <span className="font-mono text-2xl tabular-nums text-text-primary">
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
            'rounded-full p-4 transition-all',
            'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {isPaused ? <Play className="h-6 w-6" /> : <Pause className="h-6 w-6" />}
        </button>

        {/* Stop button */}
        <button
          onClick={onStop}
          disabled={isProcessing || isInitializing}
          className={cn(
            'rounded-full p-5 transition-all',
            'bg-error text-white hover:bg-error/80',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {isProcessing ? (
            <Loader2 className="h-8 w-8 animate-spin" />
          ) : (
            <Square className="h-8 w-8 fill-current" />
          )}
        </button>

        {/* Placeholder for symmetry */}
        <div className="w-14 p-4" />
      </div>
    </div>
  );
}
