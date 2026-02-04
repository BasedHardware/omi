'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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
  selectedIds?: string[];
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
  const containerRef = useRef<HTMLDivElement>(null);

  // Virtual scrolling setup with dynamic measurement
  const virtualizer = useVirtualizer({
    count: memories.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 100, // Initial estimate, will be measured dynamically
    overscan: 5, // Render 5 extra items above/below viewport
    gap: 12, // 12px gap between items (equivalent to gap-3)
    measureElement: (element) => element.getBoundingClientRect().height,
  });

  // Infinite scroll - trigger when approaching end of virtual items
  useEffect(() => {
    const virtualItems = virtualizer.getVirtualItems();
    if (!virtualItems.length) return;

    const lastItem = virtualItems[virtualItems.length - 1];
    if (!lastItem) return;

    // Trigger load more when within 5 items of the end
    if (
      lastItem.index >= memories.length - 5 &&
      hasMore &&
      !loading &&
      !loadingMore
    ) {
      setLoadingMore(true);
      onLoadMore().finally(() => {
        setLoadingMore(false);
      });
    }
  }, [
    memories.length,
    hasMore,
    loading,
    loadingMore,
    onLoadMore,
    virtualizer,
  ]);

  // Scroll to highlighted memory
  useEffect(() => {
    if (highlightedMemoryId) {
      const index = memories.findIndex((m) => m.id === highlightedMemoryId);
      if (index !== -1) {
        virtualizer.scrollToIndex(index, {
          align: 'center',
          behavior: 'smooth',
        });
      }
    }
  }, [highlightedMemoryId, memories, virtualizer]);

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

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={containerRef}
      className="flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-bg-quaternary scrollbar-track-transparent"
      style={{ maxHeight: 'calc(100vh - 350px)' }}
    >
      {/* Virtual scrolling container */}
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {/* Only render visible items */}
        {virtualItems.map((virtualItem) => {
          const memory = memories[virtualItem.index];
          if (!memory) return null;

          return (
            <div
              key={memory.id}
              id={`memory-${memory.id}`}
              data-index={virtualItem.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              <MemoryCard
                memory={memory}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleVisibility={onToggleVisibility}
                onAccept={onAccept}
                onReject={onReject}
                isHighlighted={highlightedMemoryId === memory.id}
                isSelected={selectedIds?.includes(memory.id)}
                onToggleSelect={onToggleSelect}
                onEnterSelectionMode={onEnterSelectionMode}
              />
            </div>
          );
        })}
      </div>

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
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
