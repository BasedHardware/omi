'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { transcribeVoiceMessage } from '@/lib/api';

type RecordingState = 'idle' | 'recording' | 'transcribing';

interface InlineVoiceRecorderProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

/**
 * Inline voice recorder that sits next to the send button.
 * Click to start recording, click again to stop and transcribe.
 * The mic button stays visible after transcription for continuous use.
 */
export function InlineVoiceRecorder({ onTranscript, disabled }: InlineVoiceRecorderProps) {
  const [state, setState] = useState<RecordingState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Check if browser supports recording
  const isSupported = typeof navigator !== 'undefined' &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function';

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const startRecording = async () => {
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Start recording
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4',
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;

        // Process audio
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await processAudio(audioBlob);
      };

      mediaRecorder.start(100); // Collect data every 100ms
      setState('recording');
      setDuration(0);

      // Start duration counter
      durationIntervalRef.current = setInterval(() => {
        setDuration(d => d + 1);
      }, 1000);
    } catch (err) {
      console.error('Failed to start recording:', err);
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setError('Microphone access denied');
      } else {
        setError('Failed to start recording');
      }
    }
  };

  const stopRecording = () => {
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const processAudio = async (audioBlob: Blob) => {
    setState('transcribing');

    try {
      const transcript = await transcribeVoiceMessage(audioBlob);
      if (transcript) {
        onTranscript(transcript);
      } else {
        setError('No speech detected');
      }
    } catch (err) {
      console.error('Transcription failed:', err);
      setError('Failed to transcribe');
    } finally {
      setState('idle');
    }
  };

  const handleClick = useCallback(() => {
    if (state === 'idle') {
      startRecording();
    } else if (state === 'recording') {
      stopRecording();
    }
    // Do nothing if transcribing
  }, [state]);

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (!isSupported) return null;

  // Clear error after 3 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return (
    <div className="flex items-center gap-2">
      {/* Error message */}
      {error && (
        <span className="text-xs text-error whitespace-nowrap">{error}</span>
      )}

      {/* Duration display when recording */}
      {state === 'recording' && (
        <div className="flex items-center gap-2">
          {/* Pulsing red dot */}
          <div className="relative">
            <div
              className="absolute inset-0 rounded-full bg-error/40 animate-ping"
              style={{ animationDuration: '1s' }}
            />
            <div className="w-2 h-2 rounded-full bg-error" />
          </div>
          <span className="text-sm text-text-secondary font-mono tabular-nums">
            {formatDuration(duration)}
          </span>
        </div>
      )}

      {/* Transcribing indicator */}
      {state === 'transcribing' && (
        <span className="text-xs text-text-tertiary">Transcribing...</span>
      )}

      {/* Mic button */}
      <button
        onClick={handleClick}
        disabled={disabled || state === 'transcribing'}
        className={cn(
          'p-2 rounded-lg flex-shrink-0',
          'transition-all duration-200',
          state === 'idle' && 'text-text-tertiary hover:text-purple-primary hover:bg-bg-tertiary',
          state === 'recording' && 'text-white bg-error hover:bg-error/80 animate-pulse',
          state === 'transcribing' && 'text-text-quaternary cursor-not-allowed',
          'disabled:opacity-50 disabled:cursor-not-allowed'
        )}
        title={
          state === 'idle' ? 'Click to start recording' :
          state === 'recording' ? 'Click to stop and transcribe' :
          'Transcribing...'
        }
      >
        {state === 'transcribing' ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          <Mic className="w-5 h-5" />
        )}
      </button>
    </div>
  );
}
