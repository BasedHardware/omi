'use client';

import { useEffect, useState, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Pause, Play, Square, User, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  createRecordingChannel,
  sendRecordingCommand,
  requestCurrentState,
  type RecordingBroadcastMessage,
} from '@/lib/recordingBroadcast';
import type { RecordingState, AudioMode, TranscriptSegment } from '@/components/recording/RecordingContext';

// Extended message type for start command
type ExtendedBroadcastMessage = RecordingBroadcastMessage | { type: 'command'; command: 'start' };

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Animated waveform visualization
 */
function Waveform({ level, isActive, isPaused }: { level: number; isActive: boolean; isPaused: boolean }) {
  const bars = 7;

  const heights = useMemo(() => {
    return Array.from({ length: bars }, (_, i) => {
      const base = 0.3;
      const variance = Math.sin(i * 1.2) * 0.3 + 0.5;
      return base + (level * variance * 0.7);
    });
  }, [level]);

  return (
    <div className="flex items-center justify-center gap-1 h-6">
      {heights.map((height, i) => (
        <motion.div
          key={i}
          className={cn(
            "w-1 rounded-full",
            isActive && !isPaused ? "bg-purple-400" : "bg-gray-500"
          )}
          animate={{
            height: isActive && !isPaused
              ? `${Math.max(6, height * 24)}px`
              : '6px',
          }}
          transition={{
            duration: 0.15,
            ease: "easeOut",
          }}
        />
      ))}
    </div>
  );
}

// Colors for different speakers
const speakerColors = [
  { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
  { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
  { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/20' },
  { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
];

function getSpeakerColor(speakerId: number) {
  const safeId = Math.abs(speakerId || 0);
  return speakerColors[safeId % speakerColors.length];
}

function getSpeakerLabel(isUser: boolean, speakerId: number): string {
  if (isUser) return 'You';
  const safeId = Math.abs(speakerId || 0);
  return `Speaker ${safeId + 1}`;
}

/**
 * Full transcript pop-out window.
 * Shows complete transcript with controls at the top.
 */
export default function TranscriptPopoutPage() {
  const [state, setState] = useState<RecordingState>('idle');
  const [audioMode, setAudioMode] = useState<AudioMode>('mic-only');
  const [duration, setDuration] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [channel, setChannel] = useState<BroadcastChannel | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Initialize broadcast channel
  useEffect(() => {
    const ch = createRecordingChannel();
    if (!ch) return;

    setChannel(ch);

    // Handle messages from main window
    ch.onmessage = (event: MessageEvent<RecordingBroadcastMessage>) => {
      const message = event.data;

      switch (message.type) {
        case 'state-update':
          setState(message.state);
          setAudioMode(message.audioMode);
          setDuration(message.duration);
          setMicLevel(message.micLevel);
          break;
        case 'segments-update':
          setSegments(message.segments);
          break;
      }
    };

    // Request current state from main window
    requestCurrentState(ch);

    return () => {
      ch.close();
    };
  }, []);

  // Auto-scroll to bottom when new segments arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [segments]);

  const handlePause = () => {
    if (channel) sendRecordingCommand(channel, 'pause');
  };

  const handleResume = () => {
    if (channel) sendRecordingCommand(channel, 'resume');
  };

  const handleStop = () => {
    if (channel) sendRecordingCommand(channel, 'stop');
  };

  const handleStart = () => {
    if (channel) {
      const message: ExtendedBroadcastMessage = { type: 'command', command: 'start' };
      channel.postMessage(message);
    }
  };

  const handleClose = () => {
    window.close();
  };

  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const isInitializing = state === 'initializing';
  const isIdle = state === 'idle';
  const isActive = isRecording || isPaused;

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex flex-col">
      {/* Header with controls */}
      <header className="flex-shrink-0 border-b border-white/[0.04] bg-bg-secondary">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            {/* Status indicator */}
            {isActive && (
              <span className="relative flex h-3 w-3">
                <span className={cn(
                  "absolute inline-flex h-full w-full rounded-full opacity-75",
                  isRecording ? "animate-ping bg-red-400" : "bg-yellow-400"
                )} />
                <span className={cn(
                  "relative inline-flex rounded-full h-3 w-3",
                  isRecording ? "bg-red-500" : "bg-yellow-500"
                )} />
              </span>
            )}

            {/* Timer */}
            <span className="text-lg font-mono font-semibold">
              {formatDuration(duration)}
            </span>

            {/* Audio mode badge */}
            {isActive && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-bg-tertiary text-text-tertiary">
                {audioMode === 'mic-only' ? 'Mic' : 'Mic + System'}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Start button when idle */}
            {isIdle && (
              <button
                onClick={handleStart}
                className="p-2 rounded-lg bg-purple-500 hover:bg-purple-600 text-white transition-colors"
                title="Start Recording"
              >
                <Play className="w-4 h-4" />
              </button>
            )}

            {/* Initializing spinner */}
            {isInitializing && (
              <motion.div
                className="w-5 h-5 border-2 border-purple-400 border-t-transparent rounded-full"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
            )}

            {/* Controls when active */}
            {isActive && (
              <>
                <button
                  onClick={isPaused ? handleResume : handlePause}
                  className={cn(
                    "p-2 rounded-lg transition-colors",
                    isPaused
                      ? "bg-purple-500 hover:bg-purple-600 text-white"
                      : "bg-bg-tertiary hover:bg-bg-secondary text-text-primary"
                  )}
                  title={isPaused ? "Resume" : "Pause"}
                >
                  {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                </button>

                <button
                  onClick={handleStop}
                  className="p-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
                  title="Stop"
                >
                  <Square className="w-4 h-4" />
                </button>
              </>
            )}

            {/* Close button */}
            <button
              onClick={handleClose}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors text-text-tertiary hover:text-text-primary"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Audio waveform */}
        {isActive && (
          <div className="px-4 pb-3">
            <Waveform level={micLevel} isActive={isActive} isPaused={isPaused} />
          </div>
        )}
      </header>

      {/* Transcript content */}
      <div className="flex-1 overflow-y-auto p-4">
        {segments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 rounded-full bg-bg-tertiary flex items-center justify-center mb-3">
              <User className="w-6 h-6 text-text-quaternary" />
            </div>
            <p className="text-sm text-text-tertiary">
              {isActive ? 'Listening for speech...' : isInitializing ? 'Starting...' : 'No active recording'}
            </p>
            {isIdle && (
              <button
                onClick={handleStart}
                className="mt-4 px-4 py-2 rounded-lg bg-purple-500 hover:bg-purple-600 text-white text-sm font-medium transition-colors"
              >
                Start Recording
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
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
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={cn(
                            'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border',
                            colors.bg,
                            colors.text,
                            colors.border
                          )}
                        >
                          {segment.isUser && <User className="w-3 h-3" />}
                          {getSpeakerLabel(segment.isUser, segment.speaker)}
                        </span>
                      </div>
                      <p className="text-sm text-text-primary leading-relaxed pl-0.5">
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

      {/* Footer with segment count */}
      <footer className="flex-shrink-0 border-t border-white/[0.04] px-4 py-2 bg-bg-secondary">
        <p className="text-xs text-text-quaternary text-center">
          {segments.length} segment{segments.length !== 1 ? 's' : ''}
        </p>
      </footer>
    </div>
  );
}
