'use client';

import { useRecording } from '@/hooks/useRecording';

/**
 * Controller component that initializes recording hooks.
 * Should be mounted once inside RecordingProvider.
 * This ensures handlers are registered consistently.
 */
export function RecordingController() {
  // Initialize recording hooks - this registers the action handlers with context
  useRecording();

  // This component doesn't render anything
  return null;
}
