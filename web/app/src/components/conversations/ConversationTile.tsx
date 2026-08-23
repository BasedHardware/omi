'use client';

import { useState, memo } from 'react';
import { motion } from 'framer-motion';
import { Star, Check, CheckSquare, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatTime, formatDuration } from '@/lib/utils';
import { conversationSignals } from '@/lib/conversationTimeline';
import type { Conversation } from '@/types/conversation';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface ConversationTileProps {
  conversation: Conversation;
  onClick?: () => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  isSelected?: boolean;
  // Selection mode props for merge feature
  isSelectionMode?: boolean;
  isChecked?: boolean;
  onSelect?: (id: string) => void;
  isMerging?: boolean;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

export const ConversationTile = memo(function ConversationTile({
  conversation,
  onClick,
  onStarToggle,
  isSelected = false,
  isSelectionMode = false,
  isChecked = false,
  onSelect,
  isMerging = false,
  onEnterSelectionMode,
}: ConversationTileProps) {
  const [isStarred, setIsStarred] = useState(conversation.starred);
  const [isHovered, setIsHovered] = useState(false);

  const startedAt = new Date(conversation.started_at || conversation.created_at);
  const finishedAt = conversation.finished_at ? new Date(conversation.finished_at) : null;

  // Calculate duration in seconds
  const durationSeconds = finishedAt
    ? Math.round((finishedAt.getTime() - startedAt.getTime()) / 1000)
    : 0;

  const { excerpt, category, actionItemCount, speakerCount } =
    conversationSignals(conversation);

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
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      className={cn(
        'noise-overlay group relative flex flex-col rounded-card cursor-pointer overflow-hidden',
        'border transition-all duration-150 p-4',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40',
        isChecked
          ? 'bg-bg-quaternary border-white/60'
          : isSelected
            ? 'bg-bg-raised border-white/40'
            : 'bg-bg-secondary border-stroke hover:bg-bg-tertiary hover:border-white/20',
        // Merging state - dim the card
        isMerging && 'opacity-50 pointer-events-none',
      )}
      tabIndex={0}
      role="button"
      aria-label={`Conversation: ${conversation.structured.title}`}
      aria-selected={isSelected || isChecked}
    >
      {/* Top row: Time + Star */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] tabular-nums text-text-tertiary">
          {formatTime(startedAt)}
          {durationSeconds > 0 && (
            <span className="text-text-quaternary">
              {' · '}
              {formatDuration(durationSeconds)}
            </span>
          )}
        </span>

        <button
          onClick={handleStarClick}
          className={cn(
            'p-0.5 rounded-element transition-all duration-150',
            isStarred || isHovered ? 'opacity-100' : 'opacity-0',
            'hover:bg-bg-quaternary',
          )}
          aria-label={isStarred ? 'Unstar conversation' : 'Star conversation'}
        >
          <Star
            className={cn(
              'w-3.5 h-3.5 transition-colors',
              isStarred
                ? 'fill-text-primary text-text-primary'
                : 'text-text-quaternary hover:text-text-secondary',
            )}
          />
        </button>
      </div>

      {/* Headline row: Checkbox + Emoji + Title */}
      <div className="flex items-start gap-2.5">
        {isSelectionMode && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className={cn(
              'flex-shrink-0 w-5 h-5 rounded-element border-2 flex items-center justify-center',
              'transition-all duration-150',
              isChecked
                ? 'bg-white border-white'
                : 'border-text-quaternary bg-transparent',
            )}
          >
            {isChecked && (
              <Check className="w-3.5 h-3.5 text-bg-primary" strokeWidth={3} />
            )}
          </motion.div>
        )}

        <div className="flex-shrink-0 w-9 h-9 rounded-chip bg-bg-tertiary flex items-center justify-center select-none text-xl group-hover:scale-105 transition-transform duration-150">
          {conversation.structured.emoji || '💬'}
        </div>

        <h3 className="flex-1 min-w-0 text-sm font-medium leading-snug text-text-primary line-clamp-2">
          {conversation.structured.title || 'Untitled conversation'}
        </h3>
      </div>

      {/* Excerpt — the scannable payload of a gallery tile */}
      {excerpt && (
        <p className="mt-3 text-xs leading-relaxed text-text-tertiary line-clamp-3">
          {excerpt}
        </p>
      )}

      {/* Structured signal row */}
      <div className="mt-auto pt-3 flex items-center flex-wrap gap-1.5">
        {category && (
          <span className="px-2 py-0.5 rounded-chip bg-bg-tertiary text-[10px] capitalize text-text-secondary">
            {category}
          </span>
        )}
        {actionItemCount > 0 && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-chip bg-bg-tertiary text-[10px] text-text-secondary">
            <CheckSquare className="w-3 h-3" />
            {actionItemCount}
          </span>
        )}
        {speakerCount > 1 && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-chip bg-bg-tertiary text-[10px] text-text-secondary">
            <Users className="w-3 h-3" />
            {speakerCount}
          </span>
        )}
        {conversation.status === 'processing' && (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-chip bg-bg-tertiary text-[10px] text-text-secondary">
            <span className="w-1.5 h-1.5 rounded-full bg-text-primary animate-pulse" />
            Processing
          </span>
        )}
      </div>
    </motion.div>
  );
});

// Skeleton loader for timeline tiles - matches the gallery tile layout
export function ConversationTileSkeleton() {
  return (
    <div className="rounded-card border border-stroke bg-bg-secondary p-4 animate-pulse">
      <div className="h-3 w-16 rounded bg-bg-tertiary mb-3" />
      <div className="flex items-start gap-2.5">
        <div className="flex-shrink-0 w-9 h-9 rounded-chip bg-bg-tertiary" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-3/4 rounded bg-bg-tertiary" />
          <div className="h-3 w-1/2 rounded bg-bg-tertiary" />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <div className="h-3 w-full rounded bg-bg-tertiary" />
        <div className="h-3 w-4/5 rounded bg-bg-tertiary" />
      </div>
    </div>
  );
}
