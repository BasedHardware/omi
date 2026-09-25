'use client';

import { MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TopicHighlight } from '@/types/recap';

interface HighlightsSectionProps {
  highlights: TopicHighlight[];
  onConversationClick?: (conversationIds: string[]) => void;
}

export function HighlightsSection({
  highlights,
  onConversationClick,
}: HighlightsSectionProps) {
  if (!highlights || highlights.length === 0) {
    return null;
  }

  // Limit to max 4 highlights
  const displayHighlights = highlights.slice(0, 4);

  return (
    <div
      className={cn(
        'noise-overlay overflow-hidden rounded-xl',
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        'border border-white/[0.04]',
      )}
    >
      <div className="grid grid-cols-4">
        {displayHighlights.map((highlight, idx) => (
          <HighlightCard
            key={idx}
            highlight={highlight}
            isLast={idx === displayHighlights.length - 1}
            onConversationClick={onConversationClick}
          />
        ))}
      </div>
    </div>
  );
}

interface HighlightCardProps {
  highlight: TopicHighlight;
  isLast: boolean;
  onConversationClick?: (conversationIds: string[]) => void;
}

function HighlightCard({ highlight, isLast, onConversationClick }: HighlightCardProps) {
  const hasConversations =
    highlight.conversation_ids && highlight.conversation_ids.length > 0;

  const handleConversationClick = () => {
    if (hasConversations && onConversationClick) {
      // Pass all conversation IDs to the handler
      onConversationClick(highlight.conversation_ids!);
    }
  };

  return (
    <div
      className={cn(
        'flex min-h-[160px] flex-col p-4',
        !isLast && 'border-r border-white/[0.04]',
      )}
    >
      {/* Emoji + Topic + Conversation icon */}
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xl">{highlight.emoji}</span>
        <h4 className="line-clamp-1 flex-1 text-sm font-semibold text-text-primary">
          {highlight.topic}
        </h4>
        {hasConversations && (
          <button
            onClick={handleConversationClick}
            className={cn(
              'flex-shrink-0 rounded-lg p-1.5',
              'text-text-quaternary hover:text-text-primary',
              'transition-colors hover:bg-white/[0.14]',
            )}
            title={`${highlight.conversation_ids!.length} conversation${
              highlight.conversation_ids!.length > 1 ? 's' : ''
            }`}
          >
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Summary */}
      <p className="flex-1 text-sm leading-relaxed text-text-secondary">
        {highlight.summary}
      </p>
    </div>
  );
}
