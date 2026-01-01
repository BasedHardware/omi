'use client';

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

// Types
export type AudioMode = 'mic-only' | 'mic-and-system';
export type RecordingState = 'idle' | 'initializing' | 'recording' | 'paused' | 'processing';

export interface TranscriptSegment {
  id: string;
  text: string;
  speaker: number;
  isUser: boolean;
  timestamp: number;
}

interface RecordingContextValue {
  // State
  state: RecordingState;
  audioMode: AudioMode;
  segments: TranscriptSegment[];
  duration: number;
  micLevel: number;
  systemLevel: number;
  error: string | null;

  // Widget UI state
  isWidgetExpanded: boolean;
  setWidgetExpanded: (expanded: boolean) => void;

  // Actions
  setAudioMode: (mode: AudioMode) => void;
  startRecording: () => Promise<void>;
  pauseRecording: () => void;
  resumeRecording: () => void;
  stopRecording: () => Promise<void>;
  clearError: () => void;

  // Internal setters for useRecording hook
  setState: (state: RecordingState) => void;
  setSegments: React.Dispatch<React.SetStateAction<TranscriptSegment[]>>;
  setDuration: (duration: number) => void;
  setMicLevel: (level: number) => void;
  setSystemLevel: (level: number) => void;
  setError: (error: string | null) => void;

  // Refs for hook integration
  startRecordingRef: React.MutableRefObject<(() => Promise<void>) | null>;
  pauseRecordingRef: React.MutableRefObject<(() => void) | null>;
  resumeRecordingRef: React.MutableRefObject<(() => void) | null>;
  stopRecordingRef: React.MutableRefObject<(() => Promise<void>) | null>;
}

const RecordingContext = createContext<RecordingContextValue | null>(null);

export function RecordingProvider({ children }: { children: ReactNode }) {
  // Core state
  const [state, setState] = useState<RecordingState>('idle');
  const [audioMode, setAudioMode] = useState<AudioMode>('mic-only');
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [duration, setDuration] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [systemLevel, setSystemLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Widget UI state
  const [isWidgetExpanded, setWidgetExpanded] = useState(false);

  // Refs for hook integration - these will be set by useRecording
  const startRecordingRef = useRef<(() => Promise<void>) | null>(null);
  const pauseRecordingRef = useRef<(() => void) | null>(null);
  const resumeRecordingRef = useRef<(() => void) | null>(null);
  const stopRecordingRef = useRef<(() => Promise<void>) | null>(null);

  // Action wrappers that call the refs
  const startRecording = useCallback(async () => {
    if (startRecordingRef.current) {
      await startRecordingRef.current();
    }
  }, []);

  const pauseRecording = useCallback(() => {
    if (pauseRecordingRef.current) {
      pauseRecordingRef.current();
    }
  }, []);

  const resumeRecording = useCallback(() => {
    if (resumeRecordingRef.current) {
      resumeRecordingRef.current();
    }
  }, []);

  const stopRecording = useCallback(async () => {
    if (stopRecordingRef.current) {
      await stopRecordingRef.current();
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return (
    <RecordingContext.Provider
      value={{
        // State
        state,
        audioMode,
        segments,
        duration,
        micLevel,
        systemLevel,
        error,

        // Widget UI
        isWidgetExpanded,
        setWidgetExpanded,

        // Actions
        setAudioMode,
        startRecording,
        pauseRecording,
        resumeRecording,
        stopRecording,
        clearError,

        // Internal setters
        setState,
        setSegments,
        setDuration,
        setMicLevel,
        setSystemLevel,
        setError,

        // Refs
        startRecordingRef,
        pauseRecordingRef,
        resumeRecordingRef,
        stopRecordingRef,
      }}
    >
      {children}
    </RecordingContext.Provider>
  );
}

export function useRecordingContext() {
  const context = useContext(RecordingContext);
  if (!context) {
    throw new Error('useRecordingContext must be used within a RecordingProvider');
  }
  return context;
}
