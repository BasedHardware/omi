'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, X, ChevronUp, ChevronDown, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRecording } from '@/hooks/useRecording';
import { AudioModeSelector } from './AudioModeSelector';
import { RecordingControls } from './RecordingControls';
import { LiveTranscriptCompact } from './LiveTranscript';

/**
 * Floating recording widget that appears at the bottom-left of the screen.
 * Shows recording controls and live transcript.
 */
export function RecordingWidget() {
  const {
    state,
    audioMode,
    segments,
    duration,
    micLevel,
    systemLevel,
    error,
    isWidgetExpanded,
    setAudioMode,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    setWidgetExpanded,
    clearError,
    isIdle,
    isRecording,
    isPaused,
  } = useRecording();

  const [showModeSelector, setShowModeSelector] = useState(false);

  const handleStartClick = () => {
    setShowModeSelector(true);
  };

  const handleStartRecording = () => {
    setShowModeSelector(false);
    startRecording();
  };

  const handleCancelModeSelector = () => {
    setShowModeSelector(false);
  };

  // Don't show widget when mode selector is open (it's a modal)
  const showWidget = !showModeSelector;

  return (
    <>
      {/* Mode selector modal */}
      <AnimatePresence>
        {showModeSelector && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/50"
              onClick={handleCancelModeSelector}
            />

            {/* Modal */}
            <div className="relative z-10">
              <AudioModeSelector
                selectedMode={audioMode}
                onModeSelect={setAudioMode}
                onStartRecording={handleStartRecording}
                onCancel={handleCancelModeSelector}
              />
            </div>
          </div>
        )}
      </AnimatePresence>

      {/* Floating widget */}
      <AnimatePresence>
        {showWidget && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            className={cn(
              'fixed bottom-6 left-6 z-50',
              'flex flex-col',
              isWidgetExpanded ? 'w-80' : 'w-auto',
            )}
          >
            {/* Expanded panel */}
            <AnimatePresence>
              {isWidgetExpanded && (isRecording || isPaused || segments.length > 0) && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden rounded-t-2xl border border-bg-tertiary bg-bg-secondary shadow-strong"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-bg-tertiary px-4 py-3">
                    <span className="text-sm font-medium text-text-primary">
                      Live Transcript
                    </span>
                    <button
                      onClick={() => setWidgetExpanded(false)}
                      className="rounded-lg p-1 text-text-tertiary transition-colors hover:bg-bg-tertiary hover:text-text-secondary"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </button>
                  </div>

                  {/* Transcript */}
                  <div className="max-h-60 overflow-y-auto px-4 py-3">
                    <LiveTranscriptCompact segments={segments} maxItems={5} />
                  </div>

                  {/* Controls */}
                  <div className="border-t border-bg-tertiary bg-bg-tertiary/30 px-4 py-3">
                    <RecordingControls
                      state={state}
                      duration={duration}
                      micLevel={micLevel}
                      systemLevel={systemLevel}
                      audioMode={audioMode}
                      onPause={pauseRecording}
                      onResume={resumeRecording}
                      onStop={stopRecording}
                      compact
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Main button / collapsed state */}
            <motion.div
              className={cn(
                'border border-bg-tertiary bg-bg-secondary shadow-strong',
                isWidgetExpanded && (isRecording || isPaused || segments.length > 0)
                  ? 'rounded-b-2xl border-t-0'
                  : 'rounded-2xl',
              )}
            >
              {/* Error message */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="border-b border-error/20 bg-error/10 px-4 py-2"
                  >
                    <div className="flex items-start gap-2">
                      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-error" />
                      <p className="flex-1 text-xs text-error">{error}</p>
                      <button
                        onClick={clearError}
                        className="p-0.5 text-error/60 transition-colors hover:text-error"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Button content */}
              <div className="p-3">
                {isIdle ? (
                  // Idle state - show start button
                  <button
                    onClick={handleStartClick}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl px-4 py-2.5',
                      'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                      'transition-all',
                    )}
                  >
                    <Mic className="h-5 w-5" />
                    <span className="font-medium">Start Recording</span>
                  </button>
                ) : !isWidgetExpanded ? (
                  // Recording but collapsed - show mini status
                  <button
                    onClick={() => setWidgetExpanded(true)}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl px-4 py-2.5',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'transition-all',
                    )}
                  >
                    {/* Recording indicator */}
                    {isRecording && (
                      <motion.div
                        className="h-2.5 w-2.5 rounded-full bg-error"
                        animate={{ opacity: [1, 0.5, 1] }}
                        transition={{ duration: 1, repeat: Infinity }}
                      />
                    )}
                    {isPaused && (
                      <div className="h-2.5 w-2.5 rounded-full bg-yellow-500" />
                    )}

                    <span className="font-mono text-sm tabular-nums text-text-primary">
                      {formatDuration(duration)}
                    </span>

                    <ChevronUp className="ml-auto h-4 w-4 text-text-tertiary" />
                  </button>
                ) : // Expanded and recording - show nothing here (controls are above)
                null}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
