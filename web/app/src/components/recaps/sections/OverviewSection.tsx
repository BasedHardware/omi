'use client';

import { motion } from 'framer-motion';
import { MessageSquare, Clock, CheckSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DailySummary } from '@/types/recap';

interface OverviewSectionProps {
  recap: DailySummary;
}

// Format duration in minutes to human-readable
function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours} hours`;
}

export function OverviewSection({ recap }: OverviewSectionProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-4"
    >
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        {/* Conversations */}
        <div className={cn(
          'flex flex-col items-center justify-center p-3 rounded-xl',
          'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
          'border border-white/[0.04]'
        )}>
          <MessageSquare className="w-5 h-5 text-purple-primary mb-1" />
          <span className="text-lg font-semibold text-text-primary">
            {recap.stats.total_conversations}
          </span>
          <span className="text-[10px] text-text-tertiary">Conversations</span>
        </div>

        {/* Duration */}
        <div className={cn(
          'flex flex-col items-center justify-center p-3 rounded-xl',
          'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
          'border border-white/[0.04]'
        )}>
          <Clock className="w-5 h-5 text-blue-400 mb-1" />
          <span className="text-lg font-semibold text-text-primary">
            {formatDuration(recap.stats.total_duration_minutes)}
          </span>
          <span className="text-[10px] text-text-tertiary">Recorded</span>
        </div>

        {/* Action Items */}
        <div className={cn(
          'flex flex-col items-center justify-center p-3 rounded-xl',
          'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
          'border border-white/[0.04]'
        )}>
          <CheckSquare className="w-5 h-5 text-success mb-1" />
          <span className="text-lg font-semibold text-text-primary">
            {recap.stats.action_items_count}
          </span>
          <span className="text-[10px] text-text-tertiary">Action Items</span>
        </div>
      </div>

      {/* Overview text */}
      {recap.overview && (
        <div className={cn(
          'p-4 rounded-xl',
          'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
          'border border-white/[0.04]'
        )}>
          <p className="text-sm text-text-secondary leading-relaxed">
            {recap.overview}
          </p>
        </div>
      )}
    </motion.div>
  );
}
