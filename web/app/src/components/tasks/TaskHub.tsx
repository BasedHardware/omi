'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import { LayoutGrid, List, RefreshCw, CheckSquare, Square, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useActionItems } from '@/hooks/useActionItems';
import { useTaskKeyboardShortcuts } from '@/hooks/useTaskKeyboardShortcuts';
import { TaskGroup, TaskGroupSkeleton } from './TaskGroup';
import { TaskQuickAdd } from './TaskQuickAdd';
import { TaskListView } from './TaskListView';
import { TaskRightPanel } from './TaskRightPanel';
import { BulkActionBar } from './BulkActionBar';
import { PageHeader } from '@/components/layout/PageHeader';
import { copyTasksToClipboard, downloadTasks } from '@/lib/taskExport';
import { useChat as useChatContext } from '@/components/chat/ChatContext';

type ViewMode = 'hub' | 'list';

export function TaskHub() {
  const [viewMode, setViewMode] = useState<ViewMode>('hub');
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
    refresh,
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

  // Handle select all (respects search filter)
  const handleSelectAll = useCallback(() => {
    // Filter by search query if present
    const visibleItems = searchQuery
      ? items.filter((i) => i.description.toLowerCase().includes(searchQuery.toLowerCase()))
      : items;
    const pendingItems = visibleItems.filter((i) => !i.completed);
    if (selectedIds.size === pendingItems.length && pendingItems.length > 0) {
      // Deselect all
      setSelectedIds(new Set());
    } else {
      // Select all pending items
      setSelectedIds(new Set(pendingItems.map((i) => i.id)));
    }
  }, [items, searchQuery, selectedIds.size]);

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
    [selectedIds, bulkSnooze, clearSelection]
  );

  // Handle copy to clipboard
  const handleCopy = useCallback(async () => {
    const selectedItems = items.filter(i => selectedIds.has(i.id));
    await copyTasksToClipboard(selectedItems);
  }, [items, selectedIds]);

  // Handle export
  const handleExport = useCallback((format: 'csv' | 'json' | 'markdown') => {
    const selectedItems = items.filter(i => selectedIds.has(i.id));
    downloadTasks(selectedItems, format);
  }, [items, selectedIds]);

  // Handle show no due date items
  const handleShowNoDueDateItems = useCallback(() => {
    setSearchQuery('');
    setViewMode('list');
    // Items without due dates will be at the bottom of the list
  }, []);

  // Handle set due today for selected items
  const handleSetDueToday = useCallback(async (ids: string[]) => {
    await bulkSetDueDate(ids, new Date());
  }, [bulkSetDueDate]);

  // Handle set due tomorrow for selected items
  const handleSetDueTomorrow = useCallback(async (ids: string[]) => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    await bulkSetDueDate(ids, tomorrow);
  }, [bulkSetDueDate]);

  // Handle bulk toggle complete
  const handleBulkToggleComplete = useCallback(async (ids: string[]) => {
    await bulkComplete(ids);
    clearSelection();
  }, [bulkComplete, clearSelection]);

  // Handle bulk delete via keyboard
  const handleBulkDeleteByIds = useCallback(async (ids: string[]) => {
    await bulkDelete(ids);
    clearSelection();
  }, [bulkDelete, clearSelection]);

  // Handle start edit
  const handleStartEdit = useCallback((id: string) => {
    setEditingId(id);
  }, []);

  // Handle date selection from week strip
  const handleDateSelect = useCallback((date: Date) => {
    setSelectedDate((prev) =>
      prev?.toDateString() === date.toDateString() ? null : date
    );
  }, []);

  // Handle drop on week strip
  const handleDropTask = useCallback(
    async (date: Date, taskId: string) => {
      await setDueDate(taskId, date);
    },
    [setDueDate]
  );

  // Handle add task
  const handleAddTask = useCallback(
    async (description: string, dueAt?: string) => {
      await addItem({ description, due_at: dueAt || null });
    },
    [addItem]
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

  // Keyboard navigation (defined after filteredItems)
  const handleNavigate = useCallback((direction: 'up' | 'down') => {
    const totalItems = viewMode === 'list'
      ? sortedFlatList.pending.length + (showCompleted ? sortedFlatList.completed.length : 0)
      : filteredItems.filter(i => !i.completed).length;

    if (totalItems === 0) return;

    setFocusedIndex(prev => {
      if (direction === 'up') {
        return prev <= 0 ? totalItems - 1 : prev - 1;
      } else {
        return prev >= totalItems - 1 ? 0 : prev + 1;
      }
    });
  }, [viewMode, sortedFlatList, showCompleted, filteredItems]);

  // Toggle select focused item
  const handleToggleSelectFocused = useCallback(() => {
    const allItems = viewMode === 'list'
      ? [...sortedFlatList.pending, ...(showCompleted ? sortedFlatList.completed : [])]
      : filteredItems.filter(i => !i.completed);

    if (focusedIndex >= 0 && focusedIndex < allItems.length) {
      const item = allItems[focusedIndex];
      handleSelect(item.id, !selectedIds.has(item.id));
    }
  }, [viewMode, sortedFlatList, showCompleted, filteredItems, focusedIndex, selectedIds]);

  // Keyboard shortcuts
  useTaskKeyboardShortcuts({
    enabled: !loading && items.length > 0,
    selectedIds,
    focusedIndex,
    totalItems: viewMode === 'list'
      ? sortedFlatList.pending.length
      : filteredItems.filter(i => !i.completed).length,
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
  const getVisibleGroups = () => {
    if (selectedDate) {
      // Filter to selected date only
      const dateStr = selectedDate.toDateString();
      const dateFilteredItems = filteredItems.filter((item) => {
        if (!item.due_at) return false;
        return new Date(item.due_at).toDateString() === dateStr;
      });

      const pending = dateFilteredItems.filter((i) => !i.completed);
      const completed = dateFilteredItems.filter((i) => i.completed);

      return { pending, completed, dateLabel: selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }) };
    }

    return null;
  };

  const filteredView = getVisibleGroups();
  const isEmpty = !loading && items.length === 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <PageHeader title="Tasks" icon={CheckSquare} />

      {/* Toolbar */}
      <div className="flex-shrink-0 bg-bg-secondary border-b border-bg-tertiary">
        <div className="py-3 px-4">
          <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* View mode toggle */}
            <div className="flex items-center gap-1 p-1 bg-bg-tertiary rounded-lg">
            <button
              onClick={() => setViewMode('hub')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm',
                'transition-colors',
                viewMode === 'hub'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-tertiary hover:text-text-secondary'
              )}
            >
              <LayoutGrid className="w-4 h-4" />
              Hub
            </button>
            <button
              onClick={() => {
                setViewMode('list');
                setSelectedDate(null); // Clear date filter when switching to list
              }}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm',
                'transition-colors',
                viewMode === 'list'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-tertiary hover:text-text-secondary'
              )}
            >
              <List className="w-4 h-4" />
              List
            </button>
            </div>

            {/* Select mode toggle - moved to left */}
            {filteredItems.filter((i) => !i.completed).length > 0 && (
              <button
                onClick={toggleSelectMode}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                  'transition-colors',
                  isSelectMode
                    ? 'bg-purple-primary/10 text-purple-primary'
                    : 'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
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

            {/* Search */}
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-quaternary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search tasks..."
                className={cn(
                  'w-full pl-9 pr-4 py-1.5 rounded-lg',
                  'bg-bg-tertiary border border-bg-quaternary',
                  'text-sm text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                  'placeholder:text-text-quaternary'
                )}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              disabled={loading}
              className={cn(
                'p-2 rounded-lg',
                'text-text-tertiary hover:text-text-primary',
                'hover:bg-bg-tertiary transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              title="Refresh tasks"
            >
              <RefreshCw className={cn('w-5 h-5', loading && 'animate-spin')} />
            </button>
          </div>
        </div>
        </div>
      </div>

      {/* Content - Two column layout for Hub view */}
      <div className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col lg:flex-row w-full">
          {/* Left Column - Tasks (scrollable) */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 order-last lg:order-first">
          {/* Quick add */}
          <TaskQuickAdd onAdd={handleAddTask} disabled={loading} />

          {/* Inline action bar - only shown in select mode */}
          {isSelectMode && (
            <BulkActionBar
              inline
              selectedCount={selectedIds.size}
              selectedItems={items.filter(i => selectedIds.has(i.id))}
              onComplete={handleBulkComplete}
              onDelete={handleBulkDelete}
              onSnooze={handleBulkSnooze}
              onClear={clearSelection}
              onCopy={handleCopy}
              onExport={handleExport}
              onSelectAll={handleSelectAll}
              onDone={toggleSelectMode}
              allSelected={selectedIds.size === filteredItems.filter((i) => !i.completed).length && filteredItems.filter((i) => !i.completed).length > 0}
              totalCount={filteredItems.filter((i) => !i.completed).length}
            />
          )}

          {/* Error state */}
          {error && (
            <div className="p-4 rounded-xl bg-error/10 border border-error/20 text-error text-sm">
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
              <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
                <CheckSquare className="w-8 h-8 text-text-quaternary" />
              </div>
              <h3 className="text-lg font-medium text-text-primary mb-2">
                No tasks yet
              </h3>
              <p className="text-text-tertiary text-sm max-w-xs">
                Add a task above or they&apos;ll appear automatically from your conversations
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
                    className="text-xs text-purple-primary hover:underline"
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
                    className="text-xs text-purple-primary hover:underline"
                  >
                    Show all
                  </button>
                </div>
              )}

              {/* List view - flat list with TaskListView */}
              {viewMode === 'list' ? (
                <TaskListView
                  pendingTasks={sortedFlatList.pending}
                  completedTasks={sortedFlatList.completed}
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
                  {filteredView.pending.length === 0 && filteredView.completed.length === 0 && (
                    <div className="text-center py-8 text-text-tertiary text-sm">
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
          <div className="w-full lg:w-[380px] lg:flex-shrink-0 p-4 lg:pl-6 lg:border-l border-bg-tertiary order-first lg:order-last lg:h-full lg:overflow-y-auto">
            {/* Loading state for dashboard */}
            {loading && items.length === 0 && (
              <div className="space-y-4">
                <div className="h-32 bg-bg-secondary border border-bg-tertiary rounded-xl animate-pulse" />
                <div className="h-24 bg-bg-secondary border border-bg-tertiary rounded-xl animate-pulse" />
                <div className="h-64 bg-bg-secondary border border-bg-tertiary rounded-xl animate-pulse" />
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
