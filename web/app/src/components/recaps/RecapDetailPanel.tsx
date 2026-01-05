'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  Calendar,
  Sparkles,
  CheckSquare,
  Lightbulb,
  MapPin,
  MessageSquare,
  Clock,
  Loader2,
  Maximize2,
} from 'lucide-react';
import dynamic from 'next/dynamic';

// Dynamically import LocationMap to avoid SSR issues with Leaflet
const LocationMap = dynamic(() => import('./sections/LocationMap'), {
  ssr: false,
  loading: () => (
    <div className="h-full bg-bg-tertiary animate-pulse flex items-center justify-center">
      <MapPin className="w-8 h-8 text-text-quaternary" />
    </div>
  ),
});
import { cn } from '@/lib/utils';
import { getDailySummary, getConversation } from '@/lib/api';
import type { DailySummary, LocationPin } from '@/types/recap';
import { HighlightsSection } from './sections/HighlightsSection';
import { TasksSection } from './sections/TasksSection';
import { InsightsSection } from './sections/InsightsSection';
import { LocationsSection } from './sections/LocationsSection';
import { ConversationPreviewPanel } from './ConversationPreviewPanel';

interface RecapDetailPanelProps {
  recapId: string;
  recap?: DailySummary | null;
  onBack?: () => void;
  onConversationClick?: (conversationId: string) => void;
}

type RecapTab = 'recap' | 'journey';

