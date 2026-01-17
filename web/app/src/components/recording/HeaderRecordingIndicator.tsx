'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Pause, Play, Square, ChevronDown, ExternalLink, PanelTop, FileText, Monitor } from 'lucide-react';
import Link from 'next/link';
import { useRecordingContext } from './RecordingContext';
import type { AudioMode } from './RecordingContext';
import { LiveTranscriptCompact } from './LiveTranscript';
import { openRecordingWidget, openTranscriptWindow } from '@/lib/popout';
import { useNotificationContext } from '@/components/notifications/NotificationContext';
import { useChat } from '@/components/chat/ChatContext';
import { cn } from '@/lib/utils';
import { RECORDING_ENABLED } from '@/lib/featureFlags';

/**
 * Format duration in seconds to MM:SS format
 */
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Header recording indicator - always visible.
 * When idle: shows mic icon to start recording
 * When recording: shows timer with dropdown for controls and transcript
 */
export function HeaderRecordingIndicator() {
  const {
    state,
    audioMode,
    duration,
    segments,
    micLevel,
    setAudioMode,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
  } = useRecordingContext();

  const { isOpen: isNotificationOpen } = useNotificationContext();
  const { isOpen: isChatOpen } = useChat();

  const [isExpanded, setIsExpanded] = useState(false);
  const [showModeSelector, setShowModeSelector] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Calculate right offset based on which panels are open (panel width is ~404px each)
  const rightOffset = 16 + (isChatOpen ? 404 : 0) + (isNotificationOpen ? 404 : 0);

  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const isInitializing = state === 'initializing';
  const isIdle = state === 'idle';
  const isActive = isRecording || isPaused;

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsExpanded(false);
        setShowModeSelector(false);
      }
    }

    if (isExpanded || showModeSelector) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isExpanded, showModeSelector]);

  const handleStartRecording = () => {
    setShowModeSelector(false);
    startRecording();
  };

  const handleModeSelect = (mode: AudioMode) => {
    setAudioMode(mode);
  };

  return (
    <motion.div
      className="fixed top-4 z-[9999]"
      animate={{ right: rightOffset }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      <div className="relative" ref={dropdownRef}>
        {/* Idle state - Start recording button */}
        {isIdle && (
        <>
          {!RECORDING_ENABLED ? (
            /* Coming Soon state - Recording disabled until backend is deployed */
            <div
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-full',
                'bg-bg-tertiary border border-bg-quaternary',
                'text-sm font-medium cursor-not-allowed opacity-70'
              )}
              title="Web recording coming soon"
            >
              <Mic className="w-4 h-4 text-text-quaternary" />
              <span className="text-text-tertiary">Record</span>
              <span className="text-[10px] text-text-quaternary bg-bg-quaternary px-1.5 py-0.5 rounded">
                Soon
              </span>
            </div>
          ) : (
          <button
            onClick={() => setShowModeSelector(!showModeSelector)}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-full',
              'bg-purple-primary/10 border border-purple-primary/30',
              'hover:bg-purple-primary/20 transition-colors',
              'text-sm font-medium'
            )}
          >
            <Mic className="w-4 h-4 text-purple-primary" />
            <span className="text-purple-primary">Record</span>
            <ChevronDown
              className={cn(
                'w-3.5 h-3.5 text-purple-primary/70 transition-transform',
                showModeSelector && 'rotate-180'
              )}
            />
          </button>
          )}

          {/* Mode selector dropdown */}
          <AnimatePresence>
            {showModeSelector && (
              <motion.div
                initial={{ opacity: 0, y: -10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className={cn(
                  'absolute right-0 top-full mt-2 z-50',
                  'w-72 p-4 rounded-xl',
                  'bg-bg-secondary border border-bg-tertiary',
                  'shadow-lg shadow-black/20'
                )}
              >
                <h3 className="text-sm font-medium text-text-primary mb-3">
                  Start Recording
                </h3>

                {/* Audio mode options */}
                <div className="space-y-2 mb-4">
                  <button
                    onClick={() => handleModeSelect('mic-only')}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg transition-colors text-left',
                      audioMode === 'mic-only'
                        ? 'bg-purple-primary/10 border border-purple-primary/30'
                        : 'bg-bg-tertiary hover:bg-bg-quaternary border border-transparent'
                    )}
                  >
                    <div className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center',
                      audioMode === 'mic-only' ? 'bg-purple-primary/20' : 'bg-bg-secondary'
                    )}>
                      <Mic className={cn(
                        'w-4 h-4',
                        audioMode === 'mic-only' ? 'text-purple-primary' : 'text-text-tertiary'
                      )} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={cn(
                        'text-sm font-medium',
                        audioMode === 'mic-only' ? 'text-purple-primary' : 'text-text-primary'
                      )}>
                        Microphone Only
                      </p>
                      <p className="text-xs text-text-tertiary">
                        Record from your microphone
                      </p>
                    </div>
                  </button>

                  <button
                    onClick={() => handleModeSelect('mic-and-system')}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg transition-colors text-left',
                      audioMode === 'mic-and-system'
                        ? 'bg-purple-primary/10 border border-purple-primary/30'
                        : 'bg-bg-tertiary hover:bg-bg-quaternary border border-transparent'
                    )}
                  >
                    <div className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center',
                      audioMode === 'mic-and-system' ? 'bg-purple-primary/20' : 'bg-bg-secondary'
                    )}>
                      <Monitor className={cn(
                        'w-4 h-4',
                        audioMode === 'mic-and-system' ? 'text-purple-primary' : 'text-text-tertiary'
                      )} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={cn(
                        'text-sm font-medium',
                        audioMode === 'mic-and-system' ? 'text-purple-primary' : 'text-text-primary'
                      )}>
                        Mic + System Audio
                      </p>
                      <p className="text-xs text-text-tertiary">
                        Record both mic and system audio
                      </p>
                    </div>
                  </button>
                </div>

                {/* Start button */}
                <button
                  onClick={handleStartRecording}
                  className={cn(
                    'w-full py-2.5 px-4 rounded-lg font-medium',
                    'bg-purple-primary hover:bg-purple-secondary text-white',
                    'transition-colors flex items-center justify-center gap-2'
                  )}
                >
                  <Mic className="w-4 h-4" />
                  <span>Start Recording</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}

      {/* Initializing state */}
      {isInitializing && (
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded-full',
            'bg-bg-secondary border border-bg-tertiary',
            'text-sm font-medium'
          )}
        >
          <motion.div
            className="w-4 h-4 border-2 border-purple-primary border-t-transparent rounded-full"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          />
          <span className="text-text-secondary">Starting...</span>
        </div>
      )}

      {/* Recording/Paused state */}
      {isActive && (
        <>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-full',
              'bg-bg-secondary border border-bg-tertiary',
              'hover:bg-bg-tertiary transition-colors',
              'text-sm font-medium'
            )}
          >
            {/* Recording dot */}
            {isRecording && (
              <motion.div
                className="w-2 h-2 rounded-full bg-error"
                animate={{ opacity: [1, 0.5, 1] }}
                transition={{ duration: 1, repeat: Infinity }}
              />
            )}
            {isPaused && <div className="w-2 h-2 rounded-full bg-yellow-500" />}

            {/* Timer */}
            <span className="font-mono tabular-nums text-text-primary">
              {formatDuration(duration)}
            </span>

            {/* Chevron */}
            <ChevronDown
              className={cn(
                'w-4 h-4 text-text-tertiary transition-transform',
                isExpanded && 'rotate-180'
              )}
            />
          </button>

          {/* Expanded dropdown */}
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ opacity: 0, y: -10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className={cn(
                  'absolute right-0 top-full mt-2 z-50',
                  'w-80 p-4 rounded-xl',
                  'bg-bg-secondary border border-bg-tertiary',
                  'shadow-lg shadow-black/20'
                )}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {isRecording && (
                      <motion.div
                        className="w-2.5 h-2.5 rounded-full bg-error"
                        animate={{ opacity: [1, 0.5, 1] }}
                        transition={{ duration: 1, repeat: Infinity }}
                      />
                    )}
                    {isPaused && <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />}
                    <span className="text-sm font-medium text-text-primary">
                      {isRecording ? 'Recording' : 'Paused'}
                    </span>
                  </div>
                  <span className="text-lg font-mono tabular-nums text-text-primary">
                    {formatDuration(duration)}
                  </span>
                </div>

                {/* Level meter */}
                <div className="mb-4">
                  <div className="flex items-center gap-2">
                    <Mic className="w-3 h-3 text-text-quaternary" />
                    <div className="flex-1 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-purple-primary rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(100, micLevel * 100)}%` }}
                        transition={{ duration: 0.1 }}
                      />
                    </div>
                  </div>
                </div>

                {/* Compact transcript */}
                <div className="mb-4 max-h-32 overflow-y-auto">
                  <LiveTranscriptCompact segments={segments} maxItems={3} />
                </div>

                {/* Controls */}
                <div className="flex items-center justify-between pt-3 border-t border-bg-tertiary">
                  <div className="flex items-center gap-2">
                    {/* Pause/Resume */}
                    <button
                      onClick={isPaused ? resumeRecording : pauseRecording}
                      className={cn(
                        'p-2 rounded-lg transition-colors',
                        'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary'
                      )}
                      title={isPaused ? 'Resume' : 'Pause'}
                    >
                      {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                    </button>

                    {/* Stop */}
                    <button
                      onClick={() => {
                        stopRecording();
                        setIsExpanded(false);
                      }}
                      className={cn(
                        'p-2 rounded-lg transition-colors',
                        'bg-error/10 text-error hover:bg-error/20'
                      )}
                      title="Stop recording"
                    >
                      <Square className="w-4 h-4 fill-current" />
                    </button>
                  </div>

                  {/* View full / Pop-out options */}
                  <div className="flex items-center gap-1">
                    {/* Pop-out widget */}
                    <button
                      onClick={() => {
                        openRecordingWidget();
                      }}
                      className={cn(
                        'p-2 rounded-lg transition-colors',
                        'text-text-tertiary hover:text-text-primary',
                        'hover:bg-bg-tertiary'
                      )}
                      title="Pop-out widget"
                    >
                      <PanelTop className="w-4 h-4" />
                    </button>

                    {/* Pop-out transcript */}
                    <button
                      onClick={() => {
                        openTranscriptWindow();
                      }}
                      className={cn(
                        'p-2 rounded-lg transition-colors',
                        'text-text-tertiary hover:text-text-primary',
                        'hover:bg-bg-tertiary'
                      )}
                      title="Pop-out transcript"
                    >
                      <FileText className="w-4 h-4" />
                    </button>

                    {/* View full page */}
                    <Link
                      href="/record"
                      onClick={() => setIsExpanded(false)}
                      className={cn(
                        'p-2 rounded-lg transition-colors',
                        'text-text-tertiary hover:text-text-primary',
                        'hover:bg-bg-tertiary'
                      )}
                      title="View full page"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
      </div>
    </motion.div>
  );
}
