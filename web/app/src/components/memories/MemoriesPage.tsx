'use client';

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { List, Network, Search, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMemories } from '@/hooks/useMemories';
import { MemoryList, MemoryListSkeleton } from './MemoryList';
import { MemoryFilters } from './MemoryFilters';
import { MemoryQuickAdd } from './MemoryQuickAdd';
import { KnowledgeGraph } from './KnowledgeGraph';

type ViewMode = 'list' | 'graph';

export function MemoriesPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [searchQuery, setSearchQuery] = useState('');

  const {
    memories,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
    addMemory,
    editMemory,
    removeMemory,
    toggleVisibility,
    acceptMemory,
    rejectMemory,
    setCategories,
    activeCategories,
  } = useMemories();

  // Filter memories by search query (client-side)
  const filteredMemories = searchQuery
    ? memories.filter((m) =>
        m.content.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : memories;

  // Handle node selection from graph
  const handleNodeSelect = useCallback((nodeId: string, memoryIds: string[]) => {
    // Could filter memories to show only those related to the selected node
    console.log('Selected node:', nodeId, 'with memories:', memoryIds);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header
        className={cn(
          'flex-shrink-0',
          'flex flex-col gap-4 px-4 py-4 lg:px-6',
          'bg-bg-primary/80 backdrop-blur-md',
          'border-b border-bg-tertiary'
        )}
      >
        {/* Top row: Title + View toggle + Actions */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* View toggle */}
            <div className="flex items-center gap-1 p-1 bg-bg-tertiary rounded-lg">
              <button
                onClick={() => setViewMode('list')}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium',
                  'transition-all duration-150',
                  viewMode === 'list'
                    ? 'bg-purple-primary/10 text-purple-primary'
                    : 'text-text-tertiary hover:text-text-primary'
                )}
              >
                <List className="w-4 h-4" />
                List
              </button>
              <button
                onClick={() => setViewMode('graph')}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium',
                  'transition-all duration-150',
                  viewMode === 'graph'
                    ? 'bg-purple-primary/10 text-purple-primary'
                    : 'text-text-tertiary hover:text-text-primary'
                )}
              >
                <Network className="w-4 h-4" />
                Graph
              </button>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {/* Refresh button */}
            <button
              onClick={refresh}
              disabled={loading}
              className={cn(
                'p-2 rounded-lg',
                'text-text-tertiary hover:text-text-primary',
                'hover:bg-bg-tertiary transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              title="Refresh memories"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <RefreshCw className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>

        {/* List view controls */}
        {viewMode === 'list' && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-quaternary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search memories..."
                className={cn(
                  'w-full pl-9 pr-4 py-2 rounded-lg',
                  'bg-bg-tertiary border border-bg-quaternary',
                  'text-sm text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                  'placeholder:text-text-quaternary'
                )}
              />
            </div>

            {/* Filters */}
            <MemoryFilters
              activeCategories={activeCategories}
              onCategoriesChange={setCategories}
            />
          </div>
        )}
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'list' ? (
          <div className="h-full overflow-y-auto px-4 lg:px-6 py-4">
            {/* Quick add */}
            <div className="mb-4">
              <MemoryQuickAdd onAdd={addMemory} />
            </div>

            {/* Error state */}
            {error && (
              <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-sm">
                {error}
              </div>
            )}

            {/* Stats */}
            {!loading && filteredMemories.length > 0 && (
              <p className="text-sm text-text-quaternary mb-4">
                {searchQuery
                  ? `${filteredMemories.length} matching memories`
                  : `${memories.length} memories`}
              </p>
            )}

            {/* Memory list */}
            {loading && memories.length === 0 ? (
              <MemoryListSkeleton />
            ) : (
              <MemoryList
                memories={filteredMemories}
                loading={loading}
                hasMore={hasMore && !searchQuery}
                onLoadMore={loadMore}
                onEdit={editMemory}
                onDelete={removeMemory}
                onToggleVisibility={toggleVisibility}
                onAccept={acceptMemory}
                onReject={rejectMemory}
              />
            )}
          </div>
        ) : (
          <KnowledgeGraph onNodeSelect={handleNodeSelect} />
        )}
      </div>
    </div>
  );
}
