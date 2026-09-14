'use client';

import { ExternalLink } from 'lucide-react';
import { StaticMapPreview } from '@/components/ui/StaticMapPreview';
import { googleMapsUrl } from '@/lib/staticMap';
import { cn } from '@/lib/utils';

interface SingleLocationMapProps {
  latitude: number;
  longitude: number;
  address?: string | null;
  height?: number | string;
  className?: string;
}

export default function SingleLocationMap({
  latitude,
  longitude,
  address,
  height = 280,
  className,
}: SingleLocationMapProps) {
  return (
    <a
      href={googleMapsUrl(latitude, longitude)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={
        address ? `Open ${address} in Google Maps` : 'Open location in Google Maps'
      }
      className={cn('group relative block', className)}
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        width: '100%',
      }}
    >
      <StaticMapPreview pins={[{ latitude, longitude }]} alt="" />
      <span className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg bg-bg-secondary/90 px-2 py-1 text-xs text-text-secondary backdrop-blur-sm transition-colors group-hover:text-text-primary">
        <ExternalLink className="h-3 w-3" />
        <span>Open in maps</span>
      </span>
    </a>
  );
}
