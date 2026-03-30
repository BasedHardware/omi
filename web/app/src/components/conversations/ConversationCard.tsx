'use client';

import { useState, memo } from 'react';
import { Star, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatTime, formatDuration } from '@/lib/utils';
import type { Conversation } from '@/types/conversation';
import { MixpanelManager } from '@/lib/analytics/mixpanel';


interface ConversationCardProps {
  conversation: Conversation;
  onClick?: () => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  isSelected?: boolean;
  compact?: boolean;
  // Selection mode props for merge feature
  isSelectionMode?: boolean;
  isChecked?: boolean;
  onSelect?: (id: string) => void;
  isMerging?: boolean;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

export const ConversationCard = memo(function ConversationCard({
  conversation,
  onClick,
  onStarToggle,
  isSelected = false,
  compact = false,
  isSelectionMode = false,
  isChecked = false,
  onSelect,
  isMerging = false,
  onEnterSelectionMode,
}: ConversationCardProps) {
  const [isStarred, setIsStarred] = useState(conversation.starred);
  const [isHovered, setIsHovered] = useState(false);

  const startedAt = new Date(conversation.started_at || conversation.created_at);
  const finishedAt = conversation.finished_at
    ? new Date(conversation.finished_at)
    : null;

  // Calculate duration in seconds
  const durationSeconds = finishedAt
    ? Math.round((finishedAt.getTime() - startedAt.getTime()) / 1000)
    : 0;

  // Check if conversation is new (less than 60 seconds old)
  const isNew = Date.now() - startedAt.getTime() < 60000;

  // Get category for tag display
  const category = conversation.structured.category;

  const handleStarClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const newStarred = !isStarred;
    setIsStarred(newStarred);
    onStarToggle?.(conversation.id, newStarred);
    MixpanelManager.track('Conversation Starred', {
      conversation_id: conversation.id,
      starred: newStarred,
    });
  };

  const handleClick = () => {
    if (isSelectionMode && onSelect) {
      onSelect(conversation.id);
    } else {
      MixpanelManager.track('Conversation Viewed', {
        conversation_id: conversation.id,
      });
      onClick?.();
    }
  };

  const handleDoubleClick = () => {
    // Double-click enters selection mode and selects this card
    if (!isSelectionMode && onEnterSelectionMode) {
      onEnterSelectionMode(conversation.id);
    }
  };

  return (
    <div
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'group relative flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer',
        'transition-all duration-100',
        isChecked
          ? 'bg-brand/15'
          : isSelected
            ? 'bg-white/[0.06]'
            : 'hover:bg-white/[0.04]',
        isMerging && 'opacity-50 pointer-events-none'
      )}
      tabIndex={0}
      role="button"
      aria-label={`Conversation: ${conversation.structured.title}`}
      aria-selected={isSelected || isChecked}
    >
      {/* Checkbox — selection mode */}
      {isSelectionMode && (
        <div
          className={cn(
            'flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center',
            isChecked ? 'bg-brand border-brand' : 'border-muted-foreground/40'
          )}
        >
          {isChecked && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
        </div>
      )}

      {/* Time */}
      <span className="text-[11px] text-muted-foreground tabular-nums w-14 flex-shrink-0">
        {formatTime(startedAt)}
      </span>

      {/* Title */}
      <h3
        className={cn(
          'flex-1 min-w-0 text-sm truncate transition-colors',
          isSelected ? 'text-brand font-medium' : 'text-foreground/90'
        )}
      >
        {conversation.structured.title || 'Untitled conversation'}
      </h3>

      {/* Right side: category + duration + star */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {category && category !== 'other' && (
          <span className="text-[10px] text-muted-foreground capitalize hidden sm:inline">
            {category}
          </span>
        )}
        {durationSeconds > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {formatDuration(durationSeconds)}
          </span>
        )}
        {conversation.status === 'processing' && (
          <div className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
        )}
        {isNew && !conversation.status?.includes('processing') && (
          <span className="px-1 py-0.5 rounded text-[9px] font-medium bg-brand/20 text-brand">
            New
          </span>
        )}
        <button
          onClick={handleStarClick}
          className={cn(
            'p-0.5 rounded transition-opacity',
            isStarred || isHovered ? 'opacity-100' : 'opacity-0'
          )}
          aria-label={isStarred ? 'Unstar' : 'Star'}
        >
          <Star
            className={cn(
              'w-3 h-3',
              isStarred ? 'fill-warning text-warning' : 'text-muted-foreground'
            )}
          />
        </button>
      </div>
    </div>
  );
});

// Skeleton loader for conversation cards - matches compact layout
export function ConversationCardSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 animate-pulse">
      <div className="h-3 w-14 bg-muted rounded" />
      <div className="h-3 flex-1 bg-muted rounded" />
      <div className="h-3 w-10 bg-muted rounded" />
    </div>
  );
}
