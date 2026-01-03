'use client';

import { useEffect, useCallback, useState, useRef, type CSSProperties, type ReactElement } from 'react';
import { List, type ListImperativeAPI } from 'react-window';
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
}

// Row height for each memory card (approximate)
const ROW_HEIGHT = 120;
const OVERSCAN_COUNT = 5;

// Row props passed to each row
interface RowData {
  memories: Memory[];
  onEdit: (id: string, content: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
  onToggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  onAccept?: (id: string) => Promise<boolean>;
  onReject?: (id: string) => Promise<boolean>;
  highlightedMemoryId?: string | null;
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
}

// Row component for virtualized list - react-window v2 injects ariaAttributes, index, style
function MemoryRow(props: {
  ariaAttributes: {
    'aria-posinset': number;
    'aria-setsize': number;
    role: 'listitem';
  };
  index: number;
  style: CSSProperties;
} & RowData): ReactElement {
  const {
    index,
    style,
    memories,
    onEdit,
    onDelete,
    onToggleVisibility,
    onAccept,
    onReject,
    highlightedMemoryId,
    selectedIds,
    onToggleSelect,
  } = props;

  const memory = memories[index];
  if (!memory) {
    return <div style={style} />;
  }

  return (
    <div style={{ ...style, paddingBottom: 12, paddingRight: 8 }}>
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
      />
    </div>
  );
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
}: MemoryListProps) {
  const listRef = useRef<ListImperativeAPI>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [containerHeight, setContainerHeight] = useState(600);

  // Handle scroll to load more
  const handleRowsRendered = useCallback(
    (visibleRows: { startIndex: number; stopIndex: number }) => {
      // Load more when near the end
      if (
        hasMore &&
        !loading &&
        !loadingMore &&
        visibleRows.stopIndex >= memories.length - 5
      ) {
        setLoadingMore(true);
        onLoadMore().finally(() => {
          setLoadingMore(false);
        });
      }
    },
    [hasMore, loading, loadingMore, memories.length, onLoadMore]
  );

  // Scroll to highlighted memory
  useEffect(() => {
    if (highlightedMemoryId && listRef.current) {
      const index = memories.findIndex((m) => m.id === highlightedMemoryId);
      if (index !== -1) {
        listRef.current.scrollToRow({ index, align: 'center' });
      }
    }
  }, [highlightedMemoryId, memories, listRef]);

  // Calculate container height based on viewport
  useEffect(() => {
    const updateHeight = () => {
      // Use viewport height minus some padding for header/footer
      const height = Math.max(400, window.innerHeight - 350);
      setContainerHeight(height);
    };

    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => window.removeEventListener('resize', updateHeight);
  }, []);

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
    <div className="relative">
      <List
        listRef={listRef}
        defaultHeight={containerHeight}
        rowCount={memories.length}
        rowHeight={ROW_HEIGHT}
        rowComponent={MemoryRow}
        rowProps={{
          memories,
          onEdit,
          onDelete,
          onToggleVisibility,
          onAccept,
          onReject,
          highlightedMemoryId,
          selectedIds,
          onToggleSelect,
        }}
        overscanCount={OVERSCAN_COUNT}
        onRowsRendered={handleRowsRendered}
        className="scrollbar-thin scrollbar-thumb-bg-quaternary scrollbar-track-transparent"
        style={{ height: containerHeight }}
      />

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
