'use client';

import {
  useState,
  useCallback,
  useMemo,
  useTransition,
  useEffect,
  useDeferredValue,
  lazy,
  Suspense,
} from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import {
  List,
  Network,
  Loader2,
  Tag,
  Flame,
  TrendingUp,
  Plus,
  ArrowUpDown,
  ChevronDown,
  CheckSquare,
  Square,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { matchesCategories } from '@/lib/memoryCategory';
import { useMemories } from '@/hooks/useMemories';
import { MemoryList, MemoryListSkeleton } from './MemoryList';
import { MemoryFilters } from './MemoryFilters';
import { MemoryQuickAdd } from './MemoryQuickAdd';
import { LifeBalanceChart, TrendingSidebar } from './InsightsDashboard';
import { useInsightsDashboard } from '@/hooks/useInsightsDashboard';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { PageToolbar } from '@/components/layout/PageToolbar';
import { BulkActionBar } from '@/components/tasks/BulkActionBar';
import { copyMemoriesToClipboard, downloadMemories } from '@/lib/memoryExport';
import { useChat as useChatContext } from '@/components/chat/ChatContext';

// Lazy load heavy components for better performance
const KnowledgeGraph = lazy(() =>
  import('./KnowledgeGraph').then((m) => ({ default: m.KnowledgeGraph })),
);
const InsightsDashboard = lazy(() =>
  import('./InsightsDashboard').then((m) => ({ default: m.InsightsDashboard })),
);

type ViewMode = 'list' | 'graph' | 'tags';
type SortOption = 'score' | 'created_desc' | 'created_asc' | 'updated_desc';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'score', label: 'Relevance' },
  { value: 'created_desc', label: 'Newest First' },
  { value: 'created_asc', label: 'Oldest First' },
  { value: 'updated_desc', label: 'Recently Updated' },
];

