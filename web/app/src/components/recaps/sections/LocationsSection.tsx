'use client';

import { MapPin } from 'lucide-react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';
import type { LocationPin } from '@/types/recap';

// Dynamically import the map component to avoid SSR issues
const LocationMap = dynamic(() => import('./LocationMap'), {
  ssr: false,
  loading: () => (
    <div className="h-64 rounded-xl bg-bg-tertiary animate-pulse flex items-center justify-center">
      <MapPin className="w-8 h-8 text-text-quaternary" />
    </div>
  ),
});

interface LocationsSectionProps {
  locations: LocationPin[];
  onConversationClick?: (conversationId: string) => void;
  height?: number | string;
  className?: string;
  showBorder?: boolean;
  showPlayback?: boolean;
}

export function LocationsSection({
  locations,
  onConversationClick,
  height = 320,
  className,
  showBorder = true,
  showPlayback = true,
}: LocationsSectionProps) {
  if (!locations || locations.length === 0) {
    return null;
  }

  return (
    <div className={cn(
      'overflow-hidden',
      showBorder && 'rounded-xl border border-white/[0.04]',
      className
    )}>
      <LocationMap
        locations={locations}
        height={height}
        onConversationClick={onConversationClick}
        showPlayback={showPlayback}
      />
    </div>
  );
}
