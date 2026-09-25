'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Clock, Calendar, MessageSquare, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getConversation } from '@/lib/api';
import type { Conversation } from '@/types/conversation';
import { selectConversationSummary } from '@/lib/conversationSummarySelection';

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
          conversationIds.map((id) => getConversation(id).catch(() => null)),
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
            'border-l border-white/[0.06] bg-bg-secondary',
          )}
        >
          <div className="flex h-full w-[420px] flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/[0.06] p-4">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-text-primary" />
                <span className="text-sm font-medium text-text-primary">
                  Source Conversations
                </span>
                <span className="rounded bg-white/[0.08] px-1.5 py-0.5 text-xs text-text-primary">
                  {conversationIds.length}
                </span>
              </div>
              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-text-tertiary transition-colors hover:bg-white/[0.05] hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Conversation List */}
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              {loading ? (
                // Loading skeletons
                [...Array(Math.min(conversationIds.length, 5))].map((_, i) => (
                  <div key={i} className="animate-pulse rounded-xl bg-bg-tertiary p-3">
                    <div className="flex items-start gap-3">
                      <div className="h-8 w-8 rounded bg-bg-quaternary" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 w-3/4 rounded bg-bg-quaternary" />
                        <div className="h-3 w-1/2 rounded bg-bg-quaternary" />
                        <div className="mt-2 h-12 rounded bg-bg-quaternary" />
                      </div>
                    </div>
                  </div>
                ))
              ) : conversations.length > 0 ? (
                conversations.map((conversation) => {
                  const summary = selectConversationSummary(conversation);
                  return (
                    <motion.button
                      key={conversation.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      onClick={() => onOpenFull(conversation.id)}
                      className={cn(
                        'w-full rounded-xl p-3 text-left',
                        'bg-bg-tertiary hover:bg-bg-quaternary',
                        'border border-transparent hover:border-white/25',
                        'group transition-all duration-150',
                      )}
                    >
                      <div className="flex items-start gap-3">
                        {/* Emoji */}
                        <span className="flex-shrink-0 text-xl">
                          {conversation.structured.emoji || '💬'}
                        </span>

                        <div className="min-w-0 flex-1">
                          {/* Title */}
                          <div className="flex items-start justify-between gap-2">
                            <h4 className="line-clamp-1 text-sm font-medium text-text-primary transition-colors group-hover:text-text-primary">
                              {conversation.structured.title || 'Untitled'}
                            </h4>
                            <ExternalLink className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-primary" />
                          </div>

                          {/* Time info */}
                          <div className="mt-0.5 flex items-center gap-2 text-[10px] text-text-quaternary">
                            <span className="flex items-center gap-0.5">
                              <Clock className="h-2.5 w-2.5" />
                              {formatTime(conversation.started_at)}
                            </span>
                            {conversation.finished_at && (
                              <span>
                                ·{' '}
                                {formatDuration(
                                  conversation.started_at,
                                  conversation.finished_at,
                                )}
                              </span>
                            )}
                          </div>

                          {/* Summary - selected body, truncated to ~3 lines */}
                          {summary.content && (
                            <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-text-tertiary">
                              {summary.content}
                            </p>
                          )}
                        </div>
                      </div>
                    </motion.button>
                  );
                })
              ) : (
                <div className="flex h-32 items-center justify-center">
                  <p className="text-sm text-text-tertiary">No conversations found</p>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
