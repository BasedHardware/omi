'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from '@tschk/moonshine-next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { CalendarDays, CheckSquare, Search as SearchIcon, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConversations } from '@/hooks/useConversations';
import { useConversation } from '@/hooks/useConversation';
import { useRecaps } from '@/hooks/useRecaps';
import { useSearchConversations } from '@/hooks/useSearchConversations';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { useChat } from '@/components/chat/ChatContext';
import { useAuth } from '@/components/auth/AuthProvider';
import { ConversationDetailPanel } from '@/components/conversations/ConversationDetailPanel';
import { DateFilter } from '@/components/conversations/DateFilter';
import { MergeActionBar } from '@/components/conversations/MergeActionBar';
import { MergeConfirmationDialog } from '@/components/conversations/MergeConfirmationDialog';
import { DeleteConversationsDialog } from '@/components/conversations/DeleteConversationsDialog';
import {
  FolderTabs,
  FolderTabsSkeleton,
  FOLDER_ALL,
  FOLDER_STARRED,
} from '@/components/conversations/FolderTabs';
import {
  FolderDialog,
  DeleteFolderDialog,
} from '@/components/conversations/FolderDialog';
import { MoveFolderDialog } from '@/components/conversations/MoveFolderDialog';
import { RecapDetailPanel } from '@/components/recaps/RecapDetailPanel';
import { ConversationGallery, ConversationGallerySkeleton } from './ConversationGallery';
import { ResizeHandle } from '@/components/ui/ResizeHandle';
import { PageToolbar } from '@/components/layout/PageToolbar';
import { useToast } from '@/components/ui/Toast';
import { TextSwap } from '@/components/ui/TextSwap';
import {
  mergeConversations,
  getFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  bulkMoveConversationsToFolder,
  toggleStarred,
  deleteConversation,
} from '@/lib/api';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';
import type { Folder, CreateFolderRequest, UpdateFolderRequest } from '@/types/folder';
import { buildTimelineDayGroups, countTimelineItems } from '@/lib/conversationTimeline';
import {
  MIN_CONVERSATION_GALLERY_WIDTH,
  resizeConversationDetailPanel,
} from '@/lib/conversationPanelSizing';

// Detail pane width constraints
const DEFAULT_PANEL_WIDTH = 480;

type Selection =
  { kind: 'conversation'; id: string } | { kind: 'recap'; id: string } | null;

