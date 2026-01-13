'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
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
  highlightedMemoryId?: string | null;
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
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
  highlightedMemoryId,
  selectedIds,
  onToggleSelect,
  onEnterSelectionMode,
}: MemoryListProps) {
  const [loadingMore, setLoadingMore] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Infinite scroll using IntersectionObserver
  useEffect(() => {
    if (!bottomRef.current || loading || loadingMore || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          setLoadingMore(true);
          onLoadMore().finally(() => {
            setLoadingMore(false);
          });
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(bottomRef.current);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, onLoadMore]);

  // Scroll to highlighted memory
  useEffect(() => {
    if (highlightedMemoryId) {
      const element = document.getElementById(`memory-${highlightedMemoryId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightedMemoryId]);

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
    <div
      ref={containerRef}
      className="flex flex-col gap-3 overflow-y-auto scrollbar-thin scrollbar-thumb-bg-quaternary scrollbar-track-transparent"
      style={{ maxHeight: 'calc(100vh - 350px)' }}
    >
      <AnimatePresence mode="popLayout">
        {memories.map((memory) => (
          <motion.div
            key={memory.id}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.15 }}
          >
            <MemoryCard
              memory={memory}
              onEdit={onEdit}
              onDelete={onDelete}
              onToggleVisibility={onToggleVisibility}
              onAccept={onAccept}
              onReject={onReject}
              isHighlighted={highlightedMemoryId === memory.id}
              isSelected={selectedIds?.has(memory.id)}
              onToggleSelect={onToggleSelect}
              onEnterSelectionMode={onEnterSelectionMode}
            />
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Infinite scroll trigger */}
      <div ref={bottomRef} className="h-1" />

      {/* Loading indicator */}
      {(loading || loadingMore) && (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-5 h-5 text-purple-primary animate-spin" />
          <span className="ml-2 text-sm text-text-tertiary">Loading memories...</span>
        </div>
      )}

      {/* End of list indicator */}
      {!loading && !loadingMore && !hasMore && memories.length > 0 && (
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
