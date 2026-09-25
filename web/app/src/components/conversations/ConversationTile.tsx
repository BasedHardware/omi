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
        'noise-overlay group relative flex cursor-pointer flex-col overflow-hidden rounded-card',
        'border p-4 transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40',
        isChecked
          ? 'border-white/60 bg-bg-quaternary'
          : isSelected
          ? 'border-white/40 bg-bg-raised'
          : 'border-stroke bg-bg-secondary hover:border-white/20 hover:bg-bg-tertiary',
        // Merging state - dim the card
        isMerging && 'pointer-events-none opacity-50',
      )}
      tabIndex={0}
      role="button"
      aria-label={`Conversation: ${conversation.structured.title}`}
      aria-selected={isSelected || isChecked}
    >
      {/* Top row: Time + Star */}
      <div className="mb-2 flex items-center justify-between">
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
            'rounded-element p-0.5 transition-all duration-150',
            isStarred || isHovered ? 'opacity-100' : 'opacity-0',
            'hover:bg-bg-quaternary',
          )}
          aria-label={isStarred ? 'Unstar conversation' : 'Star conversation'}
        >
          <Star
            className={cn(
              'h-3.5 w-3.5 transition-colors',
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
              'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-element border-2',
              'transition-all duration-150',
              isChecked
                ? 'border-white bg-white'
                : 'border-text-quaternary bg-transparent',
            )}
          >
            {isChecked && (
              <Check className="h-3.5 w-3.5 text-bg-primary" strokeWidth={3} />
            )}
          </motion.div>
        )}

        <div className="flex h-9 w-9 flex-shrink-0 select-none items-center justify-center rounded-chip bg-bg-tertiary text-xl transition-transform duration-150 group-hover:scale-105">
          {conversation.structured.emoji || '💬'}
        </div>

        <h3 className="line-clamp-2 min-w-0 flex-1 text-sm font-medium leading-snug text-text-primary">
          {conversation.structured.title || 'Untitled conversation'}
        </h3>
      </div>

      {/* Excerpt — the scannable payload of a gallery tile */}
      {excerpt && (
        <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-text-tertiary">
          {excerpt}
        </p>
      )}

      {/* Structured signal row */}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
        {category && (
          <span className="rounded-chip bg-bg-tertiary px-2 py-0.5 text-[10px] capitalize text-text-secondary">
            {category}
          </span>
        )}
        {actionItemCount > 0 && (
          <span className="flex items-center gap-1 rounded-chip bg-bg-tertiary px-2 py-0.5 text-[10px] text-text-secondary">
            <CheckSquare className="h-3 w-3" />
            {actionItemCount}
          </span>
        )}
        {speakerCount > 1 && (
          <span className="flex items-center gap-1 rounded-chip bg-bg-tertiary px-2 py-0.5 text-[10px] text-text-secondary">
            <Users className="h-3 w-3" />
            {speakerCount}
          </span>
        )}
        {conversation.status === 'processing' && (
          <span className="flex items-center gap-1.5 rounded-chip bg-bg-tertiary px-2 py-0.5 text-[10px] text-text-secondary">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-text-primary" />
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
    <div className="animate-pulse rounded-card border border-stroke bg-bg-secondary p-4">
      <div className="mb-3 h-3 w-16 rounded bg-bg-tertiary" />
      <div className="flex items-start gap-2.5">
        <div className="h-9 w-9 flex-shrink-0 rounded-chip bg-bg-tertiary" />
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
