'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { useRecordingContext } from '@/components/recording/RecordingContext';
import { AudioModeSelector } from '@/components/recording/AudioModeSelector';
import { RecordingControls } from '@/components/recording/RecordingControls';
import { LiveTranscript } from '@/components/recording/LiveTranscript';
import { cn } from '@/lib/utils';
import { RECORDING_ENABLED } from '@/lib/featureFlags';

/**
 * Inner content component that uses recording context.
 * Must be rendered INSIDE MainLayout (which provides RecordingProvider).
 * Uses context directly instead of useRecording hook to avoid conflicting
 * with the RecordingController that manages the actual recording infrastructure.
 */
function RecordPageContent() {
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
      <div className="h-full flex flex-col">
        {/* Header */}
        <header className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-bg-tertiary">
          <div className="flex items-center gap-4">
            <Link
              href="/conversations"
              className="p-2 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-xl font-semibold text-text-primary">Record</h1>
          </div>

          {/* Audio mode indicator */}
          {isActive && (
            <div className="flex items-center gap-2 text-sm text-text-tertiary">
              <span>
                {audioMode === 'mic-only' ? 'Mic Only' : 'Mic + System'}
              </span>
            </div>
          )}
        </header>

        {/* Main content - Vertical stack layout */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Top section - Recording controls (compact) */}
          <div className={cn(
            "flex-shrink-0 border-b border-bg-tertiary",
            isIdle ? "py-8" : "py-4"
          )}>
            {isIdle ? (
              // Start recording UI - compact centered
              <div className="flex flex-col items-center gap-4 px-6">
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-16 h-16 rounded-full flex items-center justify-center",
                    RECORDING_ENABLED ? "bg-purple-primary/10" : "bg-bg-tertiary"
                  )}>
                    <Mic className={cn(
                      "w-8 h-8",
                      RECORDING_ENABLED ? "text-purple-primary" : "text-text-quaternary"
                    )} />
                  </div>
                  <div className="text-left">
                    <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                      {RECORDING_ENABLED ? 'Start Recording' : 'Web Recording'}
                      {!RECORDING_ENABLED && (
                        <span className="text-xs text-text-quaternary bg-bg-quaternary px-2 py-1 rounded-full">
                          Coming Soon
                        </span>
                      )}
                    </h2>
                    <p className="text-sm text-text-tertiary">
                      {RECORDING_ENABLED
                        ? 'Real-time transcription with speaker identification'
                        : 'Record conversations directly from your browser with live transcription'}
                    </p>
                  </div>
                </div>

                {RECORDING_ENABLED ? (
                  <button
                    onClick={handleStartClick}
                    className={cn(
                      'px-6 py-3 rounded-xl font-medium',
                      'bg-purple-primary hover:bg-purple-secondary text-white',
                      'transition-all transform hover:scale-105',
                      'flex items-center gap-2'
                    )}
                  >
                    <Mic className="w-5 h-5" />
                    <span>Start Recording</span>
                  </button>
                ) : (
                  <div className="text-center">
                    <p className="text-sm text-text-tertiary mb-2">
                      This feature is being deployed. Check back soon!
                    </p>
                    <Link
                      href="/conversations"
                      className={cn(
                        'inline-flex items-center gap-2 px-4 py-2 rounded-lg',
                        'text-sm text-purple-primary hover:bg-purple-primary/10',
                        'transition-colors'
                      )}
                    >
                      <ArrowLeft className="w-4 h-4" />
                      Back to Conversations
                    </Link>
                  </div>
                )}
              </div>
            ) : (
              // Recording controls - horizontal compact layout
              <div className="flex items-center justify-center gap-6 px-6">
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
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 10 }}
                      className="px-4 py-2 rounded-xl bg-error/10 border border-error/20"
                    >
                      <p className="text-sm text-error">{error}</p>
                      <button
                        onClick={clearError}
                        className="text-xs text-error/60 hover:text-error transition-colors"
                      >
                        Dismiss
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>

          {/* Bottom section - Transcript (takes remaining space) */}
          <div className="flex-1 flex flex-col overflow-hidden bg-bg-secondary">
            <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary flex items-center justify-between">
              <div>
                <h2 className="text-lg font-medium text-text-primary">Live Transcript</h2>
                <p className="text-sm text-text-tertiary">
                  {segments.length} segment{segments.length !== 1 ? 's' : ''}
                </p>
              </div>
            </div>

            <div className="flex-1 overflow-hidden p-6">
              <LiveTranscript
                segments={segments}
                maxHeight="100%"
                emptyMessage={
                  isActive
                    ? 'Listening for speech...'
                    : 'Start recording to see live transcription'
                }
              />
            </div>
          </div>
        </div>
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

/**
 * Wrapper that provides MainLayout first, then renders content inside it.
 */
function RecordContent() {
  return (
    <MainLayout hideHeader>
      <RecordPageContent />
    </MainLayout>
  );
}

export default function RecordPage() {
  return (
    <ProtectedRoute>
      <RecordContent />
    </ProtectedRoute>
  );
}