// Format date for display (parse as local date, not UTC)
function formatRecapDate(dateString: string): string {
  // Parse YYYY-MM-DD as local date to avoid timezone shift
  const [year, month, day] = dateString.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

// Format duration in minutes to human-readable
function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

// Format time for journey timeline (12-hour AM/PM format)
function formatJourneyTime(timeString: string): string {
  if (!timeString) return '';

  // Try parsing as full date/time first
  let date = new Date(timeString);

  // If invalid, try parsing as time-only string (e.g., "14:30" or "14:30:00")
  if (isNaN(date.getTime())) {
    const timeMatch = timeString.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (timeMatch) {
      const [, hours, minutes] = timeMatch;
      date = new Date();
      date.setHours(parseInt(hours, 10), parseInt(minutes, 10), 0, 0);
    } else {
      return timeString; // Fallback to raw string
    }
  }

  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

// Journey Timeline component for expanded map view
interface JourneyTimelineProps {
  locations: LocationPin[];
  onConversationClick?: (conversationId: string) => void;
  currentIndex?: number; // -1 = show all, >=0 = progressive display
  onLocationClick?: (index: number) => void; // Click to jump to location
}

// Parse time string to comparable value (handles both full datetime and time-only strings)
function parseTimeValue(timeString: string): number {
  if (!timeString) return 0;

  // Try parsing as full date/time first
  const date = new Date(timeString);
  if (!isNaN(date.getTime())) {
    return date.getTime();
  }

  // Try parsing as time-only string (e.g., "14:30" or "14:30:00")
  const timeMatch = timeString.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (timeMatch) {
    const [, hours, minutes, seconds = '0'] = timeMatch;
    // Convert to seconds since midnight for comparison
    return parseInt(hours, 10) * 3600 + parseInt(minutes, 10) * 60 + parseInt(seconds, 10);
  }

  return 0;
}

function JourneyTimeline({ locations, onConversationClick, currentIndex = -1, onLocationClick }: JourneyTimelineProps) {
  const [conversationCache, setConversationCache] = useState<Record<string, { title: string; emoji: string }>>({});
  const [loading, setLoading] = useState(true);

  // Determine if we're in progressive mode
  const isProgressiveMode = currentIndex >= 0;

  // Sort locations by time (memoized to avoid infinite re-renders)
  const sortedLocations = useMemo(() => {
    return [...locations].sort(
      (a, b) => parseTimeValue(a.time) - parseTimeValue(b.time)
    );
  }, [locations]);

  // Fetch conversation details
  useEffect(() => {
    const fetchConversations = async () => {
      const uniqueIds = [...new Set(
        sortedLocations
          .map(loc => loc.conversation_id)
          .filter((id): id is string => !!id)
      )];

      if (uniqueIds.length === 0) {
        setLoading(false);
        return;
      }

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

      const cache: Record<string, { title: string; emoji: string }> = {};
      results.forEach(r => {
        if (r) cache[r.id] = { title: r.title, emoji: r.emoji };
      });
      setConversationCache(cache);
      setLoading(false);
    };

    fetchConversations();
  }, [sortedLocations]);

  const getLocationDisplay = (loc: LocationPin) => {
    if (loc.conversation_id && conversationCache[loc.conversation_id]) {
      return conversationCache[loc.conversation_id];
    }
    return { title: loc.address, emoji: '📍' };
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-white/[0.04]">
        <h4 className="text-sm font-medium text-text-primary flex items-center gap-2">
          <Clock className="w-4 h-4 text-purple-primary" />
          Your Journey
        </h4>
      </div>

      {/* Timeline list */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-3">
            {[...Array(Math.min(sortedLocations.length, 5))].map((_, i) => (
              <div key={i} className="flex gap-3 animate-pulse">
                <div className="w-8 h-8 bg-bg-tertiary rounded-full" />
                <div className="flex-1 space-y-1">
                  <div className="h-3 bg-bg-tertiary rounded w-16" />
                  <div className="h-4 bg-bg-tertiary rounded w-32" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="relative">
            {/* Vertical line connecting all items */}
            <div className="absolute left-4 top-4 bottom-4 w-px bg-purple-primary/20" />

            <div className="space-y-4">
              {sortedLocations.map((loc, idx) => {
                const display = getLocationDisplay(loc);

                // In progressive mode, determine visibility
                const isPast = !isProgressiveMode || idx < currentIndex;
                const isCurrent = isProgressiveMode && idx === currentIndex;
                const isFuture = isProgressiveMode && idx > currentIndex;

                // Hide future items during playback
                if (isFuture) return null;

                return (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: isProgressiveMode ? 0 : idx * 0.05 }}
                    className={cn(
                      "relative flex items-start gap-3 group",
                      onLocationClick && "cursor-pointer"
                    )}
                    onClick={() => onLocationClick?.(idx)}
                  >
                    {/* Numbered marker */}
                    <div className={cn(
                      "relative z-10 w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold transition-all",
                      isCurrent ? "bg-purple-primary shadow-lg ring-2 ring-purple-primary/50 scale-110" : "bg-purple-primary shadow-md",
                      isPast && !isCurrent && "opacity-60"
                    )}>
                      {idx + 1}
                    </div>

                    {/* Content */}
                    <div
                      className={cn(
                        "flex-1 py-1 transition-opacity",
                        isPast && !isCurrent && "opacity-60",
                        isCurrent && "opacity-100"
                      )}
                      onClick={(e) => {
                        if (loc.conversation_id && onConversationClick) {
                          e.stopPropagation();
                          onConversationClick(loc.conversation_id);
                        }
                      }}
                    >
                      {/* Time */}
                      <p className={cn(
                        "text-xs font-medium",
                        isCurrent ? "text-purple-primary" : "text-purple-primary/70"
                      )}>
                        {formatJourneyTime(loc.time)}
                      </p>
                      {/* Title */}
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-sm">{display.emoji}</span>
                        <p className={cn(
                          "text-sm",
                          isCurrent ? "text-text-primary font-medium" : "text-text-secondary",
                          loc.conversation_id && onConversationClick && "group-hover:text-purple-primary transition-colors"
                        )}>
                          {display.title}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function RecapDetailPanel({
  recapId,
  recap: initialRecap,
  onBack,
  onConversationClick,
}: RecapDetailPanelProps) {
  const router = useRouter();
  const [recap, setRecap] = useState<DailySummary | null>(initialRecap || null);
  const [loading, setLoading] = useState(!initialRecap);
  const [previewConversationIds, setPreviewConversationIds] = useState<string[]>([]);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<RecapTab>('recap');

  // Journey view playback state (lifted for sync between map and timeline)
  const [journeyIndex, setJourneyIndex] = useState(-1);
  const [journeyPlaying, setJourneyPlaying] = useState(false);

  // Fetch full recap details if needed
  useEffect(() => {
    if (initialRecap) {
      setRecap(initialRecap);
      setLoading(false);
      return;
    }

    const fetchRecap = async () => {
      setLoading(true);
      try {
        const data = await getDailySummary(recapId);
        setRecap(data);
      } catch (err) {
        console.error('Failed to load recap:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchRecap();
  }, [recapId, initialRecap]);

  // Extract all unique conversation IDs from the entire recap for prefetching
  const allConversationIds = useMemo(() => {
    if (!recap) return [];
    const ids = new Set<string>();

    // From locations
    recap.locations?.forEach(loc => {
      if (loc.conversation_id) ids.add(loc.conversation_id);
    });

    // From highlights
    recap.highlights?.forEach(h => {
      h.conversation_ids?.forEach(id => ids.add(id));
    });

    // From action items
    recap.action_items?.forEach(item => {
      if (item.source_conversation_id) ids.add(item.source_conversation_id);
    });

    // From questions, decisions, knowledge nuggets
    recap.unresolved_questions?.forEach(q => {
      if (q.conversation_id) ids.add(q.conversation_id);
    });
    recap.decisions_made?.forEach(d => {
      if (d.conversation_id) ids.add(d.conversation_id);
    });
    recap.knowledge_nuggets?.forEach(k => {
      if (k.conversation_id) ids.add(k.conversation_id);
    });

    return Array.from(ids);
  }, [recap]);

  // Prefetch all conversations in background when recap loads
  // This warms the API cache so child components get instant data
  useEffect(() => {
    if (allConversationIds.length === 0) return;

    // Fire and forget - just warm the cache
    // The API-level cache will deduplicate and cache results
    allConversationIds.forEach(id => {
      getConversation(id).catch(() => {}); // Ignore errors silently
    });
  }, [allConversationIds]);

  // Handle click on source conversation - opens preview panel
  const handleConversationClick = (conversationIds: string | string[]) => {
    const ids = Array.isArray(conversationIds) ? conversationIds : [conversationIds];
    setPreviewConversationIds(ids);
    setIsPanelOpen(true);
  };

  // Handle opening full conversation view
  const handleOpenFullConversation = (conversationId: string) => {
    setIsPanelOpen(false);
    if (onConversationClick) {
      onConversationClick(conversationId);
    } else {
      router.push(`/conversations?id=${conversationId}`);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="h-full flex flex-col bg-bg-secondary">
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
        </div>
      </div>
    );
  }

  // No recap found
  if (!recap) {
    return (
      <div className="h-full flex flex-col bg-bg-secondary">
        <div className="flex-1 flex items-center justify-center">
          <p className="text-text-tertiary">Recap not found</p>
        </div>
      </div>
    );
  }

  const hasHighlights = recap.highlights && recap.highlights.length > 0;
  const hasTasks = recap.action_items && recap.action_items.length > 0;
  const hasInsights =
    (recap.unresolved_questions && recap.unresolved_questions.length > 0) ||
    (recap.decisions_made && recap.decisions_made.length > 0) ||
    (recap.knowledge_nuggets && recap.knowledge_nuggets.length > 0);
  const hasLocations = recap.locations && recap.locations.length > 0;

  return (
    <div className="h-full flex bg-bg-secondary overflow-hidden">
      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header - always visible */}
        <div className="flex-shrink-0 bg-bg-secondary border-b border-bg-tertiary z-10">
          <div className="p-6">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                {/* Day emoji */}
                <div className="flex-shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-primary/20 to-purple-primary/5 flex items-center justify-center text-3xl">
                  {recap.day_emoji || '📅'}
                </div>
                <div>
                  {/* Headline */}
                  <h2 className="text-xl font-semibold text-text-primary mb-1">
                    {recap.headline || 'Daily Recap'}
                  </h2>
                  {/* Date */}
                  <p className="text-sm text-text-tertiary">
                    {formatRecapDate(recap.date)}
                  </p>
                </div>
              </div>
            </div>

            {/* Quick stats row */}
            <div className="flex items-center gap-4 mt-4">
              <div className="flex items-center gap-1.5 text-text-secondary">
                <MessageSquare className="w-4 h-4" />
                <span className="text-sm font-medium">{recap.stats.total_conversations}</span>
                <span className="text-xs text-text-tertiary">conversations</span>
              </div>
              {recap.stats.total_duration_minutes > 0 && (
                <div className="flex items-center gap-1.5 text-text-secondary">
                  <Clock className="w-4 h-4" />
                  <span className="text-sm font-medium">{formatDuration(recap.stats.total_duration_minutes)}</span>
                  <span className="text-xs text-text-tertiary">recorded</span>
                </div>
              )}
              {recap.stats.action_items_count > 0 && (
                <div className="flex items-center gap-1.5 text-text-secondary">
                  <CheckSquare className="w-4 h-4" />
                  <span className="text-sm font-medium">{recap.stats.action_items_count}</span>
                  <span className="text-xs text-text-tertiary">tasks</span>
                </div>
              )}
            </div>

            {/* Tab switcher - only show if locations exist */}
            {hasLocations && (
              <div className="flex items-center gap-1 mt-4 p-1 bg-bg-tertiary/50 rounded-lg w-fit">
                <button
                  onClick={() => setActiveTab('recap')}
                  className={cn(
                    "px-4 py-1.5 text-sm font-medium rounded-md transition-all",
                    activeTab === 'recap'
                      ? "bg-bg-secondary text-text-primary shadow-sm"
                      : "text-text-tertiary hover:text-text-secondary"
                  )}
                >
                  Recap
                </button>
                <button
                  onClick={() => {
                    setActiveTab('journey');
                    setJourneyIndex(-1);
                    setJourneyPlaying(false);
                  }}
                  className={cn(
                    "px-4 py-1.5 text-sm font-medium rounded-md transition-all flex items-center gap-1.5",
                    activeTab === 'journey'
                      ? "bg-bg-secondary text-text-primary shadow-sm"
                      : "text-text-tertiary hover:text-text-secondary"
                  )}
                >
                  <MapPin className="w-3.5 h-3.5" />
                  Journey
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Recap Tab Content - scrollable */}
        {activeTab === 'recap' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-8">
            {/* Combined Overview + Map section (when both exist) */}
            {recap.overview && hasLocations && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className="noise-overlay rounded-xl overflow-hidden"
              >
                <div className="grid grid-cols-2 min-h-[280px]">
                  {/* Left: Overview text */}
                  <div className="p-5 pt-4">
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {recap.overview}
                    </p>
                  </div>
                  {/* Right: Map */}
                  <div className="relative overflow-hidden group">
                    <LocationsSection
                      locations={recap.locations}
                      onConversationClick={handleConversationClick}
                      height={280}
                      showBorder={false}
                      className="h-full"
                    />
                    {/* Expand button - switches to Journey tab */}
                    <button
                      onClick={() => setActiveTab('journey')}
                      className="absolute top-3 right-3 p-2 rounded-lg bg-bg-tertiary/80 backdrop-blur-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all opacity-0 group-hover:opacity-100"
                      title="View full journey"
                    >
                      <Maximize2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Standalone Overview (only when no locations) */}
            {recap.overview && !hasLocations && (
              <Section title="Overview" icon={Calendar}>
                <div className={cn(
                  'noise-overlay p-4 rounded-xl',
                  'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
                  'border border-white/[0.04]'
                )}>
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {recap.overview}
                  </p>
                </div>
              </Section>
            )}

            {/* Highlights */}
            {hasHighlights && (
              <Section title="Highlights" icon={Sparkles}>
                <HighlightsSection
                  highlights={recap.highlights}
                  onConversationClick={handleConversationClick}
                />
              </Section>
            )}

            {/* Insights */}
            {hasInsights && (
              <Section title="Insights" icon={Lightbulb}>
                <InsightsSection
                  questions={recap.unresolved_questions || []}
                  decisions={recap.decisions_made || []}
                  learnings={recap.knowledge_nuggets || []}
                  onConversationClick={handleConversationClick}
                />
              </Section>
            )}

            {/* Tasks */}
            {hasTasks && (
              <Section title="Tasks" icon={CheckSquare}>
                <TasksSection
                  tasks={recap.action_items}
                  onConversationClick={handleConversationClick}
                />
              </Section>
            )}

            {/* Standalone Locations (only when no overview) */}
            {hasLocations && !recap.overview && (
              <Section title="Locations" icon={MapPin}>
                <LocationsSection
                  locations={recap.locations}
                  onConversationClick={handleConversationClick}
                />
              </Section>
            )}
          </div>
        )}

        {/* Journey Tab Content */}
        {activeTab === 'journey' && hasLocations && (
          <div className="flex-1 flex min-h-0 overflow-hidden">
            {/* Map area - fixed, no scroll */}
            <div className="flex-1 min-w-0 relative h-full">
              <LocationMap
                locations={recap.locations}
                height="100%"
                onConversationClick={(id) => handleConversationClick(id)}
                showPlayback={true}
                controlledIndex={journeyIndex}
                onIndexChange={setJourneyIndex}
                controlledPlaying={journeyPlaying}
                onPlayingChange={setJourneyPlaying}
              />
            </div>

            {/* Journey Timeline Sidebar - scrollable */}
            <div className="w-80 border-l border-white/[0.04] bg-bg-tertiary/30 flex flex-col h-full overflow-hidden">
              <JourneyTimeline
                locations={recap.locations}
                onConversationClick={handleConversationClick}
                currentIndex={journeyIndex}
                onLocationClick={(idx) => {
                  setJourneyIndex(idx);
                  setJourneyPlaying(false);
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Conversation Preview Panel */}
      <ConversationPreviewPanel
        conversationIds={previewConversationIds}
        isOpen={isPanelOpen}
        onClose={() => setIsPanelOpen(false)}
        onOpenFull={handleOpenFullConversation}
      />

    </div>
  );
}

// Section wrapper component
interface SectionProps {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}

function Section({ title, icon: Icon, children }: SectionProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {/* Section header */}
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-purple-primary" />
        <h3 className="text-base font-semibold text-text-primary">{title}</h3>
      </div>
      {/* Section content */}
      {children}
    </motion.div>
  );
}

// Skeleton for loading state
export function RecapDetailPanelSkeleton() {
  return (
    <div className="h-full flex flex-col bg-bg-secondary">
      <div className="p-6 border-b border-bg-tertiary">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-bg-tertiary animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-6 w-64 bg-bg-tertiary rounded animate-pulse" />
            <div className="h-4 w-40 bg-bg-tertiary rounded animate-pulse" />
          </div>
        </div>
      </div>
      <div className="flex-1 p-6 space-y-6">
        <div className="h-24 bg-bg-tertiary rounded-xl animate-pulse" />
        <div className="h-32 bg-bg-tertiary rounded-xl animate-pulse" />
        <div className="h-48 bg-bg-tertiary rounded-xl animate-pulse" />
      </div>
    </div>
  );
}
