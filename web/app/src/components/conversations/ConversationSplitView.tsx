'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, Search as SearchIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConversations } from '@/hooks/useConversations';
import { useConversation } from '@/hooks/useConversation';
import { useSearchConversations } from '@/hooks/useSearchConversations';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { useChat } from '@/components/chat/ChatContext';
import { useAuth } from '@/components/auth/AuthProvider';
import { DateGroup, DateGroupSkeleton } from './DateGroup';
import { ConversationDetailPanel } from './ConversationDetailPanel';
import { SearchBar } from './SearchBar';
import { DateFilter } from './DateFilter';
import { ResizeHandle } from '@/components/ui/ResizeHandle';
import type { Conversation } from '@/types/conversation';
import { formatRelativeDate } from '@/lib/utils';

// Panel width constraints
const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 600;
const DEFAULT_PANEL_WIDTH = 420;

export function ConversationSplitView() {
  const { user } = useAuth();
  const { setContext } = useChat();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const {
    results: searchResults,
    loading: searchLoading,
    search: performSearch,
    clear: clearSearch,
  } = useSearchConversations();

  // Date filter state
  const [filterDate, setFilterDate] = useState<Date | null>(null);

  // Resizable panel width
  const [panelWidth, setPanelWidth] = useLocalStorage('omi-panel-width', DEFAULT_PANEL_WIDTH);

  // Calculate date range for filter
  const dateFilterParams = useMemo(() => {
    if (!filterDate) return {};

    const startDate = new Date(filterDate);
    startDate.setHours(0, 0, 0, 0);

    const endDate = new Date(filterDate);
    endDate.setHours(23, 59, 59, 999);

    return { startDate, endDate };
  }, [filterDate]);

  const {
    groupedConversations,
    conversations,
    loading: listLoading,
    error: listError,
    hasMore,
    loadMore,
    refresh,
  } = useConversations(dateFilterParams);

  const {
    conversation: selectedConversation,
    loading: detailLoading,
    update: updateSelectedConversation,
  } = useConversation(selectedId);

  // Update chat context when conversation changes
  useEffect(() => {
    if (selectedConversation) {
      setContext({
        type: 'conversation',
        id: selectedConversation.id,
        title: selectedConversation.structured.title,
        summary: selectedConversation.structured.overview,
      });
    } else {
      setContext(null);
    }
  }, [selectedConversation, setContext]);

  // Auto-select first conversation on load
  useEffect(() => {
    if (!selectedId && !listLoading) {
      const firstGroup = Object.values(groupedConversations)[0];
      if (firstGroup && firstGroup.length > 0) {
        setSelectedId(firstGroup[0].id);
      }
    }
  }, [groupedConversations, listLoading, selectedId]);

  // Determine if we're showing search results or regular list
  const isSearching = searchQuery.trim().length > 0;

  // Group search results by date for display
  const searchGroupedConversations = useMemo(() => {
    if (!isSearching || searchResults.length === 0) return {};

    return searchResults.reduce((groups, conversation) => {
      const date = new Date(conversation.started_at || conversation.created_at);
      const dateKey = formatRelativeDate(date);

      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(conversation);
      return groups;
    }, {} as Record<string, Conversation[]>);
  }, [isSearching, searchResults]);

  // Get the conversations to display (search results or regular list)
  const displayedConversations = isSearching ? searchGroupedConversations : groupedConversations;

  // Get ordered date keys
  const dateKeys = Object.keys(displayedConversations);
  const orderedKeys = dateKeys.sort((a, b) => {
    if (a === 'Today') return -1;
    if (b === 'Today') return 1;
    if (a === 'Yesterday') return -1;
    if (b === 'Yesterday') return 1;
    return new Date(b).getTime() - new Date(a).getTime();
  });

  const isLoading = isSearching ? searchLoading : listLoading;
  const isEmpty = !isLoading && orderedKeys.length === 0;

  const handleConversationClick = (conversation: Conversation) => {
    setSelectedId(conversation.id);
  };

  // Handle search
  const handleSearch = useCallback((query: string) => {
    if (query.trim()) {
      performSearch(query);
    } else {
      clearSearch();
    }
  }, [performSearch, clearSearch]);

  // Handle date filter change
  const handleDateFilterChange = useCallback((date: Date | null) => {
    setFilterDate(date);
    // Clear search when changing date filter
    if (searchQuery) {
      setSearchQuery('');
      clearSearch();
    }
  }, [searchQuery, clearSearch]);

  // Handle resize
  const handleResize = useCallback((delta: number) => {
    setPanelWidth((prev) => {
      const newWidth = prev + delta;
      return Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, newWidth));
    });
  }, [setPanelWidth]);

  const handleResetWidth = useCallback(() => {
    setPanelWidth(DEFAULT_PANEL_WIDTH);
  }, [setPanelWidth]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Panel: Conversation List */}
      <div
        style={{ width: `${panelWidth}px` }}
        className={cn(
          'w-full lg:w-auto flex-shrink-0',
          'flex flex-col h-full overflow-hidden',
          'bg-bg-primary border-r border-bg-tertiary',
          // On mobile, hide list when conversation is selected
          selectedId ? 'hidden lg:flex' : 'flex'
        )}
      >
        {/* List Header - Fixed/Sticky, fully opaque to cover scrolling content */}
        <div className="flex-shrink-0 p-4 bg-bg-primary border-b border-bg-tertiary relative z-10">
          <h2 className="text-lg font-semibold text-text-primary mb-3">Conversations</h2>

          {/* Search and Filter Row */}
          <div className="flex items-center gap-2">
            <SearchBar
              value={searchQuery}
              onChange={setSearchQuery}
              onSearch={handleSearch}
              placeholder="Search conversations..."
              className="flex-1"
            />
            <DateFilter
              selectedDate={filterDate}
              onDateChange={handleDateFilterChange}
            />
          </div>

          {/* Active filter indicators */}
          {(isSearching || filterDate) && (
            <div className="flex items-center gap-2 mt-2 text-xs text-text-tertiary">
              {isSearching && (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-bg-tertiary">
                  <SearchIcon className="w-3 h-3" />
                  {searchResults.length} results
                </span>
              )}
              {filterDate && (
                <span className="px-2 py-0.5 rounded bg-purple-primary/10 text-purple-primary">
                  Filtered by date
                </span>
              )}
            </div>
          )}
        </div>

        {/* List Content - no top padding so date labels connect to header */}
        <div className="flex-1 overflow-y-auto px-3 pb-4">
          {/* Loading state */}
          {isLoading && orderedKeys.length === 0 && (
            <div className="space-y-6">
              <DateGroupSkeleton count={3} />
              <DateGroupSkeleton count={2} />
            </div>
          )}

          {/* Error state */}
          {listError && !isSearching && (
            <div className="p-4 rounded-xl bg-error/10 border border-error/20 text-error text-sm">
              {listError}
            </div>
          )}

          {/* Empty state */}
          {isEmpty && !listError && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
                {isSearching ? (
                  <SearchIcon className="w-6 h-6 text-text-quaternary" />
                ) : (
                  <MessageSquare className="w-6 h-6 text-text-quaternary" />
                )}
              </div>
              <p className="text-text-tertiary text-sm">
                {isSearching
                  ? 'No conversations found'
                  : filterDate
                  ? 'No conversations on this date'
                  : 'No conversations yet'}
              </p>
            </div>
          )}

          {/* Conversation groups */}
          {orderedKeys.length > 0 && (
            <div className="space-y-6">
              {orderedKeys.map((dateKey) => (
                <DateGroup
                  key={dateKey}
                  dateLabel={dateKey}
                  conversations={displayedConversations[dateKey]}
                  onConversationClick={handleConversationClick}
                  selectedId={selectedId}
                  compact={false}
                />
              ))}

              {/* Load more - only for regular list, not search */}
              {!isSearching && hasMore && (
                <button
                  onClick={loadMore}
                  disabled={listLoading}
                  className={cn(
                    'w-full py-2 text-sm text-text-tertiary',
                    'hover:text-text-secondary transition-colors',
                    listLoading && 'opacity-50'
                  )}
                >
                  {listLoading ? 'Loading...' : 'Load more'}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Resize Handle */}
      <ResizeHandle
        onResize={handleResize}
        onDoubleClick={handleResetWidth}
        className="hidden lg:flex"
      />

      {/* Right Panel: Conversation Detail */}
      <div
        className={cn(
          'flex-1 flex flex-col min-w-0 h-full overflow-hidden',
          'bg-bg-primary',
          // On mobile, show detail when conversation is selected
          !selectedId ? 'hidden lg:flex' : 'flex'
        )}
      >
        <AnimatePresence mode="wait">
          {selectedId ? (
            <motion.div
              key={selectedId}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex-1 overflow-hidden"
            >
              <ConversationDetailPanel
                conversationId={selectedId}
                conversation={selectedConversation}
                loading={detailLoading}
                userName={user?.displayName || undefined}
                onBack={() => setSelectedId(null)}
                onConversationUpdate={updateSelectedConversation}
                onDelete={() => {
                  setSelectedId(null);
                  refresh();
                }}
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex-1 flex items-center justify-center"
            >
              <div className="text-center">
                <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mx-auto mb-4">
                  <MessageSquare className="w-8 h-8 text-text-quaternary" />
                </div>
                <h3 className="text-lg font-medium text-text-primary mb-2">
                  Select a conversation
                </h3>
                <p className="text-text-tertiary text-sm">
                  Choose a conversation from the list to view details
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
