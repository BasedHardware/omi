/**
 * Cross-window communication for recording state using BroadcastChannel API.
 *
 * This allows pop-out windows to receive recording state updates and send
 * control commands back to the main window.
 */

import type { RecordingState, AudioMode, TranscriptSegment } from '@/components/recording/RecordingContext';

// Channel name for recording state sync
const CHANNEL_NAME = 'omi-recording-channel';

// Message types
export type RecordingBroadcastMessage =
  | { type: 'state-update'; state: RecordingState; audioMode: AudioMode; duration: number; micLevel: number; systemLevel: number }
  | { type: 'segments-update'; segments: TranscriptSegment[] }
  | { type: 'command'; command: 'pause' | 'resume' | 'stop' }
  | { type: 'request-state' };

/**
 * Creates a BroadcastChannel for recording state communication.
 * Returns null if BroadcastChannel is not supported.
 */
export function createRecordingChannel(): BroadcastChannel | null {
  if (typeof window === 'undefined' || !('BroadcastChannel' in window)) {
    return null;
  }
  return new BroadcastChannel(CHANNEL_NAME);
}

/**
 * Broadcasts a state update to all listening windows
 */
export function broadcastStateUpdate(
  channel: BroadcastChannel,
  state: RecordingState,
  audioMode: AudioMode,
  duration: number,
  micLevel: number,
  systemLevel: number
): void {
  const message: RecordingBroadcastMessage = {
    type: 'state-update',
    state,
    audioMode,
    duration,
    micLevel,
    systemLevel,
  };
  channel.postMessage(message);
}

/**
 * Broadcasts transcript segments to all listening windows
 */
export function broadcastSegmentsUpdate(
  channel: BroadcastChannel,
  segments: TranscriptSegment[]
): void {
  const message: RecordingBroadcastMessage = {
    type: 'segments-update',
    segments,
  };
  channel.postMessage(message);
}

/**
 * Sends a command to control recording (pause, resume, stop)
 */
export function sendRecordingCommand(
  channel: BroadcastChannel,
  command: 'pause' | 'resume' | 'stop'
): void {
  const message: RecordingBroadcastMessage = {
    type: 'command',
    command,
  };
  channel.postMessage(message);
}

/**
 * Requests current state from the main window
 */
export function requestCurrentState(channel: BroadcastChannel): void {
  const message: RecordingBroadcastMessage = {
    type: 'request-state',
  };
  channel.postMessage(message);
}
