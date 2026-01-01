'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useRecordingContext, TranscriptSegment } from '@/components/recording/RecordingContext';
import {
  createAudioCapture,
  AudioCapture,
  isAudioCaptureSupported,
} from '@/lib/audioCapture';
import {
  createTranscriptionSocket,
  TranscriptionSocket,
} from '@/lib/transcriptionSocket';

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
  } = context;

  // Refs for audio capture and WebSocket
  const audioCaptureRef = useRef<AudioCapture | null>(null);
  const transcriptionSocketRef = useRef<TranscriptionSocket | null>(null);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(0);
  const pausedDurationRef = useRef<number>(0);

  // Start recording
  const startRecording = useCallback(async () => {
    if (!isAudioCaptureSupported()) {
      setError('Audio recording is not supported in this browser');
      return;
    }

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
        mode: audioMode,
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

    setState('processing');

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

    // Reset levels
    setMicLevel(0);
    setSystemLevel(0);

    // TODO: Process conversation with backend
    // For now, just reset to idle after a short delay
    setTimeout(() => {
      setState('idle');
    }, 500);
  }, [state, setState, setMicLevel, setSystemLevel]);

  // Register action handlers with context
  useEffect(() => {
    startRecordingRef.current = startRecording;
    pauseRecordingRef.current = pauseRecording;
    resumeRecordingRef.current = resumeRecording;
    stopRecordingRef.current = stopRecording;

    return () => {
      startRecordingRef.current = null;
      pauseRecordingRef.current = null;
      resumeRecordingRef.current = null;
      stopRecordingRef.current = null;
    };
  }, [startRecording, pauseRecording, resumeRecording, stopRecording, startRecordingRef, pauseRecordingRef, resumeRecordingRef, stopRecordingRef]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
      if (audioCaptureRef.current) {
        audioCaptureRef.current.stop();
      }
      if (transcriptionSocketRef.current) {
        transcriptionSocketRef.current.disconnect();
      }
    };
  }, []);

  // Warn before closing tab during recording
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (state === 'recording' || state === 'paused') {
        e.preventDefault();
        e.returnValue = 'Recording in progress. Are you sure you want to leave?';
        return e.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [state]);

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
