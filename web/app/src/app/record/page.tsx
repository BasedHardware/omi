'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { PageHeader } from '@/components/layout/PageHeader';
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
        <PageHeader title="Record" icon={Mic} showBackButton onBack={() => window.history.back()} />

        {/* Main content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {isIdle ? (
            /* Idle — centered start prompt */
            <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6">
              <div className={cn(
                "w-14 h-14 rounded-full flex items-center justify-center",
                RECORDING_ENABLED ? "bg-primary/10" : "bg-secondary"
              )}>
                <Mic className={cn(
                  "w-7 h-7",
                  RECORDING_ENABLED ? "text-primary" : "text-muted-foreground"
                )} />
              </div>
              <div className="text-center">
                <h2 className="text-lg font-medium text-foreground flex items-center justify-center gap-2">
                  {RECORDING_ENABLED ? 'Start Recording' : 'Web Recording'}
                  {!RECORDING_ENABLED && (
                    <span className="text-[10px] text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
                      Coming Soon
                    </span>
                  )}
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {RECORDING_ENABLED
                    ? 'Real-time transcription with speaker identification'
                    : 'Record conversations directly from your browser'}
                </p>
              </div>

              {RECORDING_ENABLED ? (
                <button
                  onClick={handleStartClick}
                  className="px-5 py-2.5 rounded-full text-sm font-medium bg-primary hover:bg-primary/90 text-primary-foreground transition-colors flex items-center gap-2"
                >
                  <Mic className="w-4 h-4" />
                  Start Recording
                </button>
              ) : (
                <Link
                  href="/conversations"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm text-primary hover:bg-primary/10 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Conversations
                </Link>
              )}
            </div>
          ) : (
            /* Active — compact controls bar + transcript */
            <>
              <div className="flex-shrink-0 flex items-center justify-center gap-4 px-6 py-3 border-b border-border/50">
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
                <AnimatePresence>
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 10 }}
                      className="px-3 py-1.5 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center gap-2"
                    >
                      {error}
                      <button onClick={clearError} className="text-xs opacity-60 hover:opacity-100">Dismiss</button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Transcript */}
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-shrink-0 px-6 py-2 border-b border-border/50 flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Live Transcript
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {segments.length} segment{segments.length !== 1 ? 's' : ''}
                  </span>
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
            </>
          )}
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
