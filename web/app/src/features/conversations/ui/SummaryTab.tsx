'use client';

import { useState, useRef, useEffect } from 'react';
import dynamic from '@tschk/moonshine-next/dynamic';
import { MapPin, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AppSummaryCard } from './AppSummaryCard';
import { GenerateSummaryButton } from './GenerateSummaryButton';
import type { Conversation, AppResponse, Geolocation } from '@/types/conversation';

const SingleLocationMap = dynamic(() => import('@/shared/ui/SingleLocationMap'), {
  ssr: false,
  loading: () => (
    <div className="h-full bg-bg-tertiary animate-pulse flex items-center justify-center rounded-r-xl">
      <MapPin className="w-8 h-8 text-text-quaternary" />
    </div>
  ),
});

/**
 * Summary tab content with app summaries and optional location map
 */
interface SummaryTabProps {
  overview: string;
  category?: string;
  conversationId: string;
  appResults: AppResponse[];
  suggestedAppIds: string[];
  onGenerateComplete?: (conversation: Conversation) => void;
  geolocation?: Geolocation | null;
}

export function SummaryTab({
  overview,
  category,
  conversationId,
  appResults,
  suggestedAppIds,
  onGenerateComplete,
  geolocation,
}: SummaryTabProps) {
  const hasAppSummaries = appResults && appResults.length > 0;
  const hasLocation = geolocation && geolocation.latitude && geolocation.longitude;

  // State for expandable text
  const [isExpanded, setIsExpanded] = useState(false);
  const [needsTruncation, setNeedsTruncation] = useState(false);
  const [mapHeight, setMapHeight] = useState(0);
  const textRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<HTMLDivElement>(null);

  // Check if text overflows the map height
  useEffect(() => {
    const checkOverflow = () => {
      if (textRef.current && mapRef.current && hasLocation) {
        const actualMapHeight = mapRef.current.clientHeight;
        setMapHeight(actualMapHeight);
        // Only truncate if text is taller than the map (minus some padding for the button)
        setNeedsTruncation(textRef.current.scrollHeight > actualMapHeight - 40);
      }
    };

    // Small delay to ensure map has rendered
    const timer = setTimeout(checkOverflow, 100);
    window.addEventListener('resize', checkOverflow);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', checkOverflow);
    };
  }, [overview, hasLocation]);

  return (
    <div className="space-y-6">
      {/* Summary Section with optional Map */}
      {hasLocation ? (
        <div className="noise-overlay rounded-xl overflow-hidden border border-white/[0.04]">
          <div className="grid grid-cols-1 md:grid-cols-2 md:items-start min-h-[280px]">
            {/* Left: Overview content */}
            <div className="p-5 pt-4 relative">
              <div
                ref={textRef}
                className={cn(
                  'transition-all duration-300',
                  !isExpanded && needsTruncation && 'overflow-hidden',
                )}
                style={
                  !isExpanded && needsTruncation && mapHeight > 0
                    ? { maxHeight: mapHeight - 56 }
                    : undefined
                }
              >
                {category && (
                  <div className="mb-3">
                    <span className="inline-flex px-3 py-1 rounded-full text-xs font-medium bg-white/[0.08] text-text-primary capitalize">
                      {category}
                    </span>
                  </div>
                )}
                <p className="text-text-secondary leading-relaxed text-lg">{overview}</p>
                {geolocation.address && (
                  <div className="mt-4 flex items-start gap-2 text-sm text-text-tertiary">
                    <MapPin className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span>{geolocation.address}</span>
                  </div>
                )}
              </div>

              {/* Gradient fade and Show more button */}
              {needsTruncation && (
                <div
                  className={cn(
                    'mt-2',
                    !isExpanded &&
                      'absolute bottom-0 left-0 right-0 pt-12 pb-4 px-5 bg-gradient-to-t from-bg-secondary via-bg-secondary/90 to-transparent',
                  )}
                >
                  <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="flex items-center gap-1 text-sm text-text-primary hover:text-text-secondary transition-colors"
                  >
                    {isExpanded ? (
                      <>
                        <ChevronUp className="w-4 h-4" />
                        <span>Show less</span>
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-4 h-4" />
                        <span>Show more</span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
            {/* Right: Map */}
            <div ref={mapRef} className="relative overflow-hidden aspect-video">
              <SingleLocationMap
                latitude={geolocation.latitude}
                longitude={geolocation.longitude}
                address={geolocation.address}
                height="100%"
              />
            </div>
          </div>
        </div>
      ) : (
        /* Full-width overview when no location */
        <div>
          {category && (
            <div className="mb-3">
              <span className="inline-flex px-3 py-1 rounded-full text-xs font-medium bg-white/[0.08] text-text-primary capitalize">
                {category}
              </span>
            </div>
          )}
          <p className="text-text-secondary leading-relaxed text-lg">{overview}</p>
        </div>
      )}

      {/* App Summaries Section */}
      <div className="pt-4 border-t border-bg-tertiary">
        {/* Section Header with Generate Button */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-text-primary" />
            <h3 className="text-sm font-medium text-text-primary">Summary Templates</h3>
          </div>
          <GenerateSummaryButton
            conversationId={conversationId}
            suggestedAppIds={suggestedAppIds}
            existingAppResults={appResults}
            onGenerateComplete={onGenerateComplete}
          />
        </div>

        {/* App Summary Cards */}
        {hasAppSummaries && (
          <div className="space-y-3">
            {appResults.map((appResponse, index) => (
              <AppSummaryCard
                key={`${appResponse.app_id}-${index}`}
                appResponse={appResponse}
              />
            ))}
          </div>
        )}

        {/* Empty state for templates */}
        {!hasAppSummaries && (
          <p className="text-sm text-text-tertiary mt-2">
            No summaries yet. Click Templates above to generate one or create a custom
            template.
          </p>
        )}
      </div>
    </div>
  );
}
