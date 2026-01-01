'use client';

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { LayoutGrid, List, RefreshCw, MoreHorizontal, CheckSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useActionItems } from '@/hooks/useActionItems';
import { TaskProgressCard } from './TaskProgressCard';
import { WeekStrip } from './WeekStrip';
import { TaskGroup, TaskGroupSkeleton } from './TaskGroup';
import { TaskQuickAdd } from './TaskQuickAdd';
import { BulkActionBar } from './BulkActionBar';

type ViewMode = 'hub' | 'list';

export function TaskHub() {
  const [viewMode, setViewMode] = useState<ViewMode>('hub');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  const {
    items,
    groupedItems,
    loading,
    error,
    stats,
    weekData,
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
  } = useActionItems();

  // Common props for all TaskGroup components
  const taskGroupProps = {
    onToggleComplete: toggleComplete,
    onSnooze: snooze,
    onDelete: removeItem,
    onUpdateDescription: updateDescription,
    onSetDueDate: setDueDate,
    selectedIds,
    onSelect: handleSelect,
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

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

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

  // Filter tasks based on view mode and selected date
  const getVisibleGroups = () => {
    if (selectedDate) {
      // Filter to selected date only
      const dateStr = selectedDate.toDateString();
      const filteredItems = items.filter((item) => {
        if (!item.due_at) return false;
        return new Date(item.due_at).toDateString() === dateStr;
      });

      const pending = filteredItems.filter((i) => !i.completed);
      const completed = filteredItems.filter((i) => i.completed);

      return { pending, completed, dateLabel: selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }) };
    }

    return null;
  };

  const filteredView = getVisibleGroups();
  const isEmpty = !loading && items.length === 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-bg-primary border-b border-bg-tertiary">
        <div className="flex items-center justify-between">
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

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              disabled={loading}
              className={cn(
                'p-2 rounded-lg',
                'text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary',
                'transition-colors',
                loading && 'animate-spin'
              )}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              className={cn(
                'p-2 rounded-lg',
                'text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary',
                'transition-colors'
              )}
              title="More options"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Content - Two column layout for Hub view */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Column - Tasks (scrollable) */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 order-last lg:order-first">
          {/* Quick add */}
          <TaskQuickAdd onAdd={handleAddTask} disabled={loading} />

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
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center py-16 text-center"
            >
              <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
                <CheckSquare className="w-8 h-8 text-text-quaternary" />
              </div>
              <h3 className="text-lg font-medium text-text-primary mb-2">
                No tasks yet
              </h3>
              <p className="text-text-tertiary text-sm max-w-xs">
                Add a task above or they&apos;ll appear automatically from your conversations
              </p>
            </motion.div>
          )}

          {/* Task content */}
          {!loading && items.length > 0 && (
            <>
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

              {/* Filtered view (when date is selected in Hub view) */}
              {viewMode === 'hub' && filteredView ? (
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
                /* All task groups in single column */
                <div className="space-y-4">
                  <TaskGroup
                    title="Priority Tasks"
                    icon="🔥"
                    tasks={groupedItems.overdue}
                    {...taskGroupProps}
                  />
                  <TaskGroup
                    title="Today"
                    icon="📅"
                    tasks={groupedItems.today}
                    {...taskGroupProps}
                  />
                  <TaskGroup
                    title="Tomorrow"
                    icon="📆"
                    tasks={groupedItems.tomorrow}
                    {...taskGroupProps}
                  />
                  <TaskGroup
                    title="This Week"
                    icon="🗓"
                    tasks={groupedItems.thisWeek}
                    collapsible
                    defaultCollapsed={groupedItems.thisWeek.length > 5}
                    {...taskGroupProps}
                  />
                  {viewMode === 'list' && (
                    <TaskGroup
                      title="Later"
                      icon="📋"
                      tasks={groupedItems.later}
                      {...taskGroupProps}
                    />
                  )}
                  <TaskGroup
                    title="Completed"
                    icon="✓"
                    tasks={groupedItems.completed}
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
          <div className="w-full lg:w-[480px] lg:flex-shrink-0 p-4 lg:pl-4 lg:border-l border-bg-tertiary order-first lg:order-last space-y-4 lg:h-full lg:overflow-y-auto">
            {/* Loading state for dashboard */}
            {loading && items.length === 0 && (
              <div className="space-y-4">
                <div className="h-24 bg-bg-tertiary rounded-xl animate-pulse" />
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5, 6, 7].map((i) => (
                    <div key={i} className="w-[42px] h-16 bg-bg-tertiary rounded-lg animate-pulse" />
                  ))}
                </div>
              </div>
            )}

            {/* Dashboard content */}
            {!loading && items.length > 0 && (
              <>
                {/* Progress card */}
                <TaskProgressCard
                  overdueCount={stats.overdue}
                  todayTotal={stats.todayTotal}
                  todayCompleted={stats.todayCompleted}
                  totalPending={stats.pending}
                  totalCompleted={stats.completed}
                  weekCompleted={stats.weekCompleted}
                  weekPending={stats.weekPending}
                  streak={stats.streak}
                  compact
                />

                {/* Week strip */}
                <WeekStrip
                  days={weekData}
                  selectedDate={selectedDate}
                  onSelectDate={handleDateSelect}
                  onDropTask={handleDropTask}
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Bulk action bar */}
      <BulkActionBar
        selectedCount={selectedIds.size}
        onComplete={handleBulkComplete}
        onDelete={handleBulkDelete}
        onSnooze={handleBulkSnooze}
        onClear={clearSelection}
      />
    </div>
  );
}
