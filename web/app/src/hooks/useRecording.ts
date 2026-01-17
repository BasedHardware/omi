'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useRecordingContext, TranscriptSegment, type AudioMode } from '@/components/recording/RecordingContext';
import {
  createAudioCapture,
  isAudioCaptureSupported,
} from '@/lib/audioCapture';
import { createTranscriptionSocket } from '@/lib/transcriptionSocket';
import { processInProgressConversation } from '@/lib/api';

/**
 * Hook to manage recording lifecycle.
 * Must be used within a RecordingProvider.
 * This hook connects to the context and manages audio capture + WebSocket.
 */
export function useRecording() {
  const context = useRecordingContext();
  const {
    state,
    audioMode,
    segments,
    duration,
    micLevel,
    systemLevel,
    error,
    isWidgetExpanded,
    setWidgetExpanded,
    setState,
    setSegments,
    setDuration,
    setMicLevel,
    setSystemLevel,
    setError,
    setAudioMode,
    startRecordingRef,
    pauseRecordingRef,
    resumeRecordingRef,
    stopRecordingRef,
    // Shared refs from context - these persist across component mounts/unmounts
    audioCaptureRef,
    transcriptionSocketRef,
    durationIntervalRef,
    startTimeRef,
    pausedDurationRef,
  } = context;

  // Local ref for preventing state updates after unmount (this one is local since it's component-specific)
  const isMountedRef = useRef<boolean>(true);

  // Start recording
  const startRecording = useCallback(async (overrideMode?: AudioMode) => {
    if (!isAudioCaptureSupported()) {
      setError('Audio recording is not supported in this browser');
      return;
    }

    // Use override mode if provided, otherwise use context audioMode
    const effectiveMode = overrideMode ?? audioMode;

    setState('initializing');
    setSegments([]);
    setDuration(0);
    setError(null);
    startTimeRef.current = Date.now();
    pausedDurationRef.current = 0;

    try {
      // Create transcription socket
      const socket = createTranscriptionSocket({
        onSegment: (segment: TranscriptSegment) => {
          if (!isMountedRef.current) return;
          setSegments((prev) => {
            // Update existing segment or add new one
            const existingIndex = prev.findIndex((s) => s.id === segment.id);
            if (existingIndex >= 0) {
              const updated = [...prev];
              updated[existingIndex] = segment;
              return updated;
            }
            return [...prev, segment];
          });
        },
        onError: (err) => {
          console.error('Transcription socket error:', err);
          // Don't set error state for socket issues - just log them
        },
        onConnected: () => {
          console.log('Transcription socket connected');
        },
        onDisconnected: () => {
          console.log('Transcription socket disconnected');
        },
      });

      transcriptionSocketRef.current = socket;

      // Connect WebSocket
      await socket.connect();

      // Create audio capture
      const audioCapture = createAudioCapture({
        mode: effectiveMode,
        onAudioData: (pcmData) => {
          socket.sendAudio(pcmData);
        },
        onMicLevel: setMicLevel,
        onSystemLevel: setSystemLevel,
        onError: (err) => {
          setError(err);
        },
      });

      audioCaptureRef.current = audioCapture;

      // Start audio capture
      await audioCapture.start();

      // Start duration timer
      durationIntervalRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setDuration(elapsed - pausedDurationRef.current);
      }, 1000);

      setState('recording');

      // Expand widget when recording starts
      setWidgetExpanded(true);
    } catch (err) {
      console.error('Failed to start recording:', err);
      const message = err instanceof Error ? err.message : 'Failed to start recording';
      setError(message);
      setState('idle');

      // Cleanup on error
      if (transcriptionSocketRef.current) {
        transcriptionSocketRef.current.disconnect();
        transcriptionSocketRef.current = null;
      }
    }
  }, [audioMode, setState, setSegments, setDuration, setError, setMicLevel, setSystemLevel, setWidgetExpanded]);

  // Pause recording
  const pauseRecording = useCallback(() => {
    if (state !== 'recording') return;

    if (audioCaptureRef.current) {
      audioCaptureRef.current.pause();
    }

    // Track paused duration
    pausedDurationRef.current = Math.floor((Date.now() - startTimeRef.current) / 1000) - duration;

    setState('paused');
    setMicLevel(0);
    setSystemLevel(0);
  }, [state, duration, setState, setMicLevel, setSystemLevel]);

  // Resume recording
  const resumeRecording = useCallback(() => {
    if (state !== 'paused') return;

    if (audioCaptureRef.current) {
      audioCaptureRef.current.resume();
    }

    // Adjust start time to account for pause
    startTimeRef.current = Date.now() - (duration * 1000);

    setState('recording');
  }, [state, duration, setState]);

  // Stop recording
  const stopRecording = useCallback(async () => {
    if (state !== 'recording' && state !== 'paused') return;

    // Stop duration timer
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }

    // Stop audio capture
    if (audioCaptureRef.current) {
      audioCaptureRef.current.stop();
      audioCaptureRef.current = null;
    }

    // Disconnect WebSocket
    if (transcriptionSocketRef.current) {
      transcriptionSocketRef.current.disconnect();
      transcriptionSocketRef.current = null;
    }

    // Reset levels and state immediately - user can start a new recording
    setMicLevel(0);
    setSystemLevel(0);
    setState('idle');

    // Process the conversation in the background - don't block the user
    processInProgressConversation()
      .then((result) => {
        if (result?.conversation) {
          console.log('Conversation saved:', result.conversation.id);
          // Optionally show a toast notification here
        } else {
          console.log('No in-progress conversation found');
        }
      })
      .catch((err) => {
        console.error('Failed to process conversation:', err);
        // Optionally show an error toast here
      });
  }, [state, setState, setMicLevel, setSystemLevel]);

  // Register action handlers with context
  // Note: We do NOT clear refs on unmount - they should persist across navigation
  // as long as the RecordingProvider is mounted
  useEffect(() => {
    startRecordingRef.current = startRecording;
    pauseRecordingRef.current = pauseRecording;
    resumeRecordingRef.current = resumeRecording;
    stopRecordingRef.current = stopRecording;
  }, [startRecording, pauseRecording, resumeRecording, stopRecording, startRecordingRef, pauseRecordingRef, resumeRecordingRef, stopRecordingRef]);

  // Track mounted state for this hook instance
  // Note: We do NOT cleanup audio/WebSocket on unmount because they are shared via context
  // and should persist across navigation. Cleanup only happens via explicit stopRecording().
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Warn before closing tab during recording and cleanup on page hide
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (state === 'recording' || state === 'paused') {
        e.preventDefault();
        e.returnValue = 'Recording in progress. Are you sure you want to leave?';
        return e.returnValue;
      }
    };

    // Cleanup resources when page is actually hidden/closed
    const handlePageHide = () => {
      if (state === 'recording' || state === 'paused') {
        // Synchronously disconnect to ensure cleanup happens before page unloads
        if (audioCaptureRef.current) {
          audioCaptureRef.current.stop();
        }
        if (transcriptionSocketRef.current) {
          transcriptionSocketRef.current.disconnect();
        }
        if (durationIntervalRef.current) {
          clearInterval(durationIntervalRef.current);
        }
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('pagehide', handlePageHide);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [state, audioCaptureRef, transcriptionSocketRef, durationIntervalRef]);

  return {
    // State
    state,
    audioMode,
    segments,
    duration,
    micLevel,
    systemLevel,
    error,
    isWidgetExpanded,

    // Actions
    setAudioMode,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    setWidgetExpanded,
    clearError: context.clearError,

    // Computed
    isRecording: state === 'recording',
    isPaused: state === 'paused',
    isIdle: state === 'idle',
    isInitializing: state === 'initializing',
    isProcessing: state === 'processing',
  };
}
