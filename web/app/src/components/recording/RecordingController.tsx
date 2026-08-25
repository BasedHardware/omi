'use client';

import { useEffect, useRef } from 'react';
import { useRecording } from '@/hooks/useRecording';
import { useRecordingContext } from './RecordingContext';
import {
  createRecordingChannel,
  broadcastStateUpdate,
  broadcastSegmentsUpdate,
  type RecordingBroadcastMessage,
} from '@/lib/recordingBroadcast';

/**
 * Controller component that initializes recording hooks and broadcast communication.
 * Should be mounted once inside RecordingProvider.
 * This ensures handlers are registered consistently.
 */
export function RecordingController() {
  // Initialize recording hooks - this registers the action handlers with context
  useRecording();

  // Get context for broadcasting
  const {
    state,
    audioMode,
    segments,
    duration,
    micLevel,
    systemLevel,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
  } = useRecordingContext();

  const channelRef = useRef<BroadcastChannel | null>(null);

  // Initialize broadcast channel
  useEffect(() => {
    const channel = createRecordingChannel();
    if (!channel) return;

    channelRef.current = channel;

    // Handle messages from pop-out windows
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    channel.onmessage = (event: MessageEvent<any>) => {
      const message = event.data;

      switch (message.type) {
        case 'command':
          if (message.command === 'start') {
            // Pass audio mode directly to startRecording to avoid race condition
            startRecording(message.audioMode);
          } else if (message.command === 'pause') pauseRecording();
          else if (message.command === 'resume') resumeRecording();
          else if (message.command === 'stop') stopRecording();
          break;
        case 'request-state':
          // Send current state to the requesting window
          broadcastStateUpdate(channel, state, audioMode, duration, micLevel, systemLevel);
          broadcastSegmentsUpdate(channel, segments);
          break;
      }
    };

    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, [startRecording, pauseRecording, resumeRecording, stopRecording]);

  // Broadcast state updates when state changes
  useEffect(() => {
    if (channelRef.current) {
      broadcastStateUpdate(channelRef.current, state, audioMode, duration, micLevel, systemLevel);
    }
  }, [state, audioMode, duration, micLevel, systemLevel]);

  // Broadcast segments updates when segments change
  useEffect(() => {
    if (channelRef.current) {
      broadcastSegmentsUpdate(channelRef.current, segments);
    }
  }, [segments]);

  // This component doesn't render anything
  return null;
}
