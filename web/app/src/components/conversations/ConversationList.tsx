'use client';

import { useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, RefreshCw, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConversations } from '@/hooks/useConversations';
import { toggleStarred } from '@/lib/api';
import { DateGroup, DateGroupSkeleton } from './DateGroup';
import type { Conversation, GroupedConversations } from '@/types/conversation';

interface ConversationListProps {
  onConversationClick?: (conversation: Conversation) => void;
}

export function ConversationList({ onConversationClick }: ConversationListProps) {
  const {
    groupedConversations,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
  } = useConversations();

  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Infinite scroll observer
  useEffect(() => {
    const element = loadMoreRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [hasMore, loading, loadMore]);

  const handleStarToggle = useCallback(async (id: string, starred: boolean) => {
    try {
      await toggleStarred(id, starred);
    } catch (err) {
      console.error('Failed to toggle starred:', err);
      // Could add toast notification here
    }
  }, []);

  // Get ordered date keys (Today first, then Yesterday, then by date)
  const dateKeys = Object.keys(groupedConversations);
  const orderedKeys = dateKeys.sort((a, b) => {
    if (a === 'Today') return -1;
    if (b === 'Today') return 1;
    if (a === 'Yesterday') return -1;
    if (b === 'Yesterday') return 1;
    // For other dates, use actual conversation timestamps instead of parsing
    // the date string (which lacks year info and causes incorrect sorting)
    const convA = groupedConversations[a][0];
    const convB = groupedConversations[b][0];
    const dateA = new Date(convA?.started_at || convA?.created_at);
    const dateB = new Date(convB?.started_at || convB?.created_at);
    return dateB.getTime() - dateA.getTime();
  });

  const isEmpty = !loading && orderedKeys.length === 0;

  return (
    <div className="flex-1 overflow-auto px-4 py-6 lg:px-8">
      {/* Error state */}
      <AnimatePresence mode="wait">
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className={cn(
              'flex items-center gap-3 p-4 mb-6 rounded-xl',
              'bg-error/10 border border-error/20 text-error'
            )}
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <p className="flex-1 text-sm">{error}</p>
            <button
              onClick={refresh}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg',
                'bg-error/10 hover:bg-error/20 transition-colors',
                'text-sm font-medium'
              )}
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading state */}
      {loading && orderedKeys.length === 0 && (
        <div className="space-y-8">
          <DateGroupSkeleton count={3} />
          <DateGroupSkeleton count={2} />
        </div>
      )}

      {/* Empty state */}
      {isEmpty && !error && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={cn(
            'flex flex-col items-center justify-center',
            'py-16 text-center'
          )}
        >
          <div
            className={cn(
              'w-16 h-16 rounded-2xl mb-4',
              'bg-bg-tertiary flex items-center justify-center'
            )}
          >
            <MessageSquare className="w-8 h-8 text-text-quaternary" />
          </div>
          <h3 className="text-lg font-medium text-text-primary mb-2">
            No conversations yet
          </h3>
          <p className="text-text-tertiary max-w-sm">
            Start a conversation with your Omi device and it will appear here.
          </p>
        </motion.div>
      )}

      {/* Conversation groups */}
      {orderedKeys.length > 0 && (
        <div className="space-y-8 max-w-3xl mx-auto">
          {orderedKeys.map((dateKey) => (
            <DateGroup
              key={dateKey}
              dateLabel={dateKey}
              conversations={groupedConversations[dateKey]}
              onConversationClick={onConversationClick}
              onStarToggle={handleStarToggle}
            />
          ))}

          {/* Load more trigger */}
          <div ref={loadMoreRef} className="h-10 flex items-center justify-center">
            {loading && orderedKeys.length > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center gap-2 text-text-quaternary"
              >
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span className="text-sm">Loading more...</span>
              </motion.div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
