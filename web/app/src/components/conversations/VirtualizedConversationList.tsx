'use client';

import { memo, useCallback, useMemo, useRef, useEffect, type CSSProperties, type ReactElement } from 'react';
import { List, useListRef, type ListImperativeAPI } from 'react-window';
import { AutoSizer } from 'react-virtualized-auto-sizer';
import { cn } from '@/lib/utils';
import { ConversationCard } from './ConversationCard';
import type { Conversation } from '@/types/conversation';

// Item types for the flattened list
type ListItem =
  | { type: 'header'; dateLabel: string }
  | { type: 'conversation'; conversation: Conversation; dateLabel: string };

// Item heights
const HEADER_HEIGHT = 32;
const CARD_HEIGHT = 100;
const CARD_GAP = 6;

interface VirtualizedConversationListProps {
  groupedConversations: Record<string, Conversation[]>;
  orderedKeys: string[];
  onConversationClick?: (conversation: Conversation) => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  selectedId?: string | null;
  isSelectionMode?: boolean;
  selectedIds?: Set<string>;
  onSelect?: (id: string) => void;
  mergingIds?: Set<string>;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loading?: boolean;
  onEnterSelectionMode?: (id: string) => void;
}

// Memoized conversation card to prevent re-renders
const MemoizedConversationCard = memo(ConversationCard);

// Row props type for react-window v2
interface RowProps {
  items: ListItem[];
  onConversationClick?: (conversation: Conversation) => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  selectedId?: string | null;
  isSelectionMode?: boolean;
  selectedIds?: Set<string>;
  onSelect?: (id: string) => void;
  mergingIds?: Set<string>;
  onEnterSelectionMode?: (id: string) => void;
}

// Row component for react-window v2
function RowComponent({
  index,
  style,
  items,
  onConversationClick,
  onStarToggle,
  selectedId,
  isSelectionMode,
  selectedIds,
  onSelect,
  mergingIds,
  onEnterSelectionMode,
}: {
  ariaAttributes: {
    'aria-posinset': number;
    'aria-setsize': number;
    role: 'listitem';
  };
  index: number;
  style: CSSProperties;
} & RowProps): ReactElement {
  const item = items[index];

  if (item.type === 'header') {
    return (
      <div style={style}>
        <h2
          className={cn(
            'sticky top-0 z-10',
            'px-1 py-1.5',
            'text-xs font-medium text-text-quaternary uppercase tracking-wide',
            'bg-bg-primary'
          )}
        >
          {item.dateLabel}
        </h2>
      </div>
    );
  }

  return (
    <div style={{ ...style, paddingBottom: CARD_GAP }}>
      <MemoizedConversationCard
        conversation={item.conversation}
        onClick={() => onConversationClick?.(item.conversation)}
        onStarToggle={onStarToggle}
        isSelected={selectedId === item.conversation.id}
        compact={false}
        isSelectionMode={isSelectionMode}
        isChecked={selectedIds?.has(item.conversation.id) ?? false}
        onSelect={onSelect}
        isMerging={mergingIds?.has(item.conversation.id) ?? false}
        onEnterSelectionMode={onEnterSelectionMode}
      />
    </div>
  );
}

export function VirtualizedConversationList({
  groupedConversations,
  orderedKeys,
  onConversationClick,
  onStarToggle,
  selectedId,
  isSelectionMode = false,
  selectedIds,
  onSelect,
  mergingIds,
  hasMore = false,
  onLoadMore,
  loading = false,
  onEnterSelectionMode,
}: VirtualizedConversationListProps) {
  const listRef = useListRef(null);
  const loadMoreTriggeredRef = useRef(false);

  // Flatten the grouped conversations into a single list with headers
  const flatItems = useMemo<ListItem[]>(() => {
    const items: ListItem[] = [];

    for (const dateKey of orderedKeys) {
      const conversations = groupedConversations[dateKey];
      if (!conversations?.length) continue;

      // Add header
      items.push({ type: 'header', dateLabel: dateKey });

      // Add conversations
      for (const conversation of conversations) {
        items.push({ type: 'conversation', conversation, dateLabel: dateKey });
      }
    }

    return items;
  }, [groupedConversations, orderedKeys]);

  // Get item size based on type - function for variable row heights
  const getRowHeight = useCallback(
    (index: number, _rowProps: RowProps) => {
      const item = flatItems[index];
      if (item?.type === 'header') {
        return HEADER_HEIGHT;
      }
      return CARD_HEIGHT + CARD_GAP;
    },
    [flatItems]
  );

  // Reset load more trigger when loading completes
  useEffect(() => {
    if (!loading) {
      loadMoreTriggeredRef.current = false;
    }
  }, [loading]);

  // Handle rows rendered to detect when to load more
  const handleRowsRendered = useCallback(
    (
      visibleRows: { startIndex: number; stopIndex: number },
      allRows: { startIndex: number; stopIndex: number }
    ) => {
      if (!hasMore || loading || !onLoadMore || loadMoreTriggeredRef.current) return;

      // Load more when we're near the end of the list
      const threshold = 5; // Start loading when within 5 items of the end
      if (allRows.stopIndex >= flatItems.length - threshold) {
        loadMoreTriggeredRef.current = true;
        onLoadMore();
      }
    },
    [hasMore, loading, onLoadMore, flatItems.length]
  );

  // Row props to pass to the row component
  const rowProps = useMemo<RowProps>(
    () => ({
      items: flatItems,
      onConversationClick,
      onStarToggle,
      selectedId,
      isSelectionMode,
      selectedIds,
      onSelect,
      mergingIds,
      onEnterSelectionMode,
    }),
    [flatItems, onConversationClick, onStarToggle, selectedId, isSelectionMode, selectedIds, onSelect, mergingIds, onEnterSelectionMode]
  );

  if (flatItems.length === 0) {
    return null;
  }

  return (
    <AutoSizer
      renderProp={({ height, width }) => (
        <List
          listRef={listRef}
          rowComponent={RowComponent}
          rowCount={flatItems.length}
          rowHeight={getRowHeight}
          rowProps={rowProps}
          onRowsRendered={handleRowsRendered}
          overscanCount={5}
          className="scrollbar-thin scrollbar-thumb-bg-quaternary scrollbar-track-transparent"
          style={{ height: height ?? 400, width: width ?? '100%' }}
        />
      )}
    />
  );
}
