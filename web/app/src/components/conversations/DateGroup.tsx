'use client';

import { memo } from 'react';
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
  isSelectionMode?: boolean;
  selectedIds?: Set<string>;
  onSelect?: (id: string) => void;
  mergingIds?: Set<string>;
  onEnterSelectionMode?: (id: string) => void;
}

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
    <section>
      {/* Date header */}
      <h2
        className={cn(
          'sticky top-0 z-10',
          'px-3 py-1.5',
          'text-[10px] font-medium text-muted-foreground uppercase tracking-wider',
          'bg-bg-primary'
        )}
      >
        {dateLabel}
      </h2>

      {/* Conversation cards */}
      <div>
        {conversations.map((conversation) => (
          <ConversationCard
            key={conversation.id}
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
        ))}
      </div>
    </section>
  );
});

// Skeleton loader for date groups
interface DateGroupSkeletonProps {
  count?: number;
}

export function DateGroupSkeleton({ count = 3 }: DateGroupSkeletonProps) {
  return (
    <div>
      <div className="h-3 w-16 bg-muted rounded animate-pulse mx-3 my-1.5" />
      <div className="space-y-0.5">
        {Array.from({ length: count }).map((_, i) => (
          <ConversationCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
