'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Clock, Calendar, MessageSquare, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getConversation } from '@/lib/api';
import type { Conversation } from '@/types/conversation';

interface ConversationPreviewPanelProps {
  conversationIds: string[];
  isOpen: boolean;
  onClose: () => void;
  onOpenFull: (conversationId: string) => void;
}

function formatTime(dateString: string | null): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return '';
  const startDate = new Date(start);
  const endDate = new Date(end);
  const minutes = Math.floor((endDate.getTime() - startDate.getTime()) / 60000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

// Truncate text to approximately N lines (rough estimate based on chars)
function truncateText(text: string, maxLines: number = 3): string {
  const charsPerLine = 50; // rough estimate
  const maxChars = maxLines * charsPerLine;
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars).trim() + '...';
}

export function ConversationPreviewPanel({
  conversationIds,
  isOpen,
  onClose,
  onOpenFull,
}: ConversationPreviewPanelProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);

  // Fetch all conversations when panel opens
  useEffect(() => {
    if (!isOpen || conversationIds.length === 0) return;

    const fetchAllConversations = async () => {
      setLoading(true);
      try {
        const results = await Promise.all(
          conversationIds.map(id => getConversation(id).catch(() => null))
        );
        setConversations(results.filter((c): c is Conversation => c !== null));
      } catch (err) {
        console.error('Failed to fetch conversations:', err);
        setConversations([]);
      } finally {
        setLoading(false);
      }
    };

    fetchAllConversations();
  }, [conversationIds, isOpen]);

  // Reset when panel closes
  useEffect(() => {
    if (!isOpen) {
      setConversations([]);
    }
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: 420 }}
          exit={{ width: 0 }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          className={cn(
            'h-full flex-shrink-0 overflow-hidden',
            'bg-bg-secondary border-l border-white/[0.06]'
          )}
        >
          <div className="w-[420px] h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-purple-primary" />
                <span className="text-sm font-medium text-text-primary">
                  Source Conversations
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-purple-primary/10 text-purple-primary">
                  {conversationIds.length}
                </span>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-white/[0.05] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Conversation List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {loading ? (
                // Loading skeletons
                [...Array(Math.min(conversationIds.length, 5))].map((_, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl bg-bg-tertiary animate-pulse"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 bg-bg-quaternary rounded" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 bg-bg-quaternary rounded w-3/4" />
                        <div className="h-3 bg-bg-quaternary rounded w-1/2" />
                        <div className="h-12 bg-bg-quaternary rounded mt-2" />
                      </div>
                    </div>
                  </div>
                ))
              ) : conversations.length > 0 ? (
                conversations.map((conversation) => (
                  <motion.button
                    key={conversation.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => onOpenFull(conversation.id)}
                    className={cn(
                      'w-full text-left p-3 rounded-xl',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'border border-transparent hover:border-purple-primary/30',
                      'transition-all duration-150 group'
                    )}
                  >
                    <div className="flex items-start gap-3">
                      {/* Emoji */}
                      <span className="text-xl flex-shrink-0">
                        {conversation.structured.emoji || '💬'}
                      </span>

                      <div className="flex-1 min-w-0">
                        {/* Title */}
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="text-sm font-medium text-text-primary line-clamp-1 group-hover:text-purple-primary transition-colors">
                            {conversation.structured.title || 'Untitled'}
                          </h4>
                          <ExternalLink className="w-3.5 h-3.5 text-text-quaternary group-hover:text-purple-primary flex-shrink-0 mt-0.5 transition-colors" />
                        </div>

                        {/* Time info */}
                        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-text-quaternary">
                          <span className="flex items-center gap-0.5">
                            <Clock className="w-2.5 h-2.5" />
                            {formatTime(conversation.started_at)}
                          </span>
                          {conversation.finished_at && (
                            <span>
                              · {formatDuration(conversation.started_at, conversation.finished_at)}
                            </span>
                          )}
                        </div>

                        {/* Summary - truncated to ~3 lines */}
                        {conversation.structured.overview && (
                          <p className="text-xs text-text-tertiary leading-relaxed mt-2 line-clamp-3">
                            {conversation.structured.overview}
                          </p>
                        )}
                      </div>
                    </div>
                  </motion.button>
                ))
              ) : (
                <div className="flex items-center justify-center h-32">
                  <p className="text-sm text-text-tertiary">
                    No conversations found
                  </p>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
