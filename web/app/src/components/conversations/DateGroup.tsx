'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { ConversationCard, ConversationCardSkeleton } from './ConversationCard';
import type { Conversation } from '@/types/conversation';

interface DateGroupProps {
  dateLabel: string;
  conversations: Conversation[];
  onConversationClick?: (conversation: Conversation) => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  selectedId?: string | null;
  compact?: boolean;
  // Selection mode props for merge feature
  isSelectionMode?: boolean;
  selectedIds?: Set<string>;
  onSelect?: (id: string) => void;
  mergingIds?: Set<string>;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.2,
      ease: 'easeOut',
    },
  },
};

export const DateGroup = memo(function DateGroup({
  dateLabel,
  conversations,
  onConversationClick,
  onStarToggle,
  selectedId,
  compact = false,
  isSelectionMode = false,
  selectedIds,
  onSelect,
  mergingIds,
  onEnterSelectionMode,
}: DateGroupProps) {
  return (
    <section className="space-y-2">
      {/* Date header */}
      <h2
        className={cn(
          'sticky top-0 z-10',
          'px-1 py-1.5',
          'text-xs font-medium text-text-quaternary uppercase tracking-wide',
          'bg-bg-primary'
        )}
      >
        {dateLabel}
      </h2>

      {/* Conversation cards */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="space-y-4"
      >
        {conversations.map((conversation) => (
          <motion.div key={conversation.id} variants={itemVariants}>
            <ConversationCard
              conversation={conversation}
              onClick={() => onConversationClick?.(conversation)}
              onStarToggle={onStarToggle}
              isSelected={selectedId === conversation.id}
              compact={compact}
              isSelectionMode={isSelectionMode}
              isChecked={selectedIds?.has(conversation.id) ?? false}
              onSelect={onSelect}
              isMerging={mergingIds?.has(conversation.id) ?? false}
              onEnterSelectionMode={onEnterSelectionMode}
            />
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
});

// Skeleton loader for date groups
interface DateGroupSkeletonProps {
  count?: number;
}

export function DateGroupSkeleton({ count = 3 }: DateGroupSkeletonProps) {
  return (
    <div className="space-y-2">
      {/* Date header skeleton */}
      <div className="h-4 w-16 bg-bg-tertiary rounded animate-pulse" />

      {/* Card skeletons */}
      <div className="space-y-4">
        {Array.from({ length: count }).map((_, i) => (
          <ConversationCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
