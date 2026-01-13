'use client';

import { useState, memo } from 'react';
import { motion } from 'framer-motion';
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
    <motion.div
      whileHover={{ y: compact ? 0 : -1 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      className={cn(
        'noise-overlay group relative rounded-xl cursor-pointer overflow-hidden',
        'border transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50',
        'p-4',
        // Checked state in selection mode (purple highlight)
        isChecked
          ? 'bg-purple-primary/20 border-purple-primary shadow-[0_0_0_1px_rgba(139,92,246,0.5)]'
          // Normal selected state (viewing detail)
          : isSelected
          ? 'bg-purple-primary/10 border-purple-primary/50 shadow-[0_0_0_1px_rgba(139,92,246,0.3)]'
          : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.05] hover:border-purple-primary/30',
        // Merging state - dim the card
        isMerging && 'opacity-50 pointer-events-none'
      )}
      tabIndex={0}
      role="button"
      aria-label={`Conversation: ${conversation.structured.title}`}
      aria-selected={isSelected || isChecked}
    >
      {/* Top row: Time + Star */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] text-text-quaternary">
          {formatTime(startedAt)}
        </span>

        {/* Star button - visible on hover or if starred */}
        <button
          onClick={handleStarClick}
          className={cn(
            'p-0.5 rounded',
            'transition-all duration-150',
            isStarred || isHovered ? 'opacity-100' : 'opacity-0',
            'hover:bg-bg-secondary'
          )}
          aria-label={isStarred ? 'Unstar conversation' : 'Star conversation'}
        >
          <motion.div
            animate={isStarred ? { scale: [1, 1.2, 1] } : { scale: 1 }}
            transition={{ duration: 0.2 }}
          >
            <Star
              className={cn(
                'w-3 h-3 transition-colors',
                isStarred
                  ? 'fill-warning text-warning'
                  : 'text-text-quaternary hover:text-text-secondary'
              )}
            />
          </motion.div>
        </button>
      </div>

      {/* Main content row: Checkbox + Emoji + Title */}
      <div className="flex items-start gap-2.5">
        {/* Checkbox for selection mode */}
        {isSelectionMode && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className={cn(
              'flex-shrink-0 w-5 h-5 rounded-md border-2 flex items-center justify-center',
              'transition-all duration-150',
              isChecked
                ? 'bg-purple-primary border-purple-primary'
                : 'border-text-quaternary bg-transparent'
            )}
          >
            {isChecked && (
              <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
            )}
          </motion.div>
        )}

        {/* Emoji Icon */}
        <div
          className={cn(
            'flex-shrink-0 rounded-lg',
            'bg-bg-secondary flex items-center justify-center',
            'select-none',
            'group-hover:scale-105 transition-transform duration-150',
            'w-9 h-9 text-xl'
          )}
        >
          {conversation.structured.emoji || '💬'}
        </div>

        {/* Title + metadata */}
        <div className="flex-1 min-w-0">
          <h3
            className={cn(
              'font-medium leading-snug transition-colors text-sm',
              isSelected ? 'text-purple-primary' : 'text-text-primary group-hover:text-white'
            )}
          >
            {conversation.structured.title || 'Untitled conversation'}
          </h3>

          {/* Bottom row: Category tag + Duration */}
          <div className="flex items-center justify-between mt-1.5">
            {/* Category tag - subtle */}
            {category && category !== 'other' ? (
              <span className="text-[10px] text-text-quaternary capitalize">
                {category}
              </span>
            ) : (
              <span />
            )}

            {/* Duration - right aligned */}
            {durationSeconds > 0 && (
              <span className="text-[10px] text-text-quaternary">
                {formatDuration(durationSeconds)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Processing indicator - inline with category/duration */}
      {conversation.status === 'processing' && (
        <div className="flex items-center gap-1.5 mt-2 ml-[46px]">
          <div className="w-1.5 h-1.5 rounded-full bg-purple-primary animate-pulse" />
          <span className="text-xs text-text-quaternary">Processing...</span>
        </div>
      )}

      {/* New badge - positioned inside card bounds */}
      {isNew && !conversation.status?.includes('processing') && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          className={cn(
            'absolute top-2 right-2',
            'px-1.5 py-0.5 rounded',
            'bg-purple-primary/20 text-purple-primary text-[10px] font-medium'
          )}
        >
          New
        </motion.div>
      )}
    </motion.div>
  );
});

// Skeleton loader for conversation cards - matches compact layout
export function ConversationCardSkeleton() {
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
          <div className="h-4 w-14 bg-bg-quaternary rounded" />
          <div className="h-3 w-20 bg-bg-quaternary rounded" />
        </div>
      </div>
    </div>
  );
}
