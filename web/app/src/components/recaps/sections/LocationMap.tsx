'use client';

import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap, ZoomControl } from 'react-leaflet';
import L from 'leaflet';
import { MessageSquare, Play, Pause, RotateCcw } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { LocationPin } from '@/types/recap';
import { getConversation } from '@/lib/api';
import 'leaflet/dist/leaflet.css';

// Conversation info cache type
interface ConversationInfo {
  title: string;
  emoji: string;
}

// Create numbered marker for journey sequence
function createNumberedIcon(num: number, isActive: boolean = false, isVisible: boolean = true) {
  const size = isActive ? 32 : 24;
  const fontSize = isActive ? 13 : 11;
  const opacity = isVisible ? 1 : 0.3;
  const glow = isActive ? 'box-shadow: 0 0 12px 4px rgba(139, 92, 246, 0.5);' : 'box-shadow: 0 2px 4px rgba(0,0,0,0.3);';

  return L.divIcon({
    className: 'custom-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background: #8B5CF6;
      border: 2px solid white;
      border-radius: 50%;
      ${glow}
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: ${fontSize}px;
      font-weight: 600;
      color: white;
      font-family: system-ui, -apple-system, sans-serif;
      opacity: ${opacity};
      transition: all 0.3s ease;
    ">${num}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
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

// Component to fit bounds when locations change
function FitBounds({ locations }: { locations: LocationPin[] }) {
  const map = useMap();
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    if (locations.length === 0) return;

    // Stop any ongoing animations
    map.stop();

    const fitMapBounds = () => {
      if (!isMountedRef.current) return;

      const bounds = L.latLngBounds(
        locations.map((loc) => [loc.latitude, loc.longitude])
      );

      // More padding at bottom to leave room for playback controls
      map.fitBounds(bounds, {
        paddingTopLeft: [50, 50],
        paddingBottomRight: [50, 100], // Extra bottom padding for controls
        maxZoom: 14,
        animate: false, // Disable animation to prevent unmount errors
      });
    };

    // Small delay to ensure container is properly sized (especially in tab layouts)
    const timeout = setTimeout(fitMapBounds, 100);

    // Also re-fit when map container is resized
    map.invalidateSize();

    return () => {
      isMountedRef.current = false;
      clearTimeout(timeout);
      // Wrap in try-catch as map may be in invalid state during unmount
      try {
        map.stop();
      } catch {
        // Ignore - map already disposed
      }
    };
  }, [map, locations]);

  return null;
}

// Component to pan to current location during playback
function PanToLocation({ location, enabled }: { location: LocationPin | null; enabled: boolean }) {
  const map = useMap();
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    if (!enabled || !location) return;

    // Use requestAnimationFrame to ensure we're in a valid state
    const frameId = requestAnimationFrame(() => {
      if (isMountedRef.current) {
        map.panTo([location.latitude, location.longitude], { animate: true, duration: 0.5 });
      }
    });

    return () => {
      isMountedRef.current = false;
      cancelAnimationFrame(frameId);
      try {
        map.stop();
      } catch {
        // Ignore - map already disposed
      }
    };
  }, [map, location, enabled]);

  return null;
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
  const [conversationCache, setConversationCache] = useState<Record<string, ConversationInfo>>({});
  const [showTitleCard, setShowTitleCard] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  const playbackRef = useRef<NodeJS.Timeout | null>(null);

  // Use controlled or internal state
  const isPlaying = isControlled ? (controlledPlaying ?? false) : internalPlaying;
  const currentIndex = isControlled ? controlledIndex : internalIndex;

  // Refs to track latest values for closure safety
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  // State setters that work in both modes
  const setIsPlaying = useCallback((value: boolean | ((prev: boolean) => boolean)) => {
    const newValue = typeof value === 'function' ? value(isPlayingRef.current) : value;
    if (isControlled && onPlayingChange) {
      onPlayingChange(newValue);
    } else {
      setInternalPlaying(newValue);
    }
  }, [isControlled, onPlayingChange]);

  // Ref to track latest index for closure safety
  const currentIndexRef = useRef(currentIndex);
  useEffect(() => {
    currentIndexRef.current = currentIndex;
  }, [currentIndex]);

  const setCurrentIndex = useCallback((value: number | ((prev: number) => number)) => {
    const newValue = typeof value === 'function' ? value(currentIndexRef.current) : value;
    if (isControlled && onIndexChange) {
      onIndexChange(newValue);
    } else {
      setInternalIndex(newValue);
    }
  }, [isControlled, onIndexChange]);

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
      return parseInt(hours, 10) * 3600 + parseInt(minutes, 10) * 60 + parseInt(seconds, 10);
    }

    return 0;
  };

  // Sort locations by time for the route line
  const sortedLocations = useMemo(() => {
    return [...locations].sort(
      (a, b) => parseTimeValue(a.time) - parseTimeValue(b.time)
    );
  }, [locations]);

  // Background prefetch conversation titles
  useEffect(() => {
    if (!showPlayback || sortedLocations.length === 0) return;

    const fetchConversations = async () => {
      const uniqueIds = [...new Set(
        sortedLocations
          .map(loc => loc.conversation_id)
          .filter((id): id is string => !!id)
      )];

      const results = await Promise.all(
        uniqueIds.map(async (id) => {
          try {
            const conv = await getConversation(id);
            return { id, title: conv.structured.title, emoji: conv.structured.emoji };
          } catch {
            return null;
          }
        })
      );

      const cache: Record<string, ConversationInfo> = {};
      results.forEach(r => {
        if (r) cache[r.id] = { title: r.title, emoji: r.emoji };
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
      setCurrentIndex(prev => {
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

  // Create polyline coordinates (progressive or full)
  const polylinePositions = useMemo(() => {
    if (currentIndex === -1) {
      return sortedLocations.map((loc) => [loc.latitude, loc.longitude] as [number, number]);
    }
    return sortedLocations
      .slice(0, currentIndex + 1)
      .map((loc) => [loc.latitude, loc.longitude] as [number, number]);
  }, [sortedLocations, currentIndex]);

  // Calculate center
  const center = useMemo(() => {
    if (locations.length === 0) return { lat: 0, lng: 0 };
    const lat = locations.reduce((sum, loc) => sum + loc.latitude, 0) / locations.length;
    const lng = locations.reduce((sum, loc) => sum + loc.longitude, 0) / locations.length;
    return { lat, lng };
  }, [locations]);

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
  const getLocationDisplay = useCallback((loc: LocationPin) => {
    if (loc.conversation_id && conversationCache[loc.conversation_id]) {
      const info = conversationCache[loc.conversation_id];
      return { title: info.title, emoji: info.emoji };
    }
    return { title: loc.address, emoji: '📍' };
  }, [conversationCache]);

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
    setPlaybackSpeed(prev => {
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
  const isInPlaybackMode = currentIndex >= 0;

  // Show controls when hovering, playing, or in playback mode
  const showControls = isHovering || isPlaying || currentIndex >= 0;

  return (
    <div
      className="relative"
      style={{ height: typeof height === 'number' ? `${height}px` : height || '100%' }}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      <MapContainer
        center={[center.lat, center.lng]}
        zoom={13}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={false}
        zoomControl={false}
        className="z-0 [&_.leaflet-control-zoom]:!border-none [&_.leaflet-control-zoom]:!rounded-lg [&_.leaflet-control-zoom]:!bg-bg-tertiary/80 [&_.leaflet-control-zoom]:!backdrop-blur-sm [&_.leaflet-control-zoom-in]:!text-text-secondary [&_.leaflet-control-zoom-in]:!bg-transparent [&_.leaflet-control-zoom-in]:!border-none [&_.leaflet-control-zoom-in]:!w-8 [&_.leaflet-control-zoom-in]:!h-8 [&_.leaflet-control-zoom-in]:!leading-8 [&_.leaflet-control-zoom-out]:!text-text-secondary [&_.leaflet-control-zoom-out]:!bg-transparent [&_.leaflet-control-zoom-out]:!border-none [&_.leaflet-control-zoom-out]:!w-8 [&_.leaflet-control-zoom-out]:!h-8 [&_.leaflet-control-zoom-out]:!leading-8 hover:[&_.leaflet-control-zoom-in]:!text-text-primary hover:[&_.leaflet-control-zoom-out]:!text-text-primary"
      >
        <ZoomControl position="bottomright" />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        <FitBounds locations={locations} />
        <PanToLocation location={currentLocation} enabled={isPlaying} />

        {/* Route line - progressive during playback */}
        {polylinePositions.length > 1 && (
          <Polyline
            positions={polylinePositions}
            pathOptions={{
              color: '#8B5CF6',
              weight: 3,
              opacity: 0.7,
              dashArray: isInPlaybackMode ? undefined : '5, 10',
            }}
          />
        )}

        {/* Location markers with journey numbers */}
        {sortedLocations.map((loc, idx) => {
          const isVisible = currentIndex === -1 || idx <= currentIndex;
          const isActive = idx === currentIndex;

          if (!isVisible && currentIndex !== -1) return null;

          return (
            <Marker
              key={idx}
              position={[loc.latitude, loc.longitude]}
              icon={createNumberedIcon(idx + 1, isActive, isVisible)}
            >
              <Popup className="dark-popup">
                <div className="text-sm">
                  <p className="font-medium text-gray-900">{loc.address}</p>
                  <p className="text-gray-600 text-xs mt-1">{formatTime(loc.time)}</p>
                  {loc.conversation_id && onConversationClick && (
                    <button
                      onClick={() => onConversationClick(loc.conversation_id!)}
                      className="mt-2 flex items-center gap-1 text-xs text-purple-600 hover:text-purple-700 transition-colors"
                    >
                      <MessageSquare className="w-3 h-3" />
                      <span>View conversation</span>
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Title card overlay */}
      <AnimatePresence>
        {showTitleCard && currentDisplay && currentLocation && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-4 left-1/2 -translate-x-1/2 z-10 pointer-events-none"
          >
            <div className="bg-bg-secondary/95 backdrop-blur-sm rounded-xl px-4 py-3 shadow-lg border border-white/[0.08]">
              <div className="flex items-center gap-2">
                <span className="text-lg">{currentDisplay.emoji}</span>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {currentDisplay.title}
                  </p>
                  <p className="text-xs text-text-tertiary">{formatTime(currentLocation.time)}</p>
                </div>
              </div>
            </div>
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
            <div className="bg-bg-secondary/90 backdrop-blur-sm rounded-xl p-3 border border-white/[0.08]">
            <div className="flex items-center gap-3">
              {/* Play/Pause button */}
              <button
                onClick={isPlaying ? handlePause : handlePlay}
                className="w-8 h-8 flex items-center justify-center rounded-full bg-purple-primary hover:bg-purple-primary/90 text-white transition-colors"
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </button>

              {/* Timeline slider */}
              <div className="flex-1 flex items-center gap-2">
                <input
                  type="range"
                  min="-1"
                  max={sortedLocations.length - 1}
                  value={currentIndex}
                  onChange={handleSliderChange}
                  className="flex-1 h-1 bg-bg-tertiary rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:bg-purple-primary [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:cursor-pointer"
                />
                <span className="text-xs text-text-tertiary w-12 text-right">
                  {currentIndex >= 0 ? `${currentIndex + 1}/${sortedLocations.length}` : 'All'}
                </span>
              </div>

              {/* Speed button */}
              <button
                onClick={cycleSpeed}
                className="px-2 py-1 text-xs font-medium text-text-secondary hover:text-text-primary bg-bg-tertiary rounded-md transition-colors"
              >
                {playbackSpeed}x
              </button>

              {/* Reset button */}
              <button
                onClick={handleReset}
                className="p-1.5 text-text-tertiary hover:text-text-primary transition-colors"
                title="Reset"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>

            {/* Current time display */}
            {currentLocation && (
              <div className="mt-2 text-center">
                <span className="text-xs text-purple-primary font-medium">
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
