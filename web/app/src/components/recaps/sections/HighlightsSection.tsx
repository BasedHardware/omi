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
    <div className={cn(
      'noise-overlay rounded-xl overflow-hidden',
      'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
      'border border-white/[0.04]'
    )}>
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
  const hasConversations = highlight.conversation_ids && highlight.conversation_ids.length > 0;

  const handleConversationClick = () => {
    if (hasConversations && onConversationClick) {
      // Pass all conversation IDs to the handler
      onConversationClick(highlight.conversation_ids!);
    }
  };

  return (
    <div className={cn(
      'p-4 flex flex-col min-h-[160px]',
      !isLast && 'border-r border-white/[0.04]'
    )}>
      {/* Emoji + Topic + Conversation icon */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">{highlight.emoji}</span>
        <h4 className="text-sm font-semibold text-text-primary flex-1 line-clamp-1">
          {highlight.topic}
        </h4>
        {hasConversations && (
          <button
            onClick={handleConversationClick}
            className={cn(
              'p-1.5 rounded-lg flex-shrink-0',
              'text-text-quaternary hover:text-purple-primary',
              'hover:bg-purple-primary/10 transition-colors'
            )}
            title={`${highlight.conversation_ids!.length} conversation${highlight.conversation_ids!.length > 1 ? 's' : ''}`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Summary */}
      <p className="text-sm text-text-secondary leading-relaxed flex-1">
        {highlight.summary}
      </p>
    </div>
  );
}
