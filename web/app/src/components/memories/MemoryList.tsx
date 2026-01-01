'use client';

import { useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MemoryCard } from './MemoryCard';
import type { Memory, MemoryVisibility } from '@/types/conversation';

interface MemoryListProps {
  memories: Memory[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => Promise<void>;
  onEdit: (id: string, content: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
  onToggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  onAccept?: (id: string) => Promise<boolean>;
  onReject?: (id: string) => Promise<boolean>;
}

export function MemoryList({
  memories,
  loading,
  hasMore,
  onLoadMore,
  onEdit,
  onDelete,
  onToggleVisibility,
  onAccept,
  onReject,
}: MemoryListProps) {
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Intersection observer for infinite scroll
  const handleIntersection = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasMore && !loading) {
        onLoadMore();
      }
    },
    [hasMore, loading, onLoadMore]
  );

  useEffect(() => {
    const observer = new IntersectionObserver(handleIntersection, {
      root: null,
      rootMargin: '100px',
      threshold: 0,
    });

    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }

    return () => observer.disconnect();
  }, [handleIntersection]);

  // Empty state
  if (!loading && memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="w-16 h-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
          <Brain className="w-8 h-8 text-text-quaternary" />
        </div>
        <h3 className="text-lg font-medium text-text-primary mb-2">No memories yet</h3>
        <p className="text-sm text-text-tertiary max-w-sm">
          Memories will appear from your conversations, or you can add one manually above.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <AnimatePresence mode="popLayout">
        {memories.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggleVisibility={onToggleVisibility}
            onAccept={onAccept}
            onReject={onReject}
          />
        ))}
      </AnimatePresence>

      {/* Load more trigger */}
      <div ref={loadMoreRef} className="h-4" />

      {/* Loading indicator */}
      {loading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-center py-4"
        >
          <Loader2 className="w-5 h-5 text-purple-primary animate-spin" />
          <span className="ml-2 text-sm text-text-tertiary">Loading memories...</span>
        </motion.div>
      )}

      {/* End of list indicator */}
      {!loading && !hasMore && memories.length > 0 && (
        <p className="text-center text-sm text-text-quaternary py-4">
          You&apos;ve reached the end
        </p>
      )}
    </div>
  );
}

// Loading skeleton
export function MemoryListSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className={cn(
            'rounded-xl p-4',
            'bg-bg-tertiary border border-bg-quaternary',
            'animate-pulse'
          )}
        >
          <div className="flex items-start gap-3">
            <div className="w-4 h-4 rounded bg-bg-quaternary flex-shrink-0 mt-0.5" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-bg-quaternary rounded w-3/4" />
              <div className="h-4 bg-bg-quaternary rounded w-1/2" />
              <div className="flex gap-2 mt-2">
                <div className="h-5 bg-bg-quaternary rounded w-16" />
                <div className="h-5 bg-bg-quaternary rounded w-20" />
                <div className="h-5 bg-bg-quaternary rounded w-14" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