export function MemoriesPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('created_desc');
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [highlightedMemoryId, setHighlightedMemoryId] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const reduceMotion = useReducedMotion();

  const {
    memories,
    loading,
    error,
    hasMore,
    loadMore,
    addMemory,
    editMemory,
    removeMemory,
    removeMemories,
    toggleVisibility,
    acceptMemory,
    rejectMemory,
    setCategories,
    activeCategories,
  } = useMemories();

  // Chat context for passing selected memory info
  const { setContext } = useChatContext();

  // Extract single selected ID as a primitive to avoid array reference in dependency array
  const singleSelectedId = selectedIds.length === 1 ? selectedIds[0] : null;

  // Create memoized lookup map for O(1) memory access
  const memoriesById = useMemo(() => {
    const map = new Map<string, (typeof memories)[0]>();
    memories.forEach((m) => map.set(m.id, m));
    return map;
  }, [memories]);

  // Set chat context when a memory is highlighted or single selected
  useEffect(() => {
    const targetId = highlightedMemoryId || singleSelectedId;
    if (targetId) {
      const memory = memoriesById.get(targetId);
      if (memory) {
        setContext({
          type: 'memory',
          id: memory.id,
          title:
            memory.content.substring(0, 50) + (memory.content.length > 50 ? '...' : ''),
          summary: memory.content,
        });
      } else {
        setContext(null);
      }
    } else {
      setContext(null);
    }
  }, [highlightedMemoryId, singleSelectedId, memoriesById, setContext]);

  // Clear chat context when component unmounts
  useEffect(() => {
    return () => setContext(null);
  }, [setContext]);

  // Defer memories to prevent blocking UI during heavy computations
  const deferredMemories = useDeferredValue(memories);

  // Get insights data for sidebar - defer computation when loading empty state
  const insightsInput = loading && memories.length === 0 ? [] : deferredMemories;
  const insights = useInsightsDashboard(insightsInput);
  const { lifeBalance, risingTags, fadingTags } = insights;

  // Calculate tag stats from all memories
  const tagStats = useMemo(() => {
    const tagCounts: Record<string, number> = {};
    deferredMemories.forEach((memory) => {
      if (memory.tags && Array.isArray(memory.tags)) {
        memory.tags.forEach((tag) => {
          tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        });
      }
    });
    return Object.entries(tagCounts)
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count);
  }, [deferredMemories]);

  // Get top tags for display
  const topTags = tagStats.slice(0, 12);
  const allTags = tagStats;

  // Combined date calculations in a single pass through memories - uses deferred value
  const { recentMemoriesCount, todayMemories, activityData } = useMemo(() => {
    const now = new Date();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayStr = today.toISOString();

    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const sevenDaysAgoStr = sevenDaysAgo.toISOString();

    now.setHours(23, 59, 59, 999);
    const thirtyDaysAgo = new Date(now);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 29);
    thirtyDaysAgo.setHours(0, 0, 0, 0);

    // Initialize counts for each day
    const dayCounts: Record<string, number> = {};
    for (let i = 0; i < 30; i++) {
      const date = new Date(thirtyDaysAgo);
      date.setDate(date.getDate() + i);
      dayCounts[date.toISOString().split('T')[0]] = 0;
    }

    // Single pass through all memories
    let recentCount = 0;
    const todayMems: typeof deferredMemories = [];

    for (const m of deferredMemories) {
      // Check for recent (last 7 days)
      if (m.created_at >= sevenDaysAgoStr) {
        recentCount++;
      }
      // Check for today
      if (m.created_at >= todayStr) {
        todayMems.push(m);
      }
      // Count for activity chart (last 30 days)
      const dateKey = m.created_at.split('T')[0];
      if (dateKey in dayCounts) {
        dayCounts[dateKey]++;
      }
    }

    const activityDataResult = Object.entries(dayCounts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, count]) => ({ date, count }));

    return {
      recentMemoriesCount: recentCount,
      todayMemories: todayMems,
      activityData: activityDataResult,
    };
  }, [deferredMemories]);

  // Filter and sort memories - optimized to avoid full copy when not needed
  const filteredMemories = useMemo(() => {
    // If no filters and backend's default sort (score), return original deferred array (no copy needed)
    if (
      !searchQuery &&
      !selectedTag &&
      activeCategories.length === 0 &&
      sortBy === 'score'
    ) {
      return deferredMemories;
    }

    // Only filter what we need
    let result = deferredMemories;

    // Filter by category. `/v3/memories` has no `categories` parameter, so this
    // cannot be pushed to the server — selecting a category used to change
    // nothing at all.
    if (activeCategories.length > 0) {
      result = result.filter((m) => matchesCategories(m, activeCategories));
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((m) => m.content.toLowerCase().includes(query));
    }

    // Filter by selected tag
    if (selectedTag) {
      result = result.filter((m) => m.tags && m.tags.includes(selectedTag));
    }

    // Apply sorting (skip only for 'score' which is backend's default)
    if (sortBy !== 'score') {
      // Only create copy if we're still using original array reference
      const needsCopy = result === deferredMemories;
      result = needsCopy ? [...result] : result;

      switch (sortBy) {
        case 'created_desc':
          result.sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
          );
          break;
        case 'created_asc':
          result.sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
          );
          break;
        case 'updated_desc':
          result.sort(
            (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
          );
          break;
      }
    }

    return result;
  }, [deferredMemories, searchQuery, selectedTag, activeCategories, sortBy]);

  // Handle node selection from graph
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleNodeSelect = useCallback((_nodeId: string, _memoryIds: string[]) => {
    // Node selection handler - can be extended for future features
  }, []);

  // Handle tag click with transition for smooth loading
  const handleTagClick = (tag: string) => {
    startTransition(() => {
      setSelectedTag(selectedTag === tag ? null : tag);
    });
  };

  // Handle clicking on a memory in the sidebar to scroll to it
  const handleMemoryClick = useCallback((memoryId: string) => {
    // Clear any tag/search filters first
    setSelectedTag(null);
    setSearchQuery('');

    // Wait for DOM to update, then scroll
    setTimeout(() => {
      const element = document.getElementById(`memory-${memoryId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight the memory briefly
        setHighlightedMemoryId(memoryId);
        setTimeout(() => setHighlightedMemoryId(null), 2000);
      }
    }, 100);
  }, []);

  // Handle selection toggle for a single memory
  const handleToggleSelect = useCallback((memoryId: string) => {
    setSelectedIds((prev) =>
      prev.includes(memoryId)
        ? prev.filter((id) => id !== memoryId)
        : [...prev, memoryId],
    );
  }, []);

  // Toggle select mode
  const toggleSelectMode = useCallback(() => {
    if (isSelectMode) {
      // Exiting select mode - clear selection
      setSelectedIds([]);
    }
    setIsSelectMode(!isSelectMode);
  }, [isSelectMode]);

  // Enter selection mode and select the specified memory (for double-click)
  const enterSelectionModeWithId = useCallback((id: string) => {
    setIsSelectMode(true);
    setSelectedIds([id]);
  }, []);

  // Handle select all visible memories
  const handleSelectAll = useCallback(() => {
    if (selectedIds.length === filteredMemories.length) {
      // Deselect all
      setSelectedIds([]);
    } else {
      // Select all filtered memories
      setSelectedIds(filteredMemories.map((m) => m.id));
    }
  }, [filteredMemories, selectedIds.length]);

  // Handle bulk delete - show confirmation dialog
  const handleBulkDeleteClick = useCallback(() => {
    if (selectedIds.length === 0) return;
    setShowDeleteConfirm(true);
  }, [selectedIds.length]);

  // Execute bulk delete after confirmation
  const executeBulkDelete = useCallback(async () => {
    setIsDeleting(true);
    try {
      // Single batched request (chunked internally by removeMemories) instead of N
      // concurrent DELETEs that triggered 429s. On full success the selection clears;
      // on partial failure only the not-yet-deleted ids stay selected, so a retry never
      // re-sends ids the server already removed (which the all-or-nothing endpoint
      // would 404 on).
      const { success, deletedIds } = await removeMemories(selectedIds);
      if (success) {
        setSelectedIds([]);
        setIsSelectMode(false);
        setShowDeleteConfirm(false);
      } else if (deletedIds.length > 0) {
        // Drop ids already deleted by earlier successful chunks; keep only the failed /
        // un-attempted ids selected and retryable.
        const deleted = new Set(deletedIds);
        setSelectedIds((prev) => prev.filter((id) => !deleted.has(id)));
      }
    } finally {
      setIsDeleting(false);
    }
  }, [selectedIds, removeMemories]);

  // Handle copy to clipboard
  const handleCopy = useCallback(async () => {
    const selected = memories.filter((m) => selectedIds.includes(m.id));
    await copyMemoriesToClipboard(selected);
  }, [memories, selectedIds]);

  // Handle export
  const handleExport = useCallback(
    (format: 'csv' | 'json' | 'markdown') => {
      const selected = memories.filter((m) => selectedIds.includes(m.id));
      downloadMemories(selected, format);
    },
    [memories, selectedIds],
  );

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedIds([]);
  }, []);

  // Calculate max activity for chart scaling
  const maxActivity = Math.max(...activityData.map((d) => d.count), 1);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageToolbar
        search={
          viewMode === 'list'
            ? {
                value: searchQuery,
                onChange: setSearchQuery,
                placeholder: 'Search memories...',
              }
            : undefined
        }
        controls={
          <>
            {/* Left: View toggle */}
            <div className="flex items-center gap-4 flex-shrink-0">
              <div className="flex items-center gap-1 p-1 bg-bg-tertiary rounded-lg">
                <button
                  onClick={() => setViewMode('list')}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm font-medium',
                    'transition-all duration-150',
                    viewMode === 'list'
                      ? 'bg-white text-black'
                      : 'text-text-tertiary hover:text-text-primary',
                  )}
                >
                  <List className="w-4 h-4" />
                  List
                </button>
                <button
                  onClick={() => setViewMode('graph')}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm font-medium',
                    'transition-all duration-150',
                    viewMode === 'graph'
                      ? 'bg-white text-black'
                      : 'text-text-tertiary hover:text-text-primary',
                  )}
                >
                  <Network className="w-4 h-4" />
                  Graph
                </button>
                <button
                  onClick={() => setViewMode('tags')}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm font-medium',
                    'transition-all duration-150',
                    viewMode === 'tags'
                      ? 'bg-white text-black'
                      : 'text-text-tertiary hover:text-text-primary',
                  )}
                >
                  <Sparkles className="w-4 h-4" />
                  Insights
                </button>
              </div>

              {/* Select mode toggle - moved to left */}
              {viewMode === 'list' && filteredMemories.length > 0 && (
                <button
                  onClick={toggleSelectMode}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                    'transition-colors',
                    isSelectMode
                      ? 'bg-white/10 text-white'
                      : 'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary',
                  )}
                >
                  {isSelectMode ? (
                    <>
                      <CheckSquare className="w-4 h-4" />
                      <span>Selecting</span>
                    </>
                  ) : (
                    <>
                      <Square className="w-4 h-4" />
                      <span>Select</span>
                    </>
                  )}
                </button>
              )}

              {/* Sort dropdown - moved to left */}
              {viewMode === 'list' && (
                <div className="relative">
                  <button
                    onClick={() => setShowSortMenu(!showSortMenu)}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg',
                      'bg-bg-tertiary border border-bg-quaternary',
                      'text-sm text-text-secondary hover:text-text-primary',
                      'transition-colors',
                    )}
                  >
                    <ArrowUpDown className="w-4 h-4" />
                    <span className="hidden sm:inline">
                      {SORT_OPTIONS.find((o) => o.value === sortBy)?.label}
                    </span>
                    <ChevronDown
                      className={cn(
                        'w-3 h-3 transition-transform',
                        showSortMenu && 'rotate-180',
                      )}
                    />
                  </button>
                  {showSortMenu && (
                    <>
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setShowSortMenu(false)}
                      />
                      <div className="absolute left-0 top-full mt-1 z-50 bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg py-1 min-w-[160px]">
                        {SORT_OPTIONS.map((option) => (
                          <button
                            key={option.value}
                            onClick={() => {
                              setSortBy(option.value);
                              setShowSortMenu(false);
                            }}
                            className={cn(
                              'w-full text-left px-3 py-2 text-sm',
                              'hover:bg-bg-tertiary transition-colors',
                              sortBy === option.value
                                ? 'text-white'
                                : 'text-text-secondary',
                            )}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Filter dropdown - moved to left */}
              {viewMode === 'list' && (
                <MemoryFilters
                  activeCategories={activeCategories}
                  onCategoriesChange={setCategories}
                />
              )}
            </div>
          </>
        }
      />

      {/* Content - Two column layout */}
      <div className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col lg:flex-row w-full max-w-full overflow-x-hidden">
          {/* Left Column - Memories list */}
          <div
            data-testid="memories-list-column"
            className="flex-1 min-h-0 overflow-y-auto lg:overflow-hidden p-4 space-y-4 lg:space-y-0 lg:flex lg:flex-col lg:gap-4 min-w-0 order-1"
          >
            {viewMode === 'list' ? (
              <>
                {/* Quick add */}
                <MemoryQuickAdd onAdd={addMemory} />

                {/* Bulk action bar - only shown in select mode */}
                {isSelectMode && (
                  <BulkActionBar
                    inline
                    selectedCount={selectedIds.length}
                    onDelete={handleBulkDeleteClick}
                    onClear={clearSelection}
                    onCopy={handleCopy}
                    onExport={handleExport}
                    onSelectAll={handleSelectAll}
                    onDone={toggleSelectMode}
                    allSelected={
                      selectedIds.length === filteredMemories.length &&
                      filteredMemories.length > 0
                    }
                    totalCount={filteredMemories.length}
                    hideComplete
                    hideSnooze
                  />
                )}

                {/* Error state */}
                {error && (
                  <div className="p-3 rounded-lg bg-error/10 border border-error/30 text-error text-sm">
                    {error}
                  </div>
                )}

                {/* Selected tag indicator */}
                {selectedTag && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text-secondary">
                      Showing memories tagged with &quot;{selectedTag}&quot;
                    </span>
                    <button
                      onClick={() => setSelectedTag(null)}
                      className="text-xs text-white hover:underline"
                    >
                      Clear filter
                    </button>
                  </div>
                )}

                {/* Memory list */}
                <div data-testid="memory-list-transition" className="grid flex-1 min-h-0">
                  <AnimatePresence mode="sync" initial={false}>
                    {(loading && memories.length === 0) || isPending ? (
                      <motion.div
                        key="memory-list-skeleton"
                        data-testid="memory-list-skeleton-state"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{
                          duration: reduceMotion ? 0.08 : 0.18,
                          ease: [0.23, 1, 0.32, 1],
                        }}
                        className="col-start-1 row-start-1 min-h-0 overflow-hidden"
                      >
                        <MemoryListSkeleton />
                      </motion.div>
                    ) : (
                      <motion.div
                        key="memory-list-content"
                        data-testid="memory-list-content-state"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{
                          duration: reduceMotion ? 0.08 : 0.18,
                          ease: [0.23, 1, 0.32, 1],
                        }}
                        className="col-start-1 row-start-1 flex min-h-0 flex-col"
                      >
                        <MemoryList
                          memories={filteredMemories}
                          loading={loading}
                          hasMore={hasMore && !searchQuery && !selectedTag}
                          onLoadMore={loadMore}
                          onEdit={editMemory}
                          onDelete={removeMemory}
                          onToggleVisibility={toggleVisibility}
                          onAccept={acceptMemory}
                          onReject={rejectMemory}
                          highlightedMemoryId={highlightedMemoryId}
                          // Only pass selection props when in select mode
                          selectedIds={isSelectMode ? selectedIds : undefined}
                          onToggleSelect={isSelectMode ? handleToggleSelect : undefined}
                          // Pass onEnterSelectionMode when NOT in select mode (for double-click)
                          onEnterSelectionMode={
                            !isSelectMode ? enterSelectionModeWithId : undefined
                          }
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </>
            ) : viewMode === 'graph' ? (
              <Suspense
                fallback={
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="w-8 h-8 animate-spin text-white" />
                    <span className="ml-2 text-text-tertiary">Loading graph...</span>
                  </div>
                }
              >
                <KnowledgeGraph onNodeSelect={handleNodeSelect} />
              </Suspense>
            ) : (
              <Suspense
                fallback={
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="w-8 h-8 animate-spin text-white" />
                    <span className="ml-2 text-text-tertiary">Loading insights...</span>
                  </div>
                }
              >
                <InsightsDashboard
                  insights={insights}
                  onTagSelect={(tags) => {
                    // Use the first tag for filtering
                    setSelectedTag(tags[0] || null);
                    setViewMode('list');
                  }}
                />
              </Suspense>
            )}
          </div>

          {/* Right Column - Insights sidebar */}
          {viewMode === 'list' && (
            <div className="w-full lg:w-[380px] lg:flex-shrink-0 p-4 lg:pl-6 lg:border-l border-bg-tertiary space-y-4 lg:h-full lg:overflow-y-auto min-w-0 max-w-full order-2">
              {/* Loading state */}
              {loading && memories.length === 0 ? (
                <div className="space-y-4">
                  <div className="h-32 bg-bg-secondary border border-bg-tertiary rounded-xl animate-pulse" />
                  <div className="h-44 bg-bg-secondary border border-bg-tertiary rounded-xl animate-pulse" />
                </div>
              ) : (
                <>
                  {/* Stats Card */}
                  <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
                    <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-white" />
                      Insights
                    </h3>

                    {/* Total memories */}
                    <div className="mb-3">
                      <div className="text-2xl font-bold text-white">
                        {memories.length}
                      </div>
                      <div className="text-sm text-text-secondary">Total Memories</div>
                      {recentMemoriesCount > 0 && (
                        <div className="text-xs text-green-400 mt-1">
                          +{recentMemoriesCount} this week
                        </div>
                      )}
                    </div>

                    {/* Streak indicator */}
                    {todayMemories.length > 0 && (
                      <div className="flex items-center gap-2 mb-3">
                        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-orange-500/10">
                          <Flame className="w-3.5 h-3.5 text-orange-500" />
                          <span className="text-sm font-medium text-orange-500">
                            {todayMemories.length} today
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Activity Chart (30 days) */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-text-quaternary">
                          Activity (30 days)
                        </span>
                        <span className="text-xs text-text-quaternary">
                          {recentMemoriesCount} memories
                        </span>
                      </div>
                      <div className="flex items-end gap-0.5 h-10">
                        {activityData.map((day) => (
                          <div
                            key={day.date}
                            className="flex-1 bg-white/20 rounded-t transition-all hover:bg-white/40"
                            style={{
                              height: `${Math.max((day.count / maxActivity) * 100, 4)}%`,
                            }}
                            title={`${day.date}: ${day.count} memories`}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Life Balance Radar */}
                  {lifeBalance.length > 0 && lifeBalance.some((d) => d.rawCount > 0) && (
                    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
                      <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-white" />
                        Life Balance
                      </h3>
                      <LifeBalanceChart data={lifeBalance} compact />
                    </div>
                  )}

                  {/* Trending Topics */}
                  {(risingTags.length > 0 || fadingTags.length > 0) && (
                    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
                      <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-white" />
                        Trending
                      </h3>
                      <TrendingSidebar
                        risingTags={risingTags}
                        fadingTags={fadingTags}
                        onTagClick={handleTagClick}
                      />
                    </div>
                  )}

                  {/* Top Tags Card */}
                  {allTags.length > 0 && (
                    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider flex items-center gap-2">
                          <Tag className="w-4 h-4 text-white" />
                          Top Tags
                        </h3>
                        <button
                          onClick={() => setViewMode('tags')}
                          className={cn(
                            'p-1.5 rounded-md transition-colors',
                            'text-text-quaternary hover:text-white hover:bg-white/10',
                          )}
                          title="View all tags"
                        >
                          <Network className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="space-y-2">
                        {allTags.slice(0, 5).map(({ tag, count }) => {
                          const maxCount = allTags[0]?.count || 1;
                          const percent = (count / maxCount) * 100;
                          return (
                            <button
                              key={tag}
                              onClick={() => handleTagClick(tag)}
                              className={cn(
                                'w-full text-left group p-1 -m-1 rounded-md',
                                selectedTag === tag && 'ring-1 ring-white bg-white/5',
                              )}
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-sm text-text-primary group-hover:text-white transition-colors">
                                  {tag}
                                </span>
                                <span className="text-xs text-text-quaternary">
                                  {count}
                                </span>
                              </div>
                              <div className="h-1 bg-bg-quaternary rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-gradient-to-r from-white/60 to-white/30 rounded-full transition-all"
                                  style={{ width: `${percent}%` }}
                                />
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Added Today Card */}
                  {todayMemories.length > 0 && (
                    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
                      <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Plus className="w-4 h-4 text-white" />
                        Added Today
                      </h3>
                      <div className="space-y-2">
                        {todayMemories.slice(0, 3).map((memory) => (
                          <button
                            key={memory.id}
                            onClick={() => handleMemoryClick(memory.id)}
                            className="w-full text-left text-sm text-text-secondary line-clamp-3 p-2.5 rounded-lg bg-bg-tertiary hover:bg-bg-quaternary hover:text-text-primary transition-colors"
                          >
                            {memory.content}
                          </button>
                        ))}
                        {todayMemories.length > 3 && (
                          <p className="text-xs text-text-quaternary text-center pt-1">
                            +{todayMemories.length - 3} more today
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Memories"
        description={`Are you sure you want to delete ${selectedIds.length} ${selectedIds.length === 1 ? 'memory' : 'memories'}? This action cannot be undone.`}
        confirmLabel={isDeleting ? 'Deleting...' : 'Delete'}
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={executeBulkDelete}
        isLoading={isDeleting}
      />
    </div>
  );
}
