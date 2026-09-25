'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Headphones, Volume2, ChevronDown, ChevronUp, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AudioMode } from './RecordingContext';
import { isSystemAudioSupported } from '@/lib/audioCapture';

interface AudioModeSelectorProps {
  selectedMode: AudioMode;
  onModeSelect: (mode: AudioMode) => void;
  onStartRecording: () => void;
  onCancel: () => void;
}

export function AudioModeSelector({
  selectedMode,
  onModeSelect,
  onStartRecording,
  onCancel,
}: AudioModeSelectorProps) {
  const [showDetails, setShowDetails] = useState(false);
  const systemAudioSupported = isSystemAudioSupported();

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="w-full max-w-md rounded-2xl border border-bg-tertiary bg-bg-secondary p-6 shadow-strong"
    >
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">Choose Audio Source</h2>
        <button
          onClick={onCancel}
          className="rounded-lg p-1.5 text-text-tertiary transition-colors hover:bg-bg-tertiary hover:text-text-secondary"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Mode Options */}
      <div className="mb-6 space-y-3">
        {/* Mic Only */}
        <button
          onClick={() => onModeSelect('mic-only')}
          className={cn(
            'w-full rounded-xl border-2 p-4 text-left transition-all',
            selectedMode === 'mic-only'
              ? 'border-text-primary bg-bg-tertiary'
              : 'border-bg-tertiary hover:border-bg-quaternary hover:bg-bg-tertiary/50',
          )}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'rounded-xl p-2.5',
                selectedMode === 'mic-only'
                  ? 'bg-text-primary text-bg-primary'
                  : 'bg-bg-tertiary text-text-secondary',
              )}
            >
              <Volume2 className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary">Microphone Only</span>
                {selectedMode === 'mic-only' && (
                  <span className="rounded-full bg-bg-quaternary px-2 py-0.5 text-xs text-text-secondary">
                    Selected
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-text-tertiary">
                Best for speaker setups. Mic picks up your voice and any audio from
                speakers.
              </p>
            </div>
          </div>
        </button>

        {/* Mic + System */}
        <button
          onClick={() => systemAudioSupported && onModeSelect('mic-and-system')}
          disabled={!systemAudioSupported}
          className={cn(
            'w-full rounded-xl border-2 p-4 text-left transition-all',
            !systemAudioSupported && 'cursor-not-allowed opacity-50',
            selectedMode === 'mic-and-system'
              ? 'border-text-primary bg-bg-tertiary'
              : 'border-bg-tertiary hover:border-bg-quaternary hover:bg-bg-tertiary/50',
          )}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'rounded-xl p-2.5',
                selectedMode === 'mic-and-system'
                  ? 'bg-text-primary text-bg-primary'
                  : 'bg-bg-tertiary text-text-secondary',
              )}
            >
              <Headphones className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary">Mic + System Audio</span>
                {selectedMode === 'mic-and-system' && (
                  <span className="rounded-full bg-bg-quaternary px-2 py-0.5 text-xs text-text-secondary">
                    Selected
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-text-tertiary">
                Best for headphone users. Captures your voice and computer audio directly.
              </p>
              {!systemAudioSupported && (
                <p className="mt-1 text-sm text-error">Not supported in this browser</p>
              )}
            </div>
          </div>
        </button>
      </div>

      {/* Learn More */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="mb-4 flex w-full items-center justify-center gap-2 text-sm text-text-tertiary transition-colors hover:text-text-secondary"
      >
        <span>When to use each option</span>
        {showDetails ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </button>

      <AnimatePresence>
        {showDetails && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mb-4 rounded-xl bg-bg-tertiary/50 p-4 text-sm">
              <div className="space-y-4">
                <div>
                  <div className="mb-1 flex items-center gap-2 font-medium text-text-primary">
                    <Volume2 className="h-4 w-4" />
                    <span>Using Speakers</span>
                  </div>
                  <p className="pl-6 text-text-tertiary">
                    Your microphone will pick up both your voice AND sound from your
                    speakers. In a video call, both sides of the conversation will be
                    captured.
                    <strong className="text-text-secondary">
                      {' '}
                      Use &quot;Mic Only&quot;.
                    </strong>
                  </p>
                </div>

                <div>
                  <div className="mb-1 flex items-center gap-2 font-medium text-text-primary">
                    <Headphones className="h-4 w-4" />
                    <span>Using Headphones</span>
                  </div>
                  <p className="pl-6 text-text-tertiary">
                    Headphones send audio directly to your ears, so your mic only captures
                    your voice. To capture the other person in a call, you need system
                    audio.
                    <strong className="text-text-secondary">
                      {' '}
                      Use &quot;Mic + System&quot;.
                    </strong>
                  </p>
                </div>

                <div className="border-t border-bg-quaternary pt-2">
                  <p className="text-xs text-text-quaternary">
                    System audio requires sharing a browser tab or window. You&apos;ll be
                    prompted to select what to share when recording starts.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Start Button */}
      <button
        onClick={onStartRecording}
        className={cn(
          'w-full rounded-xl px-4 py-3 font-medium transition-all',
          'bg-text-primary text-bg-primary hover:bg-text-secondary',
          'flex items-center justify-center gap-2',
        )}
      >
        <Mic className="h-5 w-5" />
        <span>Start Recording</span>
      </button>
    </motion.div>
  );
}
