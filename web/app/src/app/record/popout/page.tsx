'use client';

import { useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Square, Mic, Monitor, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  createRecordingChannel,
  sendRecordingCommand,
  requestCurrentState,
  type RecordingBroadcastMessage,
} from '@/lib/recordingBroadcast';
import type { RecordingState, AudioMode } from '@/components/recording/RecordingContext';

// Extended message type for start command with audio mode
type ExtendedBroadcastMessage = RecordingBroadcastMessage | {
  type: 'command';
  command: 'start';
  audioMode?: AudioMode;
};

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Animated waveform visualization
 */
function Waveform({ level, isActive, isPaused }: { level: number; isActive: boolean; isPaused: boolean }) {
  const bars = 5;

  // Generate random-ish heights based on level
  const heights = useMemo(() => {
    return Array.from({ length: bars }, (_, i) => {
      const base = 0.3;
      const variance = Math.sin(i * 1.5) * 0.3 + 0.5;
      return base + (level * variance * 0.7);
    });
  }, [level]);

  return (
    <div className="flex items-center justify-center gap-[3px] h-6">
      {heights.map((height, i) => (
        <motion.div
          key={i}
          className={cn(
            "w-[3px] rounded-full",
            isActive && !isPaused ? "bg-purple-400" : "bg-gray-500"
          )}
          animate={{
            height: isActive && !isPaused
              ? `${Math.max(4, height * 24)}px`
              : '4px',
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

/**
 * Compact recording widget - Granola-style design
 * Single button to start/pause, waveform visualization, minimal chrome
 */
export default function RecordingPopoutPage() {
  const [state, setState] = useState<RecordingState>('idle');
  const [, setAudioMode] = useState<AudioMode>('mic-only');
  const [selectedMode, setSelectedMode] = useState<AudioMode>('mic-only');
  const [showModeSelector, setShowModeSelector] = useState(false);
  const [duration, setDuration] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [channel, setChannel] = useState<BroadcastChannel | null>(null);

  // Initialize broadcast channel
  useEffect(() => {
    const ch = createRecordingChannel();
    if (!ch) return;

    setChannel(ch);

    ch.onmessage = (event: MessageEvent<RecordingBroadcastMessage>) => {
      const message = event.data;
      switch (message.type) {
        case 'state-update':
          setState(message.state);
          setAudioMode(message.audioMode);
          setDuration(message.duration);
          setMicLevel(message.micLevel);
          break;
      }
    };

    requestCurrentState(ch);
    return () => ch.close();
  }, []);

  const handleToggle = () => {
    if (!channel) return;

    if (state === 'idle') {
      const message: ExtendedBroadcastMessage = { type: 'command', command: 'start', audioMode: selectedMode };
      channel.postMessage(message);
      setShowModeSelector(false);
    } else if (state === 'recording') {
      sendRecordingCommand(channel, 'pause');
    } else if (state === 'paused') {
      sendRecordingCommand(channel, 'resume');
    }
  };

  const handleStop = () => {
    if (channel) sendRecordingCommand(channel, 'stop');
  };

  const handleModeSelect = (mode: AudioMode) => {
    setSelectedMode(mode);
    setShowModeSelector(false);
  };

  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const isInitializing = state === 'initializing';
  const isActive = isRecording || isPaused;

  const isIdle = state === 'idle';

  return (
    <div className="min-h-screen bg-[#1a1a1a] text-white select-none flex flex-col items-center justify-center p-2 gap-2">
      <div className="flex items-center gap-3">
        {/* Main toggle button */}
        <button
          onClick={handleToggle}
          disabled={isInitializing}
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center transition-all",
            "focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#1a1a1a]",
            isInitializing && "opacity-50 cursor-not-allowed",
            isRecording && "bg-purple-500 hover:bg-purple-600 focus:ring-purple-500",
            isPaused && "bg-amber-500 hover:bg-amber-600 focus:ring-amber-500",
            !isActive && !isInitializing && "bg-purple-500 hover:bg-purple-600 focus:ring-purple-500"
          )}
        >
          {isInitializing ? (
            <motion.div
              className="w-4 h-4 border-2 border-white border-t-transparent rounded-full"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            />
          ) : isRecording ? (
            /* Pause icon (two bars) */
            <div className="flex gap-1">
              <div className="w-1 h-3 bg-white rounded-sm" />
              <div className="w-1 h-3 bg-white rounded-sm" />
            </div>
          ) : isPaused ? (
            /* Play icon (triangle) */
            <div className="w-0 h-0 border-t-[6px] border-t-transparent border-l-[10px] border-l-white border-b-[6px] border-b-transparent ml-0.5" />
          ) : (
            /* Mic/Record icon (circle) */
            <div className="w-3 h-3 bg-white rounded-full" />
          )}
        </button>

        {/* Mode selector button - only show when idle */}
        {isIdle && (
          <button
            onClick={() => setShowModeSelector(!showModeSelector)}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded-full text-xs",
              "bg-white/10 hover:bg-white/20 transition-colors"
            )}
          >
            {selectedMode === 'mic-only' ? (
              <Mic className="w-3 h-3" />
            ) : (
              <Monitor className="w-3 h-3" />
            )}
            <span>{selectedMode === 'mic-only' ? 'Mic' : 'Mic + System'}</span>
            <ChevronDown className={cn("w-3 h-3 transition-transform", showModeSelector && "rotate-180")} />
          </button>
        )}

        {/* Waveform + Timer - only show when active */}
        {isActive && (
          <div className="flex items-center gap-2">
            <Waveform level={micLevel} isActive={isActive} isPaused={isPaused} />

            <span className="text-sm font-mono tabular-nums min-w-[45px] text-white">
              {formatDuration(duration)}
            </span>
          </div>
        )}

        {/* Stop button - only show when active */}
        {isActive && (
          <button
            onClick={handleStop}
            className="w-7 h-7 rounded-full bg-red-500/20 hover:bg-red-500/30 flex items-center justify-center transition-colors"
            title="Stop"
          >
            <Square className="w-3 h-3 text-red-400 fill-red-400" />
          </button>
        )}
      </div>

      {/* Mode selector dropdown */}
      {showModeSelector && isIdle && (
        <div className="flex gap-2">
          <button
            onClick={() => handleModeSelect('mic-only')}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors",
              selectedMode === 'mic-only'
                ? "bg-purple-500 text-white"
                : "bg-white/10 hover:bg-white/20 text-white/70"
            )}
          >
            <Mic className="w-3 h-3" />
            <span>Mic Only</span>
          </button>
          <button
            onClick={() => handleModeSelect('mic-and-system')}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors",
              selectedMode === 'mic-and-system'
                ? "bg-purple-500 text-white"
                : "bg-white/10 hover:bg-white/20 text-white/70"
            )}
          >
            <Monitor className="w-3 h-3" />
            <span>Mic + System</span>
          </button>
        </div>
      )}
    </div>
  );
}
