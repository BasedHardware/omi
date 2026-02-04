'use client';

import { TaskProgressCard } from './TaskProgressCard';
import { NoDueDatePrompt } from './NoDueDatePrompt';
import { MonthCalendar } from './MonthCalendar';
import type { ActionItem, GroupedActionItems } from '@/types/conversation';

interface TaskRightPanelProps {
  // Stats for progress card
  stats: {
    total: number;
    completed: number;
    pending: number;
    overdue: number;
    noDueDateCount: number;
    todayTotal: number;
    todayCompleted: number;
    weekCompleted: number;
    weekPending: number;
    streak: number;
  };

  // Items for components
  items: ActionItem[];
  groupedItems: GroupedActionItems;

  // Actions
  onBulkSetDueDate: (ids: string[], date: Date | null) => void;
  onShowNoDueDateItems: () => void;

  // Calendar props
  onDateSelect: (date: Date) => void;
  selectedDate: Date | null;
  onDragToDate: (date: Date, taskId: string) => void;
}

export function TaskRightPanel({
  stats,
  items,
  groupedItems,
  onBulkSetDueDate,
  onShowNoDueDateItems,
  onDateSelect,
  selectedDate,
  onDragToDate,
}: TaskRightPanelProps) {
  const noDueDateItems = groupedItems.noDueDate;
  const noDueDateIds = noDueDateItems.map(i => i.id);

  const handleSetAllToday = () => {
    onBulkSetDueDate(noDueDateIds, new Date());
  };

  const handleSetAllTomorrow = () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    onBulkSetDueDate(noDueDateIds, tomorrow);
  };

  const handleSetAllToDate = (date: Date) => {
    onBulkSetDueDate(noDueDateIds, date);
  };

  return (
    <div className="w-full space-y-4">
      {/* Progress stats */}
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

      {/* Month calendar */}
      <MonthCalendar
        items={items}
        onSelectDate={onDateSelect}
        selectedDate={selectedDate}
        onDropTask={onDragToDate}
      />

      {/* No due date prompt */}
      {noDueDateItems.length > 0 && (
        <NoDueDatePrompt
          items={noDueDateItems}
          onSetAllToday={handleSetAllToday}
          onSetAllTomorrow={handleSetAllTomorrow}
          onSetAllToDate={handleSetAllToDate}
          onShowItems={onShowNoDueDateItems}
        />
      )}
    </div>
  );
}
