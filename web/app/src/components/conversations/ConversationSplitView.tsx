'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, Search as SearchIcon, CheckSquare, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConversations } from '@/hooks/useConversations';
import { useConversation } from '@/hooks/useConversation';
import { useSearchConversations } from '@/hooks/useSearchConversations';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { useChat } from '@/components/chat/ChatContext';
import { useAuth } from '@/components/auth/AuthProvider';
import { DateGroup, DateGroupSkeleton } from './DateGroup';
import { VirtualizedConversationList } from './VirtualizedConversationList';
import { ConversationDetailPanel } from './ConversationDetailPanel';
import { SearchBar } from './SearchBar';
import { DateFilter } from './DateFilter';
import { MergeActionBar } from './MergeActionBar';
import { MergeConfirmationDialog } from './MergeConfirmationDialog';
import { FolderTabs, FolderTabsSkeleton, FOLDER_ALL, FOLDER_STARRED } from './FolderTabs';
import { FolderDialog, DeleteFolderDialog } from './FolderDialog';
import { MoveFolderDialog } from './MoveFolderDialog';
import { ResizeHandle } from '@/components/ui/ResizeHandle';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  mergeConversations,
  getFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  bulkMoveConversationsToFolder,
  toggleStarred,
} from '@/lib/api';
import type { Conversation } from '@/types/conversation';
import type { Folder, CreateFolderRequest, UpdateFolderRequest } from '@/types/folder';
import { formatRelativeDate } from '@/lib/utils';

// Panel width constraints
const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 600;
const DEFAULT_PANEL_WIDTH = 420;

