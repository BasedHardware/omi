'use client';

import { useCallback, useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import type { TimelineDayGroup } from '@/lib/conversationTimeline';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';
import { ConversationTile, ConversationTileSkeleton } from './ConversationTile';
import { RecapTile } from './RecapTile';

interface ConversationGalleryProps {
  groups: TimelineDayGroup[];
  selectedId: string | null;
  onConversationClick: (conversation: Conversation) => void;
  onRecapClick: (recap: DailySummary) => void;
  onStarToggle?: (id: string, starred: boolean) => void;
  isSelectionMode?: boolean;
  selectedIds?: Set<string>;
  onSelect?: (id: string) => void;
  mergingIds?: Set<string>;
  onEnterSelectionMode?: (id: string) => void;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loading?: boolean;
}

// Distance from the bottom of the scroller at which the next page is fetched.
const LOAD_MORE_THRESHOLD_PX = 400;

export function ConversationGallery({
  groups,
  selectedId,
  onConversationClick,
  onRecapClick,
  onStarToggle,
  isSelectionMode = false,
  selectedIds,
  onSelect,
  mergingIds,
  onEnterSelectionMode,
  hasMore = false,
  onLoadMore,
  loading = false,
}: ConversationGalleryProps) {
  // Guards against firing loadMore repeatedly for one scroll gesture while the
  // in-flight page has not yet grown the list.
  const loadRequestedRef = useRef(false);

  // The guard is armed by a request and disarmed by that request settling.
  // Clearing it only on scrolling away from the bottom means a page that
  // failed, or came back too short to move the scroller, leaves the guard
  // stuck on and the rest of the list permanently unreachable.
  const itemCount = groups.reduce((total, group) => total + group.items.length, 0);
  useEffect(() => {
    if (!loading) loadRequestedRef.current = false;
  }, [loading, itemCount]);

  const handleScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
      const nearBottom = scrollHeight - scrollTop - clientHeight < LOAD_MORE_THRESHOLD_PX;

      if (!nearBottom) {
        loadRequestedRef.current = false;
        return;
      }
      if (loading || !hasMore || loadRequestedRef.current) return;

      loadRequestedRef.current = true;
      onLoadMore?.();
    },
    [hasMore, loading, onLoadMore],
  );

  return (
    <div
      className="h-full overflow-y-auto px-5 pb-32"
      onScroll={handleScroll}
      data-testid="conversation-gallery-scroller"
      style={{
        maskImage:
          'linear-gradient(to bottom, black 0, black calc(100% - 8rem), transparent 100%)',
        WebkitMaskImage:
          'linear-gradient(to bottom, black 0, black calc(100% - 8rem), transparent 100%)',
      }}
    >
      {groups.map((group) => (
        <section key={group.key} className="mb-8">
          <div className="sticky top-0 z-10 -mx-5 px-5 py-2.5 bg-bg-primary/90 backdrop-blur-sm border-b border-stroke mb-4">
            <h2 className="text-xs font-medium uppercase tracking-[0.14em] text-text-tertiary">
              {group.label}
            </h2>
          </div>

          <div
            className="grid gap-3 items-stretch auto-rows-auto"
            style={{
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))',
            }}
            data-testid="conversation-gallery-grid"
          >
            {group.items.map((item) =>
              item.kind === 'recap' ? (
                <RecapTile
                  key={`recap-${item.id}`}
                  recap={item.recap}
                  isSelected={selectedId === item.id}
                  onClick={() => onRecapClick(item.recap)}
                />
              ) : (
                <ConversationTile
                  key={`conversation-${item.id}`}
                  conversation={item.conversation}
                  isSelected={selectedId === item.id}
                  onClick={() => onConversationClick(item.conversation)}
                  onStarToggle={onStarToggle}
                  isSelectionMode={isSelectionMode}
                  isChecked={selectedIds?.has(item.id) ?? false}
                  onSelect={onSelect}
                  isMerging={mergingIds?.has(item.id) ?? false}
                  onEnterSelectionMode={onEnterSelectionMode}
                />
              ),
            )}
          </div>
        </section>
      ))}

      {loading && groups.length > 0 && (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 text-text-tertiary animate-spin" />
        </div>
      )}
    </div>
  );
}

export function ConversationGallerySkeleton() {
  return (
    <div className="px-5 pb-8">
      {[0, 1].map((section) => (
        <div key={section} className="mb-8">
          <div className="h-3 w-24 rounded bg-bg-tertiary animate-pulse mb-4" />
          <div
            className="grid gap-3"
            style={{
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))',
            }}
          >
            {[0, 1, 2, 3].map((tile) => (
              <ConversationTileSkeleton key={tile} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
