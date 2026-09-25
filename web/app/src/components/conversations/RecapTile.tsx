'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import { CalendarDays, CheckSquare, Clock, MapPin, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DailySummary, DailySummaryStats } from '@/types/recap';

interface RecapTileProps {
  recap: DailySummary;
  onClick?: () => void;
  isSelected?: boolean;
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

/**
 * `stats` and each of its counters are optional on the wire
 * (`DailySummaryResponse` in `backend/routers/users.py`), so a recap the
 * generator produced without them must still render a tile rather than take
 * the whole timeline down with it.
 */
const EMPTY_STATS: DailySummaryStats = {
  total_conversations: 0,
  total_duration_minutes: 0,
  action_items_count: 0,
};

function recapStats(recap: DailySummary): DailySummaryStats {
  const stats = recap.stats as Partial<DailySummaryStats> | null | undefined;
  if (!stats) return EMPTY_STATS;
  return {
    total_conversations: stats.total_conversations ?? 0,
    total_duration_minutes: stats.total_duration_minutes ?? 0,
    action_items_count: stats.action_items_count ?? 0,
  };
}

/**
 * A day's recap, rendered as a wider, raised tile so it reads as the day's
 * summary rather than one more conversation in the same grid.
 */
export const RecapTile = memo(function RecapTile({
  recap,
  onClick,
  isSelected = false,
}: RecapTileProps) {
  const stats = recapStats(recap);

  return (
    // A native button rather than a `role="button"` div: Enter and Space have
    // to open the tile a keyboard user just focused, and the element that
    // already does that is the one to use.
    <motion.button
      type="button"
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      onClick={onClick}
      className={cn(
        'noise-overlay group relative flex cursor-pointer flex-col overflow-hidden rounded-card text-left',
        'col-span-full border p-5 transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40',
        isSelected
          ? 'border-white/40 bg-bg-quaternary'
          : 'border-white/15 bg-bg-raised hover:border-white/30 hover:bg-bg-tertiary',
      )}
      aria-label={`Recap: ${recap.headline}`}
      aria-pressed={isSelected}
    >
      <div className="mb-2 flex items-center gap-1.5">
        <CalendarDays className="h-3.5 w-3.5 text-text-secondary" />
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary">
          Day recap
        </span>
      </div>

      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 flex-shrink-0 select-none items-center justify-center rounded-chip bg-bg-quaternary text-2xl transition-transform duration-150 group-hover:scale-105">
          {recap.day_emoji || '📅'}
        </div>

        {/* Spans, not a heading and a paragraph: a button may only contain
            phrasing content, so the native element stays valid HTML. */}
        <span className="line-clamp-2 min-w-0 flex-1 text-base font-semibold leading-snug text-text-primary">
          {recap.headline || 'Daily Recap'}
        </span>
      </div>

      {recap.overview && (
        <span className="mt-3 line-clamp-3 block text-xs leading-relaxed text-text-tertiary">
          {recap.overview}
        </span>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
        <span className="flex items-center gap-1 rounded-chip bg-bg-quaternary px-2 py-0.5 text-[10px] text-text-secondary">
          <MessageSquare className="h-3 w-3" />
          {stats.total_conversations}
        </span>
        {stats.total_duration_minutes > 0 && (
          <span className="flex items-center gap-1 rounded-chip bg-bg-quaternary px-2 py-0.5 text-[10px] text-text-secondary">
            <Clock className="h-3 w-3" />
            {formatDuration(stats.total_duration_minutes)}
          </span>
        )}
        {stats.action_items_count > 0 && (
          <span className="flex items-center gap-1 rounded-chip bg-bg-quaternary px-2 py-0.5 text-[10px] text-text-secondary">
            <CheckSquare className="h-3 w-3" />
            {stats.action_items_count}
          </span>
        )}
        {recap.locations && recap.locations.length > 0 && (
          <span className="flex items-center gap-1 rounded-chip bg-bg-quaternary px-2 py-0.5 text-[10px] text-text-secondary">
            <MapPin className="h-3 w-3" />
            {recap.locations.length}
          </span>
        )}
      </div>
    </motion.button>
  );
});
