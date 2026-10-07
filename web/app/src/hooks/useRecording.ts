'use client';

import { useEffect, useRef, useCallback } from 'react';
import {
  useRecordingContext,
  TranscriptSegment,
  type AudioMode,
} from '@/components/recording/RecordingContext';
import { createAudioCapture, isAudioCaptureSupported } from '@/lib/audioCapture';
import { createTranscriptionSocket } from '@/lib/transcriptionSocket';
import { finalizeConversationById, getTranscriptionPreferences } from '@/lib/api';
import { applyLiveTranscriptSegment } from '@/lib/transcriptSegments';

interface RecordingAttempt {
  socket: ReturnType<typeof createTranscriptionSocket> | null;
  capture: ReturnType<typeof createAudioCapture> | null;
  timer: ReturnType<typeof setInterval> | null;
  conversationId: string | null;
  started: boolean;
}

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
  const attemptRef = useRef<RecordingAttempt | null>(null);

  // Use attempt-owned resources: late startup cleanup must never stop a replacement.
  const release = useCallback(
    (attempt: RecordingAttempt) => {
      if (attempt.timer) clearInterval(attempt.timer);
      attempt.capture?.stop();
      attempt.socket?.disconnect();
      if (audioCaptureRef.current === attempt.capture) audioCaptureRef.current = null;
      if (transcriptionSocketRef.current === attempt.socket)
        transcriptionSocketRef.current = null;
      if (durationIntervalRef.current === attempt.timer)
        durationIntervalRef.current = null;
    },
    [audioCaptureRef, transcriptionSocketRef, durationIntervalRef],
  );

  // Start recording
  const startRecording = useCallback(
    async (overrideMode?: AudioMode) => {
      if (attemptRef.current) return;
      if (!isAudioCaptureSupported()) {
        setError('Audio recording is not supported in this browser');
        return;
      }

      // Use override mode if provided, otherwise use context audioMode
      const effectiveMode = overrideMode ?? audioMode;

      // Claim ownership before any await, including preferences and permissions.
      const attempt: RecordingAttempt = {
        socket: null,
        capture: null,
        timer: null,
        conversationId: null,
        started: false,
      };
      attemptRef.current = attempt;
      const isCurrent = () => isMountedRef.current && attemptRef.current === attempt;
      setState('initializing');
      setSegments([]);
      setDuration(0);
      setError(null);
      startTimeRef.current = Date.now();
      pausedDurationRef.current = 0;

      try {
        // Fetch user's transcription preferences to get language and single_language_mode
        // If single_language_mode is true, we must send the specific language (not 'multi')
        // to avoid the backend falling back to English
        let language = 'multi';
        try {
          const prefs = await getTranscriptionPreferences();
          // Use user's language if set, or 'multi' for multi-language detection
          // When single_language_mode is true, the backend needs the specific language
          language = prefs.language || 'multi';
        } catch (langErr) {
          console.warn(
            'Failed to fetch transcription preferences, using multi:',
            langErr,
          );
        }

        if (!isCurrent()) return;

        // Create transcription socket
        const clientConversationId = crypto.randomUUID();
        attempt.conversationId = clientConversationId;
        const socket = createTranscriptionSocket({
          language,
          clientConversationId,
          onSegment: (segment: TranscriptSegment) => {
            if (!isCurrent()) return;
            // Bound the live UI list so ~1h sessions do not freeze Chrome (#5399).
            // Server audio still holds the full session for finalize-on-stop.
            setSegments((prev) => applyLiveTranscriptSegment(prev, segment));
          },
          onConversationSession: (conversationId) => {
            if (isCurrent()) attempt.conversationId = conversationId;
          },
          onError: (err) => {
            if (!isCurrent()) return;
            console.error('Transcription socket error:', err);
            // Don't set error state for socket issues - just log them
          },
          onConnected: () => {
            // Socket connected
          },
          onDisconnected: () => {
            // Surface disconnects that leave recording "alive" while audio drops
            // (#5399 / #10941). Token-refresh close events are ignored inside the socket.
            if (!isCurrent()) return;
            console.warn(
              'Transcription socket disconnected while recording may still be active',
            );
          },
        });

        attempt.socket = socket;
        transcriptionSocketRef.current = socket;

        // Connect WebSocket
        await socket.connect();
        if (!isCurrent()) {
          release(attempt);
          return;
        }

        // Create audio capture
        const audioCapture = createAudioCapture({
          mode: effectiveMode,
          onAudioData: (pcmData) => {
            if (isCurrent()) socket.sendAudio(pcmData);
          },
          onMicLevel: (level) => {
            if (isCurrent()) setMicLevel(level);
          },
          onSystemLevel: (level) => {
            if (isCurrent()) setSystemLevel(level);
          },
          onError: (err) => {
            if (isCurrent()) setError(err);
          },
        });

        attempt.capture = audioCapture;
        audioCaptureRef.current = audioCapture;

        // Start audio capture
        await audioCapture.start();
        if (!isCurrent()) {
          release(attempt);
          return;
        }
        attempt.started = true;

        // Start duration timer
        attempt.timer = durationIntervalRef.current = setInterval(() => {
          if (!isCurrent()) return;
          const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
          setDuration(elapsed - pausedDurationRef.current);
        }, 1000);

        setState('recording');

        // Expand widget when recording starts
        setWidgetExpanded(true);
      } catch (err) {
        const current = isCurrent();
        if (current) attemptRef.current = null;
        release(attempt);
        if (!current) return;
        console.error('Failed to start recording:', err);
        const message = err instanceof Error ? err.message : 'Failed to start recording';
        setError(message);
        setState('idle');
      }
    },
    [
      audioMode,
      release,
      setState,
      setSegments,
      setDuration,
      setError,
      setMicLevel,
      setSystemLevel,
      setWidgetExpanded,
    ],
  );

  // Pause recording
  const pauseRecording = useCallback(() => {
    if (state !== 'recording') return;

    if (audioCaptureRef.current) {
      audioCaptureRef.current.pause();
    }

    // Track paused duration
    pausedDurationRef.current =
      Math.floor((Date.now() - startTimeRef.current) / 1000) - duration;

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
    startTimeRef.current = Date.now() - duration * 1000;

    setState('recording');
  }, [state, duration, setState]);

  // Stop recording
  const stopRecording = useCallback(async () => {
    const attempt = attemptRef.current;
    if (!attempt) return;
    attemptRef.current = null;
    release(attempt);

    // Reset levels and state immediately - user can start a new recording
    setMicLevel(0);
    setSystemLevel(0);
    setState('idle');

    // Process this web conversation by ID — never the shared Redis pointer (#5388).
    if (!attempt.started || !attempt.conversationId) return;
    const finalize = finalizeConversationById(attempt.conversationId);
    finalize
      .then(() => {
        // Conversation processed - could show a toast notification here
      })
      .catch((err) => {
        console.error('Failed to process conversation:', err);
        // Optionally show an error toast here
      });
  }, [release, setState, setMicLevel, setSystemLevel]);

  // Register action handlers with context
  // The root controller stays mounted across route navigation.
  useEffect(() => {
    startRecordingRef.current = startRecording;
    pauseRecordingRef.current = pauseRecording;
    resumeRecordingRef.current = resumeRecording;
    stopRecordingRef.current = stopRecording;
  }, [
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    startRecordingRef,
    pauseRecordingRef,
    resumeRecordingRef,
    stopRecordingRef,
  ]);

  // Track mounted state for this hook instance
  // The root controller survives route navigation; provider teardown retires its attempt.
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      const attempt = attemptRef.current;
      attemptRef.current = null;
      if (attempt) release(attempt);
    };
  }, [release]);

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
      const attempt = attemptRef.current;
      attemptRef.current = null;
      if (attempt) release(attempt);
      setState('idle');
      setMicLevel(0);
      setSystemLevel(0);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('pagehide', handlePageHide);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [state, release, setState, setMicLevel, setSystemLevel]);

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
