'use client';

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useImperativeHandle,
  forwardRef,
} from 'react';
import { Play, Pause, Volume2, VolumeX, Loader2, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getConversationAudioUrlsWithPoll } from '@/lib/api';
import type { AudioFileUrlInfo } from '@/types/conversation';

interface AudioPlayerProps {
  conversationId: string;
  audioFiles: AudioFileUrlInfo[];
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
      let cancelled = false;

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

          if (firstFile.status === 'unavailable') {
            setError('Audio is no longer available for this conversation');
            setIsLoading(false);
            return;
          }

          // The backend builds playback artifacts asynchronously; poll until
          // the file is cached instead of streaming through the merge proxy
          // that used to time out on long conversations.
          const fileId = firstFile.id || '0';
          const deadline = Date.now() + 90_000;
          while (Date.now() < deadline && !cancelled) {
            const { files, pollAfterMs } = await getConversationAudioUrlsWithPoll(
              conversationId,
            );
            if (cancelled) return;
            const info = files.find((f) => f.id === fileId) ?? files[0];
            if (info?.signed_url) {
              setAudioUrl(info.signed_url);
              setIsLoading(false);
              return;
            }
            if (info?.status === 'unavailable') {
              setError('Audio is no longer available for this conversation');
              setIsLoading(false);
              return;
            }
            await new Promise((resolve) => setTimeout(resolve, pollAfterMs ?? 3000));
          }
          if (!cancelled) {
            setError('Audio is still processing — try again shortly');
            setIsLoading(false);
          }
        } catch (err) {
          console.error('Failed to load audio:', err);
          setError('Failed to load audio');
          setIsLoading(false);
        }
      }

      loadAudioUrl();

      return () => {
        cancelled = true;
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
        <div
          className={cn(
            'flex items-center gap-3 rounded-xl border border-bg-quaternary/50 bg-bg-tertiary p-3',
            'text-sm text-text-tertiary',
            className,
          )}
        >
          <VolumeX className="h-5 w-5" />
          <span>{error}</span>
        </div>
      );
    }

    return (
      <div
        className={cn(
          'flex items-center gap-3 rounded-xl border border-bg-quaternary/50 bg-bg-tertiary p-3',
          className,
        )}
      >
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
            'flex h-10 w-10 items-center justify-center rounded-full',
            'bg-text-primary text-bg-primary',
            'transition-colors hover:bg-text-primary/90',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'flex-shrink-0',
          )}
        >
          {isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : isPlaying ? (
            <Pause className="h-5 w-5" />
          ) : (
            <Play className="ml-0.5 h-5 w-5" />
          )}
        </button>

        {/* Progress bar */}
        <div className="flex flex-1 items-center gap-3">
          <span className="w-10 flex-shrink-0 text-right text-xs text-text-tertiary">
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
              'h-1.5 flex-1 cursor-pointer appearance-none rounded-full',
              'bg-bg-quaternary',
              '[&::-webkit-slider-thumb]:appearance-none',
              '[&::-webkit-slider-thumb]:w-3',
              '[&::-webkit-slider-thumb]:h-3',
              '[&::-webkit-slider-thumb]:rounded-full',
              '[&::-webkit-slider-thumb]:bg-text-primary',
              '[&::-webkit-slider-thumb]:cursor-pointer',
              '[&::-moz-range-thumb]:w-3',
              '[&::-moz-range-thumb]:h-3',
              '[&::-moz-range-thumb]:rounded-full',
              '[&::-moz-range-thumb]:bg-text-primary',
              '[&::-moz-range-thumb]:border-0',
              '[&::-moz-range-thumb]:cursor-pointer',
              'disabled:opacity-50',
            )}
            style={{
              background:
                duration > 0
                  ? `linear-gradient(to right, var(--text-primary) ${
                      (currentTime / duration) * 100
                    }%, var(--bg-quaternary) ${(currentTime / duration) * 100}%)`
                  : undefined,
            }}
          />

          <span className="w-10 flex-shrink-0 text-xs text-text-tertiary">
            {formatTime(duration)}
          </span>
        </div>

        {/* Playback speed */}
        <div className="relative">
          <button
            onClick={() => setShowSpeedMenu(!showSpeedMenu)}
            className={cn(
              'rounded-md px-2 py-1 text-xs font-medium',
              'bg-bg-quaternary text-text-secondary',
              'transition-colors hover:bg-bg-tertiary hover:text-text-primary',
            )}
          >
            {playbackSpeed}x
          </button>

          {showSpeedMenu && (
            <div className="absolute bottom-full right-0 z-10 mb-2 rounded-lg border border-bg-tertiary bg-bg-secondary py-1 shadow-lg">
              {PLAYBACK_SPEEDS.map((speed) => (
                <button
                  key={speed}
                  onClick={() => handleSpeedChange(speed)}
                  className={cn(
                    'w-full px-4 py-1.5 text-left text-xs',
                    'transition-colors hover:bg-bg-tertiary',
                    speed === playbackSpeed
                      ? 'font-medium text-text-primary'
                      : 'text-text-secondary',
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
            'rounded-md p-2',
            'text-text-secondary transition-colors hover:text-text-primary',
          )}
        >
          {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </button>

        {/* Download button */}
        <button
          onClick={handleDownload}
          disabled={!audioUrl}
          className={cn(
            'rounded-md p-2',
            'text-text-secondary transition-colors hover:text-text-primary',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
          title="Download audio"
        >
          <Download className="h-4 w-4" />
        </button>
      </div>
    );
  },
);
