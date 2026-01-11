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
      className="bg-bg-secondary rounded-2xl border border-bg-tertiary shadow-strong p-6 max-w-md w-full"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-text-primary">Choose Audio Source</h2>
        <button
          onClick={onCancel}
          className="p-1.5 rounded-lg text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Mode Options */}
      <div className="space-y-3 mb-6">
        {/* Mic Only */}
        <button
          onClick={() => onModeSelect('mic-only')}
          className={cn(
            'w-full p-4 rounded-xl border-2 text-left transition-all',
            selectedMode === 'mic-only'
              ? 'border-purple-primary bg-purple-primary/10'
              : 'border-bg-tertiary hover:border-bg-quaternary hover:bg-bg-tertiary/50'
          )}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'p-2.5 rounded-xl',
                selectedMode === 'mic-only'
                  ? 'bg-purple-primary text-white'
                  : 'bg-bg-tertiary text-text-secondary'
              )}
            >
              <Volume2 className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary">Microphone Only</span>
                {selectedMode === 'mic-only' && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-primary/20 text-purple-primary">
                    Selected
                  </span>
                )}
              </div>
              <p className="text-sm text-text-tertiary mt-1">
                Best for speaker setups. Mic picks up your voice and any audio from speakers.
              </p>
            </div>
          </div>
        </button>

        {/* Mic + System */}
        <button
          onClick={() => systemAudioSupported && onModeSelect('mic-and-system')}
          disabled={!systemAudioSupported}
          className={cn(
            'w-full p-4 rounded-xl border-2 text-left transition-all',
            !systemAudioSupported && 'opacity-50 cursor-not-allowed',
            selectedMode === 'mic-and-system'
              ? 'border-purple-primary bg-purple-primary/10'
              : 'border-bg-tertiary hover:border-bg-quaternary hover:bg-bg-tertiary/50'
          )}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'p-2.5 rounded-xl',
                selectedMode === 'mic-and-system'
                  ? 'bg-purple-primary text-white'
                  : 'bg-bg-tertiary text-text-secondary'
              )}
            >
              <Headphones className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary">Mic + System Audio</span>
                {selectedMode === 'mic-and-system' && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-primary/20 text-purple-primary">
                    Selected
                  </span>
                )}
              </div>
              <p className="text-sm text-text-tertiary mt-1">
                Best for headphone users. Captures your voice and computer audio directly.
              </p>
              {!systemAudioSupported && (
                <p className="text-sm text-error mt-1">Not supported in this browser</p>
              )}
            </div>
          </div>
        </button>
      </div>

      {/* Learn More */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="w-full flex items-center justify-center gap-2 text-sm text-text-tertiary hover:text-text-secondary transition-colors mb-4"
      >
        <span>When to use each option</span>
        {showDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      <AnimatePresence>
        {showDetails && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="bg-bg-tertiary/50 rounded-xl p-4 mb-4 text-sm">
              <div className="space-y-4">
                <div>
                  <div className="flex items-center gap-2 text-text-primary font-medium mb-1">
                    <Volume2 className="w-4 h-4" />
                    <span>Using Speakers</span>
                  </div>
                  <p className="text-text-tertiary pl-6">
                    Your microphone will pick up both your voice AND sound from your speakers.
                    In a video call, both sides of the conversation will be captured.
                    <strong className="text-text-secondary"> Use &quot;Mic Only&quot;.</strong>
                  </p>
                </div>

                <div>
                  <div className="flex items-center gap-2 text-text-primary font-medium mb-1">
                    <Headphones className="w-4 h-4" />
                    <span>Using Headphones</span>
                  </div>
                  <p className="text-text-tertiary pl-6">
                    Headphones send audio directly to your ears, so your mic only captures your voice.
                    To capture the other person in a call, you need system audio.
                    <strong className="text-text-secondary"> Use &quot;Mic + System&quot;.</strong>
                  </p>
                </div>

                <div className="pt-2 border-t border-bg-quaternary">
                  <p className="text-text-quaternary text-xs">
                    System audio requires sharing a browser tab or window. You&apos;ll be prompted to select
                    what to share when recording starts.
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
          'w-full py-3 px-4 rounded-xl font-medium transition-all',
          'bg-purple-primary hover:bg-purple-secondary text-white',
          'flex items-center justify-center gap-2'
        )}
      >
        <Mic className="w-5 h-5" />
        <span>Start Recording</span>
      </button>
    </motion.div>
  );
}
