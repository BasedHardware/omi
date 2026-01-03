'use client';

import { useState, useRef, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';
import { Play, Pause, Volume2, VolumeX, Loader2, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchAudioBlob } from '@/lib/api';
import type { AudioFile } from '@/types/conversation';

interface AudioPlayerProps {
  conversationId: string;
  audioFiles: AudioFile[];
  onTimeUpdate?: (currentTime: number) => void;
  className?: string;
}

export interface AudioPlayerRef {
  seekTo: (time: number) => void;
  play: () => void;
  pause: () => void;
}

const PLAYBACK_SPEEDS = [0.75, 1, 1.25, 1.5, 2];

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export const AudioPlayer = forwardRef<AudioPlayerRef, AudioPlayerProps>(
  function AudioPlayer({ conversationId, audioFiles, onTimeUpdate, className }, ref) {
    const audioRef = useRef<HTMLAudioElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [isMuted, setIsMuted] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [playbackSpeed, setPlaybackSpeed] = useState(1);
    const [showSpeedMenu, setShowSpeedMenu] = useState(false);
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Load audio URL on mount
    useEffect(() => {
      let blobUrl: string | null = null;

      async function loadAudioUrl() {
        if (!audioFiles || audioFiles.length === 0) {
          setError('No audio files available');
          setIsLoading(false);
          return;
        }

        try {
          setIsLoading(true);
          setError(null);

          const firstFile = audioFiles[0];

          // Use signed URL if available (direct GCS access, no proxy needed)
          // This avoids timeout issues with large audio files
          if (firstFile.signed_url) {
            setAudioUrl(firstFile.signed_url);
            setIsLoading(false);
            return;
          }

          // Fallback: fetch through proxy with auth headers
          const fileId = firstFile.id || '0';
          blobUrl = await fetchAudioBlob(conversationId, fileId);
          setAudioUrl(blobUrl);
          setIsLoading(false);
        } catch (err) {
          console.error('Failed to load audio:', err);
          setError('Failed to load audio');
          setIsLoading(false);
        }
      }

      loadAudioUrl();

      // Cleanup: revoke blob URL to free memory
      return () => {
        if (blobUrl) {
          URL.revokeObjectURL(blobUrl);
        }
      };
    }, [conversationId, audioFiles]);

    // Expose methods via ref
    useImperativeHandle(ref, () => ({
      seekTo: (time: number) => {
        if (audioRef.current) {
          audioRef.current.currentTime = time;
          setCurrentTime(time);
        }
      },
      play: () => {
        audioRef.current?.play();
      },
      pause: () => {
        audioRef.current?.pause();
      },
    }));

    const handlePlayPause = useCallback(() => {
      if (!audioRef.current) return;

      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play();
      }
    }, [isPlaying]);

    const handleTimeUpdate = useCallback(() => {
      if (!audioRef.current) return;
      const time = audioRef.current.currentTime;
      setCurrentTime(time);
      onTimeUpdate?.(time);
    }, [onTimeUpdate]);

    const handleLoadedMetadata = useCallback(() => {
      if (!audioRef.current) return;
      setDuration(audioRef.current.duration);
      setIsLoading(false);
    }, []);

    const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
      if (!audioRef.current) return;
      const time = parseFloat(e.target.value);
      audioRef.current.currentTime = time;
      setCurrentTime(time);
    }, []);

    const handleSpeedChange = useCallback((speed: number) => {
      if (audioRef.current) {
        audioRef.current.playbackRate = speed;
      }
      setPlaybackSpeed(speed);
      setShowSpeedMenu(false);
    }, []);

    const toggleMute = useCallback(() => {
      if (audioRef.current) {
        audioRef.current.muted = !isMuted;
      }
      setIsMuted(!isMuted);
    }, [isMuted]);

    const handleDownload = useCallback(() => {
      if (!audioUrl) return;

      // Open the signed URL directly - browser will handle the download
      // This avoids CORS issues with fetching the blob
      window.open(audioUrl, '_blank');
    }, [audioUrl]);

    const handleError = useCallback(() => {
      setError('Failed to load audio');
      setIsLoading(false);
    }, []);

    if (!audioFiles || audioFiles.length === 0) {
      return null;
    }

    if (error) {
      return (
        <div className={cn(
          'flex items-center gap-3 p-3 rounded-xl bg-bg-tertiary border border-bg-quaternary/50',
          'text-text-tertiary text-sm',
          className
        )}>
          <VolumeX className="w-5 h-5" />
          <span>{error}</span>
        </div>
      );
    }

    return (
      <div className={cn(
        'flex items-center gap-3 p-3 rounded-xl bg-bg-tertiary border border-bg-quaternary/50',
        className
      )}>
        {/* Hidden audio element */}
        {audioUrl && (
          <audio
            ref={audioRef}
            src={audioUrl}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onError={handleError}
            onEnded={() => setIsPlaying(false)}
            preload="metadata"
          />
        )}

        {/* Play/Pause button */}
        <button
          onClick={handlePlayPause}
          disabled={isLoading}
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center',
            'bg-purple-primary text-white',
            'hover:bg-purple-secondary transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'flex-shrink-0'
          )}
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-5 h-5" />
          ) : (
            <Play className="w-5 h-5 ml-0.5" />
          )}
        </button>

        {/* Progress bar */}
        <div className="flex-1 flex items-center gap-3">
          <span className="text-xs text-text-tertiary w-10 text-right flex-shrink-0">
            {formatTime(currentTime)}
          </span>

          <input
            type="range"
            min={0}
            max={duration || 100}
            value={currentTime}
            onChange={handleSeek}
            disabled={isLoading}
            className={cn(
              'flex-1 h-1.5 rounded-full appearance-none cursor-pointer',
              'bg-bg-quaternary',
              '[&::-webkit-slider-thumb]:appearance-none',
              '[&::-webkit-slider-thumb]:w-3',
              '[&::-webkit-slider-thumb]:h-3',
              '[&::-webkit-slider-thumb]:rounded-full',
              '[&::-webkit-slider-thumb]:bg-purple-primary',
              '[&::-webkit-slider-thumb]:cursor-pointer',
              '[&::-moz-range-thumb]:w-3',
              '[&::-moz-range-thumb]:h-3',
              '[&::-moz-range-thumb]:rounded-full',
              '[&::-moz-range-thumb]:bg-purple-primary',
              '[&::-moz-range-thumb]:border-0',
              '[&::-moz-range-thumb]:cursor-pointer',
              'disabled:opacity-50'
            )}
            style={{
              background: duration > 0
                ? `linear-gradient(to right, var(--purple-primary) ${(currentTime / duration) * 100}%, var(--bg-quaternary) ${(currentTime / duration) * 100}%)`
                : undefined,
            }}
          />

          <span className="text-xs text-text-tertiary w-10 flex-shrink-0">
            {formatTime(duration)}
          </span>
        </div>

        {/* Playback speed */}
        <div className="relative">
          <button
            onClick={() => setShowSpeedMenu(!showSpeedMenu)}
            className={cn(
              'px-2 py-1 rounded-md text-xs font-medium',
              'bg-bg-quaternary text-text-secondary',
              'hover:bg-bg-tertiary hover:text-text-primary transition-colors'
            )}
          >
            {playbackSpeed}x
          </button>

          {showSpeedMenu && (
            <div className="absolute bottom-full right-0 mb-2 py-1 bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg z-10">
              {PLAYBACK_SPEEDS.map((speed) => (
                <button
                  key={speed}
                  onClick={() => handleSpeedChange(speed)}
                  className={cn(
                    'w-full px-4 py-1.5 text-xs text-left',
                    'hover:bg-bg-tertiary transition-colors',
                    speed === playbackSpeed
                      ? 'text-purple-primary font-medium'
                      : 'text-text-secondary'
                  )}
                >
                  {speed}x
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Mute button */}
        <button
          onClick={toggleMute}
          className={cn(
            'p-2 rounded-md',
            'text-text-secondary hover:text-text-primary transition-colors'
          )}
        >
          {isMuted ? (
            <VolumeX className="w-4 h-4" />
          ) : (
            <Volume2 className="w-4 h-4" />
          )}
        </button>

        {/* Download button */}
        <button
          onClick={handleDownload}
          disabled={!audioUrl}
          className={cn(
            'p-2 rounded-md',
            'text-text-secondary hover:text-text-primary transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          title="Download audio"
        >
          <Download className="w-4 h-4" />
        </button>
      </div>
    );
  }
);