export function ConversationSplitView() {
  const { user } = useAuth();
  const { setContext } = useChat();
  const { showToast } = useToast();
  const searchParams = useSearchParams();
  const urlConversationId = searchParams.get('id');
  const urlRecapId = searchParams.get('recap');

  const [selection, setSelectionState] = useState<Selection>(
    urlRecapId
      ? { kind: 'recap', id: urlRecapId }
      : urlConversationId
        ? { kind: 'conversation', id: urlConversationId }
        : null,
  );
  const selectionRef = useRef(selection);
  const setSelection = useCallback((nextSelection: Selection) => {
    selectionRef.current = nextSelection;
    setSelectionState(nextSelection);
  }, []);
  const [selectedRecap, setSelectedRecap] = useState<DailySummary | null>(null);

  const selectedConversationId = selection?.kind === 'conversation' ? selection.id : null;

  // Track if we should prevent auto-select (e.g., when user explicitly navigates to list view)
  const preventAutoSelect = useRef(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState('');
  const {
    results: searchResults,
    loading: searchLoading,
    search: performSearch,
    clear: clearSearch,
  } = useSearchConversations();

  // Date filter state
  const [filterDate, setFilterDate] = useState<Date | null>(null);

  // Resizable detail pane width
  const [panelWidth, setPanelWidth] = useLocalStorage(
    'omi-timeline-detail-width',
    DEFAULT_PANEL_WIDTH,
  );
  const splitViewRef = useRef<HTMLDivElement>(null);
  const [detailResizing, setDetailResizing] = useState(false);

  // Selection mode state (for merge feature)
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mergingIds, setMergingIds] = useState<Set<string>>(new Set());
  const [showMergeConfirm, setShowMergeConfirm] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

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
    if (
      selectedFolderId &&
      selectedFolderId !== FOLDER_ALL &&
      selectedFolderId !== FOLDER_STARRED
    ) {
      params.folderId = selectedFolderId;
    }

    return params;
  }, [filterDate, selectedFolderId]);

  const {
    conversations,
    loading: listLoading,
    error: listError,
    hasMore,
    loadMore,
    refresh,
  } = useConversations(conversationFilterParams);

  const {
    recaps,
    loading: recapsLoading,
    hasMore: recapsHasMore,
    loadMore: loadMoreRecaps,
    getRecapDetail,
  } = useRecaps();

  const {
    conversation: selectedConversation,
    loading: detailLoading,
    update: updateSelectedConversation,
  } = useConversation(selectedConversationId);

  // Update chat context when the selected tile changes. Recaps and
  // conversations both feed "ask about this", so both write the same context.
  useEffect(() => {
    if (selection?.kind === 'conversation' && selectedConversation) {
      setContext({
        type: 'conversation',
        id: selectedConversation.id,
        title: selectedConversation.structured.title,
        summary: selectedConversation.structured.overview,
      });
    } else if (selection?.kind === 'recap' && selectedRecap) {
      setContext({
        type: 'recap',
        id: selectedRecap.id,
        title: selectedRecap.headline || `Daily Recap - ${selectedRecap.date}`,
        summary: selectedRecap.overview,
      });
    } else {
      setContext(null);
    }
  }, [selection, selectedConversation, selectedRecap, setContext]);

  // Clear chat context when the timeline unmounts
  useEffect(() => {
    return () => setContext(null);
  }, [setContext]);

  // Track the previous URL conversation ID to detect when it changes
  const prevUrlConversationIdRef = useRef(urlConversationId);
  const prevUrlRecapIdRef = useRef(urlRecapId);

  // Update selection when URL changes (e.g., navigating from a notification or bottom nav)
  useEffect(() => {
    const prevUrlId = prevUrlConversationIdRef.current;
    prevUrlConversationIdRef.current = urlConversationId;

    // URL has a conversation ID - select it
    if (urlConversationId) {
      setSelection({ kind: 'conversation', id: urlConversationId });
      preventAutoSelect.current = false; // Allow auto-select on future loads
    }
    // URL changed from having an ID to not having one (user clicked Timeline in nav)
    else if (prevUrlId !== null && urlConversationId === null) {
      setSelection(null);
      preventAutoSelect.current = true; // Prevent auto-select to stay on gallery view
    }
  }, [urlConversationId]);

  // A recap deep link resolves to the full recap once the list has loaded.
  useEffect(() => {
    const prevUrlRecapId = prevUrlRecapIdRef.current;
    prevUrlRecapIdRef.current = urlRecapId;

    if (!urlRecapId) {
      if (prevUrlRecapId !== null) {
        setSelectedRecap(null);
        if (!urlConversationId) {
          setSelection(null);
          preventAutoSelect.current = true;
        }
      }
      return;
    }

    setSelection({ kind: 'recap', id: urlRecapId });
    preventAutoSelect.current = false;
    const known = recaps.find((r) => r.id === urlRecapId);
    setSelectedRecap(known ?? null);
    void getRecapDetail(urlRecapId).then((fullRecap) => {
      const activeSelection = selectionRef.current;
      if (
        fullRecap &&
        activeSelection?.kind === 'recap' &&
        activeSelection.id === fullRecap.id
      ) {
        setSelectedRecap(fullRecap);
      }
    });
  }, [urlConversationId, urlRecapId, recaps, getRecapDetail]);

  // Determine if we're showing search results or regular list
  const isSearching = submittedSearchQuery.length > 0;

  // Filter conversations for the starred folder (client-side, like folders' All)
  const visibleConversations = useMemo(() => {
    const source = isSearching ? searchResults : conversations;
    if (selectedFolderId === FOLDER_STARRED) {
      return source.filter((c) => c.starred);
    }
    return source;
  }, [isSearching, searchResults, conversations, selectedFolderId]);

  // Recaps only belong in the unfiltered gallery: a search, a date filter or a
  // folder is a question about conversations, and a day summary cannot answer it.
  const visibleRecaps = useMemo(() => {
    if (isSearching || filterDate || selectedFolderId !== FOLDER_ALL) return [];
    return recaps;
  }, [isSearching, filterDate, selectedFolderId, recaps]);

  const dayGroups = useMemo(
    () =>
      buildTimelineDayGroups({
        conversations: visibleConversations,
        recaps: visibleRecaps,
      }),
    [visibleConversations, visibleRecaps],
  );

  const isLoading = isSearching ? searchLoading : listLoading || folderSwitching;
  const isEmpty = !isLoading && countTimelineItems(dayGroups) === 0;

  // Auto-select the newest tile on load (only if no URL param and not explicitly showing the gallery)
  useEffect(() => {
    if (selection || urlConversationId || urlRecapId) return;
    const waitingForRecaps =
      !isSearching && !filterDate && selectedFolderId === FOLDER_ALL && recapsLoading;
    if (listLoading || waitingForRecaps || preventAutoSelect.current) return;

    const firstItem = dayGroups[0]?.items[0];
    if (!firstItem) return;

    if (firstItem.kind === 'recap') {
      setSelection({ kind: 'recap', id: firstItem.id });
      setSelectedRecap(firstItem.recap);
    } else {
      setSelection({ kind: 'conversation', id: firstItem.id });
    }
  }, [
    dayGroups,
    filterDate,
    isSearching,
    listLoading,
    recapsLoading,
    selectedFolderId,
    selection,
    urlConversationId,
    urlRecapId,
  ]);

  // Clear folder switching state when loading completes
  useEffect(() => {
    if (!listLoading && folderSwitching) {
      setFolderSwitching(false);
    }
  }, [listLoading, folderSwitching]);

  const handleConversationClick = useCallback((conversation: Conversation) => {
    setSelection({ kind: 'conversation', id: conversation.id });
    setSelectedRecap(null);
    preventAutoSelect.current = false; // Re-enable auto-select for future visits
  }, []);

  const handleRecapClick = useCallback(
    async (recap: DailySummary) => {
      setSelection({ kind: 'recap', id: recap.id });
      setSelectedRecap(recap);
      preventAutoSelect.current = false;

      // The list endpoint returns a trimmed recap; the detail pane needs the rest.
      const fullRecap = await getRecapDetail(recap.id);
      if (fullRecap) {
        setSelectedRecap((current) =>
          current?.id === fullRecap.id ? fullRecap : current,
        );
      }
    },
    [getRecapDetail],
  );

  // Conversations page first, then recaps, so one scroller drives both sources.
  const handleLoadMore = useCallback(() => {
    if (isSearching) return;
    if (hasMore) void loadMore();
    if (recapsHasMore) void loadMoreRecaps();
  }, [isSearching, hasMore, loadMore, recapsHasMore, loadMoreRecaps]);

  // Handle star toggle
  const handleStarToggle = useCallback(
    async (id: string, starred: boolean) => {
      try {
        await toggleStarred(id, starred);
        // Refresh the list to update starred status
        await refresh();
      } catch (error) {
        console.error('Failed to toggle starred:', error);
      }
    },
    [refresh],
  );

  // Handle folder selection with loading state
  const handleFolderSelect = useCallback(
    (folderId: string) => {
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
    },
    [selectedFolderId],
  );

  // Handle search
  const handleSearchQueryChange = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (!query.trim() && submittedSearchQuery) {
        setSubmittedSearchQuery('');
        clearSearch();
      }
    },
    [submittedSearchQuery, clearSearch],
  );

  const handleSearch = useCallback(
    (query: string) => {
      const submittedQuery = query.trim();
      setSubmittedSearchQuery(submittedQuery);
      if (submittedQuery) {
        performSearch(submittedQuery);
      } else {
        clearSearch();
      }
    },
    [performSearch, clearSearch],
  );

  // Handle date filter change
  const handleDateFilterChange = useCallback(
    (date: Date | null) => {
      setFilterDate(date);
      setSelection(null); // Reset selection to auto-select first from new results
      // Clear search when changing date filter
      if (searchQuery || submittedSearchQuery) {
        setSearchQuery('');
        setSubmittedSearchQuery('');
        clearSearch();
      }
    },
    [searchQuery, submittedSearchQuery, clearSearch],
  );

  // Handle resize. The detail pane sits on the right, so dragging the handle
  // right shrinks it — the delta is inverted relative to a left-hand list.
  const handleResize = useCallback(
    (delta: number) => {
      setPanelWidth((prev) => {
        return resizeConversationDetailPanel(
          prev,
          delta,
          splitViewRef.current?.clientWidth ?? window.innerWidth,
        );
      });
    },
    [setPanelWidth],
  );

  const handleResetWidth = useCallback(() => {
    setPanelWidth(DEFAULT_PANEL_WIDTH);
  }, [setPanelWidth]);

  // Selection mode handlers
  const enterSelectionMode = useCallback(() => {
    setIsSelectionMode(true);
    setSelectedIds(new Set());
    setSelection(null); // Deselect any viewed tile
  }, []);

  // Enter selection mode and select the specified card (for double-click)
  const enterSelectionModeWithId = useCallback((id: string) => {
    setIsSelectionMode(true);
    setSelectedIds(new Set([id]));
    setSelection(null); // Deselect any viewed tile
  }, []);

  const exitSelectionMode = useCallback(() => {
    setIsSelectionMode(false);
    setSelectedIds(new Set());
    setShowMergeConfirm(false);
  }, []);

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
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
    return allConvs.filter((c) => selectedIds.has(c.id));
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
      showToast('Failed to merge conversations. Please try again.', 'error');
    } finally {
      setMergeLoading(false);
      setMergingIds(new Set());
    }
  }, [selectedIds, refresh, showToast]);

  // Handle delete button click - open confirmation dialog
  const handleDeleteClick = useCallback(() => {
    if (selectedIds.size >= 1) {
      setShowDeleteConfirm(true);
    }
  }, [selectedIds.size]);

  // Handle delete confirmation
  const handleDeleteConfirm = useCallback(async () => {
    if (selectedIds.size < 1) return;

    setDeleteLoading(true);
    try {
      // Delete each selected conversation
      const deletePromises = Array.from(selectedIds).map((id) => deleteConversation(id));
      await Promise.all(deletePromises);

      // Exit selection mode and close dialog
      setShowDeleteConfirm(false);
      setIsSelectionMode(false);
      setSelectedIds(new Set());

      // Clear selected conversation if it was deleted
      if (selectedConversationId && selectedIds.has(selectedConversationId)) {
        setSelection(null);
      }

      // Refresh the list
      await refresh();
    } catch (error) {
      console.error('Failed to delete conversations:', error);
      showToast('Failed to delete conversations. Please try again.', 'error');
    } finally {
      setDeleteLoading(false);
    }
  }, [selectedIds, selectedConversationId, refresh, showToast]);

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

  const handleFolderSubmit = useCallback(
    async (data: CreateFolderRequest | UpdateFolderRequest) => {
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
    },
    [editingFolder, refreshFolders],
  );

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

  const handleMoveToFolder = useCallback(
    async (folderId: string) => {
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
    },
    [selectedIds, refreshFolders, refresh],
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageToolbar
        search={{
          value: searchQuery,
          onChange: handleSearchQueryChange,
          onSubmit: handleSearch,
          placeholder: 'Search conversations...',
        }}
        controls={
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
        }
        actions={
          <>
            <DateFilter selectedDate={filterDate} onDateChange={handleDateFilterChange} />

            {/* Select/Cancel button for merge mode */}
            <button
              onClick={isSelectionMode ? exitSelectionMode : enterSelectionMode}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-control flex-shrink-0 whitespace-nowrap',
                'text-sm font-medium transition-colors',
                isSelectionMode
                  ? 'bg-white text-bg-primary hover:bg-white/90'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
              )}
            >
              <span className="t-icon-swap" data-state={isSelectionMode ? 'b' : 'a'}>
                <span className="t-icon" data-icon="a">
                  <CheckSquare className="w-4 h-4" />
                </span>
                <span className="t-icon" data-icon="b">
                  <X className="w-4 h-4" />
                </span>
              </span>
              <TextSwap text={isSelectionMode ? 'Cancel' : 'Select'} />
            </button>
          </>
        }
        below={
          (isSearching ||
            filterDate ||
            selectedFolderId === FOLDER_STARRED ||
            isSelectionMode) && (
            <>
              {/* Active filter indicators */}
              {(isSearching || filterDate || selectedFolderId === FOLDER_STARRED) && (
                <div className="flex items-center gap-2 text-xs text-text-tertiary">
                  {isSearching && (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-chip bg-bg-tertiary">
                      <SearchIcon className="w-3 h-3" />
                      {searchResults.length} results
                    </span>
                  )}
                  {filterDate && (
                    <span className="px-2 py-0.5 rounded-chip bg-bg-tertiary text-text-secondary">
                      Filtered by date
                    </span>
                  )}
                  {selectedFolderId === FOLDER_STARRED && (
                    <span className="px-2 py-0.5 rounded-chip bg-bg-tertiary text-text-secondary">
                      Showing starred only
                    </span>
                  )}
                </div>
              )}

              {/* Inline Merge Action Bar - shows when in selection mode */}
              {isSelectionMode && (
                <div className="mt-2">
                  <MergeActionBar
                    selectedCount={selectedIds.size}
                    onCancel={exitSelectionMode}
                    onMerge={handleMergeClick}
                    onMoveToFolder={handleMoveToFolderClick}
                    onDelete={handleDeleteClick}
                    isLoading={mergeLoading || deleteLoading}
                    inline
                  />
                </div>
              )}
            </>
          )
        }
      />

      {/* Gallery + detail pane */}
      <div ref={splitViewRef} className="flex flex-1 overflow-hidden w-full">
        {/* Gallery */}
        <div
          className={cn(
            'flex-1 min-w-0 flex flex-col h-full overflow-hidden bg-bg-primary',
            // On mobile, hide the gallery when a tile is open
            selection ? 'hidden lg:flex' : 'flex',
          )}
        >
          {/* Loading state */}
          {isLoading && dayGroups.length === 0 && (
            <div className="flex-1 overflow-y-auto pt-4">
              <ConversationGallerySkeleton />
            </div>
          )}

          {/* Error state */}
          {listError && !isSearching && (
            <div className="m-5 p-4 rounded-section bg-error/10 border border-error/20 text-error text-sm">
              {listError}
            </div>
          )}

          {/* Empty state */}
          {isEmpty && !listError && (
            <div className="flex-1 flex flex-col items-center justify-center py-12 text-center">
              <div className="w-14 h-14 rounded-section bg-bg-tertiary flex items-center justify-center mb-3">
                {isSearching ? (
                  <SearchIcon className="w-6 h-6 text-text-quaternary" />
                ) : (
                  <CalendarDays className="w-6 h-6 text-text-quaternary" />
                )}
              </div>
              <p className="text-text-tertiary text-sm">
                {isSearching
                  ? 'No conversations found'
                  : filterDate
                    ? 'Nothing on this date'
                    : selectedFolderId === FOLDER_STARRED
                      ? 'No starred conversations'
                      : selectedFolderId !== FOLDER_ALL
                        ? 'No conversations in this folder'
                        : 'Your timeline is empty'}
              </p>
            </div>
          )}

          {dayGroups.length > 0 && (
            <div className="flex-1 overflow-hidden pt-4">
              <ConversationGallery
                groups={dayGroups}
                selectedId={selection?.id ?? null}
                onConversationClick={handleConversationClick}
                onRecapClick={handleRecapClick}
                onStarToggle={handleStarToggle}
                isSelectionMode={isSelectionMode}
                selectedIds={selectedIds}
                onSelect={toggleSelection}
                mergingIds={mergingIds}
                onEnterSelectionMode={enterSelectionModeWithId}
                hasMore={!isSearching && (hasMore || recapsHasMore)}
                onLoadMore={handleLoadMore}
                loading={listLoading || recapsLoading}
              />
            </div>
          )}
        </div>

        {/* Resize Handle */}
        {selection && (
          <ResizeHandle
            onResize={handleResize}
            onResizeStart={() => setDetailResizing(true)}
            onResizeEnd={() => setDetailResizing(false)}
            onDoubleClick={handleResetWidth}
            className="hidden lg:flex"
          />
        )}

        {/* Detail pane */}
        {selection && (
          <div
            style={{
              width: `min(${panelWidth}px, calc(100% - ${MIN_CONVERSATION_GALLERY_WIDTH}px))`,
            }}
            data-dragging={detailResizing ? 'true' : undefined}
            className="t-resize w-full lg:w-auto flex-shrink-0 flex flex-col h-full overflow-hidden bg-bg-pane border-l border-stroke"
          >
            <AnimatePresence mode="wait">
              <motion.div
                key={`${selection.kind}-${selection.id}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex-1 overflow-hidden"
              >
                {selection.kind === 'conversation' ? (
                  <ConversationDetailPanel
                    conversationId={selection.id}
                    conversation={selectedConversation}
                    loading={detailLoading}
                    userName={user?.displayName || undefined}
                    onBack={() => {
                      setSelection(null);
                      preventAutoSelect.current = true; // Stay on the gallery when using back
                    }}
                    onConversationUpdate={updateSelectedConversation}
                    onDelete={() => {
                      setSelection(null);
                      refresh();
                    }}
                  />
                ) : (
                  <RecapDetailPanel
                    recapId={selection.id}
                    recap={selectedRecap}
                    onBack={() => {
                      setSelection(null);
                      preventAutoSelect.current = true;
                    }}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Merge Confirmation Dialog */}
      <MergeConfirmationDialog
        isOpen={showMergeConfirm}
        conversations={selectedConversations}
        onConfirm={handleMergeConfirm}
        onCancel={() => setShowMergeConfirm(false)}
        isLoading={mergeLoading}
      />

      {/* Delete Conversations Confirmation Dialog */}
      <DeleteConversationsDialog
        isOpen={showDeleteConfirm}
        count={selectedIds.size}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteLoading}
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
