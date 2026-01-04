'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, Clock, CheckSquare, MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DailySummary } from '@/types/recap';

interface RecapCardProps {
  recap: DailySummary;
  onClick?: () => void;
  isSelected?: boolean;
}

// Format date as "Mon, Jan 6" (parse as local date, not UTC)
function formatRecapDate(dateString: string): string {
  const [year, month, day] = dateString.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
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

export function RecapCard({
  recap,
  onClick,
  isSelected = false,
}: RecapCardProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <motion.div
      whileHover={{ y: -1 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      onClick={onClick}
      className={cn(
        'noise-overlay group relative rounded-xl cursor-pointer',
        'border transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50',
        'p-4',
        isSelected
          ? 'bg-purple-primary/10 border-purple-primary/50'
          : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.05] hover:border-purple-primary/30'
      )}
      tabIndex={0}
      role="button"
      aria-label={`Recap: ${recap.headline}`}
      aria-selected={isSelected}
    >
      {/* Top row: Date */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] text-text-quaternary">
          {formatRecapDate(recap.date)}
        </span>
      </div>

      {/* Main content row: Emoji + Headline */}
      <div className="flex items-start gap-2.5">
        {/* Day Emoji */}
        <div
          className={cn(
            'flex-shrink-0 rounded-lg',
            'bg-bg-secondary flex items-center justify-center',
            'select-none',
            'group-hover:scale-105 transition-transform duration-150',
            'w-9 h-9 text-xl'
          )}
        >
          {recap.day_emoji || '📅'}
        </div>

        {/* Headline + stats */}
        <div className="flex-1 min-w-0">
          <h3
            className={cn(
              'font-medium leading-snug transition-colors text-sm line-clamp-2',
              isSelected ? 'text-purple-primary' : 'text-text-primary group-hover:text-white'
            )}
          >
            {recap.headline || 'Daily Recap'}
          </h3>

          {/* Stats row */}
          <div className="flex items-center gap-3 mt-1.5">
            {/* Conversations count */}
            <div className="flex items-center gap-1">
              <MessageSquare className="w-3 h-3 text-text-quaternary" />
              <span className="text-[10px] text-text-quaternary">
                {recap.stats.total_conversations}
              </span>
            </div>

            {/* Duration */}
            {recap.stats.total_duration_minutes > 0 && (
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-text-quaternary" />
                <span className="text-[10px] text-text-quaternary">
                  {formatDuration(recap.stats.total_duration_minutes)}
                </span>
              </div>
            )}

            {/* Action items count */}
            {recap.stats.action_items_count > 0 && (
              <div className="flex items-center gap-1">
                <CheckSquare className="w-3 h-3 text-text-quaternary" />
                <span className="text-[10px] text-text-quaternary">
                  {recap.stats.action_items_count}
                </span>
              </div>
            )}

            {/* Locations count */}
            {recap.locations && recap.locations.length > 0 && (
              <div className="flex items-center gap-1">
                <MapPin className="w-3 h-3 text-text-quaternary" />
                <span className="text-[10px] text-text-quaternary">
                  {recap.locations.length}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// Skeleton loader for recap cards
export function RecapCardSkeleton() {
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 p-4 rounded-xl',
        'bg-bg-tertiary animate-pulse'
      )}
    >
      {/* Emoji placeholder */}
      <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-bg-quaternary" />

      {/* Content placeholder */}
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-bg-quaternary rounded w-3/4" />
        <div className="flex items-center gap-2">
          <div className="h-3 w-12 bg-bg-quaternary rounded" />
          <div className="h-3 w-10 bg-bg-quaternary rounded" />
          <div className="h-3 w-8 bg-bg-quaternary rounded" />
        </div>
      </div>
    </div>
  );
}
