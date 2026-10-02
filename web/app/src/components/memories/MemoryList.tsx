'use client';

import { useEffect, useState, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Brain, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MemoryCard } from './MemoryCard';
import type { Memory, MemoryVisibility } from '@/types/conversation';
import type { MemoryUseAction } from '@/lib/api';

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
  onSetUse?: (id: string, action: MemoryUseAction) => Promise<boolean>;
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
  onSetUse,
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
    if (memories.length === 0 && hasMore && !loading && !loadingMore) {
      setLoadingMore(true);
      onLoadMore().finally(() => {
        setLoadingMore(false);
      });
      return;
    }
    if (!virtualItems.length) return;

    const lastItem = virtualItems[virtualItems.length - 1];
    if (!lastItem) return;

    // Trigger load more when within 5 items of the end
    if (lastItem.index >= memories.length - 5 && hasMore && !loading && !loadingMore) {
      setLoadingMore(true);
      onLoadMore().finally(() => {
        setLoadingMore(false);
      });
    }
  }, [memories.length, hasMore, loading, loadingMore, onLoadMore, virtualizer]);

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
  if (!loading && !hasMore && memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-bg-tertiary">
          <Brain className="h-8 w-8 text-text-quaternary" />
        </div>
        <h3 className="mb-2 text-lg font-medium text-text-primary">No memories yet</h3>
        <p className="max-w-sm text-sm text-text-tertiary">
          Memories will appear from your conversations, or you can add one manually above.
        </p>
      </div>
    );
  }

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={containerRef}
      role="region"
      aria-label="Memories list"
      className="flex max-h-[calc(100dvh-350px)] flex-col overflow-y-auto pr-2 [scrollbar-color:rgba(255,255,255,0.12)_transparent] [scrollbar-gutter:stable] [scrollbar-width:thin] lg:max-h-none lg:min-h-0 lg:flex-1 [&::-webkit-scrollbar-thumb:hover]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar]:w-1.5"
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
                onSetUse={onSetUse}
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
          <Loader2 className="h-5 w-5 animate-spin text-white" />
          <span className="ml-2 text-sm text-text-tertiary">Loading memories...</span>
        </div>
      )}

      {/* End of list indicator */}
      {!loading && !loadingMore && !hasMore && memories.length > 0 && (
        <p className="py-4 text-center text-sm text-text-quaternary">
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
            'border border-bg-quaternary bg-bg-tertiary',
            'animate-pulse motion-reduce:animate-none',
          )}
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5 h-4 w-4 flex-shrink-0 rounded bg-bg-quaternary" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-3/4 rounded bg-bg-quaternary" />
              <div className="h-4 w-1/2 rounded bg-bg-quaternary" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
