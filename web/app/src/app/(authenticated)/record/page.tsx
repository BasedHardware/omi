'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic } from 'lucide-react';
import { useRecordingContext } from '@/components/recording/RecordingContext';
import { AudioModeSelector } from '@/components/recording/AudioModeSelector';
import { RecordingControls } from '@/components/recording/RecordingControls';
import { LiveTranscript } from '@/components/recording/LiveTranscript';
import { cn } from '@/lib/utils';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

/**
 * Rendered inside the shared authenticated shell, whose MainLayout provides
 * RecordingProvider. Because the shell is one instance across routes, the
 * recording context (and any in-flight recording) survives navigation.
 */
function RecordPage() {
  const {
    state,
    audioMode,
    segments,
    duration,
    micLevel,
    systemLevel,
    error,
    setAudioMode,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    clearError,
  } = useRecordingContext();

  // Computed states
  const isIdle = state === 'idle';
  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const isInitializing = state === 'initializing';
  const isProcessing = state === 'processing';

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

  const isActive = isRecording || isPaused || isInitializing || isProcessing;

  return (
    <>
      <div className="flex h-full flex-col bg-bg-primary">
        {/* Header */}
        <header className="flex flex-shrink-0 items-center justify-between px-6 py-4">
          <h1 className="text-sm font-medium text-text-tertiary">Record</h1>

          {/* Audio mode indicator */}
          {isActive && (
            <div className="flex items-center gap-2 text-sm text-text-tertiary">
              <span>{audioMode === 'mic-only' ? 'Mic Only' : 'Mic + System'}</span>
            </div>
          )}
        </header>

        {isIdle ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 pb-16 text-center">
            <button
              type="button"
              onClick={handleStartClick}
              aria-label="Start recording"
              className={cn(
                'group relative flex h-32 w-32 items-center justify-center rounded-full',
                'outline-none transition-all duration-200',
                'focus-visible:ring-2 focus-visible:ring-text-primary/60 focus-visible:ring-offset-4 focus-visible:ring-offset-bg-primary',
                'bg-text-primary text-bg-primary hover:scale-105 active:scale-95',
              )}
            >
              <Mic className="h-12 w-12" strokeWidth={1.5} />
            </button>

            <div className="max-w-sm space-y-2">
              <p className="text-lg font-medium text-text-primary">Start recording</p>
              <p className="text-sm text-text-tertiary">
                Live transcription with speaker identification, straight from your
                browser.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col gap-4 overflow-hidden px-6 pb-6">
            {/* Recording controls - horizontal compact layout */}
            <div className="flex flex-shrink-0 flex-col items-center gap-3">
              <RecordingControls
                state={state}
                duration={duration}
                micLevel={micLevel}
                systemLevel={systemLevel}
                audioMode={audioMode}
                onPause={pauseRecording}
                onResume={resumeRecording}
                onStop={stopRecording}
              />

              {/* Error message */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="rounded-control border border-error/20 bg-error/10 px-4 py-2"
                  >
                    <p className="text-sm text-error">{error}</p>
                    <button
                      onClick={clearError}
                      className="text-xs text-error/60 transition-colors hover:text-error"
                    >
                      Dismiss
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Transcript (takes remaining space) */}
            <div className="flex flex-1 flex-col overflow-hidden rounded-card border border-stroke bg-bg-secondary">
              <div className="flex flex-shrink-0 items-baseline gap-2 border-b border-stroke px-5 py-3">
                <h2 className="text-sm font-medium text-text-primary">Live Transcript</h2>
                <p className="text-xs text-text-quaternary">
                  {segments.length} segment{segments.length !== 1 ? 's' : ''}
                </p>
              </div>

              <div className="flex-1 overflow-hidden p-5">
                <LiveTranscript
                  segments={segments}
                  maxHeight="100%"
                  emptyMessage="Listening for speech..."
                />
              </div>
            </div>
          </div>
        )}
      </div>

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
    </>
  );
}

export default RecordPage;

registerMoonshineRoute('/record', RecordPage, 'authenticated');
