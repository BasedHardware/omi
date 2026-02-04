'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { DailySummary } from '@/types/recap';
import { RecapCard } from './RecapCard';

interface RecapDateGroupProps {
  monthLabel: string;
  recaps: DailySummary[];
  selectedId?: string | null;
  onRecapClick?: (recap: DailySummary) => void;
}

export function RecapDateGroup({
  monthLabel,
  recaps,
  selectedId,
  onRecapClick,
}: RecapDateGroupProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="mb-6"
    >
      {/* Month header - sticky */}
      <div
        className={cn(
          'sticky top-0 z-10',
          'py-2 px-1',
          'bg-bg-primary/95 backdrop-blur-sm',
          'border-b border-white/[0.04]',
          'mb-2'
        )}
      >
        <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wider">
          {monthLabel}
        </h3>
      </div>

      {/* Recaps list */}
      <div className="space-y-2">
        {recaps.map((recap) => (
          <RecapCard
            key={recap.id}
            recap={recap}
            isSelected={selectedId === recap.id}
            onClick={() => onRecapClick?.(recap)}
          />
        ))}
      </div>
    </motion.div>
  );
}
