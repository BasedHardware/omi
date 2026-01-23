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
              isWidgetExpanded ? 'w-80' : 'w-auto'
            )}
          >
            {/* Expanded panel */}
            <AnimatePresence>
              {isWidgetExpanded && (isRecording || isPaused || segments.length > 0) && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="bg-bg-secondary border border-bg-tertiary rounded-t-2xl overflow-hidden shadow-strong"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between px-4 py-3 border-b border-bg-tertiary">
                    <span className="text-sm font-medium text-text-primary">Live Transcript</span>
                    <button
                      onClick={() => setWidgetExpanded(false)}
                      className="p-1 rounded-lg text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary transition-colors"
                    >
                      <ChevronDown className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Transcript */}
                  <div className="px-4 py-3 max-h-60 overflow-y-auto">
                    <LiveTranscriptCompact segments={segments} maxItems={5} />
                  </div>

                  {/* Controls */}
                  <div className="px-4 py-3 border-t border-bg-tertiary bg-bg-tertiary/30">
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
                'bg-bg-secondary border border-bg-tertiary shadow-strong',
                isWidgetExpanded && (isRecording || isPaused || segments.length > 0)
                  ? 'rounded-b-2xl border-t-0'
                  : 'rounded-2xl'
              )}
            >
              {/* Error message */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="px-4 py-2 bg-error/10 border-b border-error/20"
                  >
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-error flex-1">{error}</p>
                      <button
                        onClick={clearError}
                        className="p-0.5 text-error/60 hover:text-error transition-colors"
                      >
                        <X className="w-3 h-3" />
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
                      'flex items-center gap-3 px-4 py-2.5 rounded-xl w-full',
                      'bg-purple-primary hover:bg-purple-secondary text-white',
                      'transition-all'
                    )}
                  >
                    <Mic className="w-5 h-5" />
                    <span className="font-medium">Start Recording</span>
                  </button>
                ) : !isWidgetExpanded ? (
                  // Recording but collapsed - show mini status
                  <button
                    onClick={() => setWidgetExpanded(true)}
                    className={cn(
                      'flex items-center gap-3 px-4 py-2.5 rounded-xl w-full',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'transition-all'
                    )}
                  >
                    {/* Recording indicator */}
                    {isRecording && (
                      <motion.div
                        className="w-2.5 h-2.5 rounded-full bg-error"
                        animate={{ opacity: [1, 0.5, 1] }}
                        transition={{ duration: 1, repeat: Infinity }}
                      />
                    )}
                    {isPaused && <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />}

                    <span className="text-sm font-mono text-text-primary tabular-nums">
                      {formatDuration(duration)}
                    </span>

                    <ChevronUp className="w-4 h-4 text-text-tertiary ml-auto" />
                  </button>
                ) : (
                  // Expanded and recording - show nothing here (controls are above)
                  null
                )}
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
