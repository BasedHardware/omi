'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import { LayoutGrid, List, CheckSquare, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useActionItems } from '@/hooks/useActionItems';
import { useTaskKeyboardShortcuts } from '@/hooks/useTaskKeyboardShortcuts';
import { TaskGroup, TaskGroupSkeleton } from './TaskGroup';
import { TaskQuickAdd } from './TaskQuickAdd';
import { TaskListView } from './TaskListView';
import { TaskRightPanel } from './TaskRightPanel';
import { BulkActionBar } from './BulkActionBar';
import { PageToolbar } from '@/components/layout/PageToolbar';
import { copyTasksToClipboard, downloadTasks } from '@/lib/taskExport';
import { useChat as useChatContext } from '@/components/chat/ChatContext';
import { readHighlightParam, taskListFocus } from '@/lib/itemList';

type ViewMode = 'hub' | 'list';

// Detect if device is mobile (< 1024px)
const getDefaultViewMode = (): ViewMode => {
  if (typeof window === 'undefined') return 'hub';
  return window.innerWidth < 1024 ? 'list' : 'hub';
};

export function TaskHub() {
  const [viewMode, setViewMode] = useState<ViewMode>(getDefaultViewMode);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [editingId, setEditingId] = useState<string | null>(null);

  const {
    items,
    groupedItems,
    sortedFlatList,
    loading,
    error,
    stats,
    addItem,
    toggleComplete,
    snooze,
    setDueDate,
    updateDescription,
    removeItem,
    bulkComplete,
    bulkDelete,
    bulkSnooze,
    bulkSetDueDate,
  } = useActionItems();

  // Chat context for passing selected task info
  const { setContext } = useChatContext();

  // `/tasks?highlight=<id>` (from an item-list link): focus that task's row in the list view once
  // it is loaded, showing Completed when it is done. The focused row scrolls itself into view.
  const [pendingHighlight, setPendingHighlight] = useState<string | null>(() =>
    readHighlightParam(),
  );
  useEffect(() => {
    if (!pendingHighlight || loading) return;
    const focus = taskListFocus(
      sortedFlatList.pending,
      sortedFlatList.completed,
      pendingHighlight,
    );
    setPendingHighlight(null);
    if (!focus) return;
    setViewMode('list');
    setSearchQuery('');
    if (focus.completed) setShowCompleted(true);
    setFocusedIndex(focus.index);
  }, [pendingHighlight, loading, sortedFlatList]);

  // Set chat context when a single task is selected
  useEffect(() => {
    if (selectedIds.size === 1) {
      const taskId = Array.from(selectedIds)[0];
      const task = items.find((t) => t.id === taskId);
      if (task) {
        setContext({
          type: 'task',
          id: task.id,
          title: task.description,
          summary: task.completed ? 'Completed' : `Due: ${task.due_at || 'No due date'}`,
        });
      } else {
        setContext(null);
      }
    } else {
      setContext(null);
    }
  }, [selectedIds, items, setContext]);

  // Clear chat context when component unmounts
  useEffect(() => {
    return () => setContext(null);
  }, [setContext]);

  // Enter selection mode and select the specified task (for double-click)
  // Defined early because it's used in taskGroupProps
  const enterSelectionModeWithId = useCallback((id: string) => {
    setIsSelectMode(true);
    setSelectedIds(new Set([id]));
  }, []);

  // Common props for all TaskGroup components
  const taskGroupProps = {
    onToggleComplete: toggleComplete,
    onSnooze: snooze,
    onDelete: removeItem,
    onUpdateDescription: updateDescription,
    onSetDueDate: setDueDate,
    // Only pass selection props when in select mode
    ...(isSelectMode && {
      selectedIds,
      onSelect: handleSelect,
    }),
    // Pass onEnterSelectionMode when NOT in select mode (for double-click)
    ...(!isSelectMode && {
      onEnterSelectionMode: enterSelectionModeWithId,
    }),
  };

  // Handle task selection
  function handleSelect(id: string, selected: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (selected) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  // Clear selection and exit select mode
  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
    setIsSelectMode(false);
  }, []);

  // Toggle select mode
  const toggleSelectMode = useCallback(() => {
    if (isSelectMode) {
      // Exiting select mode - clear selection
      setSelectedIds(new Set());
    }
    setIsSelectMode(!isSelectMode);
  }, [isSelectMode]);

  // Bulk actions
  const handleBulkComplete = useCallback(async () => {
    await bulkComplete(Array.from(selectedIds));
    clearSelection();
  }, [selectedIds, bulkComplete, clearSelection]);

  const handleBulkDelete = useCallback(async () => {
    await bulkDelete(Array.from(selectedIds));
    clearSelection();
  }, [selectedIds, bulkDelete, clearSelection]);

  const handleBulkSnooze = useCallback(
    async (days: number) => {
      await bulkSnooze(Array.from(selectedIds), days);
      clearSelection();
    },
    [selectedIds, bulkSnooze, clearSelection],
  );

  // Handle copy to clipboard
  const handleCopy = useCallback(async () => {
    const selectedItems = items.filter((i) => selectedIds.has(i.id));
    await copyTasksToClipboard(selectedItems);
  }, [items, selectedIds]);

  // Handle export
  const handleExport = useCallback(
    (format: 'csv' | 'json' | 'markdown') => {
      const selectedItems = items.filter((i) => selectedIds.has(i.id));
      downloadTasks(selectedItems, format);
    },
    [items, selectedIds],
  );

  // Handle show no due date items
  const handleShowNoDueDateItems = useCallback(() => {
    setSearchQuery('');
    setViewMode('list');
    // Items without due dates will be at the bottom of the list
  }, []);

  // Handle set due today for selected items
  const handleSetDueToday = useCallback(
    async (ids: string[]) => {
      await bulkSetDueDate(ids, new Date());
    },
    [bulkSetDueDate],
  );

  // Handle set due tomorrow for selected items
  const handleSetDueTomorrow = useCallback(
    async (ids: string[]) => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      await bulkSetDueDate(ids, tomorrow);
    },
    [bulkSetDueDate],
  );

  // Handle bulk toggle complete (Enter): complete the selection's pending tasks, or
  // reopen the selection when every selected task is already done. Completing a done
  // task again would only reset its completion time.
  const handleBulkToggleComplete = useCallback(
    async (ids: string[]) => {
      const selected = items.filter((i) => ids.includes(i.id));
      const pendingIds = selected.filter((i) => !i.completed).map((i) => i.id);
      if (pendingIds.length > 0) {
        await bulkComplete(pendingIds);
      } else {
        await Promise.all(selected.map((i) => toggleComplete(i.id, false)));
      }
      clearSelection();
    },
    [items, bulkComplete, toggleComplete, clearSelection],
  );

  // Handle bulk delete via keyboard
  const handleBulkDeleteByIds = useCallback(
    async (ids: string[]) => {
      await bulkDelete(ids);
      clearSelection();
    },
    [bulkDelete, clearSelection],
  );

  // Handle start edit
  const handleStartEdit = useCallback((id: string) => {
    setEditingId(id);
  }, []);

  // Handle date selection from week strip
  const handleDateSelect = useCallback((date: Date) => {
    setSelectedDate((prev) =>
      prev?.toDateString() === date.toDateString() ? null : date,
    );
  }, []);

  // Handle drop on week strip
  const handleDropTask = useCallback(
    async (date: Date, taskId: string) => {
      await setDueDate(taskId, date);
    },
    [setDueDate],
  );

  // Handle add task
  const handleAddTask = useCallback(
    async (description: string, dueAt?: string) => {
      await addItem({ description, due_at: dueAt || null });
    },
    [addItem],
  );

  // Filter tasks based on search query
  const filteredItems = useMemo(() => {
    if (!searchQuery) return items;
    const query = searchQuery.toLowerCase();
    return items.filter((item) => item.description.toLowerCase().includes(query));
  }, [items, searchQuery]);

  // Filter grouped items based on search
  const filteredGroupedItems = useMemo(() => {
    if (!searchQuery) return groupedItems;
    const query = searchQuery.toLowerCase();
    const filterTasks = (tasks: typeof items) =>
      tasks.filter((item) => item.description.toLowerCase().includes(query));
    return {
      overdue: filterTasks(groupedItems.overdue),
      today: filterTasks(groupedItems.today),
      tomorrow: filterTasks(groupedItems.tomorrow),
      thisWeek: filterTasks(groupedItems.thisWeek),
      later: filterTasks(groupedItems.later),
      noDueDate: filterTasks(groupedItems.noDueDate),
      completed: filterTasks(groupedItems.completed),
    };
  }, [groupedItems, searchQuery]);

  // The list view's rows, narrowed by the search. TaskListView renders exactly these and
  // highlights focusedIndex among them (pending first, then completed), so the arrow
  // keys and Space must index the same rows, not the unfiltered list.
  const filteredFlatList = useMemo(() => {
    if (!searchQuery) return sortedFlatList;
    const query = searchQuery.toLowerCase();
    const filterTasks = (tasks: typeof items) =>
      tasks.filter((item) => item.description.toLowerCase().includes(query));
    return {
      pending: filterTasks(sortedFlatList.pending),
      completed: filterTasks(sortedFlatList.completed),
    };
  }, [sortedFlatList, searchQuery]);

  // Shortcuts act only on selected tasks the search still shows. A task selected before
  // the search hid it stays selected, but d, Enter, t and n cannot reach it unseen.
  const visibleSelectedIds = useMemo(() => {
    if (!searchQuery) return selectedIds;
    const visibleIds = new Set(filteredItems.map((item) => item.id));
    return new Set(Array.from(selectedIds).filter((id) => visibleIds.has(id)));
  }, [selectedIds, filteredItems, searchQuery]);

  // Filter tasks based on view mode and selected date
  const filteredView = useMemo(() => {
    if (!selectedDate) return null;
    const dateStr = selectedDate.toDateString();
    const dateFilteredItems = filteredItems.filter((item) => {
      if (!item.due_at) return false;
      return new Date(item.due_at).toDateString() === dateStr;
    });
    return {
      pending: dateFilteredItems.filter((i) => !i.completed),
      completed: dateFilteredItems.filter((i) => i.completed),
      dateLabel: selectedDate.toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'short',
        day: 'numeric',
      }),
    };
  }, [filteredItems, selectedDate]);

  // The pending rows the view actually shows: the search narrows them, and in the hub
  // a picked day narrows them further. Select All and its toggle state both use this
  // set, so neither can reach a row the list hides.
  const selectablePendingItems = useMemo(
    () =>
      viewMode === 'list'
        ? filteredFlatList.pending
        : filteredView
          ? filteredView.pending
          : filteredItems.filter((i) => !i.completed),
    [filteredFlatList, filteredItems, filteredView, viewMode],
  );

  // Select all toggles exactly the pending rows the view shows. Compare membership by
  // id, not by count: with a task selected that the search or the picked day hides, a
  // size comparison counts that hidden task as one of the visible rows and clears the
  // selection instead of selecting the rows on screen.
  const handleSelectAll = useCallback(() => {
    if (selectablePendingItems.length === 0) return;
    if (selectablePendingItems.every((item) => selectedIds.has(item.id))) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(selectablePendingItems.map((item) => item.id)));
    }
  }, [selectablePendingItems, selectedIds]);

  // Keyboard navigation (defined after filteredItems)
  const handleNavigate = useCallback(
    (direction: 'up' | 'down') => {
      const totalItems =
        viewMode === 'list'
          ? filteredFlatList.pending.length +
            (showCompleted ? filteredFlatList.completed.length : 0)
          : filteredItems.filter((i) => !i.completed).length;

      if (totalItems === 0) return;

      setFocusedIndex((prev) => {
        if (direction === 'up') {
          return prev <= 0 ? totalItems - 1 : prev - 1;
        } else {
          return prev >= totalItems - 1 ? 0 : prev + 1;
        }
      });
    },
    [viewMode, filteredFlatList, showCompleted, filteredItems],
  );

  // Toggle select focused item
  const handleToggleSelectFocused = useCallback(() => {
    const allItems =
      viewMode === 'list'
        ? [
            ...filteredFlatList.pending,
            ...(showCompleted ? filteredFlatList.completed : []),
          ]
        : filteredItems.filter((i) => !i.completed);

    if (focusedIndex >= 0 && focusedIndex < allItems.length) {
      const item = allItems[focusedIndex];
      handleSelect(item.id, !selectedIds.has(item.id));
    }
  }, [
    viewMode,
    filteredFlatList,
    showCompleted,
    filteredItems,
    focusedIndex,
    selectedIds,
  ]);

  // Keyboard shortcuts
  useTaskKeyboardShortcuts({
    enabled: !loading && items.length > 0,
    selectedIds: visibleSelectedIds,
    focusedIndex,
    totalItems:
      viewMode === 'list'
        ? filteredFlatList.pending.length
        : filteredItems.filter((i) => !i.completed).length,
    onSetDueToday: handleSetDueToday,
    onSetDueTomorrow: handleSetDueTomorrow,
    onDelete: handleBulkDeleteByIds,
    onToggleComplete: handleBulkToggleComplete,
    onStartEdit: handleStartEdit,
    onSelectAll: handleSelectAll,
    onDeselectAll: clearSelection,
    onNavigate: handleNavigate,
    onToggleSelectFocused: handleToggleSelectFocused,
  });

  // Filter tasks based on view mode and selected date
  const isEmpty = !loading && items.length === 0;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageToolbar
        search={{
          value: searchQuery,
          onChange: setSearchQuery,
          placeholder: 'Search tasks...',
        }}
        controls={
          <>
            {/* View mode toggle */}
            <div className="flex items-center gap-1 rounded-lg bg-bg-tertiary p-1">
              <button
                onClick={() => setViewMode('hub')}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm',
                  'transition-colors',
                  viewMode === 'hub'
                    ? 'bg-white text-black'
                    : 'text-text-tertiary hover:text-text-secondary',
                )}
              >
                <LayoutGrid className="h-4 w-4" />
                Hub
              </button>
              <button
                onClick={() => {
                  setViewMode('list');
                  setSelectedDate(null); // Clear date filter when switching to list
                }}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm',
                  'transition-colors',
                  viewMode === 'list'
                    ? 'bg-white text-black'
                    : 'text-text-tertiary hover:text-text-secondary',
                )}
              >
                <List className="h-4 w-4" />
                List
              </button>
            </div>

            {/* Select mode toggle - moved to left */}
            {filteredItems.filter((i) => !i.completed).length > 0 && (
              <button
                onClick={toggleSelectMode}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm',
                  'transition-colors',
                  isSelectMode
                    ? 'bg-white/10 text-white'
                    : 'text-text-tertiary hover:bg-bg-tertiary hover:text-text-primary',
                )}
              >
                {isSelectMode ? (
                  <>
                    <CheckSquare className="h-4 w-4" />
                    <span>Selecting</span>
                  </>
                ) : (
                  <>
                    <Square className="h-4 w-4" />
                    <span>Select</span>
                  </>
                )}
              </button>
            )}
          </>
        }
      />

      {/* Content - Two column layout for Hub view */}
      <div className="flex-1 overflow-hidden">
        <div className="flex h-full w-full flex-col lg:flex-row">
          {/* Left Column - Tasks (scrollable) */}
          <div className="order-last flex-1 space-y-4 overflow-y-auto p-4 lg:order-first">
            {/* Quick add */}
            <TaskQuickAdd onAdd={handleAddTask} disabled={loading} />

            {/* Inline action bar - only shown in select mode */}
            {isSelectMode && (
              <BulkActionBar
                inline
                selectedCount={selectedIds.size}
                selectedItems={items.filter((i) => selectedIds.has(i.id))}
                onComplete={handleBulkComplete}
                onDelete={handleBulkDelete}
                onSnooze={handleBulkSnooze}
                onClear={clearSelection}
                onCopy={handleCopy}
                onExport={handleExport}
                onSelectAll={handleSelectAll}
                onDone={toggleSelectMode}
                allSelected={
                  selectablePendingItems.length > 0 &&
                  selectablePendingItems.every((i) => selectedIds.has(i.id))
                }
                totalCount={selectablePendingItems.length}
              />
            )}

            {/* Error state */}
            {error && (
              <div className="rounded-xl border border-error/20 bg-error/10 p-4 text-sm text-error">
                {error}
              </div>
            )}

            {/* Loading state */}
            {loading && items.length === 0 && (
              <div className="space-y-4">
                <TaskGroupSkeleton count={3} />
                <TaskGroupSkeleton count={2} />
                <TaskGroupSkeleton count={3} />
              </div>
            )}

            {/* Empty state */}
            {isEmpty && (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-tertiary">
                  <CheckSquare className="h-8 w-8 text-text-quaternary" />
                </div>
                <h3 className="mb-2 text-lg font-medium text-text-primary">
                  No tasks yet
                </h3>
                <p className="max-w-xs text-sm text-text-tertiary">
                  Add a task above or they&apos;ll appear automatically from your
                  conversations
                </p>
              </div>
            )}

            {/* Task content */}
            {!loading && items.length > 0 && (
              <>
                {/* Search filter indicator */}
                {searchQuery && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text-secondary">
                      Showing tasks matching &quot;{searchQuery}&quot;
                    </span>
                    <button
                      onClick={() => setSearchQuery('')}
                      className="text-xs text-white hover:underline"
                    >
                      Clear search
                    </button>
                  </div>
                )}

                {/* Selected date filter indicator - only in Hub view */}
                {viewMode === 'hub' && selectedDate && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text-secondary">
                      Showing tasks for {filteredView?.dateLabel}
                    </span>
                    <button
                      onClick={() => setSelectedDate(null)}
                      className="text-xs text-white hover:underline"
                    >
                      Show all
                    </button>
                  </div>
                )}

                {/* List view - flat list with TaskListView */}
                {viewMode === 'list' ? (
                  <TaskListView
                    pendingTasks={filteredFlatList.pending}
                    completedTasks={filteredFlatList.completed}
                    showCompleted={showCompleted}
                    onToggleShowCompleted={() => setShowCompleted(!showCompleted)}
                    selectedIds={selectedIds}
                    onSelect={handleSelect}
                    isSelectMode={isSelectMode}
                    focusedIndex={focusedIndex}
                    onToggleComplete={toggleComplete}
                    onSnooze={snooze}
                    onDelete={removeItem}
                    onUpdateDescription={updateDescription}
                    onSetDueDate={setDueDate}
                    searchQuery={searchQuery}
                    onEnterSelectionMode={
                      !isSelectMode ? enterSelectionModeWithId : undefined
                    }
                  />
                ) : filteredView ? (
                  /* Filtered view (when date is selected in Hub view) */
                  <div className="space-y-4">
                    {filteredView.pending.length > 0 && (
                      <TaskGroup
                        title="Pending"
                        icon="📋"
                        tasks={filteredView.pending}
                        {...taskGroupProps}
                      />
                    )}
                    {filteredView.completed.length > 0 && (
                      <TaskGroup
                        title="Completed"
                        icon="✓"
                        tasks={filteredView.completed}
                        collapsible
                        defaultCollapsed
                        {...taskGroupProps}
                      />
                    )}
                    {filteredView.pending.length === 0 &&
                      filteredView.completed.length === 0 && (
                        <div className="py-8 text-center text-sm text-text-tertiary">
                          No tasks for this date
                        </div>
                      )}
                  </div>
                ) : (
                  /* Hub view - all task groups */
                  <div className="space-y-4">
                    <TaskGroup
                      title="Priority Tasks"
                      icon="🔥"
                      tasks={filteredGroupedItems.overdue}
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="Today"
                      icon="📅"
                      tasks={filteredGroupedItems.today}
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="Tomorrow"
                      icon="📆"
                      tasks={filteredGroupedItems.tomorrow}
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="This Week"
                      icon="🗓"
                      tasks={filteredGroupedItems.thisWeek}
                      collapsible
                      defaultCollapsed={filteredGroupedItems.thisWeek.length > 5}
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="Later"
                      icon="📋"
                      tasks={filteredGroupedItems.later}
                      collapsible
                      defaultCollapsed={filteredGroupedItems.later.length > 5}
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="No Due Date"
                      icon="📭"
                      tasks={filteredGroupedItems.noDueDate}
                      collapsible
                      defaultCollapsed
                      {...taskGroupProps}
                    />
                    <TaskGroup
                      title="Completed"
                      icon="✓"
                      tasks={filteredGroupedItems.completed}
                      collapsible
                      defaultCollapsed
                      maxVisible={10}
                      {...taskGroupProps}
                    />
                  </div>
                )}
              </>
            )}
          </div>

          {/* Right Column - Dashboard (sticky sidebar) - only in Hub view */}
          {viewMode === 'hub' && (
            <div className="order-first w-full border-bg-tertiary p-4 lg:order-last lg:h-full lg:w-[380px] lg:flex-shrink-0 lg:overflow-y-auto lg:border-l lg:pl-6">
              {/* Loading state for dashboard */}
              {loading && items.length === 0 && (
                <div className="space-y-4">
                  <div className="h-32 animate-pulse rounded-xl border border-bg-tertiary bg-bg-secondary" />
                  <div className="h-24 animate-pulse rounded-xl border border-bg-tertiary bg-bg-secondary" />
                  <div className="h-64 animate-pulse rounded-xl border border-bg-tertiary bg-bg-secondary" />
                </div>
              )}

              {/* Dashboard content */}
              {!loading && items.length > 0 && (
                <TaskRightPanel
                  stats={stats}
                  items={items}
                  groupedItems={groupedItems}
                  onBulkSetDueDate={bulkSetDueDate}
                  onShowNoDueDateItems={handleShowNoDueDateItems}
                  onDateSelect={handleDateSelect}
                  selectedDate={selectedDate}
                  onDragToDate={handleDropTask}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