export function ConversationSplitView() {
  const { user } = useAuth();
  const { setContext } = useChat();
  const searchParams = useSearchParams();
  const urlConversationId = searchParams.get('id');
  const [selectedId, setSelectedId] = useState<string | null>(urlConversationId);

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

  // Selection mode state (for merge feature)
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mergingIds, setMergingIds] = useState<Set<string>>(new Set());
  const [showMergeConfirm, setShowMergeConfirm] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);

  // Folder state
  const [folders, setFolders] = useState<Folder[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(true);
  const [selectedFolderId, setSelectedFolderId] = useState<string>(FOLDER_ALL);
  const [folderSwitching, setFolderSwitching] = useState(false);
  const [showFolderDialog, setShowFolderDialog] = useState(false);
  const [editingFolder, setEditingFolder] = useState<Folder | null>(null);
  const [deletingFolder, setDeletingFolder] = useState<Folder | null>(null);
  const [showMoveDialog, setShowMoveDialog] = useState(false);
  const [folderActionLoading, setFolderActionLoading] = useState(false);
  const [movingToFolderId, setMovingToFolderId] = useState<string | null>(null);

  // Calculate filter params for conversations (date and folder)
  const conversationFilterParams = useMemo(() => {
    const params: {
      startDate?: Date;
      endDate?: Date;
      folderId?: string;
    } = {};

    if (filterDate) {
      const startDate = new Date(filterDate);
      startDate.setHours(0, 0, 0, 0);
      const endDate = new Date(filterDate);
      endDate.setHours(23, 59, 59, 999);
      params.startDate = startDate;
      params.endDate = endDate;
    }

    // Add folder filter (only for user folders, not 'all' or 'starred')
    if (selectedFolderId && selectedFolderId !== FOLDER_ALL && selectedFolderId !== FOLDER_STARRED) {
      params.folderId = selectedFolderId;
    }

    return params;
  }, [filterDate, selectedFolderId]);

  const {
    groupedConversations,
    conversations,
    loading: listLoading,
    error: listError,
    hasMore,
    loadMore,
    refresh,
  } = useConversations(conversationFilterParams);

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

  // Update selected ID when URL changes (e.g., navigating from recaps)
  useEffect(() => {
    if (urlConversationId) {
      setSelectedId(urlConversationId);
    }
  }, [urlConversationId]);

  // Auto-select first conversation on load (only if no URL param)
  useEffect(() => {
    if (!selectedId && !urlConversationId && !listLoading) {
      const firstGroup = Object.values(groupedConversations)[0];
      if (firstGroup && firstGroup.length > 0) {
        setSelectedId(firstGroup[0].id);
      }
    }
  }, [groupedConversations, listLoading, selectedId, urlConversationId]);

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

  // Filter conversations for starred folder
  const displayedGroupedConversations = useMemo(() => {
    if (selectedFolderId === FOLDER_STARRED) {
      // Filter for starred conversations only
      const starredGroups: Record<string, Conversation[]> = {};
      for (const [date, convs] of Object.entries(groupedConversations)) {
        const starredConvs = convs.filter(c => c.starred);
        if (starredConvs.length > 0) {
          starredGroups[date] = starredConvs;
        }
      }
      return starredGroups;
    }
    return groupedConversations;
  }, [selectedFolderId, groupedConversations]);

  // Get the conversations to display (search results or regular list, with folder filtering)
  const displayedConversations = isSearching ? searchGroupedConversations : displayedGroupedConversations;

  // Get ordered date keys
  const dateKeys = Object.keys(displayedConversations);
  const orderedKeys = dateKeys.sort((a, b) => {
    if (a === 'Today') return -1;
    if (b === 'Today') return 1;
    if (a === 'Yesterday') return -1;
    if (b === 'Yesterday') return 1;
    return new Date(b).getTime() - new Date(a).getTime();
  });

  const isLoading = isSearching ? searchLoading : (listLoading || folderSwitching);
  const isEmpty = !isLoading && orderedKeys.length === 0;

  // Clear folder switching state when loading completes
  useEffect(() => {
    if (!listLoading && folderSwitching) {
      setFolderSwitching(false);
    }
  }, [listLoading, folderSwitching]);

  const handleConversationClick = useCallback((conversation: Conversation) => {
    setSelectedId(conversation.id);
  }, []);

  // Handle star toggle
  const handleStarToggle = useCallback(async (id: string, starred: boolean) => {
    try {
      await toggleStarred(id, starred);
      // Refresh the list to update starred status
      await refresh();
    } catch (error) {
      console.error('Failed to toggle starred:', error);
    }
  }, [refresh]);

  // Handle folder selection with loading state
  const handleFolderSelect = useCallback((folderId: string) => {
    if (folderId !== selectedFolderId) {
      // Starred filter is client-side only, no loading needed
      // Also, switching between All and Starred doesn't need API call
      const isClientSideSwitch =
        (folderId === FOLDER_STARRED || selectedFolderId === FOLDER_STARRED) &&
        (folderId === FOLDER_ALL || folderId === FOLDER_STARRED) &&
        (selectedFolderId === FOLDER_ALL || selectedFolderId === FOLDER_STARRED);

      if (!isClientSideSwitch) {
        setFolderSwitching(true);
      }
      setSelectedFolderId(folderId);
    }
  }, [selectedFolderId]);

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
    setSelectedId(null); // Reset selection to auto-select first from new results
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

  // Selection mode handlers
  const enterSelectionMode = useCallback(() => {
    setIsSelectionMode(true);
    setSelectedIds(new Set());
    setSelectedId(null); // Deselect any viewed conversation
  }, []);

  const exitSelectionMode = useCallback(() => {
    setIsSelectionMode(false);
    setSelectedIds(new Set());
    setShowMergeConfirm(false);
  }, []);

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Get selected conversations for merge dialog
  const selectedConversations = useMemo(() => {
    const allConvs = isSearching ? searchResults : conversations;
    return allConvs.filter(c => selectedIds.has(c.id));
  }, [isSearching, searchResults, conversations, selectedIds]);

  const handleMergeClick = useCallback(() => {
    if (selectedIds.size >= 2) {
      setShowMergeConfirm(true);
    }
  }, [selectedIds.size]);

  const handleMergeConfirm = useCallback(async () => {
    if (selectedIds.size < 2) return;

    setMergeLoading(true);
    try {
      // Mark selected conversations as merging
      setMergingIds(new Set(selectedIds));

      // Call merge API
      await mergeConversations(Array.from(selectedIds), true);

      // Exit selection mode and close dialog
      setShowMergeConfirm(false);
      setIsSelectionMode(false);
      setSelectedIds(new Set());

      // Refresh the list to show the new merged conversation
      await refresh();
    } catch (error) {
      console.error('Failed to merge conversations:', error);
      // TODO: Show error toast
    } finally {
      setMergeLoading(false);
      setMergingIds(new Set());
    }
  }, [selectedIds, refresh]);

  // ============================================================================
  // Folder handlers
  // ============================================================================

  // Fetch folders on mount
  useEffect(() => {
    const fetchFolders = async () => {
      setFoldersLoading(true);
      try {
        const data = await getFolders();
        setFolders(data);
      } catch (error) {
        console.error('Failed to fetch folders:', error);
      } finally {
        setFoldersLoading(false);
      }
    };
    fetchFolders();
  }, []);

  // Refresh folders after any folder action
  const refreshFolders = useCallback(async () => {
    try {
      const data = await getFolders();
      setFolders(data);
    } catch (error) {
      console.error('Failed to refresh folders:', error);
    }
  }, []);

  const handleCreateFolder = useCallback(() => {
    setEditingFolder(null);
    setShowFolderDialog(true);
  }, []);

  const handleEditFolder = useCallback((folder: Folder) => {
    setEditingFolder(folder);
    setShowFolderDialog(true);
  }, []);

  const handleFolderSubmit = useCallback(async (data: CreateFolderRequest | UpdateFolderRequest) => {
    setFolderActionLoading(true);
    try {
      if (editingFolder) {
        await updateFolder(editingFolder.id, data);
      } else {
        await createFolder(data as CreateFolderRequest);
      }
      setShowFolderDialog(false);
      setEditingFolder(null);
      await refreshFolders();
    } catch (error) {
      console.error('Failed to save folder:', error);
    } finally {
      setFolderActionLoading(false);
    }
  }, [editingFolder, refreshFolders]);

  const handleDeleteFolderConfirm = useCallback(async () => {
    if (!deletingFolder) return;

    setFolderActionLoading(true);
    try {
      await deleteFolder(deletingFolder.id);
      // If we were viewing this folder, go back to All
      if (selectedFolderId === deletingFolder.id) {
        setSelectedFolderId(FOLDER_ALL);
      }
      setDeletingFolder(null);
      await refreshFolders();
      await refresh(); // Refresh conversations as they may have moved
    } catch (error) {
      console.error('Failed to delete folder:', error);
    } finally {
      setFolderActionLoading(false);
    }
  }, [deletingFolder, selectedFolderId, refreshFolders, refresh]);

  const handleMoveToFolderClick = useCallback(() => {
    if (selectedIds.size >= 1) {
      setShowMoveDialog(true);
    }
  }, [selectedIds.size]);

  const handleMoveToFolder = useCallback(async (folderId: string) => {
    if (selectedIds.size < 1) return;

    setMovingToFolderId(folderId);
    try {
      await bulkMoveConversationsToFolder(folderId, Array.from(selectedIds));

      // Exit selection mode and close dialog
      setShowMoveDialog(false);
      setIsSelectionMode(false);
      setSelectedIds(new Set());

      // Refresh both folders and conversations
      await Promise.all([refreshFolders(), refresh()]);
    } catch (error) {
      console.error('Failed to move conversations:', error);
    } finally {
      setMovingToFolderId(null);
    }
  }, [selectedIds, refreshFolders, refresh]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <PageHeader title="Conversations" icon={MessageSquare} />

      {/* Toolbar: Folder Tabs + Select */}
      <div className="flex-shrink-0 bg-bg-secondary border-b border-bg-tertiary">
        <div className="flex items-center gap-4 px-6 py-3">
          {/* Folder Tabs - takes up available space */}
          <div className="flex-1 min-w-0">
            {foldersLoading ? (
              <FolderTabsSkeleton />
            ) : (
              <FolderTabs
                folders={folders}
                selectedFolderId={selectedFolderId}
                onSelectFolder={handleFolderSelect}
                onCreateFolder={handleCreateFolder}
                onEditFolder={handleEditFolder}
                onDeleteFolder={(folder) => setDeletingFolder(folder)}
                loading={folderActionLoading}
              />
            )}
          </div>

          {/* Select/Cancel button for merge mode */}
          <button
            onClick={isSelectionMode ? exitSelectionMode : enterSelectionMode}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg flex-shrink-0',
              'text-sm font-medium transition-colors',
              isSelectionMode
                ? 'bg-purple-primary/20 text-purple-primary hover:bg-purple-primary/30'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
            )}
          >
            {isSelectionMode ? (
              <>
                <X className="w-4 h-4" />
                <span>Cancel</span>
              </>
            ) : (
              <>
                <CheckSquare className="w-4 h-4" />
                <span>Select</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Split Panels Container */}
      <div className="flex flex-1 overflow-hidden w-full">
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
          {/* Search and Date Filter - stays with list */}
          <div className="flex-shrink-0 px-3 pt-4 pb-3">
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
            {(isSearching || filterDate || selectedFolderId === FOLDER_STARRED) && (
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
                {selectedFolderId === FOLDER_STARRED && (
                  <span className="px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-600">
                    Showing starred only
                  </span>
                )}
              </div>
            )}
          </div>

          {/* List Content */}
          <div className="flex-1 overflow-hidden px-3 pb-4">
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
                    : selectedFolderId === FOLDER_STARRED
                    ? 'No starred conversations'
                    : selectedFolderId !== FOLDER_ALL
                    ? 'No conversations in this folder'
                    : 'No conversations yet'}
                </p>
              </div>
            )}

            {/* Virtualized conversation list */}
            {orderedKeys.length > 0 && (
              <VirtualizedConversationList
                groupedConversations={displayedConversations}
                orderedKeys={orderedKeys}
                onConversationClick={handleConversationClick}
                onStarToggle={handleStarToggle}
                selectedId={selectedId}
                isSelectionMode={isSelectionMode}
                selectedIds={selectedIds}
                onSelect={toggleSelection}
                mergingIds={mergingIds}
                hasMore={!isSearching && hasMore}
                onLoadMore={loadMore}
                loading={listLoading}
              />
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
          {selectedId ? (
            <div className="flex-1 overflow-hidden">
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
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
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
            </div>
          )}
        </div>
      </div>

      {/* Merge Action Bar - shows when in selection mode */}
      <AnimatePresence>
        {isSelectionMode && (
          <MergeActionBar
            selectedCount={selectedIds.size}
            onCancel={exitSelectionMode}
            onMerge={handleMergeClick}
            onMoveToFolder={handleMoveToFolderClick}
            isLoading={mergeLoading}
          />
        )}
      </AnimatePresence>

      {/* Merge Confirmation Dialog */}
      <MergeConfirmationDialog
        isOpen={showMergeConfirm}
        conversations={selectedConversations}
        onConfirm={handleMergeConfirm}
        onCancel={() => setShowMergeConfirm(false)}
        isLoading={mergeLoading}
      />

      {/* Create/Edit Folder Dialog */}
      <FolderDialog
        isOpen={showFolderDialog}
        folder={editingFolder}
        onClose={() => {
          setShowFolderDialog(false);
          setEditingFolder(null);
        }}
        onSubmit={handleFolderSubmit}
        isLoading={folderActionLoading}
      />

      {/* Delete Folder Confirmation Dialog */}
      <DeleteFolderDialog
        isOpen={!!deletingFolder}
        folder={deletingFolder}
        onClose={() => setDeletingFolder(null)}
        onConfirm={handleDeleteFolderConfirm}
        isLoading={folderActionLoading}
      />

      {/* Move to Folder Dialog */}
      <MoveFolderDialog
        isOpen={showMoveDialog}
        folders={folders}
        selectedCount={selectedIds.size}
        onClose={() => setShowMoveDialog(false)}
        onSelectFolder={handleMoveToFolder}
        onCreateFolder={() => {
          setShowMoveDialog(false);
          handleCreateFolder();
        }}
        isLoading={!!movingToFolderId}
        loadingFolderId={movingToFolderId}
      />
    </div>
  );
}
