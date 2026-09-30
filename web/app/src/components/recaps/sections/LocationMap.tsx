'use client';

import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Pause, RotateCcw } from 'lucide-react';
import type { LocationPin } from '@/types/recap';
import { getConversation } from '@/lib/api';
import { StaticMapPreview } from '@/components/ui/StaticMapPreview';

// Conversation info cache type
interface ConversationInfo {
  title: string;
  emoji: string;
}

interface LocationMapProps {
  locations: LocationPin[];
  height?: number | string;
  onConversationClick?: (conversationId: string) => void;
  showPlayback?: boolean;
  // Controlled mode props (for syncing with external timeline)
  controlledIndex?: number;
  onIndexChange?: (index: number) => void;
  controlledPlaying?: boolean;
  onPlayingChange?: (playing: boolean) => void;
}

export default function LocationMap({
  locations,
  height = 320,
  onConversationClick,
  showPlayback = true,
  controlledIndex,
  onIndexChange,
  controlledPlaying,
  onPlayingChange,
}: LocationMapProps) {
  // Determine if we're in controlled mode
  const isControlled = controlledIndex !== undefined;

  // Internal state (used when not in controlled mode)
  const [internalPlaying, setInternalPlaying] = useState(false);
  const [internalIndex, setInternalIndex] = useState(-1); // -1 means show all
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [conversationCache, setConversationCache] = useState<
    Record<string, ConversationInfo>
  >({});
  const [showTitleCard, setShowTitleCard] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  const playbackRef = useRef<NodeJS.Timeout | null>(null);

  // Use controlled or internal state
  const isPlaying = isControlled ? controlledPlaying ?? false : internalPlaying;
  const currentIndex = isControlled ? controlledIndex : internalIndex;

  // Refs to track latest values for closure safety
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  // State setters that work in both modes
  const setIsPlaying = useCallback(
    (value: boolean | ((prev: boolean) => boolean)) => {
      const newValue = typeof value === 'function' ? value(isPlayingRef.current) : value;
      if (isControlled && onPlayingChange) {
        onPlayingChange(newValue);
      } else {
        setInternalPlaying(newValue);
      }
    },
    [isControlled, onPlayingChange],
  );

  // Ref to track latest index for closure safety
  const currentIndexRef = useRef(currentIndex);
  useEffect(() => {
    currentIndexRef.current = currentIndex;
  }, [currentIndex]);

  const setCurrentIndex = useCallback(
    (value: number | ((prev: number) => number)) => {
      const newValue =
        typeof value === 'function' ? value(currentIndexRef.current) : value;
      if (isControlled && onIndexChange) {
        onIndexChange(newValue);
      } else {
        setInternalIndex(newValue);
      }
    },
    [isControlled, onIndexChange],
  );

  // Parse time string to comparable value (handles both full datetime and time-only strings)
  const parseTimeValue = (timeString: string): number => {
    if (!timeString) return 0;

    // Try parsing as full date/time first
    let date = new Date(timeString);
    if (!isNaN(date.getTime())) {
      return date.getTime();
    }

    // Try parsing as time-only string (e.g., "14:30" or "14:30:00")
    const timeMatch = timeString.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (timeMatch) {
      const [, hours, minutes, seconds = '0'] = timeMatch;
      // Convert to minutes since midnight for comparison
      return (
        parseInt(hours, 10) * 3600 + parseInt(minutes, 10) * 60 + parseInt(seconds, 10)
      );
    }

    return 0;
  };

  // Sort locations by time for playback order
  const sortedLocations = useMemo(() => {
    return [...locations].sort((a, b) => parseTimeValue(a.time) - parseTimeValue(b.time));
  }, [locations]);

  // Background prefetch conversation titles
  useEffect(() => {
    if (!showPlayback || sortedLocations.length === 0) return;

    const fetchConversations = async () => {
      const uniqueIds = [
        ...new Set(
          sortedLocations
            .map((loc) => loc.conversation_id)
            .filter((id): id is string => !!id),
        ),
      ];

      const results = await Promise.all(
        uniqueIds.map(async (id) => {
          try {
            const conv = await getConversation(id);
            return { id, title: conv.structured.title, emoji: conv.structured.emoji };
          } catch {
            return null;
          }
        }),
      );

      const cache: Record<string, ConversationInfo> = {};
      results.forEach((r) => {
        if (r) cache[r.id] = { title: r.title ?? '', emoji: r.emoji ?? '' };
      });
      setConversationCache(cache);
    };

    fetchConversations();
  }, [sortedLocations, showPlayback]);

  // Playback logic
  useEffect(() => {
    if (!isPlaying) {
      if (playbackRef.current) clearTimeout(playbackRef.current);
      return;
    }

    const advancePlayback = () => {
      setCurrentIndex((prev) => {
        const next = prev + 1;
        if (next >= sortedLocations.length) {
          setIsPlaying(false);
          return prev;
        }
        // Show title card for this location
        setShowTitleCard(true);
        setTimeout(() => setShowTitleCard(false), 2000 / playbackSpeed);
        return next;
      });
    };

    // Initial advance if starting fresh
    if (currentIndex === -1) {
      setCurrentIndex(0);
      setShowTitleCard(true);
      setTimeout(() => setShowTitleCard(false), 2000 / playbackSpeed);
    }

    const interval = 3000 / playbackSpeed; // Time per location
    playbackRef.current = setTimeout(advancePlayback, interval);

    return () => {
      if (playbackRef.current) clearTimeout(playbackRef.current);
    };
  }, [isPlaying, currentIndex, sortedLocations.length, playbackSpeed]);

  // Format time with fallback for invalid dates
  const formatTime = (timeString: string) => {
    if (!timeString) return '';

    // Try parsing as full date/time first
    let date = new Date(timeString);

    // If invalid, try parsing as time-only string (e.g., "14:30" or "14:30:00")
    if (isNaN(date.getTime())) {
      // Check if it looks like a time string (HH:MM or HH:MM:SS)
      const timeMatch = timeString.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
      if (timeMatch) {
        const [, hours, minutes] = timeMatch;
        date = new Date();
        date.setHours(parseInt(hours, 10), parseInt(minutes, 10), 0, 0);
      } else {
        return timeString; // Fallback to raw string if still can't parse
      }
    }

    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  // Get display info for a location
  const getLocationDisplay = useCallback(
    (loc: LocationPin) => {
      if (loc.conversation_id && conversationCache[loc.conversation_id]) {
        const info = conversationCache[loc.conversation_id];
        return { title: info.title, emoji: info.emoji };
      }
      return { title: loc.address, emoji: '📍' };
    },
    [conversationCache],
  );

  // Playback controls
  const handlePlay = () => {
    if (currentIndex >= sortedLocations.length - 1) {
      // Reset if at end
      setCurrentIndex(-1);
    }
    setIsPlaying(true);
  };

  const handlePause = () => {
    setIsPlaying(false);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentIndex(-1);
    setShowTitleCard(false);
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value);
    setCurrentIndex(value);
    setIsPlaying(false);
    if (value >= 0) {
      setShowTitleCard(true);
      setTimeout(() => setShowTitleCard(false), 2000);
    }
  };

  const cycleSpeed = () => {
    setPlaybackSpeed((prev) => {
      if (prev === 1) return 2;
      if (prev === 2) return 4;
      return 1;
    });
  };

  if (locations.length === 0) {
    return null;
  }

  const currentLocation = currentIndex >= 0 ? sortedLocations[currentIndex] : null;
  const currentDisplay = currentLocation ? getLocationDisplay(currentLocation) : null;

  // Show controls when hovering, playing, or in playback mode
  const showControls = isHovering || isPlaying || currentIndex >= 0;

  // A single stop has no playback or title card, so the map itself opens its conversation.
  const singleStopConversationId =
    sortedLocations.length === 1 ? sortedLocations[0]?.conversation_id : undefined;
  const mapAlt = `Map of ${sortedLocations.length} recap ${
    sortedLocations.length === 1 ? 'location' : 'locations'
  }`;

  return (
    <div
      className="relative"
      style={{ height: typeof height === 'number' ? `${height}px` : height || '100%' }}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      {singleStopConversationId && onConversationClick ? (
        <button
          type="button"
          onClick={() => onConversationClick(singleStopConversationId)}
          aria-label="View conversation for this location"
          className="block h-full w-full"
        >
          <StaticMapPreview pins={sortedLocations} alt="" />
        </button>
      ) : (
        <StaticMapPreview pins={sortedLocations} alt={mapAlt} />
      )}

      {/* Title card overlay */}
      <AnimatePresence>
        {showTitleCard && currentDisplay && currentLocation && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute left-1/2 top-4 z-10 -translate-x-1/2"
          >
            <button
              type="button"
              disabled={!currentLocation.conversation_id || !onConversationClick}
              onClick={() => {
                if (currentLocation.conversation_id) {
                  onConversationClick?.(currentLocation.conversation_id);
                }
              }}
              className="rounded-xl border border-white/[0.08] bg-bg-secondary/95 px-4 py-3 text-left shadow-lg backdrop-blur-sm transition-colors enabled:hover:bg-bg-tertiary disabled:cursor-default"
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{currentDisplay.emoji}</span>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {currentDisplay.title}
                  </p>
                  <p className="text-xs text-text-tertiary">
                    {formatTime(currentLocation.time)}
                  </p>
                </div>
              </div>
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Playback controls - show on hover or during playback */}
      <AnimatePresence>
        {showPlayback && sortedLocations.length > 1 && showControls && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            className="absolute bottom-3 left-3 right-3 z-10"
          >
            <div className="rounded-xl border border-white/[0.08] bg-bg-secondary/90 p-3 backdrop-blur-sm">
              <div className="flex items-center gap-3">
                {/* Play/Pause button */}
                <button
                  onClick={isPlaying ? handlePause : handlePlay}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-text-primary text-bg-primary transition-colors hover:bg-text-primary/90"
                >
                  {isPlaying ? (
                    <Pause className="h-4 w-4" />
                  ) : (
                    <Play className="ml-0.5 h-4 w-4" />
                  )}
                </button>

                {/* Timeline slider */}
                <div className="flex flex-1 items-center gap-2">
                  <input
                    type="range"
                    min="-1"
                    max={sortedLocations.length - 1}
                    value={currentIndex}
                    onChange={handleSliderChange}
                    className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-bg-tertiary [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text-primary"
                  />
                  <span className="w-12 text-right text-xs text-text-tertiary">
                    {currentIndex >= 0
                      ? `${currentIndex + 1}/${sortedLocations.length}`
                      : 'All'}
                  </span>
                </div>

                {/* Speed button */}
                <button
                  onClick={cycleSpeed}
                  className="rounded-md bg-bg-tertiary px-2 py-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
                >
                  {playbackSpeed}x
                </button>

                {/* Reset button */}
                <button
                  onClick={handleReset}
                  className="p-1.5 text-text-tertiary transition-colors hover:text-text-primary"
                  title="Reset"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
              </div>

              {/* Current time display */}
              {currentLocation && (
                <div className="mt-2 text-center">
                  <span className="text-xs font-medium text-text-primary">
                    {formatTime(currentLocation.time)}
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
